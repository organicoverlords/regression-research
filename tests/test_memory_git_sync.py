import subprocess
import unittest
from unittest.mock import patch

from tools.memory_git_sync import MemorySyncError, _git, merge_bank_entries


class MemoryGitSyncTests(unittest.TestCase):
    def test_remote_order_is_preserved_and_local_only_entries_append(self):
        remote = [{"id": "a", "text": "remote"}, {"id": "b", "text": "shared"}]
        local = [{"id": "a", "text": "remote"}, {"id": "b", "text": "shared"}, {"id": "c", "text": "local"}]
        self.assertEqual(merge_bank_entries(remote, local), remote + [local[-1]])

    def test_same_id_with_different_content_is_rejected(self):
        with self.assertRaises(MemorySyncError):
            merge_bank_entries([{"id": "same", "text": "one"}], [{"id": "same", "text": "two"}])

    @patch("tools.memory_git_sync.subprocess.run")
    def test_git_output_is_decoded_as_utf8(self, run):
        run.return_value = subprocess.CompletedProcess(["git", "status"], 0, "ok", "")

        _git("status")

        self.assertEqual(run.call_args.kwargs["encoding"], "utf-8")


if __name__ == "__main__":
    unittest.main()
