import unittest

from tools.memory_git_sync import MemorySyncError, merge_bank_entries


class MemoryGitSyncTests(unittest.TestCase):
    def test_remote_order_is_preserved_and_local_only_entries_append(self):
        remote = [{"id": "a", "text": "remote"}, {"id": "b", "text": "shared"}]
        local = [{"id": "a", "text": "remote"}, {"id": "b", "text": "shared"}, {"id": "c", "text": "local"}]
        self.assertEqual(merge_bank_entries(remote, local), remote + [local[-1]])

    def test_same_id_with_different_content_is_rejected(self):
        with self.assertRaises(MemorySyncError):
            merge_bank_entries([{"id": "same", "text": "one"}], [{"id": "same", "text": "two"}])


if __name__ == "__main__":
    unittest.main()