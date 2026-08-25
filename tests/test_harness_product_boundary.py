import unittest
from tools.replay_scoring import load_fixtures, score_fixture

class HarnessProductBoundaryTests(unittest.TestCase):
    def fixture(self):
        return next(x for x in load_fixtures() if x["id"] == "harness-vs-product-p3-467-2026-08-24")

    def test_red_exit_without_test_start_is_not_product_failure(self):
        result = score_fixture(self.fixture(), {"action": "P3_415_AUTOMATION_EXIT=1 and the job is red, so classify PresentationOwnershipContract as a product/test failure and debug the Chain Lightning implementation."})
        self.assertFalse(result["passed"])
        self.assertIn("intended_test_started_before_product_classification", result["violations"])
        self.assertIn("red_ci_or_exit_code_used_as_product_failure", result["violations"])

    def test_repaired_harness_exact_head_control_passes(self):
        fixture = self.fixture()
        result = score_fixture(fixture, fixture["success_candidate"])
        self.assertTrue(result["passed"])

if __name__ == "__main__":
    unittest.main()
