import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tools.worktree_hygiene_task import (
    MAX_AUXILIARY,
    MAX_DIRTY,
    SOFT_FREE_GIB,
    TARGET_FREE_GIB,
    capacity_tick,
    classify_health,
    pressure_active,
)


class WorktreeHygieneTaskTests(unittest.TestCase):
    def test_health_is_healthy_at_bounds(self):
        snapshot = {"auxiliary_count": MAX_AUXILIARY, "dirty_count": MAX_DIRTY}
        roots = {"Vault": {"status": "current"}, "Agents": {"status": "restored"}}
        self.assertEqual(classify_health(snapshot, roots), "healthy")

    def test_health_degrades_before_large_tail(self):
        self.assertEqual(
            classify_health({"auxiliary_count": MAX_AUXILIARY + 1, "dirty_count": 0}),
            "degraded",
        )
        self.assertEqual(
            classify_health({"auxiliary_count": 0, "dirty_count": MAX_DIRTY + 1}),
            "degraded",
        )

    def test_health_checks_both_canonical_roots(self):
        snapshot = {"auxiliary_count": 0, "dirty_count": 0}
        self.assertEqual(
            classify_health(snapshot, {"Vault": {"status": "current"}, "Agents": {"status": "dirty_blocked"}}),
            "degraded",
        )

    def test_pressure_hysteresis_enters_at_soft_and_clears_at_target(self):
        self.assertFalse(pressure_active(SOFT_FREE_GIB, False))
        self.assertTrue(pressure_active(SOFT_FREE_GIB - 0.1, False))
        self.assertTrue(pressure_active(TARGET_FREE_GIB - 0.1, True))
        self.assertFalse(pressure_active(TARGET_FREE_GIB, True))

    def test_healthy_tick_is_observation_only(self):
        reclaim = Mock(return_value={"mode": "pressure-auto"})
        state, cleanup = capacity_tick(
            previous_pressure=False,
            probe=Mock(return_value=SOFT_FREE_GIB + 5),
            reclaimer=reclaim,
        )
        reclaim.assert_not_called()
        self.assertIsNone(cleanup)
        self.assertFalse(state["reclaim_attempted"])
        self.assertEqual(state["reclaim_passes"], 0)

    def test_pressure_tick_runs_exactly_one_reclaim_and_reprobes(self):
        probe = Mock(side_effect=[SOFT_FREE_GIB - 1, TARGET_FREE_GIB + 2])
        reclaim = Mock(return_value={"mode": "pressure-auto", "rounds_run": 1})
        state, cleanup = capacity_tick(previous_pressure=False, probe=probe, reclaimer=reclaim)
        reclaim.assert_called_once_with()
        self.assertEqual(probe.call_count, 2)
        self.assertEqual(cleanup["mode"], "pressure-auto")
        self.assertEqual(state["reclaim_passes"], 1)
        self.assertFalse(state["pressure_active"])

    def test_existing_pressure_reclaims_until_target_not_soft(self):
        probe = Mock(side_effect=[SOFT_FREE_GIB + 5, SOFT_FREE_GIB + 6])
        reclaim = Mock(return_value={"mode": "pressure-auto"})
        state, _cleanup = capacity_tick(previous_pressure=True, probe=probe, reclaimer=reclaim)
        reclaim.assert_called_once_with()
        self.assertTrue(state["pressure_active"])

    def test_installer_default_cadence_is_one_minute_and_runtime_is_immutable(self):
        installer = (Path(__file__).resolve().parents[1] / "tools" / "Install-WorktreeHygieneTask.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("[int]$IntervalMinutes = 1", installer)
        self.assertIn("if ($IntervalMinutes -lt 1)", installer)
        self.assertIn("merge-base --is-ancestor $sourceCommit origin/main", installer)
        self.assertIn("VaultWorktreeHygiene\\runtime", installer)
        self.assertIn("source_commit = $sourceCommit", installer)
        self.assertIn("RestartCount", installer)
        self.assertIn("-MultipleInstances IgnoreNew", installer)
        self.assertNotIn("New-ScheduledTaskSettingsSet -Restart", installer)
        self.assertNotIn("[int]$IntervalMinutes = 15", installer)

    def test_task_source_checks_vault_and_agents_and_reports_degraded_without_scheduler_failure(self):
        source = (Path(__file__).resolve().parents[1] / "tools" / "worktree_hygiene_task.py").read_text(encoding="utf-8")
        self.assertIn('"Vault": ensure_canonical_main(VAULT_ROOT, 600)', source)
        self.assertIn('"Agents": ensure_canonical_main(AGENTS_ROOT, 600)', source)
        self.assertIn("return 0", source)
        self.assertIn("pressure_auto=True", source)
        self.assertIn("max_rounds=1", source)


if __name__ == "__main__":
    unittest.main()
