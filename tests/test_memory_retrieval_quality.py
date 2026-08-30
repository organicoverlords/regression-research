import unittest
from unittest.mock import patch

from tools.benchmark_memory_retrieval import DEFAULT_BANK, DEFAULT_FIXTURE, evaluate as evaluate_general
from tools import benchmark_memory_behavior_retrieval as behavior_benchmark
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

    def test_behavior_retrieval_quality_for_curated_cases(self):
        result=behavior_benchmark.evaluate()
        self.assertEqual(result["coverage"]["stale"],[])
        self.assertGreaterEqual(result["all"]["recall_at_8"],0.95)
        self.assertGreaterEqual(result["holdout"]["recall_at_8"],0.95)

    def test_new_active_rule_does_not_require_fixture_update(self):
        original = behavior_benchmark.behavioral_context

        def with_unrepresented_rule(entries):
            return [
                *original(entries),
                {
                    "id": "mem-synthetic-new-rule",
                    "behavioral_authority": {"role": behavior_benchmark.ROLE_USER},
                },
            ]

        with patch.object(behavior_benchmark, "behavioral_context", side_effect=with_unrepresented_rule):
            result = behavior_benchmark.evaluate()

        self.assertIn("mem-synthetic-new-rule", result["coverage"]["missing"])
        self.assertGreaterEqual(result["all"]["recall_at_8"], 0.95)
        self.assertGreaterEqual(result["holdout"]["recall_at_8"], 0.95)


if __name__ == "__main__": unittest.main()
