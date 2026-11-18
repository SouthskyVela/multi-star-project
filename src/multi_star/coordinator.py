"""Pure coordination and planning logic for the three-main-satellite service."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from .satellite import Command, CommandKind, HealthState, TaskState
from .uv import baseline_vectors, dirty_beam, generate_formation, project_baselines

DEFAULT_SMALL_SATELLITES = tuple(f"small-sat-{index}" for index in range(9))
_ACTIVE_TASKS = {TaskState.OFFERED.value, TaskState.ACCEPTED.value, TaskState.STARTED.value}


class ObservationMode(str, Enum):
    SURVEY = "SURVEY"
    FIXED_SOURCE = "FIXED_SOURCE"
    CALIBRATION = "CALIBRATION"


@dataclass(frozen=True)
class ScienceEvent:
    event_id: str
    target: str
    frequency: float
    flux: float
    confidence: float
    expiry: float
    priority: float = 0.0
    observed_at: float = 0.0
    spectral_index: float = 0.0

    def __post_init__(self) -> None:
        if not self.event_id or not self.target:
            raise ValueError("event_id and target must not be empty")
        for name in (
            "frequency", "flux", "confidence", "expiry", "priority",
            "observed_at", "spectral_index",
        ):
            if not math.isfinite(float(getattr(self, name))):
                raise ValueError(f"{name} must be finite")
        if self.frequency <= 0 or self.flux < 0:
            raise ValueError("frequency must be positive and flux non-negative")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between zero and one")

    @property
    def frequency_hz(self) -> float:
        return self.frequency

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "target": self.target,
            "frequency": self.frequency,
            "flux": self.flux,
            "confidence": self.confidence,
            "expiry": self.expiry,
            "priority": self.priority,
            "observed_at": self.observed_at,
            "spectral_index": self.spectral_index,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ScienceEvent:
        data = dict(value)
        aliases = {
            "target": "target_id",
            "frequency": "frequency_hz",
            "flux": "flux_jy",
            "expiry": "expiry_s",
        }
        for canonical, alias in aliases.items():
            if canonical not in data and alias in data:
                data[canonical] = data.pop(alias)
        return cls(**data)


@dataclass(frozen=True)
class PlanRevision:
    epoch: int
    parent_version: int
    plan_version: int
    event_ids: tuple[str, ...]
    assignments: dict[str, dict[str, Any]]
    formation: str = "spiral"
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "epoch": self.epoch,
            "parent_version": self.parent_version,
            "plan_version": self.plan_version,
            "event_ids": list(self.event_ids),
            "assignments": self.assignments,
            "formation": self.formation,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> PlanRevision:
        return cls(
            epoch=int(value["epoch"]),
            parent_version=int(value["parent_version"]),
            plan_version=int(value["plan_version"]),
            event_ids=tuple(value["event_ids"]),
            assignments={key: dict(item) for key, item in value["assignments"].items()},
            formation=str(value.get("formation", "spiral")),
            created_at=float(value.get("created_at", 0.0)),
        )


@dataclass
class SatelliteView:
    satellite_id: str
    health: HealthState = HealthState.NOMINAL
    position_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    task_state: str = "idle"
    current_command_id: str | None = None
    tasks: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def healthy(self) -> bool:
        return self.health in {HealthState.NOMINAL, HealthState.DEGRADED}

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.satellite_id,
            "health": self.health.value,
            "position_m": list(self.position_m),
            "task_state": self.task_state,
            "current_command_id": self.current_command_id,
            "tasks": self.tasks,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> SatelliteView:
        return cls(
            satellite_id=str(value.get("id", value.get("satellite_id"))),
            health=HealthState(str(value["health"]).lower()),
            position_m=_position(value["position_m"]),
            task_state=str(value.get("task_state", "idle")),
            current_command_id=value.get("current_command_id"),
            tasks={key: dict(item) for key, item in value.get("tasks", {}).items()},
        )


class Coordinator:
    """Serializable, deterministic state machine; all cluster I/O lives elsewhere."""

    def __init__(
        self,
        satellite_ids: Sequence[str] = DEFAULT_SMALL_SATELLITES,
        *,
        formation: str = "spiral",
        radius_m: float = 5000.0,
        frequency_hz: float = 100_000_000.0,
        source_unit: Sequence[float] = (0.0, 0.0, 1.0),
        image_size: int = 64,
        seed: int = 20261118,
        main_satellites_correlated: bool = False,
        include_central_short_baselines: bool = False,
        main_satellite_positions: Mapping[str, Sequence[float]] | None = None,
    ) -> None:
        if len(set(satellite_ids)) != len(satellite_ids) or not satellite_ids:
            raise ValueError("satellite_ids must be non-empty and unique")
        self.mode = ObservationMode.SURVEY
        self.events: dict[str, ScienceEvent] = {}
        self.plans: list[PlanRevision] = []
        self.plan_version = 0
        self.epoch = 0
        self.time_s = 0.0
        self.formation = formation
        self.radius_m = float(radius_m)
        self.frequency_hz = float(frequency_hz)
        self.source_unit = _position(source_unit)
        self.image_size = int(image_size)
        self.seed = int(seed)
        self.main_satellites_correlated = bool(main_satellites_correlated)
        self.include_central_short_baselines = bool(include_central_short_baselines)
        self.main_satellite_positions = {
            key: _position(value) for key, value in (main_satellite_positions or {}).items()
        }
        self.audit_log: list[dict[str, Any]] = []
        initial = generate_formation(
            formation, len(satellite_ids), radius_m, seed=seed
        )
        self.satellites = {
            satellite_id: SatelliteView(
                satellite_id=satellite_id,
                position_m=tuple(float(value) for value in initial[index]),
            )
            for index, satellite_id in enumerate(satellite_ids)
        }

    @property
    def healthy_satellite_ids(self) -> list[str]:
        return [key for key, satellite in self.satellites.items() if satellite.healthy]

    @property
    def current_plan(self) -> PlanRevision | None:
        return self.plans[-1] if self.plans else None

    def set_epoch(self, epoch: int) -> None:
        epoch = int(epoch)
        if epoch < self.epoch:
            raise ValueError("leader epoch cannot move backwards")
        self.epoch = epoch

    def advance_time(self, time_s: float) -> None:
        time_s = float(time_s)
        if not math.isfinite(time_s) or time_s < self.time_s:
            raise ValueError("coordination time must be finite and monotonic")
        self.time_s = time_s

    def add_event(self, event: ScienceEvent, *, now: float | None = None) -> bool:
        now = self.time_s if now is None else float(now)
        if event.event_id in self.events:
            return False
        if event.expiry <= now:
            raise ValueError("cannot ingest an expired science event")
        self.events[event.event_id] = event
        self.audit(f"event {event.event_id} accepted for {event.target}")
        return True

    ingest_event = add_event

    def active_events(self, *, now: float | None = None) -> list[ScienceEvent]:
        now = self.time_s if now is None else float(now)
        return sorted(
            (event for event in self.events.values() if event.expiry > now),
            key=lambda event: (
                -event.priority,
                -event.confidence,
                -event.flux,
                event.event_id,
            ),
        )

    def switch_mode(
        self,
        mode: ObservationMode | str,
        *,
        event_id: str | None = None,
        formation: str | None = None,
        now: float | None = None,
    ) -> PlanRevision:
        try:
            requested = mode if isinstance(mode, ObservationMode) else ObservationMode(mode.upper())
        except (ValueError, AttributeError) as exc:
            raise ValueError(f"invalid observation mode: {mode}") from exc
        now = self.time_s if now is None else float(now)
        if len(self.healthy_satellite_ids) < 2:
            raise ValueError("mode changes require at least two healthy small satellites")
        unresolved = [
            key for key, value in self.satellites.items()
            if value.task_state == TaskState.UNKNOWN.value
        ]
        if unresolved:
            raise ValueError(f"mode change blocked by UNKNOWN tasks: {', '.join(unresolved)}")
        selected: list[ScienceEvent] = []
        if requested is ObservationMode.FIXED_SOURCE:
            candidates = self.active_events(now=now)
            if event_id is not None:
                candidates = [event for event in candidates if event.event_id == event_id]
            if not candidates:
                raise ValueError("FIXED_SOURCE requires a matching, unexpired science event")
            selected = [candidates[0]]
        elif event_id is not None:
            raise ValueError("event_id is only valid when entering FIXED_SOURCE")

        # Build the complete revision before mutating mode or version.  Any
        # validation/generation error leaves the previous revision untouched.
        next_mode = requested
        next_formation = formation or self.formation
        plan = self._build_revision(next_mode, next_formation, selected, now=now)
        self.mode = next_mode
        self.formation = next_formation
        self._commit(plan)
        self.audit(f"mode changed to {next_mode.value}; plan {plan.plan_version}")
        return plan

    def replan(
        self,
        *,
        formation: str | None = None,
        reason: str = "scheduled replanning",
        now: float | None = None,
    ) -> PlanRevision:
        now = self.time_s if now is None else float(now)
        if len(self.healthy_satellite_ids) < 2:
            raise ValueError("replanning requires at least two healthy small satellites")
        selected = self.active_events(now=now)[:1] if self.mode is ObservationMode.FIXED_SOURCE else []
        if self.mode is ObservationMode.FIXED_SOURCE and not selected:
            raise ValueError("FIXED_SOURCE cannot be planned without an active event")
        next_formation = formation or self.formation
        plan = self._build_revision(self.mode, next_formation, selected, now=now)
        self.formation = next_formation
        self._commit(plan)
        self.audit(f"{reason}; plan {plan.plan_version}")
        return plan

    def _build_revision(
        self,
        mode: ObservationMode,
        formation: str,
        selected_events: Sequence[ScienceEvent],
        *,
        now: float,
    ) -> PlanRevision:
        healthy = self.healthy_satellite_ids
        targets = generate_formation(formation, len(healthy), self.radius_m, seed=self.seed)
        version = self.plan_version + 1
        assignments: dict[str, dict[str, Any]] = {}
        for index, satellite_id in enumerate(healthy):
            satellite = self.satellites[satellite_id]
            # An unreachable executor may already have applied an irreversible
            # transfer.  Keep its last physical position and do not reissue it.
            if satellite.task_state == TaskState.UNKNOWN.value:
                continue
            if satellite.task_state in {TaskState.ACCEPTED.value, TaskState.STARTED.value}:
                continue
            target = tuple(float(value) for value in targets[index])
            distance = math.dist(satellite.position_m, target)
            if distance > 1.0e-6:
                command = Command(
                    command_id=f"e{self.epoch}-p{version}-{satellite_id}-transfer",
                    satellite_id=satellite_id,
                    epoch=self.epoch,
                    plan_version=version,
                    kind=CommandKind.TRANSFER,
                    not_before=now,
                    expires_at=now + 300.0,
                    duration_s=5.0,
                    target_position_m=target,
                    delta_v_cost_mps=min(100.0, distance / 10_000.0),
                )
            else:
                event = selected_events[0] if selected_events else None
                expiry = event.expiry if event is not None else now + 300.0
                command = Command(
                    command_id=f"e{self.epoch}-p{version}-{satellite_id}-{mode.value.lower()}",
                    satellite_id=satellite_id,
                    epoch=self.epoch,
                    plan_version=version,
                    kind=CommandKind.OBSERVATION,
                    not_before=now,
                    expires_at=expiry,
                    duration_s=1.0,
                    data_bytes=1_048_576,
                )
            assignments[satellite_id] = _command_dict(command)
        return PlanRevision(
            epoch=self.epoch,
            parent_version=self.plan_version,
            plan_version=version,
            event_ids=tuple(event.event_id for event in selected_events),
            assignments=assignments,
            formation=formation,
            created_at=now,
        )

    def _commit(self, plan: PlanRevision) -> None:
        if plan.parent_version != self.plan_version or plan.plan_version != self.plan_version + 1:
            raise ValueError("plan versions must increment atomically from their parent")
        self.plans.append(plan)
        self.plan_version = plan.plan_version
        for satellite_id in plan.assignments:
            self.satellites[satellite_id].task_state = TaskState.OFFERED.value

    def pending_commands(self, plan_version: int | None = None) -> list[Command]:
        plan = self.current_plan if plan_version is None else self.plan(plan_version)
        if plan is None:
            return []
        commands: list[Command] = []
        for satellite_id, value in plan.assignments.items():
            satellite = self.satellites[satellite_id]
            command = Command(**value)
            if not satellite.healthy:
                continue
            if satellite.task_state in {
                TaskState.ACCEPTED.value,
                TaskState.STARTED.value,
                TaskState.UNKNOWN.value,
            }:
                continue
            original = satellite.tasks.get(command.command_id)
            if original is None:
                commands.append(command)
                continue
            if command.kind is not CommandKind.OBSERVATION or original.get("state") not in {
                TaskState.COMPLETED.value,
                TaskState.VERIFIED.value,
            }:
                continue
            upload_id = f"{command.command_id}-upload"
            if upload_id in satellite.tasks:
                continue
            commands.append(Command(
                command_id=upload_id,
                satellite_id=satellite_id,
                epoch=command.epoch,
                plan_version=command.plan_version,
                kind=CommandKind.UPLOAD,
                not_before=self.time_s,
                expires_at=self.time_s + 300.0,
                duration_s=2.0,
                data_bytes=command.data_bytes,
            ))
        return commands

    def plan(self, plan_version: int) -> PlanRevision:
        for plan in self.plans:
            if plan.plan_version == plan_version:
                return plan
        raise KeyError(plan_version)

    def record_command_state(
        self,
        command: Command,
        state: TaskState | str,
        *,
        reason: str = "",
    ) -> None:
        satellite = self.satellites[command.satellite_id]
        state_value = state.value if isinstance(state, TaskState) else str(state).lower()
        TaskState(state_value)
        satellite.tasks[command.command_id] = {
            "command": _command_dict(command),
            "state": state_value,
            "reason": reason,
        }
        satellite.task_state = state_value
        satellite.current_command_id = (
            command.command_id if state_value in _ACTIVE_TASKS else None
        )

    def update_satellite(self, status: Mapping[str, Any]) -> None:
        satellite_id = str(status.get("satellite_id", status.get("id")))
        if satellite_id not in self.satellites:
            raise KeyError(f"unknown small satellite {satellite_id}")
        satellite = self.satellites[satellite_id]
        satellite.health = HealthState(str(status["health"]).lower())
        # A fault does not erase the last known physical location.
        if status.get("position_m") is not None:
            satellite.position_m = _position(status["position_m"])
        tasks = {
            str(item["command"]["command_id"]): dict(item)
            for item in status.get("tasks", [])
        }
        if tasks:
            satellite.tasks = tasks
        satellite.current_command_id = status.get("current_command_id")
        if satellite.current_command_id and satellite.current_command_id in satellite.tasks:
            satellite.task_state = str(satellite.tasks[satellite.current_command_id]["state"])
        elif tasks:
            satellite.task_state = str(next(reversed(tasks.values()))["state"])
        elif satellite.task_state != TaskState.OFFERED.value:
            satellite.task_state = "idle"

    def mark_unreachable(self, satellite_id: str, reason: str = "status poll failed") -> None:
        satellite = self.satellites[satellite_id]
        satellite.health = HealthState.FAILED
        if satellite.current_command_id:
            task = satellite.tasks.get(satellite.current_command_id)
            if task is not None:
                task["state"] = TaskState.UNKNOWN.value
                task["reason"] = reason
        for command_id, task in satellite.tasks.items():
            if task.get("state") in {TaskState.ACCEPTED.value, TaskState.STARTED.value}:
                task["state"] = TaskState.UNKNOWN.value
                task["reason"] = reason
        satellite.task_state = TaskState.UNKNOWN.value if satellite.tasks else "idle"
        satellite.current_command_id = None
        self.audit(f"{satellite_id} excluded after communication failure")

    def uv_and_psf(self) -> tuple[list[list[float]], list[list[float]], dict[str, Any]]:
        healthy = self.healthy_satellite_ids
        positions = [self.satellites[key].position_m for key in healthy]
        labels = list(healthy)
        if self.main_satellites_correlated:
            for key, position in self.main_satellite_positions.items():
                labels.append(key)
                positions.append(position)
        metrics: dict[str, Any] = {
            "healthy_small_satellites": len(healthy),
            "baseline_count": 0,
            "main_satellites_correlated": self.main_satellites_correlated,
            "central_short_baselines_included": self.include_central_short_baselines,
        }
        if len(positions) < 2:
            return [], [], metrics
        baselines, indices = baseline_vectors(positions, return_indices=True)
        if self.formation == "y" and not self.include_central_short_baselines:
            # generate_formation places the single-dish-like central element at
            # index zero.  Its short baselines are excluded by default.
            keep = (indices[:, 0] != 0) & (indices[:, 1] != 0)
            baselines = baselines[keep]
        if len(baselines) == 0:
            return [], [], metrics
        event_frequency = self.frequency_hz
        if self.mode is ObservationMode.FIXED_SOURCE:
            active = self.active_events()
            if active:
                event_frequency = active[0].frequency
        uvw, uv = project_baselines(baselines, event_frequency, self.source_unit)
        del uvw
        limit = max(1.0, float(abs(uv[:, :2]).max()) * 1.05)
        beam, beam_metrics = dirty_beam(
            uv,
            image_size=self.image_size,
            max_uv_lambda=limit,
            backend="numpy",
            return_metrics=True,
        )
        metrics.update(beam_metrics)
        metrics["frequency_hz"] = event_frequency
        metrics["elements"] = labels
        return uv[:, :2].tolist(), beam.tolist(), metrics

    def snapshot(self, *, leader_id: str = "", leader_epoch: int | None = None) -> dict[str, Any]:
        uv_points, psf, metrics = self.uv_and_psf()
        return {
            "time_s": self.time_s,
            "leader": {
                "id": leader_id,
                "epoch": self.epoch if leader_epoch is None else leader_epoch,
            },
            "mode": self.mode.value,
            "plan_version": self.plan_version,
            "small_satellites": [
                {
                    "id": satellite.satellite_id,
                    "health": satellite.health.value,
                    "position_m": list(satellite.position_m),
                    "task_state": satellite.task_state,
                }
                for satellite in self.satellites.values()
            ],
            "uv_points": uv_points,
            "psf": psf,
            "metrics": metrics,
            "events": [dict(event) for event in self.audit_log],
        }

    def audit(self, message: str) -> None:
        sequence = self.audit_log[-1]["seq"] + 1 if self.audit_log else 1
        self.audit_log.append({"seq": sequence, "message": str(message)})
        if len(self.audit_log) > 500:
            del self.audit_log[:-500]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "mode": self.mode.value,
            "events": [event.to_dict() for event in self.events.values()],
            "plans": [plan.to_dict() for plan in self.plans],
            "plan_version": self.plan_version,
            "epoch": self.epoch,
            "time_s": self.time_s,
            "formation": self.formation,
            "radius_m": self.radius_m,
            "frequency_hz": self.frequency_hz,
            "source_unit": list(self.source_unit),
            "image_size": self.image_size,
            "seed": self.seed,
            "main_satellites_correlated": self.main_satellites_correlated,
            "include_central_short_baselines": self.include_central_short_baselines,
            "main_satellite_positions": {
                key: list(value) for key, value in self.main_satellite_positions.items()
            },
            "small_satellites": [value.to_dict() for value in self.satellites.values()],
            "audit_log": self.audit_log,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Coordinator:
        if int(value.get("schema_version", 1)) != 1:
            raise ValueError("unsupported coordinator snapshot schema")
        satellites = [SatelliteView.from_dict(item) for item in value["small_satellites"]]
        coordinator = cls(
            [satellite.satellite_id for satellite in satellites],
            formation=str(value["formation"]),
            radius_m=float(value["radius_m"]),
            frequency_hz=float(value["frequency_hz"]),
            source_unit=value["source_unit"],
            image_size=int(value["image_size"]),
            seed=int(value["seed"]),
            main_satellites_correlated=bool(value["main_satellites_correlated"]),
            include_central_short_baselines=bool(value["include_central_short_baselines"]),
            main_satellite_positions=value.get("main_satellite_positions", {}),
        )
        coordinator.mode = ObservationMode(value["mode"])
        coordinator.events = {
            item["event_id"]: ScienceEvent.from_dict(item) for item in value.get("events", [])
        }
        coordinator.plans = [PlanRevision.from_dict(item) for item in value.get("plans", [])]
        coordinator.plan_version = int(value["plan_version"])
        coordinator.epoch = int(value["epoch"])
        coordinator.time_s = float(value["time_s"])
        coordinator.satellites = {item.satellite_id: item for item in satellites}
        coordinator.audit_log = [dict(item) for item in value.get("audit_log", [])]
        if coordinator.current_plan and coordinator.current_plan.plan_version != coordinator.plan_version:
            raise ValueError("latest plan does not match plan_version")
        return coordinator

    @classmethod
    def from_json(cls, payload: str) -> Coordinator:
        return cls.from_dict(json.loads(payload))


def _position(value: Sequence[float]) -> tuple[float, float, float]:
    if len(value) != 3:
        raise ValueError("a position must contain exactly three coordinates")
    result = tuple(float(item) for item in value)
    if not all(math.isfinite(item) for item in result):
        raise ValueError("position coordinates must be finite")
    return result


def _command_dict(command: Command) -> dict[str, Any]:
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
