import unittest

from tools.benchmark_memory_retrieval import DEFAULT_BANK, DEFAULT_FIXTURE, evaluate as evaluate_general
from tools.benchmark_memory_behavior_retrieval import evaluate as evaluate_behavior
from tools.memory_bank import load_bank, search_context_memory


class MemoryRetrievalQualityTests(unittest.TestCase):
    def test_general_retrieval_quality_gate(self):
        result=evaluate_general(DEFAULT_BANK,DEFAULT_FIXTURE,"hybrid")
        self.assertGreaterEqual(result["metrics"]["paraphrase"]["recall_at_5"],0.95)
        self.assertEqual(result["metrics"]["exact_control"]["recall_at_1"],1.0)
        self.assertEqual(result["metrics"]["abstain"]["correct_abstention"],1.0)

    def test_normal_context_reserves_relevant_behavior_rules(self):
        entries = load_bank()
        cases = [
            ("when I correct one detail keep the rest of the task intact", "mem-20260829-f8a09d2b"),
            ("test my theories instead of agreeing with them", "mem-20260829-15f349c0"),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                ids = [entry["id"] for entry in search_context_memory(entries, query, limit=8)]
                self.assertIn(expected, ids[:2])

    def test_behavior_retrieval_covers_all_active_user_rules(self):
        result=evaluate_behavior()
        self.assertEqual(result["coverage"]["missing"],[])
        self.assertEqual(result["coverage"]["stale"],[])
        self.assertGreaterEqual(result["all"]["recall_at_8"],0.95)
        self.assertGreaterEqual(result["holdout"]["recall_at_8"],0.95)


if __name__ == "__main__": unittest.main()
