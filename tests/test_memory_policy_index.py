import unittest

from tools.memory_bank import load_bank, search_entries, source_relevance


class MemoryPolicyIndexTests(unittest.TestCase):
    def setUp(self):
        self.entries = load_bank()

    def test_current_policy_outranks_historical_snapshot(self):
        hits = search_entries(self.entries, "policy live state AGENTS mutation", history=True)
        ids = [entry["id"] for entry in hits]
        self.assertIn("mem-20260825-policy-live-state-current", ids)
        self.assertIn("mem-20260825-policy-live-state-v13", ids)
        current = next(entry for entry in hits if entry["id"].endswith("current"))
        historical = next(entry for entry in hits if entry["id"].endswith("v13"))
        self.assertGreater(source_relevance(current), source_relevance(historical))

    def test_ordinary_recall_hides_superseded_policy_snapshot(self):
        hits = search_entries(self.entries, "policy live state AGENTS mutation")
        ids = [entry["id"] for entry in hits]
        self.assertIn("mem-20260825-policy-live-state-current", ids)
        self.assertNotIn("mem-20260825-policy-live-state-v13", ids)

    def test_policy_entries_are_policy_not_user_preference(self):
        policy = [entry for entry in self.entries if entry["id"].startswith("mem-20260825-policy-live-state")]
        self.assertEqual({entry["kind"] for entry in policy}, {"decision"})
        self.assertFalse(any(entry["kind"] == "preference" for entry in policy))


if __name__ == "__main__":
    unittest.main()
