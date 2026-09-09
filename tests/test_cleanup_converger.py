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
    CLEANLINESS_PROBE_TIMEOUT_SECONDS,
    Worktree,
    canonical_main_contains_head,
    converge,
    cwd_targets_path,
    dirty_changes_match_origin_main,
    eligibility_reason,
    exact_anchor_refs,
    generated_cache_dirs,
    hygiene_snapshot,
    _clean_generated_cache_one,
    _fresh_cache_guard,
    parse_worktrees,
    path_is_same_or_child,
    process_targets_path,
    recent_mcp_cwds,
    summarize_actions,
    scan_repo,
    worktree_anchor_matches,
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

    def test_recent_mcp_cwd_reads_all_current_instances_and_rotated_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            now = datetime(2026, 9, 6, 14, 0, tzinfo=timezone.utc).timestamp()

            first = root / "clone-a" / "transport.jsonl"
            first.parent.mkdir(parents=True)
            first.write_text(
                json.dumps(
                    {
                        "at": datetime.fromtimestamp(now - 30, tz=timezone.utc).isoformat(),
                        "cwd": r"C:\Temp\first",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            second = root / "clone-b" / "transport.jsonl"
            second.parent.mkdir(parents=True)
            second.write_text(
                json.dumps(
                    {
                        "at": datetime.fromtimestamp(now - 90, tz=timezone.utc).isoformat(),
                        "cwd": r"C:\Temp\second-active",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            archive = second.with_name("transport.jsonl.archive") / "rotated.jsonl"
            archive.parent.mkdir(parents=True)
            archive.write_text(
                json.dumps(
                    {
                        "at": datetime.fromtimestamp(now - 10, tz=timezone.utc).isoformat(),
                        "cwd": r"C:\Temp\second-rotated",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            rows = recent_mcp_cwds(300, log_root=root, now=now)
            self.assertTrue(cwd_targets_path(Path(r"C:\Temp\first"), rows))
            self.assertTrue(cwd_targets_path(Path(r"C:\Temp\second-rotated"), rows))
            self.assertFalse(cwd_targets_path(Path(r"C:\Temp\second-active"), rows))

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

    @patch("tools.cleanup_converger._git")
    def test_canonical_main_contains_head_uses_cached_origin_main_ancestry(self, git):
        git.return_value = subprocess.CompletedProcess(["git"], 0, stdout="", stderr="")
        lane = Worktree(Path(r"C:\Temp\detached"), "abcd", None, True)
        self.assertTrue(canonical_main_contains_head(Path(r"C:\repo"), lane))
        git.assert_called_once_with(
            Path(r"C:\repo"),
            "merge-base",
            "--is-ancestor",
            "abcd",
            "refs/remotes/origin/main",
            check=False,
            timeout=CLEANLINESS_PROBE_TIMEOUT_SECONDS,
        )

    @patch("tools.cleanup_converger.canonical_main_contains_head", return_value=True)
    @patch("tools.cleanup_converger.exact_anchor_refs", return_value=[])
    def test_detached_worktree_can_anchor_via_canonical_main_ancestry(self, _exact, _contained):
        lane = Worktree(Path(r"C:\Temp\detached"), "abcd", None, True)
        self.assertTrue(worktree_anchor_matches(Path(r"C:\repo"), lane))

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
    def test_cleanliness_probe_uses_one_status_for_all_dirty_states(self, git):
        git.side_effect = [
            subprocess.CompletedProcess(["git"], 0, stdout="", stderr=""),
            subprocess.CompletedProcess(["git"], 0, stdout=" M tracked.txt\0", stderr=""),
            subprocess.CompletedProcess(["git"], 0, stdout="M  staged.txt\0", stderr=""),
            subprocess.CompletedProcess(["git"], 0, stdout="?? untracked.txt\0", stderr=""),
        ]
        lane = Path(r"C:\Temp\lane")
        self.assertTrue(worktree_is_clean(lane))
        self.assertFalse(worktree_is_clean(lane))
        self.assertFalse(worktree_is_clean(lane))
        self.assertFalse(worktree_is_clean(lane))
        self.assertEqual(git.call_count, 4)
        for call in git.call_args_list:
            self.assertEqual(
                call.args,
                (
                    lane,
                    "status",
                    "--porcelain=v1",
                    "-z",
                    "--untracked-files=normal",
                    "--ignore-submodules=none",
                ),
            )
            self.assertEqual(call.kwargs, {"check": False, "timeout": CLEANLINESS_PROBE_TIMEOUT_SECONDS})

    @patch("tools.cleanup_converger._git")
    def test_cleanliness_probe_timeout_returns_unknown(self, git):
        git.side_effect = subprocess.TimeoutExpired(["git", "status"], 15)
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

    @patch("tools.cleanup_converger.disk_free_gb", return_value=10.0)
    @patch("tools.cleanup_converger.scan_repo")
    @patch("tools.cleanup_converger._git")
    def test_apply_prunes_missing_worktree_registration_before_scan(self, git, scan, _disk):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            order = []

            def git_side_effect(_repo, *args, **kwargs):
                if args == ("worktree", "prune"):
                    order.append("prune")
                return subprocess.CompletedProcess(["git"], 0, stdout="", stderr="")

            def scan_side_effect(*_args, **_kwargs):
                self.assertEqual(order, ["prune"])
                return [], [], []

            git.side_effect = git_side_effect
            scan.side_effect = scan_side_effect
            with patch("tools.cleanup_converger.DEFAULT_REPOS", (("P3", repo, "p3:git-worktree-metadata"),)):
                result = converge(
                    apply=True,
                    max_rounds=1,
                    stable_rounds=1,
                    settle_seconds=0,
                    window_seconds=300,
                    actor="test-operator",
                )

            self.assertEqual(result["rounds_run"], 1)
            git.assert_any_call(repo, "worktree", "prune", check=False)

    @patch("tools.cleanup_converger.disk_free_gb", return_value=10.0)
    @patch("tools.cleanup_converger.busy_release")
    @patch("tools.cleanup_converger.busy_claim")
    @patch("tools.cleanup_converger._remove_one")
    @patch("tools.cleanup_converger.scan_repo")
    @patch("tools.cleanup_converger._git")
    def test_apply_live_branch_ref_claim_vetoes_worktree_removal(
        self, git, scan, remove_one, busy_claim, _busy_release, _disk
    ):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            lane = Worktree(Path(tmp) / "lane", "abcd", "topic", False)
            scan.return_value = ([lane], [], [])
            git.return_value = subprocess.CompletedProcess(["git"], 0, stdout="", stderr="")
            busy_claim.side_effect = [
                (True, "metadata acquired"),
                (False, "scope_already_claimed"),
            ]

            with patch(
                "tools.cleanup_converger.DEFAULT_REPOS",
                (("Vault", repo, "organicoverlords/regression-research:git-worktree-metadata"),),
            ):
                result = converge(
                    apply=True,
                    max_rounds=1,
                    stable_rounds=1,
                    settle_seconds=0,
                    window_seconds=300,
                    actor="test-operator",
                )

            remove_one.assert_not_called()
            self.assertEqual(
                busy_claim.call_args_list[1].args,
                ("test-operator", "organicoverlords/regression-research:git-ref:refs/heads/topic"),
            )
            blocked = [action for action in result["actions"] if action["action"] == "BLOCKED"]
            self.assertEqual(len(blocked), 1)
            self.assertEqual(blocked[0]["reason"], "branch_busy_claim_failed:scope_already_claimed")

    def test_default_repo_scopes_use_canonical_github_owner_names(self):
        from tools.cleanup_converger import DEFAULT_REPOS, _branch_ref_scope
        scopes = {name: scope for name, _path, scope in DEFAULT_REPOS}
        self.assertEqual(scopes["Vault"], "organicoverlords/regression-research:git-worktree-metadata")
        self.assertEqual(scopes["Agents"], "organicoverlords/agents:git-worktree-metadata")
        lane = Worktree(Path(r"C:\Temp\lane"), "abcd", "topic", False)
        self.assertEqual(_branch_ref_scope(scopes["Agents"], lane), "organicoverlords/agents:git-ref:refs/heads/topic")

    @patch("tools.cleanup_converger.os.getpid", return_value=999)
    def test_clean_anchored_idle_lane_is_eligible(self, _getpid):
        lane = Worktree(Path(r"C:\Temp\lane"), "abcd", "topic", False)
        self.assertIsNone(
            eligibility_reason(lane, recent_cwds=set(), processes=[], clean=True, ref_matches=True)
        )


    @patch("tools.cleanup_converger.canonical_main_contains_head", return_value=True)
    @patch("tools.cleanup_converger._git")
    def test_dirty_classifier_proves_only_paths_matching_origin_main(self, git, _contained):
        with tempfile.TemporaryDirectory() as tmp:
            lane_path = Path(tmp)
            (lane_path / "same.txt").write_text("same", encoding="utf-8")
            lane = Worktree(lane_path, "abcd", "topic", False)
            git.side_effect = [
                subprocess.CompletedProcess(["git"], 0, stdout="same.txt\0", stderr=""),
                subprocess.CompletedProcess(["git"], 0, stdout="", stderr=""),
                subprocess.CompletedProcess(["git"], 0, stdout="deadbeef\n", stderr=""),
                subprocess.CompletedProcess(["git"], 0, stdout="deadbeef\n", stderr=""),
            ]
            self.assertTrue(dirty_changes_match_origin_main(Path(r"C:\repo"), lane))

    @patch("tools.cleanup_converger.disk_free_gb", return_value=10.0)
    @patch("tools.cleanup_converger.scan_repo", return_value=([], [], []))
    @patch("tools.cleanup_converger._git")
    def test_safe_auto_requires_contained_scan_and_is_not_operator_mode(self, git, scan, _disk):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            git.return_value = subprocess.CompletedProcess(["git"], 0, stdout="", stderr="")
            with patch("tools.cleanup_converger.DEFAULT_REPOS", (("Vault", repo, "organicoverlords/regression-research:git-worktree-metadata"),)):
                result = converge(apply=False, safe_auto=True, max_rounds=1, stable_rounds=1, settle_seconds=0, window_seconds=300, actor="scheduled-test")
        scan.assert_called_once_with("Vault", repo, 300, require_contained=True)
        self.assertEqual(result["mode"], "safe-auto")
        self.assertFalse(result["operator_only"])

    @patch("tools.cleanup_converger.scan_repo")
    def test_hygiene_snapshot_counts_dirty_and_safe_reap(self, scan):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            lane = Worktree(repo / "reap", "abcd", "topic", False)
            scan.return_value = ([lane], [], [Action("Vault", str(repo / "dirty"), "PRESERVE", "old", "beef", "dirty_unique_contained_in_origin_main")])
            with patch("tools.cleanup_converger.DEFAULT_REPOS", (("Vault", repo, "organicoverlords/regression-research:git-worktree-metadata"),)):
                result = hygiene_snapshot(300, repo_names={"Vault"})
        self.assertEqual(result["auxiliary_count"], 2)
        self.assertEqual(result["dirty_count"], 1)
        self.assertEqual(result["contained_dirty_count"], 1)
        self.assertEqual(result["safe_reap_count"], 1)


if __name__ == "__main__":
    unittest.main()
