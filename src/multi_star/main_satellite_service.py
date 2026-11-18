"""HTTP service and cluster adapters for the three main satellites."""

from __future__ import annotations

import importlib.resources
import json
import math
import os
import socket
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .coordinator import Coordinator, ObservationMode, ScienceEvent
from .lease import KubernetesAPI, KubernetesAPIError, LeaseConflict, LeaseManager
from .satellite import TaskState

MAX_BODY_BYTES = 1_048_576
PLAN_CONFIGMAP = "multi-star-plan"


class StateConflict(RuntimeError):
    """ConfigMap resourceVersion conflict; the latest state has been re-read."""


class ConfigMapStateStore:
    """Persist the complete coordinator state in one ConfigMap document."""

    def __init__(
        self,
        api: KubernetesAPI,
        *,
        namespace: str | None = None,
        name: str = PLAN_CONFIGMAP,
    ) -> None:
        self.api = api
        self.namespace = namespace or api.namespace
        self.name = name
        self.resource_version: str | None = None
        namespace_path = urllib.parse.quote(self.namespace, safe="")
        name_path = urllib.parse.quote(name, safe="")
        self._collection = f"/api/v1/namespaces/{namespace_path}/configmaps"
        self._path = f"{self._collection}/{name_path}"

    def load(self) -> dict[str, Any] | None:
        try:
            value = self.api.request("GET", self._path)
        except KubernetesAPIError as exc:
            if exc.status == 404:
                self.resource_version = None
                return None
            raise
        self.resource_version = value.get("metadata", {}).get("resourceVersion")
        payload = value.get("data", {}).get("state")
        return json.loads(payload) if payload else None

    def save(self, state: dict[str, Any]) -> None:
        encoded = json.dumps(state, sort_keys=True, separators=(",", ":"))
        metadata: dict[str, Any] = {"name": self.name, "namespace": self.namespace}
        if self.resource_version is not None:
            metadata["resourceVersion"] = self.resource_version
        body = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": metadata,
            "data": {"state": encoded},
        }
        try:
            if self.resource_version is None:
                result = self.api.request("POST", self._collection, body)
            else:
                result = self.api.request("PUT", self._path, body)
        except LeaseConflict as exc:
            # A writer must never blindly retry its stale document.  Re-read so
            # the caller can restore and reapply its operation if still valid.
            self.load()
            raise StateConflict(str(exc)) from exc
        self.resource_version = result.get("metadata", {}).get("resourceVersion")


