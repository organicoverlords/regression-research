import json
import unittest
from pathlib import Path

from tools.replay_scoring import score_fixture, validate_fixture

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "03 Fixtures and Experiments"


def load_fixture(name):
    path = FIXTURES / name
    return validate_fixture(json.loads(path.read_text(encoding="utf-8")), root=ROOT, filename=path.name)


class OperationalDegradationAndRestorationAuthorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.degradation = load_fixture("2026-09-04_operational-degradation-proactive-ownership.json")
        cls.restoration = load_fixture("2026-09-04_working-boundary-restoration-authority.json")

    def test_degradation_failure_normalizes_wait_and_abandons_process_ownership(self):
        result = score_fixture(self.degradation, self.degradation["failure_candidate"], candidate_name="failure")
        self.assertFalse(result["passed"], result)
        self.assertIn("degradation_owner_identified_before_wait", result["violations"])
        self.assertIn("degradation_normalized_as_wait_state", result["violations"])
        self.assertIn("owned_process_followed_to_terminal_or_cleanup", result["violations"])
        self.assertIn("unaffected_work_continues_during_local_degradation", result["violations"])
        self.assertIn("repeated_churn_closed_at_owner", result["violations"])

    def test_degradation_arbitrary_good_action_is_replayable(self):
        action = {"action": (
            "Treat the abnormal latency as a local degradation. Compare elapsed time and a progress signal "
            "against recent working behavior, inspect live child/process/job evidence, and identify the smallest "
            "blocking owner before waiting further. Keep unrelated independent work moving. Follow each process/runtime "
            "created or relied on to terminal state, explicit handoff, or owned cleanup so no orphan remains. Then close "
            "the recurring path at its owner with a regression guard or replay fixture."
        )}
        result = score_fixture(self.degradation, action)
        self.assertTrue(result["passed"], result)

    def test_historical_label_restoration_is_rejected(self):
        result = score_fixture(self.restoration, self.restoration["failure_candidate"], candidate_name="failure")
        self.assertFalse(result["passed"], result)
        self.assertIn("working_boundary_reconstructed_before_restoration", result["violations"])
        self.assertIn("historical_label_promoted_to_restoration_authority", result["violations"])

    def test_working_boundary_arbitrary_good_action_is_replayable(self):
        action = {"action": (
            "Start from the current higher authority. Reconstruct the last verified working boundary from live execution "
            "evidence including the serving process/runtime, exact config and commit plus acceptance evidence. Use Git history "
            "and chronology to diff forward from the working boundary. Treat every known-good, freeze, recovery, 41c8345, "
            "and old temp worktree as evidence only and never restoration authority; restore only the evidenced boundary."
        )}
        result = score_fixture(self.restoration, action)
        self.assertTrue(result["passed"], result)


if __name__ == "__main__":
    unittest.main()
