from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from multi_star.satellite import (  # noqa: E402
    Command,
    CommandKind,
    HealthState,
    SmallSatellite,
    TaskState,
)


class SmallSatelliteTest(unittest.TestCase):
    def setUp(self) -> None:
        self.satellite = SmallSatellite(
            "small-01",
            delta_v_mps=20.0,
            storage_bytes=1_000,
            minimum_separation_m=50.0,
            neighbor_targets_m={"small-02": (100.0, 0.0, 0.0)},
        )

    def command(
        self,
        command_id: str,
        *,
        satellite_id: str = "small-01",
        epoch: int = 1,
        plan_version: int = 1,
        kind: CommandKind | str = CommandKind.OBSERVATION,
        not_before: float = 0.0,
        expires_at: float = 100.0,
        duration_s: float = 0.0,
        target_position_m=None,
        delta_v_cost_mps: float = 0.0,
        data_bytes: int = 100,
    ) -> Command:
        return Command(
            command_id=command_id,
            satellite_id=satellite_id,
            epoch=epoch,
            plan_version=plan_version,
            kind=kind,
            not_before=not_before,
            expires_at=expires_at,
            duration_s=duration_s,
            target_position_m=target_position_m,
            delta_v_cost_mps=delta_v_cost_mps,
            data_bytes=data_bytes,
        )

    def test_recipient_epoch_and_plan_fencing(self) -> None:
        wrong = self.satellite.receive_command(
            self.command("wrong", satellite_id="small-02")
        )
        self.assertFalse(wrong.accepted)
        self.assertIn("another satellite", wrong.reason)

        self.assertTrue(self.satellite.receive_command(self.command("new", epoch=2)).accepted)
        stale_epoch = self.satellite.receive_command(self.command("old", epoch=1))
        self.assertEqual(stale_epoch.state, TaskState.REJECTED)
        self.assertIn("epoch", stale_epoch.reason)

        stale_plan = self.satellite.receive_command(
            self.command("old-plan", epoch=2, plan_version=0)
        )
        self.assertFalse(stale_plan.accepted)
        self.assertIn("plan", stale_plan.reason)

    def test_duplicate_transfer_has_no_second_effect(self) -> None:
        command = self.command(
            "move",
            kind="transfer",
            target_position_m=(200.0, 0.0, 0.0),
            delta_v_cost_mps=5.0,
        )
        self.assertTrue(self.satellite.receive_command(command).accepted)
        self.satellite.advance(0.0)
        self.assertEqual(self.satellite.delta_v_remaining_mps, 15.0)
        self.assertEqual(self.satellite.position_m, (200.0, 0.0, 0.0))

        duplicate = self.satellite.receive_command(command)
        self.assertTrue(duplicate.duplicate)
        self.assertTrue(duplicate.accepted)
        self.assertEqual(duplicate.state, TaskState.COMPLETED)
        self.satellite.advance(1.0)
        self.assertEqual(self.satellite.delta_v_remaining_mps, 15.0)

    def test_time_window_and_complete_state_flow(self) -> None:
        command = self.command(
            "windowed", not_before=10.0, expires_at=30.0, duration_s=5.0
        )
        receipt = self.satellite.receive_command(command)
        self.assertEqual(receipt.state, TaskState.ACCEPTED)
        self.satellite.advance(5.0)
        self.assertEqual(self.satellite.tasks[command.command_id].state, TaskState.ACCEPTED)
        self.satellite.advance(10.0)
        self.assertEqual(self.satellite.tasks[command.command_id].state, TaskState.STARTED)
        self.satellite.advance(14.0)
        self.assertEqual(self.satellite.tasks[command.command_id].state, TaskState.STARTED)
        self.satellite.advance(15.0)
        self.assertEqual(self.satellite.tasks[command.command_id].state, TaskState.COMPLETED)
        self.assertEqual(self.satellite.storage_remaining_bytes, 900)

        verified = self.satellite.verify(command.command_id)
        self.assertTrue(verified.accepted)
        self.assertEqual(verified.state, TaskState.VERIFIED)
        self.assertFalse(self.satellite.verify(command.command_id).accepted)

    def test_advance_can_cross_start_and_completion_in_one_step(self) -> None:
        command = self.command(
            "jump", not_before=5.0, expires_at=20.0, duration_s=2.0
        )
        self.satellite.receive_command(command)
        self.satellite.advance(7.0)
        task = self.satellite.tasks[command.command_id]
        self.assertEqual(task.state, TaskState.COMPLETED)
        self.assertEqual(task.started_at, 5.0)
        self.assertEqual(task.completed_at, 7.0)
        self.assertEqual(self.satellite.storage_remaining_bytes, 900)

    def test_expired_and_never_started_commands_are_rejected(self) -> None:
        expired = self.satellite.receive_command(
            self.command("expired", not_before=0.0, expires_at=5.0), sim_time_s=5.0
        )
        self.assertFalse(expired.accepted)
        self.assertIn("expired", expired.reason)

        future = self.command("too-late", not_before=10.0, expires_at=10.0)
        self.assertTrue(self.satellite.receive_command(future, sim_time_s=6.0).accepted)
        self.satellite.advance(10.0)
        self.assertEqual(self.satellite.tasks[future.command_id].state, TaskState.REJECTED)
        self.assertEqual(self.satellite.storage_remaining_bytes, 1_000)

    def test_transfer_resources_and_all_neighbor_separations(self) -> None:
        self.satellite.set_neighbor_target("small-03", (300.0, 0.0, 0.0))
        insufficient = self.satellite.receive_command(
            self.command(
                "fuel",
                kind=CommandKind.TRANSFER,
                target_position_m=(200.0, 0.0, 0.0),
                delta_v_cost_mps=21.0,
            )
        )
        self.assertFalse(insufficient.accepted)
        self.assertIn("delta-v", insufficient.reason)

        for command_id, target in (
            ("near-02", (120.0, 0.0, 0.0)),
            ("near-03", (280.0, 0.0, 0.0)),
        ):
            with self.subTest(command_id=command_id):
                receipt = self.satellite.receive_command(
                    self.command(
                        command_id,
                        kind=CommandKind.TRANSFER,
                        target_position_m=target,
                        delta_v_cost_mps=1.0,
                    )
                )
                self.assertFalse(receipt.accepted)
                self.assertIn("separation", receipt.reason)

        no_storage = self.satellite.receive_command(
            self.command("storage", data_bytes=1_001)
        )
        self.assertFalse(no_storage.accepted)
        self.assertIn("storage", no_storage.reason)

    def test_single_current_command_and_safe_mode_preemption(self) -> None:
        move = self.command(
            "move",
            kind=CommandKind.TRANSFER,
            target_position_m=(200.0, 0.0, 0.0),
            delta_v_cost_mps=5.0,
            duration_s=10.0,
        )
        self.satellite.receive_command(move)
        self.satellite.advance(0.0)
        busy = self.satellite.receive_command(self.command("other", epoch=2))
        self.assertFalse(busy.accepted)
        self.assertIn("active", busy.reason)

        safe = self.satellite.receive_command(
            self.command("safe", epoch=3, kind=CommandKind.SAFE_MODE, data_bytes=0)
        )
        self.assertTrue(safe.accepted)
        self.assertEqual(self.satellite.tasks[move.command_id].state, TaskState.UNKNOWN)
        self.assertEqual(self.satellite.health, HealthState.SAFE)
        self.satellite.advance(0.0)
        self.assertEqual(self.satellite.tasks["safe"].state, TaskState.COMPLETED)
        rejected = self.satellite.receive_command(self.command("after-safe", epoch=4))
        self.assertFalse(rejected.accepted)
        self.assertIn("SAFE", rejected.reason)

    def test_upload_releases_storage_only_after_verification(self) -> None:
        observation = self.command("observe", data_bytes=400)
        self.satellite.receive_command(observation)
        self.satellite.advance(0.0)
        self.assertEqual(self.satellite.storage_remaining_bytes, 600)

        duplicate_observation = self.satellite.receive_command(observation)
        self.assertTrue(duplicate_observation.duplicate)
        self.assertEqual(self.satellite.storage_remaining_bytes, 600)

        upload = self.command(
            "upload", epoch=2, kind=CommandKind.UPLOAD, data_bytes=400
        )
        self.satellite.receive_command(upload)
        self.satellite.advance(1.0)
        self.assertEqual(self.satellite.tasks[upload.command_id].state, TaskState.COMPLETED)
        self.assertEqual(self.satellite.storage_remaining_bytes, 600)

        self.assertTrue(self.satellite.verify(upload.command_id).accepted)
        self.assertEqual(self.satellite.storage_remaining_bytes, 1_000)
        second_verify = self.satellite.verify(upload.command_id)
        self.assertFalse(second_verify.accepted)
        self.assertEqual(self.satellite.storage_remaining_bytes, 1_000)

        duplicate_upload = self.satellite.receive_command(upload)
        self.assertTrue(duplicate_upload.duplicate)
        self.assertEqual(self.satellite.storage_remaining_bytes, 1_000)

    def test_failure_survives_snapshot_restore(self) -> None:
        command = self.command("in-flight", duration_s=10.0)
        self.satellite.receive_command(command)
        self.satellite.advance(0.0)
        self.satellite.fail()
        self.assertEqual(self.satellite.health, HealthState.FAILED)
        self.assertEqual(self.satellite.tasks[command.command_id].state, TaskState.UNKNOWN)

        restored = SmallSatellite.restore(self.satellite.snapshot())
        self.assertEqual(restored.health, HealthState.FAILED)
        self.assertEqual(restored.tasks[command.command_id].state, TaskState.UNKNOWN)
        self.assertEqual(restored.highest_epoch, 1)
        self.assertEqual(restored.storage_remaining_bytes, 1_000)
        restored.advance(20.0)
        self.assertEqual(restored.tasks[command.command_id].state, TaskState.UNKNOWN)
        rejected = restored.receive_command(self.command("new", epoch=2))
        self.assertFalse(rejected.accepted)
        self.assertIn("FAILED", rejected.reason)
        restored.recover()
        self.assertEqual(restored.health, HealthState.NOMINAL)
        self.assertEqual(restored.tasks[command.command_id].state, TaskState.UNKNOWN)

    def test_snapshot_restores_position_resources_history_and_clock(self) -> None:
        move = self.command(
            "move",
            kind=CommandKind.TRANSFER,
            target_position_m=(200.0, 0.0, 0.0),
            delta_v_cost_mps=5.0,
        )
        self.satellite.receive_command(move)
        self.satellite.advance(0.0)
        future = self.command("future", epoch=2, not_before=10.0, duration_s=2.0)
        self.satellite.receive_command(future, sim_time_s=1.0)

        restored = SmallSatellite.restore(self.satellite.snapshot())
        self.assertEqual(restored.position_m, (200.0, 0.0, 0.0))
        self.assertEqual(restored.delta_v_remaining_mps, 15.0)
        self.assertEqual(restored.highest_epoch, 2)
        self.assertEqual(restored.sim_time_s, 1.0)
        self.assertTrue(restored.receive_command(move).duplicate)
        restored.advance(10.0)
        self.assertEqual(restored.tasks[future.command_id].state, TaskState.STARTED)
        restored.advance(12.0)
        self.assertEqual(restored.tasks[future.command_id].state, TaskState.COMPLETED)
        self.assertEqual(restored.storage_remaining_bytes, 900)
        self.assertEqual(json.loads(restored.snapshot())["health"], "nominal")

    def test_verify_rejects_unknown_and_non_completed_tasks(self) -> None:
        unknown = self.satellite.verify("missing")
        self.assertFalse(unknown.accepted)
        self.assertEqual(unknown.state, TaskState.UNKNOWN)
        self.assertTrue(unknown.reason)

        command = self.command("pending", not_before=10.0)
        self.satellite.receive_command(command)
        pending = self.satellite.verify(command.command_id)
        self.assertFalse(pending.accepted)
        self.assertEqual(pending.state, TaskState.ACCEPTED)
        self.assertEqual(self.satellite.tasks[command.command_id].state, TaskState.ACCEPTED)


if __name__ == "__main__":
    unittest.main()