class SmallSatelliteClient:
    """Cluster-internal HTTP client for the nine stateful executors."""

    def __init__(self, count: int = 9, *, timeout_s: float = 3.0) -> None:
        self.satellite_ids = [f"small-sat-{index}" for index in range(count)]
        self.timeout_s = timeout_s
        self.url_template = os.environ.get(
            "SMALL_SATELLITE_URL_TEMPLATE",
            "http://{satellite_id}.small-sat.multi-star.svc.cluster.local:8080",
        )

    def get_status(self, satellite_id: str) -> dict[str, Any]:
        return self._request(satellite_id, "GET", "/status")

    def advance(self, satellite_id: str, time_s: float) -> dict[str, Any]:
        return self._request(satellite_id, "POST", "/advance", {"sim_time_s": time_s})

    def verify(self, satellite_id: str, command_id: str) -> dict[str, Any]:
        return self._request(satellite_id, "POST", "/verify", {"command_id": command_id})

    def send_command(self, command: dict[str, Any], time_s: float) -> dict[str, Any]:
        body = dict(command)
        body["sim_time_s"] = time_s
        return self._request(command["satellite_id"], "POST", "/commands", body)

    def _request(
        self,
        satellite_id: str,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = self.url_template.format(satellite_id=satellite_id) + path
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            return json.load(response)


class MainSatelliteServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        coordinator: Coordinator,
        lease: LeaseManager,
        state_store: ConfigMapStateStore,
        small_satellites: SmallSatelliteClient,
        *,
        step_s: float = 1.0,
    ) -> None:
        super().__init__(address, MainSatelliteHandler)
        self.coordinator = coordinator
        self.lease = lease
        self.state_store = state_store
        self.small_satellites = small_satellites
        self.identity = lease.identity
        self.step_s = step_s
        self.lock = threading.RLock()
        self.ready = True
        self.suspended_until = 0.0
        self._stopping = threading.Event()
        self._worker: threading.Thread | None = None
        self._scheduler_worker: threading.Thread | None = None
        self._planned_healthy: set[str] | None = None
        self._active_label: bool | None = None

    def start_background(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        self._worker = threading.Thread(
            target=self._run, name="main-satellite-coordinator", daemon=True
        )
        self._worker.start()
        if self._scheduler_worker is None or not self._scheduler_worker.is_alive():
            self._scheduler_worker = threading.Thread(
                target=self._scheduler_run, name="main-satellite-scheduler", daemon=True
            )
            self._scheduler_worker.start()

    def stop_background(self) -> None:
        self._stopping.set()
        if self._worker is not None:
            self._worker.join(timeout=5)
        if self._scheduler_worker is not None:
            self._scheduler_worker.join(timeout=5)

    def _run(self) -> None:
        while not self._stopping.is_set():
            try:
                self._iteration()
            except Exception as exc:
                traceback.print_exc()
                # No command is sent outside _leader_tick, and LeaseManager
                # fences command issue before every renewal attempt.
                with self.lock:
                    self.coordinator.audit(f"coordination iteration failed: {exc}")
                self._set_active_label(False)
            self._stopping.wait(1.0)

    def _scheduler_run(self) -> None:
        while not self._stopping.is_set():
            try:
                if self.lease.can_issue_commands and time.monotonic() >= self.suspended_until:
                    self._leader_tick()
            except Exception as exc:
                traceback.print_exc()
                with self.lock:
                    self.coordinator.audit(f"scheduler iteration failed: {exc}")
            self._stopping.wait(0.2)

    def _iteration(self) -> None:
        if time.monotonic() < self.suspended_until:
            self.lease.suspend()
            self._set_active_label(False)
            return
        self.lease.resume()
        state = self.lease.acquire_or_renew()
        if state.holder_identity != self.identity or not self.lease.can_issue_commands:
            self._set_active_label(False)
            return
        self._set_active_label(True)

    def _leader_tick(self) -> None:
        with self.lock:
            latest = self.state_store.load()
            if latest is not None:
                self.coordinator = Coordinator.from_dict(latest)
            self.coordinator.set_epoch(self.lease.state.epoch)
            self.coordinator.advance_time(self.coordinator.time_s + self.step_s)

            for satellite_id in self.small_satellites.satellite_ids:
                try:
                    status = self.small_satellites.get_status(satellite_id)
                    self.coordinator.update_satellite(status)
                    if not self.lease.can_issue_commands:
                        break
                    advanced = self.small_satellites.advance(
                        satellite_id, self.coordinator.time_s
                    )
                    self.coordinator.update_satellite(advanced)
                    for item in advanced.get("tasks", []):
                        command = item.get("command", {})
                        if (
                            item.get("state") != TaskState.COMPLETED.value
                            or command.get("kind") not in {"transfer", "observation", "upload"}
                        ):
                            continue
                        if (
                            not self.lease.can_issue_commands
                            or time.monotonic() < self.suspended_until
                        ):
                            break
                        verified = self.small_satellites.verify(
                            satellite_id, command["command_id"]
                        )
                        self.coordinator.update_satellite(verified)
                except (OSError, ValueError, KeyError, urllib.error.URLError) as exc:
                    self.coordinator.mark_unreachable(satellite_id, str(exc))

            healthy = set(self.coordinator.healthy_satellite_ids)
            reason = None
            if self.coordinator.current_plan is None:
                reason = "initial plan"
            elif self.coordinator.current_plan.epoch != self.coordinator.epoch:
                reason = "leader epoch changed"
            elif healthy != self._planned_healthy:
                reason = "healthy satellite set changed"
            if reason is not None and len(healthy) >= 2:
                try:
                    self.coordinator.replan(reason=reason)
                except ValueError as exc:
                    # A rejected revision must not be retried at scheduler
                    # cadence; record it once and wait for the next real change.
                    self.coordinator.audit(f"replanning skipped: {exc}")
            self._planned_healthy = healthy

            # Persist polling and the new revision before exposing commands.
            try:
                self.state_store.save(self.coordinator.to_dict())
            except StateConflict:
                latest = self.state_store.load()
                if latest is not None:
                    self.coordinator = Coordinator.from_dict(latest)
                return

            for command in self.coordinator.pending_commands():
                if not self.lease.can_issue_commands or time.monotonic() < self.suspended_until:
                    break
                try:
                    response = self.small_satellites.send_command(
                        command.to_dict() if hasattr(command, "to_dict") else _command_dict(command),
                        self.coordinator.time_s,
                    )
                    self.coordinator.update_satellite(response)
                    receipt = response.get("receipt", {})
                    self.coordinator.record_command_state(
                        command,
                        receipt.get("state", TaskState.ACCEPTED.value),
                        reason=receipt.get("reason", ""),
                    )
                except (OSError, ValueError, KeyError, urllib.error.URLError) as exc:
                    # Timeout/reset is ambiguous: never directly retransmit an
                    # irreversible transfer.  Reconcile from executor status.
                    self.coordinator.record_command_state(
                        command, TaskState.UNKNOWN, reason=str(exc)
                    )
            try:
                self.state_store.save(self.coordinator.to_dict())
            except StateConflict:
                latest = self.state_store.load()
                if latest is not None:
                    self.coordinator = Coordinator.from_dict(latest)

    def _set_active_label(self, active: bool) -> None:
        if self._active_label is active:
            return
        self._active_label = active
        namespace = urllib.parse.quote(self.lease.namespace, safe="")
        pod = urllib.parse.quote(self.identity, safe="")
        try:
            self.lease.api.request(
                "PATCH",
                f"/api/v1/namespaces/{namespace}/pods/{pod}",
                {"metadata": {"labels": {"multi-star.io/active": "true" if active else "false"}}},
                content_type="application/merge-patch+json",
            )
        except Exception as exc:
            with self.lock:
                self.coordinator.audit(f"active pod label update failed: {exc}")

    def submit_event(self, event: ScienceEvent) -> tuple[bool, int]:
        self._require_leader()
        with self.lock:
            if self.lease.state is not None:
                self.coordinator.set_epoch(self.lease.state.epoch)
            for _ in range(3):
                added = self.coordinator.add_event(event)
                try:
                    # The science event is durable before any orchestration.
                    self.state_store.save(self.coordinator.to_dict())
                    break
                except StateConflict:
                    latest = self.state_store.load()
                    if latest is not None:
                        self.coordinator = Coordinator.from_dict(latest)
            else:
                raise StateConflict("could not persist event after repeated conflicts")
            if added:
                self.coordinator.switch_mode(ObservationMode.FIXED_SOURCE, event_id=event.event_id)
                self.state_store.save(self.coordinator.to_dict())
            return added, self.coordinator.plan_version

    def change_mode(self, mode: str, event_id: str | None = None) -> int:
        self._require_leader()
        with self.lock:
            if self.lease.state is not None:
                self.coordinator.set_epoch(self.lease.state.epoch)
            plan = self.coordinator.switch_mode(mode, event_id=event_id)
            self.state_store.save(self.coordinator.to_dict())
            return plan.plan_version

    def suspend(self, seconds: float) -> float:
        if not math.isfinite(seconds) or not 0.0 <= seconds <= 3600.0:
            raise ValueError("seconds must be between 0 and 3600")
        self.suspended_until = time.monotonic() + seconds
        self.lease.suspend()
        self._set_active_label(False)
        return self.suspended_until

    def _require_leader(self) -> None:
        if not self.lease.can_issue_commands or time.monotonic() < self.suspended_until:
            raise PermissionError("this main satellite is not an active, renewable leader")

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            state = self.lease.state
            leader_id = state.holder_identity if state is not None else ""
            epoch = state.epoch if state is not None else self.coordinator.epoch
            return self.coordinator.snapshot(leader_id=leader_id, leader_epoch=epoch)

    def status(self) -> dict[str, Any]:
        state = self.lease.state
        return {
            "id": self.identity,
            "ready": self.ready,
            "leader": self.lease.can_issue_commands,
            "holder": state.holder_identity if state is not None else "",
            "epoch": state.epoch if state is not None else self.coordinator.epoch,
            "suspended": time.monotonic() < self.suspended_until,
            "plan_version": self.coordinator.plan_version,
        }


class MainSatelliteHandler(BaseHTTPRequestHandler):
    server: MainSatelliteServer

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length < 0 or length > MAX_BODY_BYTES:
            raise ValueError("request body exceeds 1 MiB")
        value = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(value, dict):
            raise ValueError("JSON body must be an object")
        return value

    @property
    def _path(self) -> str:
        return urllib.parse.urlsplit(self.path).path

    def do_GET(self) -> None:
        try:
            if self._path == "/healthz":
                self._json(200, {"process": "alive", "id": self.server.identity})
            elif self._path == "/readyz":
                self._json(
                    200 if self.server.ready else 503,
                    {"ready": self.server.ready, "leader_required": False},
                )
            elif self._path == "/status":
                self._json(200, self.server.status())
            elif self._path == "/api/snapshot":
                self._json(200, self.server.snapshot())
            elif self._path == "/":
                self._dashboard()
            else:
                self._json(404, {"error": "not found"})
        except Exception as exc:
            self._json(500, {"error": str(exc)})

    def do_POST(self) -> None:
        try:
            body = self._body()
            if self._path == "/events":
                event = _event_from_request(body, self.server.coordinator.time_s)
                added, version = self.server.submit_event(event)
                self._json(202, {"accepted": added, "duplicate": not added, "plan_version": version})
            elif self._path == "/mode":
                version = self.server.change_mode(str(body["mode"]), body.get("event_id"))
                self._json(200, {"mode": str(body["mode"]).upper(), "plan_version": version})
            elif self._path == "/test/suspend":
                seconds = float(body["seconds"])
                self.server.suspend(seconds)
                self._json(200, {"suspended_seconds": seconds})
            else:
                self._json(404, {"error": "not found"})
        except PermissionError as exc:
            self._json(503, {"error": str(exc)})
        except StateConflict as exc:
            self._json(409, {"error": str(exc)})
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:
            self._json(500, {"error": str(exc)})

    def _dashboard(self) -> None:
        try:
            resource = importlib.resources.files("multi_star").joinpath("static", "dashboard.html")
            content = resource.read_bytes()
        except (FileNotFoundError, ModuleNotFoundError, NotADirectoryError) as exc:
            self._json(
                503,
                {"error": "dashboard resource is unavailable: multi_star/static/dashboard.html"},
            )
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.server.identity} {format % args}", flush=True)


