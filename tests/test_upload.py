from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from multi_star.upload import ChunkedUpload, UploadManifest  # noqa: E402


class ChunkedUploadTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary_root = PROJECT_ROOT / "runtime" / "tmp"
        temporary_root.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=temporary_root)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "upload"
        self.data = b"0123456789abcdef"
        self.manifest = UploadManifest(
            upload_id="observation-1",
            total_bytes=len(self.data),
            chunk_size=5,
            sha256=hashlib.sha256(self.data).hexdigest(),
        )

    def chunks(self, data: bytes | None = None) -> list[bytes]:
        content = self.data if data is None else data
        size = self.manifest.chunk_size
        return [content[offset:offset + size] for offset in range(0, len(content), size)]

    def test_manifest_validation_and_chunk_count(self) -> None:
        self.assertEqual(self.manifest.chunk_count, 4)
        self.assertEqual(UploadManifest("empty", 0, 1, hashlib.sha256(b"").hexdigest()).chunk_count, 0)
        with self.assertRaises(ValueError):
            UploadManifest("bad-digest", 1, 1, "not-a-sha256")
        with self.assertRaises(ValueError):
            UploadManifest("bad-size", 1, 0, hashlib.sha256(b"x").hexdigest())
        with self.assertRaises(ValueError):
            UploadManifest("negative", -1, 1, hashlib.sha256(b"").hexdigest())

    def test_out_of_order_receipt_and_identical_duplicate_are_idempotent(self) -> None:
        upload = ChunkedUpload.create_or_resume(self.root, self.manifest)
        chunks = self.chunks()
        for index in (2, 0, 3):
            self.assertTrue(upload.receive_chunk(index, chunks[index]))

        status = upload.status()
        self.assertEqual(status["received_chunks"], 3)
        self.assertEqual(status["received_bytes"], 11)
        self.assertEqual(status["missing_chunks"], [1])
        self.assertFalse(status["complete"])

        chunk_path = self.root / "chunks" / "00000002.chunk"
        modified_before = chunk_path.stat().st_mtime_ns
        self.assertFalse(upload.receive_chunk(2, chunks[2]))
        self.assertEqual(chunk_path.stat().st_mtime_ns, modified_before)
        self.assertEqual(upload.status()["received_chunks"], 3)

    def test_duplicate_with_tampered_content_is_rejected_without_overwrite(self) -> None:
        upload = ChunkedUpload.create_or_resume(self.root, self.manifest)
        original = self.chunks()[0]
        upload.receive_chunk(0, original)
        with self.assertRaisesRegex(ValueError, "different content"):
            upload.receive_chunk(0, b"XXXXX")
        self.assertEqual((self.root / "chunks" / "00000000.chunk").read_bytes(), original)

    def test_missing_chunks_block_finalize_and_invalid_chunks_are_rejected(self) -> None:
        upload = ChunkedUpload.create_or_resume(self.root, self.manifest)
        upload.receive_chunk(0, self.chunks()[0])
        with self.assertRaises(RuntimeError):
            upload.finalize()
        with self.assertRaises(IndexError):
            upload.receive_chunk(self.manifest.chunk_count, b"x")
        with self.assertRaises(ValueError):
            upload.receive_chunk(1, b"tiny")
        with self.assertRaises(ValueError):
            upload.receive_chunk(3, b"too long")
        self.assertFalse(self.assembled_exists())

    def assembled_exists(self) -> bool:
        return (self.root / "assembled.bin").exists()

    def test_resume_after_object_reconstruction_and_manifest_mismatch(self) -> None:
        upload = ChunkedUpload.create_or_resume(self.root, self.manifest)
        chunks = self.chunks()
        upload.receive_chunk(2, chunks[2])
        upload.receive_chunk(0, chunks[0])

        resumed = ChunkedUpload.create_or_resume(self.root, self.manifest)
        self.assertEqual(resumed.status()["missing_chunks"], [1, 3])
        resumed.receive_chunk(3, chunks[3])
        resumed.receive_chunk(1, chunks[1])
        self.assertEqual(resumed.finalize().read_bytes(), self.data)

        changed = UploadManifest(
            self.manifest.upload_id,
            self.manifest.total_bytes,
            4,
            self.manifest.sha256,
        )
        with self.assertRaisesRegex(ValueError, "does not match"):
            ChunkedUpload.create_or_resume(self.root, changed)

    def test_final_hash_mismatch_leaves_no_assembled_file(self) -> None:
        wrong_manifest = UploadManifest(
            "wrong-hash",
            len(self.data),
            self.manifest.chunk_size,
            hashlib.sha256(b"different").hexdigest(),
        )
        upload = ChunkedUpload.create_or_resume(self.root, wrong_manifest)
        for index, chunk in enumerate(self.chunks()):
            upload.receive_chunk(index, chunk)
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            upload.finalize()
        self.assertFalse(self.assembled_exists())
        self.assertEqual(len(list(self.root.glob(".assembled.bin.*.tmp"))), 0)

    def test_finalize_is_repeatable_and_preserves_source_chunks(self) -> None:
        upload = ChunkedUpload.create_or_resume(self.root, self.manifest)
        for index, chunk in reversed(list(enumerate(self.chunks()))):
            upload.receive_chunk(index, chunk)

        assembled = upload.finalize()
        self.assertEqual(assembled.read_bytes(), self.data)
        modified = assembled.stat().st_mtime_ns
        self.assertEqual(upload.finalize(), assembled)
        self.assertEqual(assembled.stat().st_mtime_ns, modified)
        self.assertEqual(len(list((self.root / "chunks").glob("*.chunk"))), 4)
        persisted = json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(persisted, self.manifest.to_dict())

    def test_empty_upload_can_be_finalized(self) -> None:
        empty = b""
        manifest = UploadManifest("empty", 0, 8, hashlib.sha256(empty).hexdigest())
        upload = ChunkedUpload.create_or_resume(self.root, manifest)
        self.assertTrue(upload.status()["complete"])
        self.assertEqual(upload.finalize().read_bytes(), empty)


if __name__ == "__main__":
    unittest.main()
