import sys
import unittest
from unittest.mock import patch

from tools.worker_recovery_guard import (
    authorize_recovery,
    authorize_supervising_chat_recovery,
    main,
)



TEST_RECURRING_WORKER_PARTITIONS = {
    "S1": tuple((str(index) * 32, f"S1 Test Worker {index}") for index in range(1, 6)),
    "S2": tuple((char * 32, f"S2 Test Worker {index}") for index, char in enumerate("abcde", start=1)),
}

NONCANONICAL_WORKER_ID = "00000000000000000000000000000000"


class WorkerRecoveryGuardTests(unittest.TestCase):
    def setUp(self):
        self.s1 = TEST_RECURRING_WORKER_PARTITIONS["S1"]
        self.s2 = TEST_RECURRING_WORKER_PARTITIONS["S2"]
        partition_by_id = {
            automation_id: partition
            for partition, workers in TEST_RECURRING_WORKER_PARTITIONS.items()
            for automation_id, _label in workers
        }
        self.binding_patch = patch(
            "tools.worker_recovery_guard._binding_partition_map",
            return_value=(partition_by_id, {"status": "OK"}),
        )
        self.binding_patch.start()
        self.addCleanup(self.binding_patch.stop)

    def _watch(self, *, candidates, scope="S2"):
        return {
            "status": "SUSPECT_DEGRADED" if candidates else "CURRENT_LOCAL_EVIDENCE",
            "authority": "local_worker_reports_and_machine_start_receipts",
            "subscription_scope": scope,
            "recovery_candidates": candidates,
        }

    def test_worker_mode_rejects_noncanonical_target_without_fleet_read(self):
        actor = self.s2[0][0]
        called = False

        def fleet_watch(**_kwargs):
            nonlocal called
            called = True
            return {}

        result = authorize_recovery(actor, NONCANONICAL_WORKER_ID, fleet_watch=fleet_watch)
        self.assertFalse(result["authorized"])
        self.assertEqual(result["reason"], "TARGET_NOT_BOUND_TO_RECURRING_SLOT")
        self.assertFalse(called)

    def test_worker_mode_rejects_self_administration_without_fleet_read(self):
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

    def test_worker_mode_rejects_canonical_sibling_without_fleet_read(self):
        actor = self.s2[0][0]
        target = self.s2[1][0]
        called = False

        def fleet_watch(**_kwargs):
            nonlocal called
            called = True
            return {}

        result = authorize_recovery(actor, target, fleet_watch=fleet_watch)
        self.assertFalse(result["authorized"])
        self.assertEqual(result["reason"], "WORKER_SCHEDULER_ADMINISTRATION_FORBIDDEN")
        self.assertFalse(called)
        self.assertNotIn("scheduler_action", result)

    def test_supervising_chat_authorizes_exact_actionable_s2_target(self):
        target = self.s2[1][0]
        candidate = {
            "automation_id": target,
            "subscription_partition": "S2",
            "reason": "MISSED_EXPECTED_HOURLY_CADENCE",
        }
        calls = []

        def fleet_watch(**kwargs):
            calls.append(kwargs)
            return self._watch(candidates=[candidate])

        result = authorize_supervising_chat_recovery("S2", target, scheduler_enabled=False, fleet_watch=fleet_watch)
        self.assertTrue(result["authorized"])
        self.assertEqual(calls, [{"partition": "S2"}])
        self.assertEqual(result["actor_mode"], "supervising_chat")
        self.assertNotIn("actor_worker_id", result)
        self.assertEqual(result["supervising_chat_partition"], "S2")
        self.assertEqual(result["target_partition"], "S2")
        self.assertEqual(result["scheduler_action"], {"operation": "set_is_enabled", "is_enabled": True})
        self.assertEqual(result["scheduler_probe"], "verified_disabled")

    def test_supervising_chat_requires_live_scheduler_probe_for_local_candidate(self):
        target = self.s2[1][0]
        candidate = {
            "automation_id": target,
            "subscription_partition": "S2",
            "reason": "MISSED_EXPECTED_HOURLY_CADENCE",
        }
        result = authorize_supervising_chat_recovery(
            "S2",
            target,
            fleet_watch=lambda **_kwargs: self._watch(candidates=[candidate]),
        )
        self.assertFalse(result["authorized"])
        self.assertEqual(result["reason"], "LIVE_SCHEDULER_PROBE_REQUIRED")
        self.assertEqual(result["scheduler_probe"], "required")

    def test_supervising_chat_rejects_stale_local_report_when_scheduler_is_current(self):
        from datetime import datetime, timezone
        target = self.s2[1][0]
        candidate = {
            "automation_id": target,
            "subscription_partition": "S2",
            "reason": "MISSED_EXPECTED_HOURLY_CADENCE",
        }
        result = authorize_supervising_chat_recovery(
            "S2",
            target,
            scheduler_enabled=True,
            scheduler_last_run_at=datetime.now(timezone.utc).isoformat(),
            fleet_watch=lambda **_kwargs: self._watch(candidates=[candidate]),
        )
        self.assertFalse(result["authorized"])
        self.assertEqual(result["reason"], "LOCAL_EVIDENCE_STALE_SCHEDULER_CURRENT")

    def test_supervising_chat_allows_idempotent_rearm_when_enabled_scheduler_missed_cadence(self):
        from datetime import datetime, timedelta, timezone
        target = self.s2[1][0]
        candidate = {
            "automation_id": target,
            "subscription_partition": "S2",
            "reason": "MISSED_EXPECTED_HOURLY_CADENCE",
        }
        result = authorize_supervising_chat_recovery(
            "S2",
            target,
            scheduler_enabled=True,
            scheduler_last_run_at=(datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(),
            fleet_watch=lambda **_kwargs: self._watch(candidates=[candidate]),
        )
        self.assertTrue(result["authorized"])
        self.assertEqual(result["reason"], "ENABLED_BUT_MISSED_SCHEDULER_CADENCE_REARM")
        self.assertEqual(result["scheduler_probe"], "verified_enabled_missed_cadence")

    def test_supervising_chat_authorizes_exact_actionable_s1_target(self):
        target = self.s1[1][0]
        candidate = {
            "automation_id": target,
            "subscription_partition": "S1",
            "reason": "MISSED_EXPECTED_HOURLY_CADENCE",
        }
        result = authorize_supervising_chat_recovery(
            "S1",
            target,
            scheduler_enabled=False,
            fleet_watch=lambda **_kwargs: self._watch(candidates=[candidate], scope="S1"),
        )
        self.assertTrue(result["authorized"])
        self.assertEqual(result["target_partition"], "S1")

    def test_supervising_chat_rejects_cross_partition_target_before_fleet_read(self):
        target = self.s2[0][0]
        called = False

        def fleet_watch(**_kwargs):
            nonlocal called
            called = True
            return {}

        result = authorize_supervising_chat_recovery("S1", target, fleet_watch=fleet_watch)
        self.assertFalse(result["authorized"])
        self.assertEqual(result["reason"], "CROSS_PARTITION_RECOVERY_FORBIDDEN")
        self.assertFalse(called)

    def test_supervising_chat_rejects_bad_target_before_fleet_read(self):
        called = False

        def fleet_watch(**_kwargs):
            nonlocal called
            called = True
            return {}

        result = authorize_supervising_chat_recovery("S2", "not-a-worker", fleet_watch=fleet_watch)
        self.assertFalse(result["authorized"])
        self.assertEqual(result["reason"], "TARGET_NOT_BOUND_TO_RECURRING_SLOT")
        self.assertFalse(called)

    def test_supervising_chat_rejects_scope_mismatch(self):
        target = self.s2[1][0]
        result = authorize_supervising_chat_recovery(
            "S2", target, fleet_watch=lambda **_kwargs: self._watch(candidates=[], scope="S1")
        )
        self.assertFalse(result["authorized"])
        self.assertEqual(result["reason"], "FLEET_WATCH_SCOPE_MISMATCH")

    def test_supervising_chat_rejects_non_actionable_s2_target(self):
        target = self.s2[1][0]
        result = authorize_supervising_chat_recovery(
            "S2", target, fleet_watch=lambda **_kwargs: self._watch(candidates=[])
        )
        self.assertFalse(result["authorized"])
        self.assertEqual(result["reason"], "TARGET_NOT_ACTIONABLE")

    def test_supervising_chat_rejects_candidate_scope_mismatch(self):
        target = self.s2[1][0]
        candidate = {
            "automation_id": target,
            "subscription_partition": "S1",
            "reason": "NO_LOCAL_START_EVIDENCE",
        }
        result = authorize_supervising_chat_recovery(
            "S2", target, fleet_watch=lambda **_kwargs: self._watch(candidates=[candidate])
        )
        self.assertFalse(result["authorized"])
        self.assertEqual(result["reason"], "CANDIDATE_PARTITION_MISMATCH")

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
