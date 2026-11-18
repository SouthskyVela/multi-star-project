"""Execution-side model for one small satellite.

The model deliberately contains no networking or consensus logic.  Epochs and
plan versions are supplied by the caller; this module only enforces fencing,
idempotency, local resources, and deterministic simulation-time transitions.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence


class CommandKind(str, Enum):
    TRANSFER = "transfer"
    OBSERVATION = "observation"
    UPLOAD = "upload"
    SAFE_MODE = "safe_mode"


class TaskState(str, Enum):
    OFFERED = "offered"
    ACCEPTED = "accepted"
    STARTED = "started"
    COMPLETED = "completed"
    VERIFIED = "verified"
    UNKNOWN = "unknown"
    FAILED = "failed"
    REJECTED = "rejected"


class HealthState(str, Enum):
    NOMINAL = "nominal"
    DEGRADED = "degraded"
    FAILED = "failed"
    SAFE = "safe"


@dataclass(frozen=True)
class Command:
    command_id: str
    satellite_id: str
    epoch: int
    plan_version: int
    kind: CommandKind | str
    not_before: float
    expires_at: float
    duration_s: float
    target_position_m: Sequence[float] | None = None
    delta_v_cost_mps: float = 0.0
    data_bytes: int = 0

    def __post_init__(self) -> None:
        if isinstance(self.kind, str):
            object.__setattr__(self, "kind", CommandKind(self.kind.lower()))
        if self.target_position_m is not None:
            object.__setattr__(
                self, "target_position_m", _position(self.target_position_m)
            )


@dataclass(frozen=True)
class CommandReceipt:
    accepted: bool
    duplicate: bool
    state: TaskState
    reason: str = ""


@dataclass
class SatelliteTask:
    command: Command
    state: TaskState
    original_accepted: bool
    reason: str = ""
    accepted_at: float | None = None
    started_at: float | None = None
    completed_at: float | None = None
    effect_applied: bool = False

    def to_dict(self) -> dict:
        return {
            "command": _command_to_dict(self.command),
            "state": self.state.value,
            "original_accepted": self.original_accepted,
            "reason": self.reason,
            "accepted_at": self.accepted_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "effect_applied": self.effect_applied,
        }

    @classmethod
    def from_dict(cls, data: dict) -> SatelliteTask:
        return cls(
            command=_command_from_dict(data["command"]),
            state=TaskState(data["state"]),
            original_accepted=bool(data["original_accepted"]),
            reason=data["reason"],
            accepted_at=data["accepted_at"],
            started_at=data["started_at"],
            completed_at=data["completed_at"],
            effect_applied=bool(data["effect_applied"]),
        )


class SmallSatellite:
    """Stateful command executor using a caller-owned, monotonic clock."""

    def __init__(
        self,
        satellite_id: str,
        *,
        position_m: Sequence[float] = (0.0, 0.0, 0.0),
        delta_v_mps: float = 150.0,
        storage_bytes: int = 1_073_741_824,
        minimum_separation_m: float = 50.0,
        neighbor_targets_m: Mapping[str, Sequence[float]] | None = None,
    ) -> None:
        if not satellite_id:
            raise ValueError("satellite_id must not be empty")
        if delta_v_mps < 0 or storage_bytes < 0 or minimum_separation_m < 0:
            raise ValueError("resource capacities and separation must be non-negative")
        self.satellite_id = satellite_id
        self.position_m = _position(position_m)
        self.delta_v_remaining_mps = float(delta_v_mps)
        self.storage_capacity_bytes = int(storage_bytes)
        self.storage_remaining_bytes = int(storage_bytes)
        self.minimum_separation_m = float(minimum_separation_m)
        self.neighbor_targets_m = {
            neighbor_id: _position(target)
            for neighbor_id, target in (neighbor_targets_m or {}).items()
        }
        self.health = HealthState.NOMINAL
        self.highest_epoch = -1
        self.highest_plan_version = -1
        self.sim_time_s = 0.0
        self.tasks: dict[str, SatelliteTask] = {}
        self.current_command_id: str | None = None

    @property
    def storage_used_bytes(self) -> int:
        return self.storage_capacity_bytes - self.storage_remaining_bytes

    @property
    def current_task(self) -> SatelliteTask | None:
        if self.current_command_id is None:
            return None
        return self.tasks[self.current_command_id]

    def set_neighbor_target(
        self, satellite_id: str, target_position_m: Sequence[float]
    ) -> None:
        """Update the advertised target used by subsequent transfer checks."""
        self.neighbor_targets_m[satellite_id] = _position(target_position_m)

    def receive_command(
        self, command: Command, sim_time_s: float | None = None
    ) -> CommandReceipt:
        """Fence and accept a command without advancing other tasks."""
        if sim_time_s is not None:
            self._set_time(sim_time_s)

        duplicate = self.tasks.get(command.command_id)
        if duplicate is not None:
            return CommandReceipt(
                accepted=duplicate.original_accepted,
                duplicate=True,
                state=duplicate.state,
                reason=duplicate.reason or "duplicate command; original result retained",
            )

        if command.satellite_id != self.satellite_id:
            return self._reject(command, "command is addressed to another satellite")
        if command.epoch < self.highest_epoch:
            return self._reject(command, "stale epoch")
        if (
            command.epoch == self.highest_epoch
            and command.plan_version < self.highest_plan_version
        ):
            return self._reject(command, "stale plan version")
        if self.sim_time_s >= command.expires_at:
            return self._reject(command, "command has expired")

        if command.epoch > self.highest_epoch:
            self.highest_epoch = command.epoch
            self.highest_plan_version = command.plan_version
        else:
            self.highest_plan_version = max(
                self.highest_plan_version, command.plan_version
            )

        if self.health is HealthState.FAILED:
            return self._reject(command, "satellite health is FAILED")
        if self.health is HealthState.SAFE and command.kind is not CommandKind.SAFE_MODE:
            return self._reject(command, "satellite is in SAFE mode")

        reason = self._resource_rejection(command)
        if reason:
            return self._reject(command, reason)

        current = self.current_task
        if current is not None and current.state in {
            TaskState.ACCEPTED,
            TaskState.STARTED,
        }:
            if command.kind is not CommandKind.SAFE_MODE:
                return self._reject(command, "another command is currently active")
            current.state = TaskState.UNKNOWN
            current.reason = "preempted by SAFE_MODE"
            self.current_command_id = None

        task = SatelliteTask(
            command=command,
            state=TaskState.ACCEPTED,
            original_accepted=True,
            accepted_at=self.sim_time_s,
        )
        self.tasks[command.command_id] = task
        self.current_command_id = command.command_id
        if command.kind is CommandKind.SAFE_MODE:
            self.health = HealthState.SAFE
        return CommandReceipt(
            accepted=True,
            duplicate=False,
            state=TaskState.ACCEPTED,
        )

    def advance(self, sim_time_s: float) -> None:
        """Advance the current task; completion effects are applied exactly once."""
        self._set_time(sim_time_s)
        task = self.current_task
        if task is None or self.health is HealthState.FAILED:
            return

        command = task.command
        if task.state is TaskState.ACCEPTED:
            assert task.accepted_at is not None
            start_at = max(task.accepted_at, command.not_before)
            if start_at >= command.expires_at:
                task.state = TaskState.REJECTED
                task.reason = "command expired before it could start"
                self.current_command_id = None
                return
            if self.sim_time_s < start_at:
                return
            task.state = TaskState.STARTED
            task.started_at = start_at

        if task.state is not TaskState.STARTED:
            return
        assert task.started_at is not None
        completed_at = task.started_at + command.duration_s
        if self.sim_time_s < completed_at:
            return
        if not task.effect_applied:
            reason = self._resource_rejection(command)
            if reason:
                task.state = TaskState.FAILED
                task.reason = reason
                self.current_command_id = None
                return
            self._apply_effect(command)
            task.effect_applied = True
        task.state = TaskState.COMPLETED
        task.completed_at = completed_at
        self.current_command_id = None

    def verify(self, command_id: str) -> CommandReceipt:
        """Verify a matching completed task and release verified upload storage."""
        task = self.tasks.get(command_id)
        if task is None:
            return CommandReceipt(
                accepted=False,
                duplicate=False,
                state=TaskState.UNKNOWN,
                reason="unknown command_id",
            )
        if task.state is not TaskState.COMPLETED:
            return CommandReceipt(
                accepted=False,
                duplicate=False,
                state=task.state,
                reason="only a COMPLETED command can be verified",
            )
        task.state = TaskState.VERIFIED
        if task.command.kind is CommandKind.UPLOAD:
            self.storage_remaining_bytes += task.command.data_bytes
        return CommandReceipt(
            accepted=True,
            duplicate=False,
            state=TaskState.VERIFIED,
        )

    def fail(self) -> None:
        """Enter a persistent failed state; in-flight work becomes UNKNOWN."""
        self.health = HealthState.FAILED
        for task in self.tasks.values():
            if task.state in {TaskState.ACCEPTED, TaskState.STARTED}:
                task.state = TaskState.UNKNOWN
                task.reason = "satellite failed while command was in flight"
        self.current_command_id = None

    def recover(self) -> None:
        """Explicitly recover a failed satellite without changing UNKNOWN tasks."""
        if self.health is not HealthState.FAILED:
            raise ValueError("only a FAILED satellite can be explicitly recovered")
        self.health = HealthState.NOMINAL

    def snapshot(self) -> str:
        """Return a JSON snapshot sufficient to resume without losing fencing state."""
        return json.dumps(
            {
                "schema_version": 1,
                "satellite_id": self.satellite_id,
                "position_m": list(self.position_m),
                "delta_v_remaining_mps": self.delta_v_remaining_mps,
                "storage_capacity_bytes": self.storage_capacity_bytes,
                "storage_remaining_bytes": self.storage_remaining_bytes,
                "minimum_separation_m": self.minimum_separation_m,
                "neighbor_targets_m": {
                    key: list(value) for key, value in self.neighbor_targets_m.items()
                },
                "health": self.health.value,
                "highest_epoch": self.highest_epoch,
                "highest_plan_version": self.highest_plan_version,
                "sim_time_s": self.sim_time_s,
                "current_command_id": self.current_command_id,
                "tasks": [task.to_dict() for task in self.tasks.values()],
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def restore(cls, payload: str) -> SmallSatellite:
        """Restore health and task history; notably, FAILED is not auto-cleared."""
        data = json.loads(payload)
        satellite = cls(
            data["satellite_id"],
            position_m=data["position_m"],
            delta_v_mps=data["delta_v_remaining_mps"],
            storage_bytes=data["storage_capacity_bytes"],
            minimum_separation_m=data["minimum_separation_m"],
            neighbor_targets_m=data["neighbor_targets_m"],
        )
        satellite.storage_remaining_bytes = int(data["storage_remaining_bytes"])
        satellite.health = HealthState(data["health"])
        satellite.highest_epoch = int(data["highest_epoch"])
        satellite.highest_plan_version = int(data["highest_plan_version"])
        satellite.sim_time_s = float(data["sim_time_s"])
        satellite.tasks = {
            item["command"]["command_id"]: SatelliteTask.from_dict(item)
            for item in data["tasks"]
        }
        satellite.current_command_id = data["current_command_id"]
        return satellite

    def _set_time(self, sim_time_s: float) -> None:
        sim_time_s = float(sim_time_s)
        if not math.isfinite(sim_time_s) or sim_time_s < self.sim_time_s:
            raise ValueError("simulation time must be finite and monotonic")
        self.sim_time_s = sim_time_s

    def _reject(self, command: Command, reason: str) -> CommandReceipt:
        self.tasks[command.command_id] = SatelliteTask(
            command=command,
            state=TaskState.REJECTED,
            original_accepted=False,
            reason=reason,
        )
        return CommandReceipt(
            accepted=False,
            duplicate=False,
            state=TaskState.REJECTED,
            reason=reason,
        )

    def _resource_rejection(self, command: Command) -> str:
        if command.duration_s < 0 or command.not_before > command.expires_at:
            return "invalid command time window or duration"
        if command.kind is CommandKind.TRANSFER:
            if command.target_position_m is None:
                return "transfer requires target_position_m"
            if command.delta_v_cost_mps < 0:
                return "transfer delta-v cost must be non-negative"
            if command.delta_v_cost_mps > self.delta_v_remaining_mps:
                return "insufficient remaining delta-v"
            for neighbor_id, neighbor_target in self.neighbor_targets_m.items():
                if neighbor_id == self.satellite_id:
                    continue
                if _distance(command.target_position_m, neighbor_target) < self.minimum_separation_m:
                    return f"transfer violates minimum separation from {neighbor_id}"
        elif command.kind is CommandKind.OBSERVATION:
            if command.data_bytes <= 0:
                return "observation requires positive data_bytes"
            if command.data_bytes > self.storage_remaining_bytes:
                return "insufficient remaining storage"
        elif command.kind is CommandKind.UPLOAD:
            if command.data_bytes <= 0:
                return "upload requires positive data_bytes"
            if command.data_bytes > self.storage_used_bytes:
                return "upload data_bytes exceeds stored observation data"
        return ""

    def _apply_effect(self, command: Command) -> None:
        if command.kind is CommandKind.TRANSFER:
            assert command.target_position_m is not None
            self.delta_v_remaining_mps -= command.delta_v_cost_mps
            self.position_m = command.target_position_m
        elif command.kind is CommandKind.OBSERVATION:
            self.storage_remaining_bytes -= command.data_bytes


def _position(value: Sequence[float]) -> tuple[float, float, float]:
    if len(value) != 3:
        raise ValueError("a position must contain exactly three coordinates")
    return (float(value[0]), float(value[1]), float(value[2]))


def _distance(a: Sequence[float], b: Sequence[float]) -> float:
    return math.sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(a, b)))


def _command_to_dict(command: Command) -> dict:
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
            list(command.target_position_m)
            if command.target_position_m is not None
            else None
        ),
        "delta_v_cost_mps": command.delta_v_cost_mps,
        "data_bytes": command.data_bytes,
    }


def _command_from_dict(data: dict) -> Command:
    return Command(**data)
