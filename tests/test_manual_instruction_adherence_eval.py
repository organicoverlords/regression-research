import json
import tempfile
import unittest
from pathlib import Path

from tools.manual_instruction_adherence_eval import (
    DEFAULT_SUITE,
    evaluate_case,
    load_responses,
    load_suite,
    score_suite,
    selftest_suite,
)


class ManualInstructionAdherenceEvalTests(unittest.TestCase):
    def setUp(self):
        self.suite = load_suite(DEFAULT_SUITE)

    def test_canonical_suite_selftests_both_directions(self):
        result = selftest_suite(self.suite)
        self.assertTrue(result["passed"], result["failures"])
        self.assertGreaterEqual(result["case_count"], 10)

    def test_positive_controls_score_100_hard_and_soft(self):
        responses = {case["id"]: case["positive_response"] for case in self.suite["cases"]}
        result = score_suite(self.suite, responses)
        self.assertTrue(result["all_cases_evaluated"])
        self.assertEqual(result["hard_satisfaction_rate"], 100.0)
        self.assertEqual(result["soft_satisfaction_rate"], 100.0)

    def test_negative_controls_fail_every_case(self):
        responses = {case["id"]: case["negative_response"] for case in self.suite["cases"]}
        result = score_suite(self.suite, responses)
        self.assertEqual(result["hard_satisfaction_rate"], 0.0)
        self.assertLess(result["soft_satisfaction_rate"], 100.0)
        self.assertTrue(all(not row["passed"] for row in result["cases"]))

    def test_hard_rate_and_soft_rate_are_separate(self):
        case = next(item for item in self.suite["cases"] if item["id"] == "compound_constraints")
        result = evaluate_case(case, "OK, partial DONE")
        self.assertFalse(result["passed"])
        self.assertEqual(result["passed_checks"], 2)
        self.assertEqual(result["total_checks"], 3)

    def test_json_shape_rejects_extra_fields(self):
        case = next(item for item in self.suite["cases"] if item["id"] == "exact_json_shape")
        self.assertTrue(evaluate_case(case, '{"answer":4}')["passed"])
        self.assertFalse(evaluate_case(case, '{"answer":4,"extra":true}')["passed"])
        self.assertFalse(evaluate_case(case, "answer: 4")["passed"])

    def test_missing_responses_do_not_silently_count_as_pass(self):
        case = self.suite["cases"][0]
        result = score_suite(self.suite, {case["id"]: case["positive_response"]})
        self.assertFalse(result["all_cases_evaluated"])
        self.assertEqual(result["evaluated_case_count"], 1)
        self.assertEqual(result["missing_case_count"], len(self.suite["cases"]) - 1)

    def test_response_jsonl_rejects_duplicate_case_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "responses.jsonl"
            path.write_text(
                json.dumps({"case_id": "x", "response": "a"}) + "\n" +
                json.dumps({"case_id": "x", "response": "b"}) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate case_id"):
                load_responses(path)

    def test_unknown_case_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown cases"):
            score_suite(self.suite, {"does-not-exist": "anything"})

    def test_categories_report_hard_and_soft_rates(self):
        responses = {case["id"]: case["positive_response"] for case in self.suite["cases"]}
        result = score_suite(self.suite, responses)
        self.assertIn("hierarchy", result["by_category"])
        self.assertEqual(result["by_category"]["hierarchy"]["hard_satisfaction_rate"], 100.0)
        self.assertEqual(result["by_category"]["hierarchy"]["soft_satisfaction_rate"], 100.0)


if __name__ == "__main__":
    unittest.main()
