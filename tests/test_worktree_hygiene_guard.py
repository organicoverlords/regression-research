import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.cleanup_converger import Worktree
from tools.worktree_hygiene_guard import ensure_canonical_main, quarantine_pressure


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, text=True, capture_output=True)


class WorktreeHygieneGuardTests(unittest.TestCase):
    def test_clean_idle_wrong_branch_restores_main(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            git(repo.parent, "init", "-b", "main", str(repo))
            git(repo, "config", "user.name", "test")
            git(repo, "config", "user.email", "test@example.invalid")
            (repo / "a.txt").write_text("a", encoding="utf-8")
            git(repo, "add", "a.txt"); git(repo, "commit", "-m", "init")
            git(repo, "switch", "-c", "topic")
            with patch("tools.worktree_hygiene_guard.recent_mcp_cwds", return_value=[]), patch("tools.worktree_hygiene_guard.windows_processes", return_value=[]), patch("tools.worktree_hygiene_guard.cwd_targets_path", return_value=False), patch("tools.worktree_hygiene_guard.process_targets_path", return_value=False):
                result = ensure_canonical_main(repo)
            self.assertEqual(result["status"], "restored")
            self.assertEqual(git(repo, "branch", "--show-current").stdout.strip(), "main")

    def test_dirty_wrong_branch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            git(repo.parent, "init", "-b", "main", str(repo))
            git(repo, "config", "user.name", "test")
            git(repo, "config", "user.email", "test@example.invalid")
            (repo / "a.txt").write_text("a", encoding="utf-8")
            git(repo, "add", "a.txt"); git(repo, "commit", "-m", "init")
            git(repo, "switch", "-c", "topic")
            (repo / "a.txt").write_text("dirty", encoding="utf-8")
            result = ensure_canonical_main(repo)
            self.assertEqual(result["status"], "dirty_blocked")
            self.assertEqual(git(repo, "branch", "--show-current").stdout.strip(), "topic")

    @patch("tools.worktree_hygiene_guard.shutil.move")
    def test_pressure_rechecks_live_process_before_move(self, move):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"; lane_path = Path(tmp) / "lane"
            repo.mkdir(); lane_path.mkdir()
            main = Worktree(repo, "m" * 40, "main", False)
            lane = Worktree(lane_path, "a" * 40, "topic", False)
            dirty = subprocess.CompletedProcess(["git"], 0, stdout=" M x.txt\0", stderr="")
            listed = subprocess.CompletedProcess(["git"], 0, stdout="unused", stderr="")
            with patch("tools.worktree_hygiene_guard._git", side_effect=[listed, dirty]), patch("tools.worktree_hygiene_guard.parse_worktrees", return_value=[main, lane]), patch("tools.worktree_hygiene_guard.recent_mcp_cwds", return_value=[]), patch("tools.worktree_hygiene_guard.windows_processes", side_effect=[[], ["live"]]), patch("tools.worktree_hygiene_guard.cwd_targets_path", return_value=False), patch("tools.worktree_hygiene_guard.process_targets_path", side_effect=[False, True]), patch("tools.worktree_hygiene_guard._dirty_age_seconds", return_value=7200), patch("tools.worktree_hygiene_guard.worktree_anchor_matches", return_value=True), patch("tools.worktree_hygiene_guard.busy_claim", return_value=(True, {})), patch("tools.worktree_hygiene_guard.busy_release"):
                result = quarantine_pressure("Vault", repo, "organicoverlords/regression-research:git-worktree-metadata", max_dirty=0)
            self.assertEqual(result["quarantined"], 0); move.assert_not_called()
