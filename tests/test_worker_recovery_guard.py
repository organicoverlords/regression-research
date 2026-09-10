import sys
import unittest
from unittest.mock import patch

from tools.stack_atlas import CANONICAL_RECURRING_WORKER_PARTITIONS
from tools.worker_recovery_guard import (
    authorize_recovery,
    authorize_supervising_chat_recovery,
    main,
)


class WorkerRecoveryGuardTests(unittest.TestCase):
    def setUp(self):
        self.s1 = CANONICAL_RECURRING_WORKER_PARTITIONS["S1"]
        self.s2 = CANONICAL_RECURRING_WORKER_PARTITIONS["S2"]

    def _watch(self, *, actor_id, candidates):
        partition = next(
            name
            for name, workers in CANONICAL_RECURRING_WORKER_PARTITIONS.items()
            if actor_id in {worker_id for worker_id, _ in workers}
        )
        return {
            "status": "SUSPECT_DEGRADED" if candidates else "CURRENT_LOCAL_EVIDENCE",
            "authority": "local_worker_reports_and_machine_start_receipts",
            "subscription_scope": partition,
            "recovery_candidates": candidates,
        }

    def test_rejects_cross_partition_target_without_fleet_read(self):
        actor = self.s2[0][0]
        target = self.s1[0][0]
        called = False

        def fleet_watch(**_kwargs):
            nonlocal called
            called = True
            return {}

        result = authorize_recovery(actor, target, fleet_watch=fleet_watch)
        self.assertFalse(result["authorized"])
        self.assertEqual(result["reason"], "CROSS_PARTITION_RECOVERY_FORBIDDEN")
        self.assertFalse(called)

    def test_rejects_self_administration_without_fleet_read(self):
        actor = self.s2[0][0]
        called = False

        def fleet_watch(**_kwargs):
            nonlocal called
            called = True
            return {}

        result = authorize_recovery(actor, actor, fleet_watch=fleet_watch)
        self.assertFalse(result["authorized"])
        self.assertEqual(result["reason"], "SELF_ADMINISTRATION_FORBIDDEN")
        self.assertFalse(called)

    def test_rejects_same_partition_target_not_in_recovery_candidates(self):
        actor = self.s2[0][0]
        target = self.s2[1][0]

        result = authorize_recovery(
            actor,
            target,
            fleet_watch=lambda **_kwargs: self._watch(actor_id=actor, candidates=[]),
        )
        self.assertFalse(result["authorized"])
        self.assertEqual(result["reason"], "TARGET_NOT_ACTIONABLE")

    def test_rejects_actor_scoped_watch_mismatch(self):
        actor = self.s2[0][0]
        target = self.s2[1][0]
        result = authorize_recovery(
            actor,
            target,
            fleet_watch=lambda **_kwargs: {
                "status": "SUSPECT_DEGRADED",
                "authority": "local_worker_reports_and_machine_start_receipts",
                "subscription_scope": "S1",
                "recovery_candidates": [],
            },
        )
        self.assertFalse(result["authorized"])
        self.assertEqual(result["reason"], "FLEET_WATCH_SCOPE_MISMATCH")

    def test_authorizes_only_exact_same_partition_actionable_target(self):
        actor = self.s2[0][0]
        target = self.s2[1][0]
        candidate = {
            "automation_id": target,
            "subscription_partition": "S2",
            "reason": "MISSED_EXPECTED_HOURLY_CADENCE",
        }
        calls = []

        def fleet_watch(**kwargs):
            calls.append(kwargs)
            return self._watch(actor_id=actor, candidates=[candidate])

        result = authorize_recovery(actor, target, fleet_watch=fleet_watch)
        self.assertTrue(result["authorized"])
        self.assertEqual(calls, [{"worker_id": actor}])
        self.assertEqual(result["actor_partition"], "S2")
        self.assertEqual(result["target_partition"], "S2")
        self.assertEqual(result["scheduler_action"], {"operation": "set_is_enabled", "is_enabled": True})
        self.assertEqual(result["reason"], "MISSED_EXPECTED_HOURLY_CADENCE")

    def test_rejects_candidate_partition_mismatch_even_if_target_id_matches(self):
        actor = self.s2[0][0]
        target = self.s2[1][0]
        candidate = {
            "automation_id": target,
            "subscription_partition": "S1",
            "reason": "NO_LOCAL_START_EVIDENCE",
        }
        result = authorize_recovery(
            actor,
            target,
            fleet_watch=lambda **_kwargs: self._watch(actor_id=actor, candidates=[candidate]),
        )
        self.assertFalse(result["authorized"])
        self.assertEqual(result["reason"], "CANDIDATE_PARTITION_MISMATCH")


    def test_supervising_chat_authorizes_exact_actionable_partition_target(self):
        target = self.s2[1][0]
        candidate = {
            "automation_id": target,
            "subscription_partition": "S2",
            "reason": "MISSED_EXPECTED_HOURLY_CADENCE",
        }
        calls = []

        def fleet_watch(**kwargs):
            calls.append(kwargs)
            return {
                "status": "SUSPECT_DEGRADED",
                "authority": "local_worker_reports_and_machine_start_receipts",
                "subscription_scope": "S2",
                "recovery_candidates": [candidate],
            }

        result = authorize_supervising_chat_recovery("S2", target, fleet_watch=fleet_watch)
        self.assertTrue(result["authorized"])
        self.assertEqual(calls, [{"partition": "S2"}])
        self.assertEqual(result["actor_mode"], "supervising_chat")
        self.assertNotIn("actor_worker_id", result)
        self.assertEqual(result["supervising_chat_partition"], "S2")
        self.assertEqual(result["target_partition"], "S2")
        self.assertEqual(result["scheduler_action"], {"operation": "set_is_enabled", "is_enabled": True})
        self.assertEqual(result["scheduler_probe"], "not_performed")

    def test_supervising_chat_rejects_cross_partition_target_before_fleet_read(self):
        target = self.s1[0][0]
        called = False

        def fleet_watch(**_kwargs):
            nonlocal called
            called = True
            return {}

        result = authorize_supervising_chat_recovery("S2", target, fleet_watch=fleet_watch)
        self.assertFalse(result["authorized"])
        self.assertEqual(result["reason"], "CROSS_PARTITION_RECOVERY_FORBIDDEN")
        self.assertFalse(called)

    def test_supervising_chat_rejects_bad_partition_before_fleet_read(self):
        target = self.s2[0][0]
        called = False

        def fleet_watch(**_kwargs):
            nonlocal called
            called = True
            return {}

        result = authorize_supervising_chat_recovery("S3", target, fleet_watch=fleet_watch)
        self.assertFalse(result["authorized"])
        self.assertEqual(result["reason"], "SUPERVISING_CHAT_PARTITION_NOT_CANONICAL")
        self.assertFalse(called)

    def test_supervising_chat_rejects_bad_target_before_fleet_read(self):
        called = False

        def fleet_watch(**_kwargs):
            nonlocal called
            called = True
            return {}

        result = authorize_supervising_chat_recovery("S2", "not-a-worker", fleet_watch=fleet_watch)
        self.assertFalse(result["authorized"])
        self.assertEqual(result["reason"], "TARGET_NOT_CANONICAL")
        self.assertFalse(called)

    def test_supervising_chat_rejects_non_actionable_same_partition_target(self):
        target = self.s2[1][0]
        result = authorize_supervising_chat_recovery(
            "S2",
            target,
            fleet_watch=lambda **_kwargs: {
                "status": "CURRENT_LOCAL_EVIDENCE",
                "authority": "local_worker_reports_and_machine_start_receipts",
                "subscription_scope": "S2",
                "recovery_candidates": [],
            },
        )
        self.assertFalse(result["authorized"])
        self.assertEqual(result["reason"], "TARGET_NOT_ACTIONABLE")

    def test_cli_worker_and_supervising_chat_actor_modes_are_mutually_exclusive(self):
        argv = [
            "worker_recovery_guard.py",
            "--actor-worker-id", self.s2[0][0],
            "--supervising-chat-partition", "S2",
            "--target-worker-id", self.s2[1][0],
        ]
        with patch.object(sys, "argv", argv):
            with self.assertRaises(SystemExit) as raised:
                main()
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
