import tempfile
import unittest
from pathlib import Path

from tools.memory_git_sync import MemorySyncError, _align_checkout, _git, merge_bank_entries


class MemoryGitSyncTests(unittest.TestCase):
    def test_remote_order_is_preserved_and_local_only_entries_append(self):
        remote = [{"id": "a", "text": "remote"}, {"id": "b", "text": "shared"}]
        local = [{"id": "a", "text": "remote"}, {"id": "b", "text": "shared"}, {"id": "c", "text": "local"}]
        self.assertEqual(merge_bank_entries(remote, local), remote + [local[-1]])

    def test_same_id_with_different_content_is_rejected(self):
        with self.assertRaises(MemorySyncError):
            merge_bank_entries([{"id": "same", "text": "one"}], [{"id": "same", "text": "two"}])

    def test_align_checkout_fast_forwards_memory_commit_preserving_other_dirty_work(self):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            _git("init", "-b", "main", cwd=repo)
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
            _git("update-ref", "refs/remotes/origin/main", target, cwd=repo)
            _git("config", "branch.main.remote", "origin", cwd=repo)
            _git("config", "branch.main.merge", "refs/heads/main", cwd=repo)

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