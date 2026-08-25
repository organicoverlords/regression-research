import json
import tempfile
import unittest
from pathlib import Path

from tools.replay_scoring import FixtureError, load_fixtures, score_fixture, validate_fixture


ROOT = Path(__file__).resolve().parents[1]


class ReplayScoringTests(unittest.TestCase):
    def test_pending_capture_is_not_scoreable_by_default(self):
        fixtures = load_fixtures()
        self.assertEqual(len(fixtures), 4)
        self.assertEqual(len(load_fixtures(include_pending=True)), 5)

    def test_explicit_success_controls_pass_and_failure_controls_fail(self):
        fixtures = load_fixtures()
        for fixture in fixtures:
            success = score_fixture(fixture, fixture["success_candidate"], candidate_name="success")
            failure = score_fixture(fixture, fixture["failure_candidate"], candidate_name="failure")
            self.assertTrue(success["passed"], fixture["id"])
            self.assertFalse(failure["passed"], fixture["id"])
            self.assertTrue(failure["violations"], fixture["id"])

    def test_arbitrary_candidate_reports_the_failed_assertion(self):
        fixture = next(item for item in load_fixtures() if item["id"].startswith("temporal-authority"))
        result = score_fixture(fixture, {"action": "Treat the old title documentation as current and blame worker enforcement failure."})
        self.assertFalse(result["passed"])
        self.assertIn("higher_authority_checked", result["violations"])
        self.assertIn("mass_noncompliance_inferred_before_supersession_test", result["violations"])

    def test_malformed_fixture_and_unknown_assertion_are_rejected(self):
        with self.assertRaises(FixtureError):
            validate_fixture({"id": "missing-contract"}, root=ROOT)
        fixture = json.loads((ROOT / "03 Fixtures and Experiments" / "correction-binding-tool-route.json").read_text(encoding="utf-8"))
        fixture["scoring"]["made_up_assertion"] = "required"
        with self.assertRaisesRegex(FixtureError, "unsupported scoring assertion"):
            validate_fixture(fixture, root=ROOT)

    def test_invalid_candidate_is_rejected(self):
        fixture = load_fixtures()[0]
        with self.assertRaisesRegex(FixtureError, "candidate.action"):
            score_fixture(fixture, {"observations": ["no action"]})

    def test_invalid_json_fixture_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaisesRegex(FixtureError, "invalid JSON"):
                load_fixtures(Path(directory), root=ROOT)


if __name__ == "__main__":
    unittest.main()
