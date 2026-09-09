import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.memory_git_sync import (
    BRANCH,
    REPO_ROOT,
    MemorySyncError,
    _accelerated_remote_branch_probe,
    _align_checkout,
    _ensure_remote_branch,
    _git,
    _memory_commit_message,
    _remote_branch_exists,
    _validate_sync_branch,
    _write_bank,
    merge_bank_entries,
)


class MemoryGitSyncTests(unittest.TestCase):
    def test_memory_sync_uses_dedicated_non_protected_branch(self):
        self.assertEqual(BRANCH, "memory/live")
        _validate_sync_branch()
        with patch("tools.memory_git_sync.BRANCH", "main"):
            with self.assertRaisesRegex(MemorySyncError, "refuses protected branch"):
                _validate_sync_branch()

    def test_missing_sync_branch_is_recreated_from_main_without_pushing_main(self):
        calls = []
        accelerated_missing = subprocess.CompletedProcess([], 2, "", "")

        def fake_git(*args, cwd=None, check=True):
            calls.append(args)
            if args[:3] == ("ls-remote", "--exit-code", "--heads"):
                return subprocess.CompletedProcess(args, 0, "deadbeef\trefs/heads/memory/live\n", "")
            if args == ("fetch", "origin", "main"):
                return subprocess.CompletedProcess(args, 0, "", "")
            if args == ("rev-parse", "origin/main"):
                return subprocess.CompletedProcess(args, 0, "abc123\n", "")
            if args == ("push", "origin", "abc123:refs/heads/memory/live"):
                return subprocess.CompletedProcess(args, 1, "", "remote raced")
            raise AssertionError(args)

        with patch(
            "tools.memory_git_sync._accelerated_remote_branch_probe", return_value=accelerated_missing
        ) as accelerated, patch("tools.memory_git_sync._git", side_effect=fake_git):
            self.assertTrue(_ensure_remote_branch())

        accelerated.assert_called_once_with()
        self.assertIn(("push", "origin", "abc123:refs/heads/memory/live"), calls)
        self.assertIn(("ls-remote", "--exit-code", "--heads", "origin", "refs/heads/memory/live"), calls)
        self.assertFalse(any(args[:2] == ("push", "origin") and args[-1].endswith(":refs/heads/main") for args in calls))

    def test_existing_sync_branch_uses_accelerated_probe_without_direct_git(self):
        existing = subprocess.CompletedProcess([], 0, "deadbeef\trefs/heads/memory/live\n", "")
        with patch(
            "tools.memory_git_sync._accelerated_remote_branch_probe", return_value=existing
        ), patch("tools.memory_git_sync._git") as git:
            self.assertFalse(_ensure_remote_branch())
        git.assert_not_called()

    def test_accelerator_failure_falls_back_to_direct_git(self):
        failed = subprocess.CompletedProcess([], 1, "", "proxy unavailable")
        existing = subprocess.CompletedProcess([], 0, "deadbeef\trefs/heads/memory/live\n", "")
        with patch(
            "tools.memory_git_sync._accelerated_remote_branch_probe", return_value=failed
        ), patch("tools.memory_git_sync._git", return_value=existing) as git:
            self.assertTrue(_remote_branch_exists())
        git.assert_called_once_with(
            "ls-remote", "--exit-code", "--heads", "origin", "refs/heads/memory/live", check=False
        )

    def test_accelerated_probe_invokes_git_only_rust_lane(self):
        completed = subprocess.CompletedProcess([], 0, "deadbeef\trefs/heads/memory/live\n", "")
        with patch("tools.memory_git_sync._ghbuf_executable", return_value="ghbuf"), patch(
            "tools.memory_git_sync.subprocess.run", return_value=completed
        ) as run:
            self.assertIs(_accelerated_remote_branch_probe(), completed)
        run.assert_called_once_with(
            [
                "ghbuf",
                "exec-git",
                "--",
                "git",
                "ls-remote",
                "--exit-code",
                "--heads",
                "origin",
                "refs/heads/memory/live",
            ],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
        )

    def test_remote_order_is_preserved_and_local_only_entries_append(self):
        remote = [{"id": "a", "text": "remote"}, {"id": "b", "text": "shared"}]
        local = [{"id": "a", "text": "remote"}, {"id": "b", "text": "shared"}, {"id": "c", "text": "local"}]
        self.assertEqual(merge_bank_entries(remote, local), remote + [local[-1]])

    def test_memory_sync_commit_message_names_changed_ids(self):
        entries = [{"id": "mem-a", "title": "Review architecture first", "kind": "correction", "scope": "assistant"}]
        subject, body = _memory_commit_message(entries, {"mem-a"})
        self.assertEqual(subject, "memory: add mem-a")
        self.assertIn("mem-a: Review architecture first", body)

    def test_same_id_with_different_content_is_rejected(self):
        with self.assertRaises(MemorySyncError):
            merge_bank_entries([{"id": "same", "text": "one"}], [{"id": "same", "text": "two"}])

    def test_windows_replace_lock_falls_back_to_verified_in_place_rewrite(self):
        with tempfile.TemporaryDirectory() as raw:
            bank = Path(raw) / "memory-bank.jsonl"
            bank.write_text('{"id":"old"}\n', encoding="utf-8", newline="\n")
            entries = [{"id": "new", "text": "replacement"}]
            with patch("tools.memory_git_sync.IS_WINDOWS", True), patch(
                "tools.memory_git_sync.os.replace", side_effect=PermissionError(13, "locked")
            ):
                _write_bank(bank, entries)
            self.assertEqual(bank.read_text(encoding="utf-8"), '{"id":"new","text":"replacement"}\n')
            self.assertFalse(bank.with_name(bank.name + ".sync-tmp").exists())

    def test_non_windows_replace_permission_error_stays_fail_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            bank = Path(raw) / "memory-bank.jsonl"
            bank.write_text('{"id":"old"}\n', encoding="utf-8", newline="\n")
            with patch("tools.memory_git_sync.IS_WINDOWS", False), patch(
                "tools.memory_git_sync.os.replace", side_effect=PermissionError(13, "denied")
            ):
                with self.assertRaises(PermissionError):
                    _write_bank(bank, [{"id": "new"}])
            self.assertEqual(bank.read_text(encoding="utf-8"), '{"id":"old"}\n')
            self.assertTrue(bank.with_name(bank.name + ".sync-tmp").exists())

    def test_align_checkout_fast_forwards_memory_commit_preserving_other_dirty_work(self):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            _git("init", "-b", "memory/live", cwd=repo)
            _git("config", "user.email", "memory-sync@example.invalid", cwd=repo)
            _git("config", "user.name", "memory-sync-test", cwd=repo)
            bank = repo / "memory" / "memory-bank.jsonl"
            bank.parent.mkdir(parents=True)
            bank.write_text('{"id":"old"}\n', encoding="utf-8", newline="\n")
            agents = repo / "AGENTS.md"
            agents.write_text("base\n", encoding="utf-8")
            _git("add", "memory/memory-bank.jsonl", "AGENTS.md", cwd=repo)
            _git("commit", "-m", "base", cwd=repo)
            base = _git("rev-parse", "HEAD", cwd=repo).stdout.strip()

            bank.write_text('{"id":"old"}\n{"id":"new"}\n', encoding="utf-8", newline="\n")
            _git("add", "memory/memory-bank.jsonl", cwd=repo)
            _git("commit", "-m", "remote memory", cwd=repo)
            target = _git("rev-parse", "HEAD", cwd=repo).stdout.strip()
            _git("reset", "--hard", base, cwd=repo)
            _git("remote", "add", "origin", str(repo), cwd=repo)
            _git("update-ref", "refs/remotes/origin/memory/live", target, cwd=repo)
            _git("branch", "--set-upstream-to", "origin/memory/live", "memory/live", cwd=repo)

            agents.write_text("dirty policy work\n", encoding="utf-8")
            bank.write_text('{"id":"old"}\n{"id":"new"}\n', encoding="utf-8", newline="\n")
            self.assertTrue(_align_checkout(target, bank, repo_root=repo))
            self.assertEqual(_git("rev-parse", "HEAD", cwd=repo).stdout.strip(), target)
            self.assertEqual(agents.read_text(encoding="utf-8"), "dirty policy work\n")
            self.assertEqual(_git("status", "--porcelain", cwd=repo).stdout.splitlines(), [" M AGENTS.md"])

    def test_git_output_is_decoded_as_utf8(self):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            _git("init", cwd=repo)
            _git("config", "user.email", "memory-sync@example.invalid", cwd=repo)
            _git("config", "user.name", "memory-sync-test", cwd=repo)
            expected = "incident " + chr(0x2014) + " unicode survives\n"
            (repo / "unicode.txt").write_text(expected, encoding="utf-8", newline="\n")
            _git("add", "unicode.txt", cwd=repo)
            _git("commit", "-m", "unicode fixture", cwd=repo)
            shown = _git("show", "HEAD:unicode.txt", cwd=repo).stdout
            self.assertEqual(shown, expected)


if __name__ == "__main__":
    unittest.main()