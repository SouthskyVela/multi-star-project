"""Stable dashboard entry point that discovers the current leader via pod DNS."""

from __future__ import annotations

import importlib.resources
import json
import os
import re
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

MAIN_BASE = "http://{pod}.main-sat.multi-star.svc.cluster.local:8081"
FORWARDED_POSTS = {"/events", "/mode", "/test/suspend"}


def choose_leader(statuses: list[dict[str, Any]]) -> str:
    leaders = [item for item in statuses if item.get("ready") and item.get("leader")]
    if not leaders:
        raise RuntimeError("no active leader is currently available")
    highest = max(int(item.get("epoch", -1)) for item in leaders)
    current = [item for item in leaders if int(item.get("epoch", -1)) == highest]
    if len(current) != 1:
        raise RuntimeError("multiple leaders report the same highest epoch")
    return str(current[0]["id"])


def small_satellite_base(satellite_id: str) -> str:
    match = re.fullmatch(r"small-sat-(\d+)", satellite_id)
    count = int(os.environ.get("SMALL_SATELLITE_COUNT", "9"))
    if match is None or not 0 <= int(match.group(1)) < count:
        raise ValueError("invalid small satellite id")
    return f"http://{satellite_id}.small-sat.multi-star.svc.cluster.local:8080"


class LeaderProxy:
    def discover(self) -> str:
        count = int(os.environ.get("MAIN_SATELLITE_COUNT", "3"))
        statuses = []
        for index in range(count):
            pod = f"main-sat-{index}"
            try:
                with urllib.request.urlopen(MAIN_BASE.format(pod=pod) + "/status", timeout=2) as response:
                    statuses.append(json.load(response))
            except (OSError, ValueError, urllib.error.URLError):
                continue
        return MAIN_BASE.format(pod=choose_leader(statuses))


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    proxy = LeaderProxy()


class DashboardHandler(BaseHTTPRequestHandler):
    server: DashboardServer

    def _bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, value: dict[str, Any]) -> None:
        self._bytes(status, json.dumps(value).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._json(200, {"process": "alive", "role": "dashboard-proxy"})
            return
        if self.path == "/":
            try:
                content = importlib.resources.files("multi_star").joinpath("static", "dashboard.html").read_bytes()
            except (FileNotFoundError, ModuleNotFoundError, NotADirectoryError):
                self._json(503, {"error": "dashboard resource unavailable"})
                return
            self._bytes(200, content, "text/html; charset=utf-8")
            return
        if self.path == "/sample-events.csv":
            try:
                content = importlib.resources.files("multi_star").joinpath("static", "test-events.csv").read_bytes()
            except (FileNotFoundError, ModuleNotFoundError, NotADirectoryError):
                self._json(503, {"error": "sample event data unavailable"})
                return
            self._bytes(200, content, "text/csv; charset=utf-8")
            return
        if self.path in {"/api/snapshot", "/status"}:
            self._forward("GET", None)
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        small_action = self.path in {"/small-sat/fault", "/small-sat/recover"}
        if not small_action and self.path not in FORWARDED_POSTS:
            self._json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > 1_048_576:
            self._json(400, {"error": "invalid or excessive body size"})
            return
        body = self.rfile.read(length)
        if small_action:
            try:
                satellite_id = json.loads(body)["satellite_id"]
                base = small_satellite_base(satellite_id)
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                self._json(400, {"error": str(exc)})
                return
            target = "/" + self.path.rsplit("/", 1)[-1]
            self._forward("POST", body, base=base, path=target)
            return
        self._forward("POST", body)

    def _forward(
        self,
        method: str,
        body: bytes | None,
        *,
        base: str | None = None,
        path: str | None = None,
    ) -> None:
        try:
            base = base or self.server.proxy.discover()
            request = urllib.request.Request(
                base + (path or self.path),
                data=body,
                method=method,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                self._bytes(response.status, response.read(), response.headers.get("Content-Type", "application/json"))
        except urllib.error.HTTPError as exc:
            self._bytes(exc.code, exc.read(), exc.headers.get("Content-Type", "application/json"))
        except (OSError, ValueError, RuntimeError, urllib.error.URLError) as exc:
            self._json(503, {"error": str(exc)})

    def log_message(self, format: str, *args: Any) -> None:
        print(f"dashboard-proxy {format % args}", flush=True)


def main() -> None:
    port = int(os.environ.get("PORT", "8082"))
    server = DashboardServer(("0.0.0.0", port), DashboardHandler)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
