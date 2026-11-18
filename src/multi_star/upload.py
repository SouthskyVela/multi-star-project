"""Persistent, verifiable chunked uploads with resume support."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_COPY_BUFFER_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class UploadManifest:
    """Immutable description of an upload and its expected final digest."""

    upload_id: str
    total_bytes: int
    chunk_size: int
    sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.upload_id, str) or not self.upload_id.strip():
            raise ValueError("upload_id must be a non-empty string")
        if isinstance(self.total_bytes, bool) or not isinstance(self.total_bytes, int):
            raise TypeError("total_bytes must be an integer")
        if isinstance(self.chunk_size, bool) or not isinstance(self.chunk_size, int):
            raise TypeError("chunk_size must be an integer")
        if self.total_bytes < 0:
            raise ValueError("total_bytes cannot be negative")
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if not isinstance(self.sha256, str) or not _SHA256_PATTERN.fullmatch(self.sha256):
            raise ValueError("sha256 must be a 64-character hexadecimal digest")
        object.__setattr__(self, "sha256", self.sha256.lower())

    @property
    def chunk_count(self) -> int:
        """Number of chunks, including a possibly shorter final chunk."""
        return (self.total_bytes + self.chunk_size - 1) // self.chunk_size

    def to_dict(self) -> dict[str, str | int]:
        return {
            "upload_id": self.upload_id,
            "total_bytes": self.total_bytes,
            "chunk_size": self.chunk_size,
            "sha256": self.sha256,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> UploadManifest:
        if not isinstance(value, dict):
            raise ValueError("manifest.json must contain a JSON object")
        try:
            return cls(
                upload_id=value["upload_id"],
                total_bytes=value["total_bytes"],
                chunk_size=value["chunk_size"],
                sha256=value["sha256"],
            )
        except KeyError as exc:
            raise ValueError(f"manifest is missing {exc.args[0]!r}") from exc


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, path)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(_COPY_BUFFER_SIZE):
            digest.update(block)
    return digest.hexdigest()


class ChunkedUpload:
    """Receive chunks below *root* and assemble them after full verification."""

    def __init__(self, root: str | os.PathLike[str], manifest: UploadManifest) -> None:
        if not isinstance(manifest, UploadManifest):
            raise TypeError("manifest must be an UploadManifest")
        self.root = Path(root)
        self.manifest = manifest
        self.manifest_path = self.root / "manifest.json"
        self.chunks_directory = self.root / "chunks"
        self.assembled_path = self.root / "assembled.bin"
        self._chunks: dict[int, int] = {}

        self.root.mkdir(parents=True, exist_ok=True)
        self.chunks_directory.mkdir(exist_ok=True)
        if self.manifest_path.exists():
            try:
                persisted = UploadManifest.from_dict(
                    json.loads(self.manifest_path.read_text(encoding="utf-8"))
                )
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise ValueError("persisted manifest.json is invalid") from exc
            if persisted != manifest:
                raise ValueError("manifest does not match the existing upload")
        else:
            encoded = json.dumps(manifest.to_dict(), indent=2, sort_keys=True).encode("utf-8")
            _atomic_write_bytes(self.manifest_path, encoded + b"\n")
        self._scan_chunks()

    @classmethod
    def create_or_resume(
        cls, root: str | os.PathLike[str], manifest: UploadManifest
    ) -> ChunkedUpload:
        """Create a new upload directory or resume the upload already there."""
        return cls(root, manifest)

    def _chunk_path(self, index: int) -> Path:
        return self.chunks_directory / f"{index:08d}.chunk"

    def _expected_chunk_size(self, index: int) -> int:
        return min(self.manifest.chunk_size, self.manifest.total_bytes - index * self.manifest.chunk_size)

    def _scan_chunks(self) -> None:
        found: dict[int, int] = {}
        for index in range(self.manifest.chunk_count):
            path = self._chunk_path(index)
            if not path.exists():
                continue
            if not path.is_file():
                raise ValueError(f"chunk {index} is not a regular file")
            size = path.stat().st_size
            expected = self._expected_chunk_size(index)
            if size != expected:
                raise ValueError(
                    f"persisted chunk {index} has {size} bytes; expected {expected}"
                )
            found[index] = size
        self._chunks = found

    def receive_chunk(self, index: int, payload: bytes | bytearray | memoryview) -> bool:
        """Persist one chunk; return False for an identical duplicate, True if new."""
        if isinstance(index, bool) or not isinstance(index, int):
            raise TypeError("chunk index must be an integer")
        if not 0 <= index < self.manifest.chunk_count:
            raise IndexError(f"chunk index {index} is outside the manifest")
        if not isinstance(payload, (bytes, bytearray, memoryview)):
            raise TypeError("chunk payload must be bytes-like")
        data = bytes(payload)
        expected = self._expected_chunk_size(index)
        if len(data) != expected:
            raise ValueError(f"chunk {index} has {len(data)} bytes; expected {expected}")

        path = self._chunk_path(index)
        if path.exists():
            if not path.is_file() or path.stat().st_size != expected:
                raise ValueError(f"persisted chunk {index} is invalid")
            if path.read_bytes() != data:
                raise ValueError(f"chunk {index} was already received with different content")
            self._chunks[index] = expected
            return False

        _atomic_write_bytes(path, data)
        self._chunks[index] = len(data)
        return True

    def status(self) -> dict[str, int | list[int] | bool]:
        """Report on-disk unique chunks, actual bytes, gaps, and completeness."""
        self._scan_chunks()
        missing = [
            index for index in range(self.manifest.chunk_count) if index not in self._chunks
        ]
        return {
            "received_chunks": len(self._chunks),
            "received_bytes": sum(self._chunks.values()),
            "missing_chunks": missing,
            "complete": not missing,
        }

    def finalize(self) -> Path:
        """Stream all chunks in order into an atomically published assembled.bin."""
        if not self.status()["complete"]:
            raise RuntimeError("cannot finalize an upload with missing chunks")

        if self.assembled_path.exists() and self.assembled_path.is_file():
            if (
                self.assembled_path.stat().st_size == self.manifest.total_bytes
                and _file_sha256(self.assembled_path) == self.manifest.sha256
            ):
                return self.assembled_path

        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.root, prefix=".assembled.bin.", suffix=".tmp"
        )
        temporary_path = Path(temporary_name)
        digest = hashlib.sha256()
        try:
            with os.fdopen(descriptor, "wb") as output:
                for index in range(self.manifest.chunk_count):
                    with self._chunk_path(index).open("rb") as source:
                        while block := source.read(_COPY_BUFFER_SIZE):
                            output.write(block)
                            digest.update(block)
                output.flush()
                os.fsync(output.fileno())
            if digest.hexdigest() != self.manifest.sha256:
                raise ValueError("assembled upload SHA-256 does not match the manifest")
            os.replace(temporary_path, self.assembled_path)
        finally:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
        return self.assembled_path
