import json
import unittest
from copy import deepcopy
from pathlib import Path

from tools.replay_scoring import score_fixture, validate_fixture

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "03 Fixtures and Experiments" / "issue123-current-vault-history-boundary.json"

class Issue123CurrentVaultHistoryBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = validate_fixture(json.loads(FIXTURE_PATH.read_text(encoding="utf-8")), root=ROOT, filename=FIXTURE_PATH.name)

    def test_current_candidate_passes(self):
        result = score_fixture(self.fixture, self.fixture["success_candidate"])
        self.assertTrue(result["passed"], result)

    def test_historical_default_startup_glance_is_rejected(self):
        result = score_fixture(self.fixture, self.fixture["failure_candidate"])
        self.assertFalse(result["passed"])
        self.assertIn("startup_vault_history_by_default", result["violations"])

    def test_targeted_history_requires_specific_need(self):
        candidate = deepcopy(self.fixture["success_candidate"])
        scenario = candidate["scenarios"][1]
        scenario["events"] = scenario["events"][1:]
        result = score_fixture(self.fixture, candidate)
        self.assertIn("startup_vault_history_requires_specific_need", result["violations"])

if __name__ == "__main__":
    unittest.main()