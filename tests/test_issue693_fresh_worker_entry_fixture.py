import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "03 Fixtures and Experiments" / "issue693-fresh-worker-entry.json"
DECISIONS = {"reuse_resume", "complement", "review_prove", "integrate", "new"}

class Issue693FreshWorkerEntryFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(FIXTURE.read_text(encoding="utf-8-sig"))
        cls.cases = {case["id"]: case for case in cls.payload["cases"]}

    def test_fixture_uses_only_issue_decision_vocabulary(self):
        self.assertEqual(set(self.payload["decision_vocabulary"]), DECISIONS)
        for case in self.cases.values():
            expected = case["expected"]
            self.assertLessEqual(set(expected["allowed_decisions"]), DECISIONS)
            self.assertLessEqual(set(expected["forbidden_decisions"]), DECISIONS)

    def test_history_can_never_establish_current_liveness(self):
        for case in self.cases.values():
            history = case["history"]
            self.assertEqual(history["authority"], "HISTORY_ONLY")
            self.assertFalse(history["may_establish_current_liveness"])

    def test_hummingbird_overlap_forbids_duplicate_new_implementation(self):
        case = self.cases["hummingbird_overlap"]
        current = case["current_evidence"]
        expected = case["expected"]
        self.assertIn("targeted_repo_wip", current["required_classes"])
        self.assertIn("exact_busy_scope", current["required_classes"])
        self.assertTrue(current["example"]["targeted_repo_wip"]["planned_scope_overlap"])
        self.assertTrue(current["example"]["exact_busy_scope"]["planned_scope_overlap"])
        self.assertIn("new", expected["forbidden_decisions"])
        self.assertTrue(expected["must_select_nonduplicate_contribution"])
        self.assertIn("no_prior_work", expected["forbidden_conclusions"])
        self.assertGreaterEqual(len(case["history"]["required_primary_anchors"]), 4)
        self.assertGreaterEqual(len(case["history"]["must_avoid_wrong_approaches"]), 4)

    def test_negative_control_stays_fast_and_skips_archaeology(self):
        case = self.cases["routine_small_fix_negative_control"]
        self.assertEqual(case["history"]["relevant_items"], [])
        self.assertEqual(case["expected"]["allowed_decisions"], ["new"])
        self.assertTrue(case["expected"]["archaeology_forbidden"])
        self.assertTrue(case["expected"]["broad_scan_forbidden"])
        self.assertTrue(case["expected"]["must_remain_fast"])

if __name__ == "__main__":
    unittest.main()
