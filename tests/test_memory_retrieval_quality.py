import unittest

from tools.benchmark_memory_retrieval import DEFAULT_BANK, DEFAULT_FIXTURE, evaluate as evaluate_general
from tools.memory_bank import search_context_memory


class MemoryRetrievalQualityTests(unittest.TestCase):
    def test_general_retrieval_quality_gate(self):
        result = evaluate_general(DEFAULT_BANK, DEFAULT_FIXTURE)
        self.assertGreaterEqual(result["metrics"]["paraphrase"]["recall_at_5"], 0.95)
        self.assertEqual(result["metrics"]["exact_control"]["recall_at_1"], 1.0)
        self.assertEqual(result["metrics"]["abstain"]["correct_abstention"], 1.0)

    def test_context_retrieval_is_relevance_based(self):
        entries = [
            {"id": "relevant", "timestamp": "2026-08-27T10:00:00+03:00", "kind": "lesson", "scope": "global", "tags": [],
             "title": "Preserve inherited task", "text": "Preserve inherited task when one detail changes", "state": "PROVEN",
             "evidence": ["user-instruction:test"], "supersedes": [], "behavior_rule": True},
            {"id": "other", "timestamp": "2026-08-27T10:01:00+03:00", "kind": "lesson", "scope": "global", "tags": [],
             "title": "Unrelated cache note", "text": "Unrelated cache cleanup evidence", "state": "PROVEN",
             "evidence": ["incident:test"], "supersedes": []},
        ]
        hits = search_context_memory(entries, "preserve inherited", limit=8)
        self.assertEqual([entry["id"] for entry in hits], ["relevant"])


if __name__ == "__main__":
    unittest.main()
