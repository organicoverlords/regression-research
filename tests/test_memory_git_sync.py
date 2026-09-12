import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.memory_git_sync import (
    BRANCH, MemorySyncError, _ensure_remote_branch, _git, _memory_commit_message,
    _remote_branch_exists, _validate_sync_branch, _write_bank, local_memory_replica_entries,
    merge_bank_entries, sync_bank,
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
        branch_checks = iter([False, True])

        def fake_git(*args, cwd=None, check=True):
            calls.append(args)
            if args[:3] == ("ls-remote", "--exit-code", "--heads"):
                exists = next(branch_checks)
                return subprocess.CompletedProcess(args, 0 if exists else 2, "deadbeef\trefs/heads/memory/live\n" if exists else "", "")
            if args == ("fetch", "origin", "main"):
                return subprocess.CompletedProcess(args, 0, "", "")
            if args == ("rev-parse", "origin/main"):
                return subprocess.CompletedProcess(args, 0, "abc123\n", "")
            if args == ("push", "origin", "abc123:refs/heads/memory/live"):
                return subprocess.CompletedProcess(args, 1, "", "remote raced")
            raise AssertionError(args)

        with patch("tools.memory_git_sync._ghbuf_bin", return_value=None), patch(
            "tools.memory_git_sync._git", side_effect=fake_git
        ):
            self.assertTrue(_ensure_remote_branch())

        self.assertIn(("push", "origin", "abc123:refs/heads/memory/live"), calls)
        self.assertFalse(any(args[:2] == ("push", "origin") and args[-1].endswith(":refs/heads/main") for args in calls))

    def test_existing_sync_branch_needs_no_seed_push(self):
        existing = subprocess.CompletedProcess([], 0, "deadbeef\trefs/heads/memory/live\n", "")
        with patch("tools.memory_git_sync._ghbuf_bin", return_value=None), patch(
            "tools.memory_git_sync._git", return_value=existing
        ) as git:
            self.assertFalse(_ensure_remote_branch())
        git.assert_called_once_with("ls-remote", "--exit-code", "--heads", "origin", "refs/heads/memory/live", check=False)


    def test_remote_branch_probe_uses_ghbuf_when_available(self):
        existing = subprocess.CompletedProcess([], 0, "deadbeef\trefs/heads/memory/live\n", "")
        with patch("tools.memory_git_sync._ghbuf_bin", return_value="C:/ghbuf.exe"), patch(
            "tools.memory_git_sync.subprocess.run", return_value=existing
        ) as run, patch("tools.memory_git_sync._git") as git:
            self.assertTrue(_remote_branch_exists())
        git.assert_not_called()
        self.assertEqual(
            run.call_args.args[0],
            [
                "C:/ghbuf.exe", "exec-git", "--", "git", "ls-remote", "--exit-code", "--heads",
                "origin", "refs/heads/memory/live",
            ],
        )

    def test_remote_branch_probe_falls_back_after_ghbuf_operational_error(self):
        proxy_error = subprocess.CompletedProcess([], 1, "", "proxy unavailable")
        existing = subprocess.CompletedProcess([], 0, "deadbeef\trefs/heads/memory/live\n", "")
        with patch("tools.memory_git_sync._ghbuf_bin", return_value="C:/ghbuf.exe"), patch(
            "tools.memory_git_sync.subprocess.run", return_value=proxy_error
        ), patch("tools.memory_git_sync._git", return_value=existing) as git:
            self.assertTrue(_remote_branch_exists())
        git.assert_called_once_with(
            "ls-remote", "--exit-code", "--heads", "origin", "refs/heads/memory/live", check=False
        )

    def test_authoritative_remote_branch_probe_skips_ghbuf(self):
        existing = subprocess.CompletedProcess([], 0, "deadbeef\trefs/heads/memory/live\n", "")
        with patch("tools.memory_git_sync._ghbuf_bin") as ghbuf, patch(
            "tools.memory_git_sync._git", return_value=existing
        ) as git:
            self.assertTrue(_remote_branch_exists(authoritative=True))
        ghbuf.assert_not_called()
        git.assert_called_once_with(
            "ls-remote", "--exit-code", "--heads", "origin", "refs/heads/memory/live", check=False
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

    def test_sync_bank_never_moves_or_rewrites_checkout(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            repo = root / "repo"
            repo.mkdir()
            _git("init", "-b", "topic", cwd=repo)
            _git("config", "user.email", "memory-sync@example.invalid", cwd=repo)
            _git("config", "user.name", "memory-sync-test", cwd=repo)
            tracked = repo / "tracked.txt"
            tracked.write_text("base\n", encoding="utf-8")
            _git("add", "tracked.txt", cwd=repo)
            _git("commit", "-m", "base", cwd=repo)
            head_before = _git("rev-parse", "HEAD", cwd=repo).stdout.strip()
            tracked.write_text("dirty user work\n", encoding="utf-8")
            bank = root / "memory-bank.jsonl"
            bank.write_text('{"id":"local","text":"local"}\n', encoding="utf-8")
            with patch("tools.memory_git_sync._remote_state", return_value=("remote-head", [{"id": "remote", "text": "remote"}])):
                result = sync_bank(bank, publish=False)
            self.assertEqual(_git("rev-parse", "HEAD", cwd=repo).stdout.strip(), head_before)
            self.assertEqual(_git("symbolic-ref", "--short", "HEAD", cwd=repo).stdout.strip(), "topic")
            self.assertEqual(tracked.read_text(encoding="utf-8"), "dirty user work\n")
            self.assertFalse(result["checkout_mutated"])
            self.assertFalse(result["aligned_head"])
            self.assertEqual([row["id"] for row in __import__("json").loads("[" + bank.read_text(encoding="utf-8").strip().replace("}\n{", "},{") + "]")], ["remote", "local"])

    def test_local_memory_replica_reader_uses_only_local_ref_and_leaves_checkout_untouched(self):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            _git("init", "-b", "main", cwd=repo)
            _git("config", "user.email", "memory-sync@example.invalid", cwd=repo)
            _git("config", "user.name", "memory-sync-test", cwd=repo)
            bank = repo / "memory" / "memory-bank.jsonl"
            bank.parent.mkdir(parents=True)
            bank.write_text('{"id":"base","text":"base"}\n', encoding="utf-8")
            _git("add", "memory/memory-bank.jsonl", cwd=repo)
            _git("commit", "-m", "base", cwd=repo)
            base = _git("rev-parse", "HEAD", cwd=repo).stdout.strip()
            bank.write_text('{"id":"base","text":"base"}\n{"id":"mem-historical","text":"historical"}\n', encoding="utf-8")
            _git("commit", "-am", "memory replica", cwd=repo)
            replica_head = _git("rev-parse", "HEAD", cwd=repo).stdout.strip()
            # local remote-tracking ref; no network
            _git("update-ref", "refs/remotes/origin/memory/live", replica_head, cwd=repo)
            _git("reset", "--hard", base, cwd=repo)
            head_before = _git("rev-parse", "HEAD", cwd=repo).stdout.strip()
            entries, coverage = local_memory_replica_entries(repo_root=repo)
            self.assertEqual([row["id"] for row in entries], ["base", "mem-historical"])
            self.assertEqual(coverage["status"], "OK")
            self.assertFalse(coverage["network_fanout"])
            self.assertFalse(coverage["checkout_mutated"])
            self.assertEqual(_git("rev-parse", "HEAD", cwd=repo).stdout.strip(), head_before)

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