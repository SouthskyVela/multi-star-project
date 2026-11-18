"""Cluster-internal HTTP adapter for one stateful small-satellite container."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .satellite import Command, CommandReceipt, HealthState, SmallSatellite
from .upload import ChunkedUpload, UploadManifest
from .uv import generate_formation

MAX_BODY_BYTES = 1_048_576


def _receipt_dict(receipt: CommandReceipt) -> dict[str, Any]:
    return {
        "accepted": receipt.accepted,
        "duplicate": receipt.duplicate,
        "state": receipt.state.value,
        "reason": receipt.reason,
    }


def _upload_from_body(server: "SatelliteServer", body: dict[str, Any]) -> ChunkedUpload:
    manifest = UploadManifest.from_dict(body["manifest"])
    directory = hashlib.sha256(manifest.upload_id.encode("utf-8")).hexdigest()
    return ChunkedUpload.create_or_resume(
        server.snapshot_path.parent / "uploads" / directory, manifest
    )


class SatelliteServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], satellite: SmallSatellite, snapshot_path: Path):
        super().__init__(address, SatelliteHandler)
        self.satellite = satellite
        self.snapshot_path = snapshot_path
        self.lock = threading.RLock()

    def persist(self) -> None:
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.snapshot_path.with_suffix(self.snapshot_path.suffix + ".tmp")
        temporary.write_text(self.satellite.snapshot(), encoding="utf-8")
        temporary.replace(self.snapshot_path)

    def status(self) -> dict[str, Any]:
        status = json.loads(self.satellite.snapshot())
        status["ready"] = self.satellite.health in {HealthState.NOMINAL, HealthState.DEGRADED}
        return status


class SatelliteHandler(BaseHTTPRequestHandler):
    server: SatelliteServer

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > MAX_BODY_BYTES:
            raise ValueError("request body exceeds 1 MiB")
        value = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(value, dict):
            raise ValueError("JSON body must be an object")
        return value

    def do_GET(self) -> None:
        with self.server.lock:
            if self.path == "/healthz":
                self._json(200, {"process": "alive", "satellite_id": self.server.satellite.satellite_id})
                return
            if self.path == "/readyz":
                status = self.server.status()
                self._json(200 if status["ready"] else 503, status)
                return
            if self.path == "/status":
                self._json(200, self.server.status())
                return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        try:
            body = self._body()
            with self.server.lock:
                upload_status = None
                assembled_path = None
                if self.path == "/commands":
                    sim_time = body.pop("sim_time_s", None)
                    neighbors = body.pop("neighbor_targets_m", None)
                    if neighbors:
                        for neighbor_id, target in neighbors.items():
                            self.server.satellite.set_neighbor_target(neighbor_id, target)
                    receipt = self.server.satellite.receive_command(Command(**body), sim_time)
                elif self.path == "/advance":
                    self.server.satellite.advance(float(body["sim_time_s"]))
                    receipt = None
                elif self.path == "/fault":
                    self.server.satellite.fail()
                    receipt = None
                elif self.path == "/recover":
                    self.server.satellite.recover()
                    receipt = None
                elif self.path == "/verify":
                    receipt = self.server.satellite.verify(str(body["command_id"]))
                elif self.path == "/neighbors":
                    for neighbor_id, target in body["neighbor_targets_m"].items():
                        self.server.satellite.set_neighbor_target(neighbor_id, target)
                    receipt = None
                elif self.path == "/uploads/create":
                    upload_status = _upload_from_body(self.server, body).status()
                    receipt = None
                elif self.path == "/uploads/chunk":
                    upload = _upload_from_body(self.server, body)
                    accepted_new = upload.receive_chunk(
                        body["chunk_index"],
                        base64.b64decode(body["payload_b64"], validate=True),
                    )
                    upload_status = upload.status()
                    upload_status["accepted_new_chunk"] = accepted_new
                    receipt = None
                elif self.path == "/uploads/finalize":
                    upload = _upload_from_body(self.server, body)
                    assembled_path = str(upload.finalize())
                    upload_status = upload.status()
                    receipt = None
                else:
                    self._json(404, {"error": "not found"})
                    return
                self.server.persist()
                payload = self.server.status()
                if receipt is not None:
                    payload["receipt"] = _receipt_dict(receipt)
                if upload_status is not None:
                    payload["upload"] = upload_status
                if assembled_path is not None:
                    payload["assembled_path"] = assembled_path
                self._json(200, payload)
        except (KeyError, IndexError, TypeError, ValueError, RuntimeError, binascii.Error, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.server.satellite.satellite_id} {format % args}", flush=True)


def _ordinal(satellite_id: str) -> int:
    match = re.search(r"(\d+)$", satellite_id)
    if match is None:
        raise ValueError("SATELLITE_ID must end with a numeric ordinal")
    return int(match.group(1))


def create_server(host: str = "0.0.0.0", port: int = 8080, snapshot_path: Path | None = None) -> SatelliteServer:
    satellite_id = os.environ.get("SATELLITE_ID", socket.gethostname())
    count = int(os.environ.get("SMALL_SATELLITE_COUNT", "9"))
    radius = float(os.environ.get("FORMATION_RADIUS_M", "5000"))
    seed = int(os.environ.get("SIMULATION_SEED", "20261118"))
    positions = generate_formation("spiral", count, radius, seed=seed)
    ordinal = _ordinal(satellite_id)
    if ordinal >= count:
        raise ValueError(f"satellite ordinal {ordinal} exceeds count {count}")
    neighbors = {
        f"small-sat-{index}": tuple(positions[index])
        for index in range(count)
        if index != ordinal
    }
    satellite = SmallSatellite(
        satellite_id,
        position_m=positions[ordinal],
        neighbor_targets_m=neighbors,
    )
    path = snapshot_path or Path(os.environ.get("SNAPSHOT_PATH", "/data/snapshot.json"))
    if path.exists():
        satellite = SmallSatellite.restore(path.read_text(encoding="utf-8"))
        if satellite.satellite_id != satellite_id:
            raise ValueError("snapshot belongs to another satellite")
    return SatelliteServer((host, port), satellite, path)


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    server = create_server(port=port)
    print(f"Serving {server.satellite.satellite_id} on 0.0.0.0:{port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
