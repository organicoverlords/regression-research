import json
import unittest
from copy import deepcopy
from pathlib import Path

from tools.replay_scoring import score_fixture, validate_fixture


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "03 Fixtures and Experiments" / "issue123-startup-memory-orchestration.json"


class Issue123StartupMemoryAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = validate_fixture(
            json.loads(FIXTURE_PATH.read_text(encoding="utf-8")),
            root=ROOT,
            filename=FIXTURE_PATH.name,
        )

    def score(self, candidate):
        return score_fixture(self.fixture, candidate)

    def good_candidate(self):
        candidate = deepcopy(self.fixture["success_candidate"])
        candidate["action"] += " Then continue the active task."
        return candidate

    def scenario(self, candidate, scenario_id):
        return next(item for item in candidate["scenarios"] if item["id"] == scenario_id)

    def test_positive_packet_covers_no_match_relevant_match_and_read_failure(self):
        result = self.score(self.good_candidate())
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["violations"], [])

    def test_first_reply_and_ten_title_boundaries_are_independently_enforced(self):
        reply_first = self.good_candidate()
        scenario = self.scenario(reply_first, "no-relevant-title")
        scenario["events"] = [scenario["events"][0], scenario["events"][2], scenario["events"][1]]
        result = self.score(reply_first)
        self.assertIn("startup_recent_titles_before_reply", result["violations"])

        wrong_limit = self.good_candidate()
        self.scenario(wrong_limit, "one-relevant-title")["events"][1]["limit"] = 20
        result = self.score(wrong_limit)
        self.assertIn("startup_recent_titles_limit_ten", result["violations"])

    def test_detail_read_requires_prior_relevance_and_default_full_load_is_rejected(self):
        irrelevant = self.good_candidate()
        detail = self.scenario(irrelevant, "one-relevant-title")["events"][3]
        detail["memory_id"] = "mem-other"
        result = self.score(irrelevant)
        self.assertIn("startup_detail_reads_require_relevance", result["violations"])

        overread = self.good_candidate()
        events = self.scenario(overread, "no-relevant-title")["events"]
        events.insert(2, {"kind": "corpus_search"})
        result = self.score(overread)
        self.assertIn("startup_full_memory_load_by_default", result["violations"])

    def test_failed_recent_read_continues_immediately_without_investigation(self):
        spiral = self.good_candidate()
        events = self.scenario(spiral, "recent-read-fails")["events"]
        events.insert(2, {"kind": "memory_failure_investigation"})
        result = self.score(spiral)
        self.assertIn("startup_failure_continues_immediately", result["violations"])
        self.assertIn("startup_failure_investigation", result["violations"])

    def test_explicit_failure_control_is_rejected(self):
        result = self.score(self.fixture["failure_candidate"])
        self.assertFalse(result["passed"])
        self.assertTrue(result["violations"])


if __name__ == "__main__":
    unittest.main()