def create_server(
    host: str = "0.0.0.0",
    port: int = 8081,
    *,
    coordinator: Coordinator | None = None,
    lease: LeaseManager | None = None,
    state_store: ConfigMapStateStore | None = None,
    small_satellites: SmallSatelliteClient | None = None,
) -> MainSatelliteServer:
    namespace = os.environ.get("POD_NAMESPACE", "multi-star")
    identity = os.environ.get("MAIN_SATELLITE_ID", socket.gethostname())
    api = None if lease is not None and state_store is not None else KubernetesAPI(namespace)
    lease = lease or LeaseManager(identity, api, namespace=namespace)
    state_store = state_store or ConfigMapStateStore(api, namespace=namespace)
    return MainSatelliteServer(
        (host, port),
        coordinator or Coordinator(),
        lease,
        state_store,
        small_satellites or SmallSatelliteClient(),
    )


def main() -> None:
    port = int(os.environ.get("PORT", "8081"))
    server = create_server(port=port)
    print(f"Serving {server.identity} on 0.0.0.0:{port}", flush=True)
    server.start_background()
    try:
        server.serve_forever()
    finally:
        server.stop_background()
        server.server_close()


def _event_from_request(body: dict[str, Any], now_s: float) -> ScienceEvent:
    data = dict(body)
    if "expiry_s" in data:
        duration = float(data.pop("expiry_s"))
        if not math.isfinite(duration) or duration <= 0.0:
            raise ValueError("expiry_s must be a positive duration")
        data["expiry"] = float(now_s) + duration
    data.setdefault("observed_at", float(now_s))
    return ScienceEvent.from_dict(data)


def _command_dict(command: Any) -> dict[str, Any]:
    return {
        "command_id": command.command_id,
        "satellite_id": command.satellite_id,
        "epoch": command.epoch,
        "plan_version": command.plan_version,
        "kind": command.kind.value,
        "not_before": command.not_before,
        "expires_at": command.expires_at,
        "duration_s": command.duration_s,
        "target_position_m": (
            list(command.target_position_m) if command.target_position_m is not None else None
        ),
        "delta_v_cost_mps": command.delta_v_cost_mps,
        "data_bytes": command.data_bytes,
    }


if __name__ == "__main__":
    main()
