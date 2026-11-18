from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from multi_star.small_satellite_service import create_server


class SmallSatelliteServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_root = Path(__file__).resolve().parents[1] / "runtime" / "tmp"
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=self.temp_root)
        self.snapshot = Path(self.temp.name) / "snapshot.json"
        self.server = self._server()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def _server(self):
        os.environ["SATELLITE_ID"] = "small-sat-0"
        os.environ["SMALL_SATELLITE_COUNT"] = "9"
        return create_server("127.0.0.1", 0, self.snapshot)

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temp.cleanup()

    def request(self, path: str, body=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            self.url + path,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    def test_command_fault_and_snapshot_restart(self) -> None:
        command = {
            "command_id": "observe-1",
            "satellite_id": "small-sat-0",
            "epoch": 1,
            "plan_version": 1,
            "kind": "observation",
            "not_before": 0,
            "expires_at": 100,
            "duration_s": 0,
            "data_bytes": 128,
        }
        status, response = self.request("/commands", command)
        self.assertEqual(status, 200)
        self.assertTrue(response["receipt"]["accepted"])
        self.request("/advance", {"sim_time_s": 0})
        status, response = self.request("/status")
        self.assertEqual(response["storage_remaining_bytes"], 1_073_741_696)

        self.request("/fault", {})
        status, _ = self.request("/readyz")
        self.assertEqual(status, 503)
        status, _ = self.request("/healthz")
        self.assertEqual(status, 200)

        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.server = self._server()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        status, response = self.request("/readyz")
        self.assertEqual(status, 503)
        self.assertEqual(response["health"], "failed")
        self.request("/recover", {})
        status, response = self.request("/readyz")
        self.assertEqual(status, 200)
        self.assertEqual(response["health"], "nominal")

    def test_chunked_upload_round_trip(self) -> None:
        data = b"0123456789abcdef"
        manifest = {
            "upload_id": "observation-http-1",
            "total_bytes": len(data),
            "chunk_size": 5,
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        status, response = self.request("/uploads/create", {"manifest": manifest})
        self.assertEqual(status, 200)
        self.assertEqual(response["upload"]["missing_chunks"], [0, 1, 2, 3])

        chunks = [data[offset:offset + 5] for offset in range(0, len(data), 5)]
        for index in (2, 0, 3, 1):
            status, response = self.request("/uploads/chunk", {
                "manifest": manifest,
                "chunk_index": index,
                "payload_b64": base64.b64encode(chunks[index]).decode("ascii"),
            })
            self.assertEqual(status, 200)
            self.assertTrue(response["upload"]["accepted_new_chunk"])
        status, response = self.request("/uploads/chunk", {
            "manifest": manifest,
            "chunk_index": 1,
            "payload_b64": base64.b64encode(chunks[1]).decode("ascii"),
        })
        self.assertFalse(response["upload"]["accepted_new_chunk"])
        status, response = self.request("/uploads/finalize", {"manifest": manifest})
        self.assertEqual(status, 200)
        self.assertTrue(response["upload"]["complete"])
        self.assertEqual(Path(response["assembled_path"]).read_bytes(), data)

    def test_wrong_recipient_is_audited(self) -> None:
        command = {
            "command_id": "wrong-1",
            "satellite_id": "small-sat-1",
            "epoch": 1,
            "plan_version": 1,
            "kind": "safe_mode",
            "not_before": 0,
            "expires_at": 100,
            "duration_s": 0,
        }
        status, response = self.request("/commands", command)
        self.assertEqual(status, 200)
        self.assertFalse(response["receipt"]["accepted"])
        self.assertIn("another satellite", response["receipt"]["reason"])


if __name__ == "__main__":
    unittest.main()
