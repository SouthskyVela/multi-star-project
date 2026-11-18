from __future__ import annotations

import json
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import Mock
from dataclasses import FrozenInstanceError

from multi_star.coordinator import Coordinator, ObservationMode, ScienceEvent
from multi_star.lease import LeaseState, _format_rfc3339
from multi_star.main_satellite_service import MainSatelliteServer, _event_from_request, _event_from_request
from multi_star.satellite import Command, CommandKind, HealthState, TaskState


def event(event_id="event-1", **changes):
    values = {
        "event_id": event_id,
        "target": "target-a",
        "frequency": 120_000_000.0,
        "flux": 2.5,
        "confidence": 0.9,
        "expiry": 100.0,
        "priority": 1.0,
    }
    values.update(changes)
    return ScienceEvent(**values)


class CoordinatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.coordinator = Coordinator(image_size=16)

    def test_event_deduplication_expiry_priority_and_immutability(self) -> None:
        self.assertTrue(self.coordinator.add_event(event()))
        self.assertFalse(self.coordinator.add_event(event(event_id="event-1", flux=999)))
        self.assertEqual(len(self.coordinator.events), 1)
        with self.assertRaises(FrozenInstanceError):
            self.coordinator.events["event-1"].flux = 4.0
        with self.assertRaises(ValueError):
            self.coordinator.add_event(event("expired", expiry=0.0))
        self.coordinator.add_event(event("event-2", priority=2.0))
        self.assertEqual(self.coordinator.active_events()[0].event_id, "event-2")
        dashboard_event = ScienceEvent.from_dict({
            "event_id": "dashboard-1", "target_id": "target-b",
            "frequency_hz": 100.0, "flux_jy": 1.5, "confidence": 0.8,
            "spectral_index": -0.7, "expiry_s": 200.0,
        })
        self.assertEqual(dashboard_event.target, "target-b")
        self.assertEqual(dashboard_event.frequency, 100.0)
        self.assertEqual(dashboard_event.spectral_index, -0.7)
        mapped = _event_from_request({
            "event_id": "dashboard-2", "target_id": "target-c",
            "frequency_hz": 100.0, "flux_jy": 1.5, "confidence": 0.8,
            "spectral_index": -0.7, "expiry_s": 30.0,
        }, now_s=12.0)
        self.assertEqual(mapped.expiry, 42.0)
        self.assertEqual(mapped.observed_at, 12.0)
        with self.assertRaises(ValueError):
            _event_from_request({
                "event_id": "bad", "target_id": "target-c", "frequency_hz": 100.0,
                "flux_jy": 1.5, "confidence": 0.8, "expiry_s": 0.0,
            }, now_s=12.0)

    def test_mode_preconditions_and_atomic_version_increment(self) -> None:
        with self.assertRaises(ValueError):
            self.coordinator.switch_mode("not-a-mode")
        with self.assertRaises(ValueError):
            self.coordinator.switch_mode(ObservationMode.FIXED_SOURCE)
        self.assertEqual(self.coordinator.plan_version, 0)
        self.assertIsNone(self.coordinator.current_plan)

        self.coordinator.add_event(event())
        plan = self.coordinator.switch_mode("fixed_source", event_id="event-1")
        self.assertEqual(self.coordinator.mode, ObservationMode.FIXED_SOURCE)
        self.assertEqual(plan.parent_version, 0)
        self.assertEqual(plan.plan_version, 1)
        self.assertEqual(plan.event_ids, ("event-1",))
        calibration = self.coordinator.switch_mode("CALIBRATION")
        self.assertEqual(calibration.parent_version, 1)
        self.assertEqual(self.coordinator.plan_version, 2)
        with self.assertRaises(ValueError):
            self.coordinator.switch_mode("SURVEY", event_id="event-1")
        self.assertEqual(self.coordinator.plan_version, 2)

    def test_fault_replan_excludes_failed_and_never_reissues_unknown_transfer(self) -> None:
        self.coordinator.replan(reason="test initial")
        failed = self.coordinator.satellites["small-sat-2"]
        last_position = failed.position_m
        failed.health = HealthState.FAILED
        unknown = self.coordinator.satellites["small-sat-1"]
        command = Command(
            command_id="ambiguous-transfer",
            satellite_id=unknown.satellite_id,
            epoch=0,
            plan_version=1,
            kind=CommandKind.TRANSFER,
            not_before=0,
            expires_at=100,
            duration_s=5,
            target_position_m=(1, 2, 3),
        )
        self.coordinator.record_command_state(command, TaskState.UNKNOWN)
        plan = self.coordinator.replan(reason="fault test")
        self.assertNotIn("small-sat-2", plan.assignments)
        self.assertNotIn("small-sat-1", plan.assignments)
        self.assertEqual(failed.position_m, last_position)
        self.assertNotIn(command, self.coordinator.pending_commands())
        self.assertNotIn("small-sat-2", self.coordinator.healthy_satellite_ids)
        self.assertEqual(plan.plan_version, 2)

    def test_completed_observation_generates_one_upload_in_same_revision(self) -> None:
        plan = self.coordinator.replan(reason="observation upload test")
        observation = Command(**plan.assignments["small-sat-0"])
        self.assertEqual(observation.kind, CommandKind.OBSERVATION)
        self.coordinator.record_command_state(observation, TaskState.COMPLETED)

        pending = [
            command for command in self.coordinator.pending_commands()
            if command.satellite_id == observation.satellite_id
        ]
        self.assertEqual(len(pending), 1)
        upload = pending[0]
        self.assertEqual(upload.kind, CommandKind.UPLOAD)
        self.assertEqual(upload.command_id, observation.command_id + "-upload")
        self.assertEqual(upload.epoch, observation.epoch)
        self.assertEqual(upload.plan_version, observation.plan_version)
        self.assertEqual(upload.data_bytes, observation.data_bytes)

        self.coordinator.record_command_state(upload, TaskState.ACCEPTED)
        self.assertNotIn(upload, self.coordinator.pending_commands())
        self.coordinator.record_command_state(upload, TaskState.COMPLETED)
        self.coordinator.record_command_state(upload, TaskState.VERIFIED)
        self.assertNotIn(upload, self.coordinator.pending_commands())
        self.assertEqual(self.coordinator.plan_version, plan.plan_version)

    def test_shared_state_round_trip_and_snapshot_schema(self) -> None:
        self.coordinator.add_event(event())
        self.coordinator.switch_mode("FIXED_SOURCE")
        restored = Coordinator.from_json(self.coordinator.to_json())
        self.assertEqual(restored.to_dict(), self.coordinator.to_dict())
        snapshot = restored.snapshot(leader_id="main-sat-0", leader_epoch=3)
        self.assertEqual(
            set(snapshot),
            {
                "time_s", "leader", "mode", "plan_version", "small_satellites",
                "uv_points", "psf", "metrics", "events",
            },
        )
        self.assertEqual(snapshot["leader"], {"id": "main-sat-0", "epoch": 3})
        self.assertEqual(len(snapshot["small_satellites"]), 9)
        self.assertEqual(
            set(snapshot["small_satellites"][0]),
            {"id", "health", "position_m", "task_state"},
        )
        self.assertTrue(all(set(item) == {"seq", "message"} for item in snapshot["events"]))
        json.dumps(snapshot)
        self.assertEqual(snapshot["metrics"]["baseline_count"], 36)
        self.assertFalse(snapshot["metrics"]["main_satellites_correlated"])

    def test_observation_completion_creates_one_idempotent_upload(self) -> None:
        self.coordinator.set_epoch(1)
        self.coordinator.replan(reason="upload test")
        original = Command(**self.coordinator.current_plan.assignments["small-sat-0"])
        self.assertEqual(original.kind, CommandKind.OBSERVATION)
        self.coordinator.record_command_state(original, TaskState.COMPLETED)
        uploads = [
            command for command in self.coordinator.pending_commands()
            if command.kind is CommandKind.UPLOAD
        ]
        self.assertEqual(len(uploads), 1)
        upload = uploads[0]
        self.assertEqual(upload.command_id, original.command_id + "-upload")
        self.assertEqual(upload.data_bytes, original.data_bytes)
        self.coordinator.record_command_state(upload, TaskState.ACCEPTED)
        self.assertNotIn(upload, self.coordinator.pending_commands())

    def test_dashboard_expiry_is_a_relative_duration(self) -> None:
        mapped = _event_from_request({
            "event_id": "relative", "target_id": "target-b",
            "frequency_hz": 140.0, "flux_jy": 2.0, "confidence": 0.9,
            "spectral_index": -0.7, "expiry_s": 50.0,
        }, 100.0)
        self.assertEqual(mapped.expiry, 150.0)
        self.assertEqual(mapped.observed_at, 100.0)
        self.assertEqual(mapped.spectral_index, -0.7)
        with self.assertRaises(ValueError):
            _event_from_request({
                "event_id": "bad", "target_id": "t", "frequency_hz": 1.0,
                "flux_jy": 1.0, "confidence": 0.5, "expiry_s": 0.0,
            }, 100.0)


