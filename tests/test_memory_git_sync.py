import tempfile
import unittest
from pathlib import Path

from tools.memory_git_sync import MemorySyncError, _git, merge_bank_entries


class MemoryGitSyncTests(unittest.TestCase):
    def test_remote_order_is_preserved_and_local_only_entries_append(self):
        remote = [{"id": "a", "text": "remote"}, {"id": "b", "text": "shared"}]
        local = [{"id": "a", "text": "remote"}, {"id": "b", "text": "shared"}, {"id": "c", "text": "local"}]
        self.assertEqual(merge_bank_entries(remote, local), remote + [local[-1]])

    def test_same_id_with_different_content_is_rejected(self):
        with self.assertRaises(MemorySyncError):
            merge_bank_entries([{"id": "same", "text": "one"}], [{"id": "same", "text": "two"}])

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