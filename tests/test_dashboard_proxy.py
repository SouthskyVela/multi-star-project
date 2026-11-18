import unittest

from multi_star.dashboard_proxy import choose_leader, small_satellite_base


class LeaderChoiceTest(unittest.TestCase):
    def test_single_ready_leader_wins(self):
        self.assertEqual(choose_leader([
            {"id": "main-sat-0", "ready": True, "leader": False, "epoch": 3},
            {"id": "main-sat-1", "ready": True, "leader": True, "epoch": 4},
        ]), "main-sat-1")

    def test_no_leader_and_equal_epoch_conflict_fail_closed(self):
        with self.assertRaises(RuntimeError):
            choose_leader([])
        with self.assertRaises(RuntimeError):
            choose_leader([
                {"id": "a", "ready": True, "leader": True, "epoch": 2},
                {"id": "b", "ready": True, "leader": True, "epoch": 2},
            ])

    def test_only_highest_epoch_is_accepted(self):
        self.assertEqual(choose_leader([
            {"id": "old", "ready": True, "leader": True, "epoch": 2},
            {"id": "new", "ready": True, "leader": True, "epoch": 3},
        ]), "new")

    def test_small_satellite_fault_target_is_validated(self):
        self.assertIn("small-sat-8.small-sat", small_satellite_base("small-sat-8"))
        for invalid in ("main-sat-0", "small-sat-9", "small-sat-1/../../x"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                small_satellite_base(invalid)


if __name__ == "__main__":
    unittest.main()
