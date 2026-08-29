import unittest

from tools.benchmark_memory_retrieval import DEFAULT_BANK, DEFAULT_FIXTURE, evaluate as evaluate_general
from tools.benchmark_memory_behavior_retrieval import evaluate as evaluate_behavior


class MemoryRetrievalQualityTests(unittest.TestCase):
    def test_general_retrieval_quality_gate(self):
        result=evaluate_general(DEFAULT_BANK,DEFAULT_FIXTURE,"hybrid")
        self.assertGreaterEqual(result["metrics"]["paraphrase"]["recall_at_5"],0.95)
        self.assertEqual(result["metrics"]["exact_control"]["recall_at_1"],1.0)
        self.assertEqual(result["metrics"]["abstain"]["correct_abstention"],1.0)

    def test_behavior_retrieval_covers_all_active_user_rules(self):
        result=evaluate_behavior()
        self.assertEqual(result["coverage"]["missing"],[])
        self.assertEqual(result["coverage"]["stale"],[])
        self.assertGreaterEqual(result["all"]["recall_at_8"],0.95)
        self.assertGreaterEqual(result["holdout"]["recall_at_8"],0.95)


if __name__ == "__main__": unittest.main()