class EmptyStore:
    def load(self):
        return None

    def save(self, state):
        return None


class EmptySmallSatellites:
    satellite_ids = []


class NonLeaderLease:
    identity = "main-sat-1"
    namespace = "multi-star"

    def __init__(self):
        self.state = LeaseState("main-sat-0", _format_rfc3339(0), 15, 0, "1")
        self.can_issue_commands = False


class LeaderLease(NonLeaderLease):
    def __init__(self):
        super().__init__()
        self.state = LeaseState(self.identity, _format_rfc3339(0), 15, 0, "1")
        self.can_issue_commands = True


class MainServiceSnapshotTest(unittest.TestCase):
    def test_entrypoint_is_after_helper_definitions(self):
        source = (Path(__file__).resolve().parents[1] / "src" / "multi_star" / "main_satellite_service.py").read_text(encoding="utf-8")
        self.assertGreater(source.rindex('if __name__ == "__main__":'), source.index("def _command_dict"))
        self.assertGreater(source.rindex('if __name__ == "__main__":'), source.index("def _event_from_request"))

    def test_election_iteration_never_runs_scheduler_inline(self):
        server = MainSatelliteServer(
            ("127.0.0.1", 0), Coordinator(image_size=16), LeaderLease(),
            EmptyStore(), EmptySmallSatellites(),
        )
        try:
            server._leader_tick = Mock()
            server.lease.resume = Mock()
            server.lease.acquire_or_renew = Mock(return_value=server.lease.state)
            server._set_active_label = Mock()
            server._iteration()
            server._leader_tick.assert_not_called()
        finally:
            server.server_close()

    def test_event_request_enters_fixed_source_and_duplicate_keeps_plan_version(self):
        coordinator = Coordinator(image_size=16)
        coordinator.advance_time(7.0)
        server = MainSatelliteServer(
            ("127.0.0.1", 0), coordinator, LeaderLease(), EmptyStore(), EmptySmallSatellites()
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        body = {
            "event_id": "dashboard-event", "target_id": "target-a",
            "frequency_hz": 120_000_000.0, "flux_jy": 2.5, "confidence": 0.9,
            "spectral_index": -0.5, "expiry_s": 20.0,
        }
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/events"
            request = urllib.request.Request(
                url, data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                first = json.load(response)
            self.assertTrue(first["accepted"])
            self.assertEqual(first["plan_version"], 1)
            stored = server.coordinator.events["dashboard-event"]
            self.assertEqual(stored.expiry, 27.0)
            self.assertEqual(stored.observed_at, 7.0)
            self.assertEqual(stored.spectral_index, -0.5)
            self.assertEqual(server.coordinator.mode, ObservationMode.FIXED_SOURCE)
            self.assertEqual(server.coordinator.current_plan.event_ids, ("dashboard-event",))

            with urllib.request.urlopen(request, timeout=5) as response:
                duplicate = json.load(response)
            self.assertTrue(duplicate["duplicate"])
            self.assertEqual(duplicate["plan_version"], 1)
            self.assertEqual(server.coordinator.plan_version, 1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_snapshot_endpoint_and_readiness_do_not_require_leadership(self):
        server = MainSatelliteServer(
            ("127.0.0.1", 0),
            Coordinator(image_size=16),
            NonLeaderLease(),
            EmptyStore(),
            EmptySmallSatellites(),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urllib.request.urlopen(base + "/readyz", timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertTrue(json.load(response)["ready"])
            with urllib.request.urlopen(base + "/api/snapshot", timeout=5) as response:
                snapshot = json.load(response)
            self.assertEqual(snapshot["leader"]["id"], "main-sat-0")
            self.assertIn("uv_points", snapshot)
            self.assertIn("events", snapshot)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_new_event_automatically_enters_fixed_source_and_deduplicates(self):
        lease = NonLeaderLease()
        lease.can_issue_commands = True
        server = MainSatelliteServer(
            ("127.0.0.1", 0), Coordinator(image_size=16), lease,
            EmptyStore(), EmptySmallSatellites(),
        )
        try:
            added, version = server.submit_event(event("automatic-source"))
            self.assertTrue(added)
            self.assertEqual(server.coordinator.mode, ObservationMode.FIXED_SOURCE)
            self.assertEqual(server.coordinator.current_plan.event_ids, ("automatic-source",))
            duplicate, duplicate_version = server.submit_event(event("automatic-source"))
            self.assertFalse(duplicate)
            self.assertEqual(duplicate_version, version)
        finally:
            server.server_close()


if __name__ == "__main__":
    unittest.main()
