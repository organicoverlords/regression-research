import unittest
from pathlib import Path


class TimelineRuntimeInstallerTests(unittest.TestCase):
    def test_installer_uses_commit_addressed_archive_runtime_not_checkout(self):
        installer = (Path(__file__).resolve().parents[1] / "tools" / "Install-TimelineMaterializerTask.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("merge-base --is-ancestor $sourceCommit origin/main", installer)
        self.assertIn("VaultTimeline\\runtime", installer)
        self.assertIn("git -C $repo archive --format=zip", installer)
        self.assertIn("$runtime = Join-Path $runtimeRoot $sourceCommit", installer)
        self.assertIn("schema = 'vault-timeline-runtime.v1'", installer)
        self.assertIn("source_commit = $sourceCommit", installer)
        self.assertIn("$runtimeScript install-task --minutes $IntervalMinutes --root $VaultRoot", installer)
        self.assertNotIn("git -C $repo reset", installer)
        self.assertNotIn("git -C $repo checkout", installer)
        self.assertNotIn("git -C $repo merge ", installer)

    def test_installer_preserves_task_state_and_recognizes_only_known_previous_actions(self):
        installer = (Path(__file__).resolve().parents[1] / "tools" / "Install-TimelineMaterializerTask.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("$wasEnabled = [bool]$existing.Settings.Enabled", installer)
        self.assertIn("task is running; retry after it returns Ready", installer)
        self.assertIn("VaultTimelineServing\\tools\\timeline_materializer.py", installer)
        self.assertIn("Existing $TaskName task uses an unknown action; preserved without changes", installer)
        self.assertIn("if (-not $wasEnabled) { Disable-ScheduledTask", installer)
        self.assertIn("legacy_serving_preserved", installer)


if __name__ == "__main__":
    unittest.main()
