import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from tools.cleanup_converger import (
    Worktree,
    cwd_targets_path,
    eligibility_reason,
    parse_worktrees,
    path_is_same_or_child,
    process_targets_path,
    recent_mcp_cwds,
)


class CleanupConvergerTests(unittest.TestCase):
    def test_parse_worktrees_preserves_branch_and_detached_state(self):
        rows = parse_worktrees(
            "\n".join(
                [
                    "worktree C:/repo",
                    "HEAD aaaa",
                    "branch refs/heads/main",
                    "locked protected worker lane",
                    "",
                    "worktree C:/temp/lane",
                    "HEAD bbbb",
                    "detached",
                    "",
                ]
            )
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].branch, "main")
        self.assertFalse(rows[0].detached)
        self.assertEqual(rows[0].locked, "protected worker lane")
        self.assertIsNone(rows[1].branch)
        self.assertTrue(rows[1].detached)

    def test_path_child_guard_is_boundary_aware(self):
        self.assertTrue(path_is_same_or_child(r"C:\Temp\lane", r"C:\Temp\lane"))
        self.assertTrue(path_is_same_or_child(r"C:\Temp\lane\Saved", r"C:\Temp\lane"))
        self.assertFalse(path_is_same_or_child(r"C:\Temp\lane-old", r"C:\Temp\lane"))

    def test_process_target_guard_catches_cross_cwd_reference(self):
        lane = Path(r"C:\Temp\p3-lane")
        processes = [
            {
                "ProcessId": 41,
                "CommandLine": r'dotnet.exe UnrealBuildTool.dll -Project=C:\Temp\p3-lane\p3.uproject',
            }
        ]
        self.assertTrue(process_targets_path(lane, processes, self_pid=99))
        self.assertFalse(process_targets_path(Path(r"C:\Temp\other"), processes, self_pid=99))

    def test_process_guard_can_exclude_self(self):
        lane = Path(r"C:\Temp\p3-lane")
        processes = [{"ProcessId": 99, "CommandLine": r"tool C:\Temp\p3-lane"}]
        self.assertFalse(process_targets_path(lane, processes, self_pid=99))

    def test_recent_mcp_cwd_reads_only_fresh_events(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            log = root / "clone-a" / "transport.jsonl"
            log.parent.mkdir(parents=True)
            now = datetime(2026, 9, 6, 14, 0, tzinfo=timezone.utc).timestamp()
            fresh = datetime.fromtimestamp(now - 30, tz=timezone.utc).isoformat()
            old = datetime.fromtimestamp(now - 900, tz=timezone.utc).isoformat()
            log.write_text(
                json.dumps({"at": old, "cwd": r"C:\Temp\old"})
                + "\n"
                + json.dumps({"at": fresh, "cwd": r"C:\Temp\fresh"})
                + "\n",
                encoding="utf-8",
            )
            os.utime(log, (now, now))
            rows = recent_mcp_cwds(300, log_root=root, now=now)
            self.assertTrue(cwd_targets_path(Path(r"C:\Temp\fresh"), rows))
            self.assertFalse(cwd_targets_path(Path(r"C:\Temp\old"), rows))

    def test_eligibility_preserves_active_dirty_detached_and_ref_mismatch(self):
        lane = Worktree(Path(r"C:\Temp\lane"), "abcd", "topic", False)
        detached = Worktree(Path(r"C:\Temp\detached"), "abcd", None, True)
        self.assertEqual(
            eligibility_reason(detached, recent_cwds=set(), processes=[], clean=True, ref_matches=False),
            "detached_or_unanchored",
        )
        self.assertEqual(
            eligibility_reason(lane, recent_cwds={r"C:\Temp\lane"}, processes=[], clean=True, ref_matches=True),
            "recent_mcp_cwd_activity",
        )
        self.assertEqual(
            eligibility_reason(
                lane,
                recent_cwds=set(),
                processes=[{"ProcessId": 42, "CommandLine": r"cl.exe C:\Temp\lane\x.cpp"}],
                clean=True,
                ref_matches=True,
            ),
            "external_process_targets_path",
        )
        self.assertEqual(
            eligibility_reason(lane, recent_cwds=set(), processes=[], clean=False, ref_matches=True),
            "dirty",
        )
        self.assertEqual(
            eligibility_reason(lane, recent_cwds=set(), processes=[], clean=True, ref_matches=False),
            "branch_ref_mismatch",
        )


    def test_locked_worktree_is_never_eligible(self):
        lane = Worktree(Path(r"C:\Temp\lane"), "abcd", "topic", False, "protected worker lane")
        self.assertEqual(
            eligibility_reason(lane, recent_cwds=set(), processes=[], clean=True, ref_matches=True),
            "git_worktree_locked:protected worker lane",
        )

    @patch("tools.cleanup_converger.os.getpid", return_value=999)
    def test_clean_anchored_idle_lane_is_eligible(self, _getpid):
        lane = Worktree(Path(r"C:\Temp\lane"), "abcd", "topic", False)
        self.assertIsNone(
            eligibility_reason(lane, recent_cwds=set(), processes=[], clean=True, ref_matches=True)
        )


if __name__ == "__main__":
    unittest.main()
