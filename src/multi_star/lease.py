"""Kubernetes Lease based leader election using only the standard library.

A Lease provides fencing epochs and a single active holder during normal API
server operation.  It is not a claim of consensus under arbitrary network
partitions; command execution must still enforce epoch and plan fencing.
"""

from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

SERVICE_ACCOUNT_ROOT = "/var/run/secrets/kubernetes.io/serviceaccount"
DEFAULT_LEASE_NAME = "multi-star-control"


class KubernetesAPIError(RuntimeError):
    """An HTTP error returned by the Kubernetes API."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class LeaseConflict(KubernetesAPIError):
    """The Lease changed between reading and writing it."""


class KubernetesAPI:
    """Small in-cluster Kubernetes HTTP client shared by Lease and ConfigMap code."""

    def __init__(
        self,
        namespace: str = "multi-star",
        *,
        host: str | None = None,
        port: str | None = None,
        token: str | None = None,
        ca_path: str | None = None,
        timeout_s: float = 5.0,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        host = host or os.environ.get("KUBERNETES_SERVICE_HOST", "kubernetes.default.svc")
        port = port or os.environ.get("KUBERNETES_SERVICE_PORT", "443")
        self.base_url = f"https://{host}:{port}"
        self.namespace = namespace
        self.timeout_s = timeout_s
        token_path = os.path.join(SERVICE_ACCOUNT_ROOT, "token")
        if token is None:
            with open(token_path, encoding="utf-8") as token_file:
                token = token_file.read().strip()
        self.token = token
        self.ssl_context = ssl.create_default_context(
            cafile=ca_path or os.path.join(SERVICE_ACCOUNT_ROOT, "ca.crt")
        )
        self._opener = opener or urllib.request.urlopen

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        content_type: str = "application/json",
    ) -> dict[str, Any]:
        data = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "Content-Type": content_type,
            },
        )
        try:
            with self._opener(
                request, timeout=self.timeout_s, context=self.ssl_context
            ) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                detail = json.loads(raw).get("message", str(exc))
            except (ValueError, AttributeError):
                detail = str(exc)
            error_type = LeaseConflict if exc.code == 409 else KubernetesAPIError
            raise error_type(exc.code, detail) from exc
        return json.loads(raw) if raw else {}


@dataclass(frozen=True)
class LeaseState:
    holder_identity: str
    renew_time: str
    lease_duration_seconds: int
    lease_transitions: int
    resource_version: str

    @property
    def epoch(self) -> int:
        # Satellite epochs are positive; Kubernetes starts leaseTransitions at zero.
        return self.lease_transitions + 1

    @property
    def renew_timestamp(self) -> float:
        return _parse_rfc3339(self.renew_time)

    def expires_at(self) -> float:
        return self.renew_timestamp + self.lease_duration_seconds

    def is_expired(self, now: float) -> bool:
        return now >= self.expires_at()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> LeaseState:
        spec = value.get("spec", {})
        metadata = value.get("metadata", {})
        return cls(
            holder_identity=str(spec.get("holderIdentity", "")),
            renew_time=str(spec.get("renewTime", "")),
            lease_duration_seconds=int(spec.get("leaseDurationSeconds", 0)),
            lease_transitions=int(spec.get("leaseTransitions", 0)),
            resource_version=str(metadata.get("resourceVersion", "")),
        )

    def object(self, name: str, namespace: str) -> dict[str, Any]:
        metadata = {"name": name, "namespace": namespace}
        if self.resource_version:
            metadata["resourceVersion"] = self.resource_version
        return {
            "apiVersion": "coordination.k8s.io/v1",
            "kind": "Lease",
            "metadata": metadata,
            "spec": {
                "holderIdentity": self.holder_identity,
                "renewTime": self.renew_time,
                "leaseDurationSeconds": self.lease_duration_seconds,
                "leaseTransitions": self.lease_transitions,
            },
        }


class LeaseManager:
    """Acquire or renew one Lease with resourceVersion compare-and-swap.

    ``can_issue_commands`` is cleared before every renewal attempt and on every
    error.  A failed renewal therefore immediately fences the command path.
    """

    def __init__(
        self,
        identity: str,
        api: KubernetesAPI,
        *,
        name: str = DEFAULT_LEASE_NAME,
        namespace: str | None = None,
        duration_seconds: int = 15,
        clock: Callable[[], float] = time.time,
        max_attempts: int = 3,
    ) -> None:
        if not identity:
            raise ValueError("identity must not be empty")
        if duration_seconds < 1:
            raise ValueError("duration_seconds must be positive")
        self.identity = identity
        self.api = api
        self.name = name
        self.namespace = namespace or api.namespace
        self.duration_seconds = duration_seconds
        self.clock = clock
        self.max_attempts = max_attempts
        self.state: LeaseState | None = None
        self._can_issue_commands = False
        self._suspended = False
        escaped_name = urllib.parse.quote(name, safe="")
        escaped_namespace = urllib.parse.quote(self.namespace, safe="")
        self._path = (
            f"/apis/coordination.k8s.io/v1/namespaces/{escaped_namespace}"
            f"/leases/{escaped_name}"
        )

    @property
    def can_issue_commands(self) -> bool:
        if self._suspended or not self._can_issue_commands or self.state is None:
            return False
        return (
            self.state.holder_identity == self.identity
            and not self.state.is_expired(self.clock())
        )

    @property
    def is_leader(self) -> bool:
        return self.can_issue_commands

    def suspend(self) -> None:
        """Immediately fence this holder without deleting the shared Lease."""
        self._suspended = True
        self._can_issue_commands = False

    def resume(self) -> None:
        self._suspended = False
        self._can_issue_commands = False

    def acquire_or_renew(self, now: float | None = None) -> LeaseState:
        self._can_issue_commands = False
        if self._suspended:
            raise RuntimeError("leader renewal is suspended")
        now = self.clock() if now is None else float(now)
        last_conflict: LeaseConflict | None = None
        for _ in range(self.max_attempts):
            try:
                current = self.api.request("GET", self._path)
            except KubernetesAPIError as exc:
                if exc.status != 404:
                    raise
                current = None

            if current is None:
                candidate = LeaseState(
                    holder_identity=self.identity,
                    renew_time=_format_rfc3339(now),
                    lease_duration_seconds=self.duration_seconds,
                    lease_transitions=0,
                    resource_version="",
                )
                try:
                    created = self.api.request(
                        "POST", self._collection_path(), candidate.object(self.name, self.namespace)
                    )
                except LeaseConflict as exc:
                    last_conflict = exc
                    continue
                self.state = LeaseState.from_dict(created)
                self._can_issue_commands = True
                return self.state

            observed = LeaseState.from_dict(current)
            available = not observed.holder_identity or observed.is_expired(now)
            if observed.holder_identity != self.identity and not available:
                self.state = observed
                return observed

            transitions = observed.lease_transitions
            if observed.holder_identity != self.identity:
                transitions += 1
            candidate = LeaseState(
                holder_identity=self.identity,
                renew_time=_format_rfc3339(now),
                lease_duration_seconds=self.duration_seconds,
                lease_transitions=transitions,
                resource_version=observed.resource_version,
            )
            try:
                updated = self.api.request(
                    "PUT", self._path, candidate.object(self.name, self.namespace)
                )
            except LeaseConflict as exc:
                last_conflict = exc
                continue
            self.state = LeaseState.from_dict(updated)
            self._can_issue_commands = self.state.holder_identity == self.identity
            return self.state

        self._can_issue_commands = False
        raise last_conflict or LeaseConflict(409, "Lease update conflict")

    def _collection_path(self) -> str:
        return self._path.rsplit("/", 1)[0]


def _format_rfc3339(timestamp: float) -> str:
    value = datetime.fromtimestamp(timestamp, timezone.utc)
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_rfc3339(value: str) -> float:
    if not value:
        return 0.0
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
