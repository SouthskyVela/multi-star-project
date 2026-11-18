from __future__ import annotations

import copy
import unittest

from multi_star.lease import (
    KubernetesAPIError,
    LeaseConflict,
    LeaseManager,
    _format_rfc3339,
)


class FakeLeaseAPI:
    namespace = "multi-star"

    def __init__(self) -> None:
        self.value = None
        self.revision = 0
        self.fail_with = None
        self.force_conflict = 0

    def request(self, method, path, body=None, **kwargs):
        if self.fail_with is not None:
            raise self.fail_with
        if method == "GET":
            if self.value is None:
                raise KubernetesAPIError(404, "not found")
            return copy.deepcopy(self.value)
        if method == "POST":
            if self.value is not None:
                raise LeaseConflict(409, "already exists")
            self.revision += 1
            self.value = copy.deepcopy(body)
            self.value["metadata"]["resourceVersion"] = str(self.revision)
            return copy.deepcopy(self.value)
        if method == "PUT":
            if self.force_conflict:
                self.force_conflict -= 1
                self.revision += 1
                self.value["metadata"]["resourceVersion"] = str(self.revision)
                raise LeaseConflict(409, "injected conflict")
            if self.value is None:
                raise KubernetesAPIError(404, "not found")
            supplied = body["metadata"].get("resourceVersion")
            current = self.value["metadata"]["resourceVersion"]
            if supplied != current:
                raise LeaseConflict(409, "resourceVersion mismatch")
            self.revision += 1
            self.value = copy.deepcopy(body)
            self.value["metadata"]["resourceVersion"] = str(self.revision)
            return copy.deepcopy(self.value)
        raise AssertionError(method)


class LeaseManagerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.api = FakeLeaseAPI()
        self.now = [1000.0]
        self.lease = LeaseManager(
            "main-sat-0", self.api, duration_seconds=10, clock=lambda: self.now[0]
        )

    def test_get_or_create_and_renew_preserve_epoch(self) -> None:
        state = self.lease.acquire_or_renew()
        self.assertTrue(self.lease.can_issue_commands)
        self.assertEqual(state.holder_identity, "main-sat-0")
        self.assertEqual(state.lease_transitions, 0)
        self.assertEqual(state.epoch, 1)
        self.now[0] += 3
        renewed = self.lease.acquire_or_renew()
        self.assertEqual(renewed.lease_transitions, 0)
        self.assertNotEqual(renewed.renew_time, state.renew_time)

    def test_active_holder_blocks_peer_and_expiry_allows_takeover(self) -> None:
        self.lease.acquire_or_renew()
        peer = LeaseManager(
            "main-sat-1", self.api, duration_seconds=10, clock=lambda: self.now[0]
        )
        observed = peer.acquire_or_renew()
        self.assertEqual(observed.holder_identity, "main-sat-0")
        self.assertFalse(peer.can_issue_commands)
        self.now[0] += 10
        takeover = peer.acquire_or_renew()
        self.assertTrue(peer.can_issue_commands)
        self.assertEqual(takeover.lease_transitions, 1)
        self.assertEqual(takeover.epoch, 2)

    def test_resource_version_conflict_is_retried(self) -> None:
        self.lease.acquire_or_renew()
        self.api.force_conflict = 1
        state = self.lease.acquire_or_renew()
        self.assertTrue(self.lease.can_issue_commands)
        self.assertEqual(state.resource_version, "3")

    def test_exhausted_conflict_and_renewal_failure_fence_commands(self) -> None:
        self.lease.acquire_or_renew()
        self.lease.max_attempts = 1
        self.api.force_conflict = 1
        with self.assertRaises(LeaseConflict):
            self.lease.acquire_or_renew()
        self.assertFalse(self.lease.can_issue_commands)

        self.lease.max_attempts = 3
        self.api.fail_with = KubernetesAPIError(503, "API unavailable")
        with self.assertRaises(KubernetesAPIError):
            self.lease.acquire_or_renew()
        self.assertFalse(self.lease.can_issue_commands)

    def test_suspend_immediately_stops_commands(self) -> None:
        self.lease.acquire_or_renew()
        self.lease.suspend()
        self.assertFalse(self.lease.can_issue_commands)
        with self.assertRaises(RuntimeError):
            self.lease.acquire_or_renew()
        self.lease.resume()
        self.assertFalse(self.lease.can_issue_commands)
        self.lease.acquire_or_renew()
        self.assertTrue(self.lease.can_issue_commands)

    def test_expiry_uses_lease_renew_time(self) -> None:
        state = self.lease.acquire_or_renew()
        self.assertEqual(state.renew_time, _format_rfc3339(1000.0))
        self.assertTrue(state.is_expired(1010.0))
        self.now[0] = 1010.0
        self.assertFalse(self.lease.can_issue_commands)


if __name__ == "__main__":
    unittest.main()
