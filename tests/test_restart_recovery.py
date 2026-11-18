import importlib.util
import unittest
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "scripts" / "reconcile_unknown_pods.py"
SPEC = importlib.util.spec_from_file_location("restart_recovery", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RestartRecoveryTest(unittest.TestCase):
    def test_only_unknown_or_nodelost_pods_are_selected(self):
        document = {"items": [
            {"metadata": {"name": "unknown"}, "status": {"phase": "Unknown"}},
            {"metadata": {"name": "lost"}, "status": {"phase": "Running", "reason": "NodeLost"}},
            {"metadata": {"name": "starting"}, "status": {"phase": "Running"}},
            {"metadata": {"name": "done"}, "status": {"phase": "Succeeded"}},
        ]}
        self.assertEqual(MODULE.unknown_pod_names(document), ["lost", "unknown"])


if __name__ == "__main__":
    unittest.main()
