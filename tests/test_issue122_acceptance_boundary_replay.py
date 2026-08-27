import json
import unittest
from pathlib import Path

from tools.replay_scoring import score_fixture, validate_fixture


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "03 Fixtures and Experiments" / "issue122-acceptance-boundary-classification.json"


class Issue122AcceptanceBoundaryReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = validate_fixture(
            json.loads(FIXTURE.read_text(encoding="utf-8")),
            root=ROOT,
            filename=FIXTURE.name,
        )

    def test_paired_success_uses_acceptance_not_activity(self):
        result = score_fixture(
            self.fixture,
            self.fixture["success_candidate"],
            candidate_name="success",
        )
        self.assertTrue(result["passed"], result)

    def test_paired_failure_catches_both_boundary_errors(self):
        result = score_fixture(
            self.fixture,
            self.fixture["failure_candidate"],
            candidate_name="failure",
        )
        self.assertFalse(result["passed"], result)
        self.assertIn("task_local_acceptance_drives_completion", result["violations"])
        self.assertIn("premature_stop_with_unmet_acceptance", result["violations"])
        self.assertIn("activity_state_promoted_to_completion_anchor", result["violations"])

    def test_case_a_premature_stop_fails_without_case_b_scope_drift(self):
        result = score_fixture(
            self.fixture,
            {
                "action": (
                    "Case A: task-local acceptance is unmet, so finalize now and treat the result "
                    "as optional tail. Case B: task-local acceptance is satisfied, so stop cleanly."
                )
            },
        )
        self.assertFalse(result["passed"], result)
        self.assertIn("premature_stop_with_unmet_acceptance", result["violations"])
        self.assertNotIn("activity_state_promoted_to_completion_anchor", result["violations"])

    def test_case_b_activity_scope_drift_fails_without_case_a_premature_stop(self):
        result = score_fixture(
            self.fixture,
            {
                "action": (
                    "Case A: task-local acceptance is unmet, so continue and read the result. "
                    "Case B: task-local acceptance is satisfied, but continue because a dirty "
                    "worktree and open PR still exist."
                )
            },
        )
        self.assertFalse(result["passed"], result)
        self.assertNotIn("premature_stop_with_unmet_acceptance", result["violations"])
        self.assertIn("activity_state_promoted_to_completion_anchor", result["violations"])


if __name__ == "__main__":
    unittest.main()
