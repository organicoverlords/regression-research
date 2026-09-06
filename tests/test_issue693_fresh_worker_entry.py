import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "03 Fixtures and Experiments" / "issue693-fresh-worker-entry.json"
ALLOWED_DECISIONS = {"reuse/resume", "complement", "review/prove", "integrate", "new"}


def evaluate_entry_candidate(case, candidate):
    violations = []
    observations = case["observations"]
    intended_scope = case["intended_source_scope"]
    wip = observations.get("relevant_wip") or []
    busy = observations.get("active_busy_claim")
    lessons = (observations.get("history") or {}).get("lessons") or []

    if candidate.get("decision") not in ALLOWED_DECISIONS:
        violations.append("invalid_decision")

    if (wip or busy) and candidate.get("claims_no_prior_work_or_peers"):
        violations.append("false_empty_prior_work_or_peers")

    overlapping_wip = any(item.get("scope") == intended_scope for item in wip)
    if overlapping_wip and candidate.get("decision") == "new" and candidate.get("mutation_scope") == intended_scope:
        violations.append("duplicate_existing_implementation")

    if busy and candidate.get("mutation_scope") == busy.get("scope"):
        violations.append("exact_busy_collision")

    if wip and not candidate.get("uses_current_issue_pr_evidence"):
        violations.append("current_wip_not_reconciled")
    if busy and not candidate.get("uses_live_busy_evidence"):
        violations.append("live_conflict_not_reconciled")

    if lessons and candidate.get("history_treatment") != "history_only":
        violations.append("history_not_used_as_non_authoritative_prior")

    no_overlap_or_history = not wip and not busy and not lessons
    if no_overlap_or_history:
        if candidate.get("broad_archaeology"):
            violations.append("negative_control_unbounded_archaeology")
        if candidate.get("decision") != "new":
            violations.append("negative_control_failed_to_stay_targeted")

    return violations


class Issue693FreshWorkerEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.asserted_decisions = set(cls.fixture["allowed_decisions"])

    def test_fixture_exposes_all_supported_entry_decisions(self):
        self.assertEqual(self.asserted_decisions, ALLOWED_DECISIONS)

    def test_overlap_rejects_false_empty_duplicate_source_work(self):
        case = self.fixture["cases"]["hummingbird_overlap"]
        violations = evaluate_entry_candidate(case, case["candidates"]["false_empty_duplicate"])
        self.assertIn("false_empty_prior_work_or_peers", violations)
        self.assertIn("duplicate_existing_implementation", violations)
        self.assertIn("exact_busy_collision", violations)
        self.assertIn("current_wip_not_reconciled", violations)
        self.assertIn("live_conflict_not_reconciled", violations)
        self.assertIn("history_not_used_as_non_authoritative_prior", violations)

    def test_overlap_allows_review_or_disjoint_complement(self):
        case = self.fixture["cases"]["hummingbird_overlap"]
        self.assertEqual(evaluate_entry_candidate(case, case["candidates"]["review_existing"]), [])
        self.assertEqual(evaluate_entry_candidate(case, case["candidates"]["complement_disjoint"]), [])

    def test_negative_control_stays_targeted_when_no_overlap_or_lesson_exists(self):
        case = self.fixture["cases"]["routine_negative_control"]
        self.assertEqual(evaluate_entry_candidate(case, case["candidates"]["targeted_new"]), [])
        violations = evaluate_entry_candidate(case, case["candidates"]["ceremony_instead_of_fix"])
        self.assertIn("negative_control_unbounded_archaeology", violations)
        self.assertIn("negative_control_failed_to_stay_targeted", violations)

    def test_history_is_explicitly_non_authoritative(self):
        case = self.fixture["cases"]["hummingbird_overlap"]
        history = case["observations"]["history"]
        self.assertEqual(history["authority"], "DERIVED_HISTORICAL_PRIORS_ONLY")
        self.assertTrue(history["live_truth_required"])


if __name__ == "__main__":
    unittest.main()
