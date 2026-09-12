import unittest
from unittest.mock import patch

from tools.worktree_hygiene_task import MAX_AUXILIARY, MAX_DIRTY, classify_health


class WorktreeHygieneTaskTests(unittest.TestCase):
    def test_health_is_healthy_at_bounds(self):
        snapshot = {"auxiliary_count": MAX_AUXILIARY, "dirty_count": MAX_DIRTY}
        self.assertEqual(classify_health(snapshot), "healthy")

    def test_health_degrades_before_large_tail(self):
        self.assertEqual(
            classify_health({"auxiliary_count": MAX_AUXILIARY + 1, "dirty_count": 0}),
            "degraded",
        )
        self.assertEqual(
            classify_health({"auxiliary_count": 0, "dirty_count": MAX_DIRTY + 1}),
            "degraded",
        )

    def test_installer_default_cadence_is_five_minutes_and_runtime_is_immutable(self):
        installer = (__import__("pathlib").Path(__file__).resolve().parents[1] / "tools" / "Install-WorktreeHygieneTask.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("[int]$IntervalMinutes = 5", installer)
        self.assertIn("if ($IntervalMinutes -lt 1)", installer)
        self.assertIn("merge-base --is-ancestor $sourceCommit origin/main", installer)
        self.assertIn("VaultWorktreeHygiene\\runtime", installer)
        self.assertIn("Hygiene runtime source differs from committed snapshot", installer)
        self.assertIn("source_commit = $sourceCommit", installer)
        self.assertIn("Existing $TaskName task uses an unknown action; preserved without changes", installer)
        self.assertIn("$legacyMutableRoot = 'C:\\Users\\Lauri\\Desktop\\vault'", installer)
        self.assertIn("AddMinutes($IntervalMinutes)", installer)

    def test_installer_preserves_existing_disabled_state_during_runtime_cutover(self):
        installer = (__import__("pathlib").Path(__file__).resolve().parents[1] / "tools" / "Install-WorktreeHygieneTask.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("$wasEnabled = [bool]$existing.Settings.Enabled", installer)
        self.assertIn("if (-not $wasEnabled) { Disable-ScheduledTask -TaskName $TaskName", installer)
        self.assertIn("preserved_enabled_state = $wasEnabled", installer)


if __name__ == "__main__":
    unittest.main()
