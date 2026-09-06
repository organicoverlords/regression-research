import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from tools.cleanup_converger import (
    Action,
    Worktree,
    cwd_targets_path,
    eligibility_reason,
    exact_anchor_refs,
    generated_cache_dirs,
    _clean_generated_cache_one,
    _fresh_cache_guard,
    parse_worktrees,
    path_is_same_or_child,
    process_targets_path,
    recent_mcp_cwds,
    summarize_actions,
    scan_repo,
    worktree_is_clean,
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
        self.assertIsNone(
            eligibility_reason(detached, recent_cwds=set(), processes=[], clean=True, ref_matches=True)
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



    @patch("tools.cleanup_converger._git")
    def test_exact_anchor_refs_requires_direct_non_symbolic_ref(self, git):
        git.return_value = subprocess.CompletedProcess(
            ["git"],
            0,
            stdout=(
                "refs/heads/topic\n"
                "refs/remotes/origin/HEAD\n"
                "refs/remotes/origin/main\n"
            ),
            stderr="",
        )
        lane = Worktree(Path(r"C:\Temp\lane"), "abcd", None, True)
        self.assertEqual(
            exact_anchor_refs(Path(r"C:\repo"), lane),
            ["refs/heads/topic", "refs/remotes/origin/main"],
        )
        args = git.call_args.args
        self.assertIn("--points-at", args)
        self.assertIn("abcd", args)

    def test_locked_worktree_is_never_eligible(self):
        lane = Worktree(Path(r"C:\Temp\lane"), "abcd", "topic", False, "protected worker lane")
        self.assertEqual(
            eligibility_reason(lane, recent_cwds=set(), processes=[], clean=True, ref_matches=True),
            "git_worktree_locked:protected worker lane",
        )



    def test_progress_summary_retains_cache_cleanup_before_later_preserve(self):
        actions = [
            Action("P3", r"C:\lane", "CLEANED_GENERATED_CACHE", reason="dirs=3"),
            Action("P3", r"C:\lane", "PRESERVE", reason="dirty"),
        ]
        summary = summarize_actions(actions)
        self.assertEqual(summary["generated_cache_cleanup_count"], 1)
        self.assertEqual(summary["actions"][0]["action"], "PRESERVE")
        self.assertEqual(summary["progress_events"][0]["action"], "CLEANED_GENERATED_CACHE")

    def test_generated_cache_dirs_are_git_ignored_unreal_outputs_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text(
                "Intermediate/\nBinaries/\nDerivedDataCache/\nPlugins/**/Intermediate/\nPlugins/**/Binaries/\n",
                encoding="utf-8",
            )
            for relative in (
                "Intermediate/x",
                "Binaries/x",
                "Plugins/P3/P3UI/Intermediate/x",
                "Plugins/P3/P3UI/Binaries/x",
                "Content/keep",
                "Saved/proof",
                "evidence/keep",
            ):
                (root / relative).mkdir(parents=True, exist_ok=True)
            found = {item.relative_to(root).as_posix() for item in generated_cache_dirs(root)}
            self.assertEqual(
                found,
                {"Intermediate", "Binaries", "Plugins/P3/P3UI/Intermediate", "Plugins/P3/P3UI/Binaries"},
            )

    @patch("tools.cleanup_converger._fresh_cache_guard", return_value=None)
    def test_generated_cache_cleanup_preserves_content_saved_and_dirty_source(self, _guard):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text(
                "Intermediate/\nPlugins/**/Intermediate/\n", encoding="utf-8"
            )
            keep_paths = [root / "Content" / "asset.uasset", root / "Saved" / "proof.png", root / "Source" / "dirty.cpp"]
            for keep in keep_paths:
                keep.parent.mkdir(parents=True, exist_ok=True)
                keep.write_text("keep", encoding="utf-8")
            generated = [root / "Intermediate" / "build.obj", root / "Plugins" / "P3" / "P3UI" / "Intermediate" / "build.obj"]
            for item in generated:
                item.parent.mkdir(parents=True, exist_ok=True)
                item.write_text("generated", encoding="utf-8")
            lane = Worktree(root, "abcd", "topic", False)
            result = _clean_generated_cache_one("P3", root, lane, 300)
            self.assertEqual(result.action, "CLEANED_GENERATED_CACHE")
            self.assertTrue(all(path.exists() for path in keep_paths))
            self.assertTrue(all(not path.exists() for path in generated))

    @patch("tools.cleanup_converger.windows_processes")
    @patch("tools.cleanup_converger.recent_mcp_cwds", return_value=set())
    @patch("tools.cleanup_converger._current_worktree")
    def test_generated_cache_guard_preserves_locked_or_process_targeted_lane(self, current, _cwds, processes):
        lane = Worktree(Path(r"C:\Temp\lane"), "abcd", "topic", False)
        current.return_value = Worktree(lane.path, lane.head, lane.branch, False, "protected")
        processes.return_value = []
        self.assertEqual(_fresh_cache_guard(Path(r"C:\repo"), lane, 300), "git_worktree_locked:protected")
        current.return_value = lane
        processes.return_value = [{"ProcessId": 42, "CommandLine": r"cl.exe C:\Temp\lane\x.cpp"}]
        self.assertEqual(_fresh_cache_guard(Path(r"C:\repo"), lane, 300), "external_process_targets_path")

    @patch("tools.cleanup_converger._git")
    def test_cleanliness_probe_timeout_returns_unknown(self, git):
        git.side_effect = subprocess.TimeoutExpired(["git", "diff-files"], 15)
        self.assertIsNone(worktree_is_clean(Path(r"C:\Temp\slow-lane")))

    @patch("tools.cleanup_converger.generated_cache_dirs", return_value=[])
    @patch("tools.cleanup_converger.branch_ref_matches", return_value=True)
    @patch("tools.cleanup_converger.worktree_is_clean", return_value=None)
    @patch("tools.cleanup_converger.windows_processes", return_value=[])
    @patch("tools.cleanup_converger.recent_mcp_cwds", return_value=set())
    @patch("tools.cleanup_converger._git")
    def test_scan_preserves_lane_when_cleanliness_probe_times_out(
        self, git, _cwds, _processes, _clean, _ref, _cache
    ):
        git.return_value = subprocess.CompletedProcess(
            ["git"],
            0,
            stdout=(
                "worktree C:/repo\nHEAD root\nbranch refs/heads/main\n\n"
                "worktree C:/slow-lane\nHEAD abcd\nbranch refs/heads/topic\n\n"
            ),
            stderr="",
        )
        candidates, cache_candidates, observations = scan_repo("P3", Path(r"C:\repo"), 300)
        self.assertEqual(candidates, [])
        self.assertEqual(cache_candidates, [])
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].action, "PRESERVE")
        self.assertEqual(observations[0].reason, "cleanliness_probe_timeout")

    @patch("tools.cleanup_converger.os.getpid", return_value=999)
    def test_clean_anchored_idle_lane_is_eligible(self, _getpid):
        lane = Worktree(Path(r"C:\Temp\lane"), "abcd", "topic", False)
        self.assertIsNone(
            eligibility_reason(lane, recent_cwds=set(), processes=[], clean=True, ref_matches=True)
        )


if __name__ == "__main__":
    unittest.main()
