import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "02 Evidence" / "positive-correction-cases.json"


def _message(transcript: Path, number: int):
    text = transcript.read_text(encoding="utf-8-sig", errors="replace")
    pattern = re.compile(
        rf"^===== {number} (USER|ASSISTANT|TOOL|SYSTEM) =====\r?\n(.*?)(?=^===== \d+ (?:USER|ASSISTANT|TOOL|SYSTEM) =====|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return None, ""
    return match.group(1), match.group(2).strip()


class PositiveCorrectionCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(CASES.read_text(encoding="utf-8-sig"))
        cls.cases = cls.payload["cases"]

    def test_at_least_three_distinct_positive_cases_cover_required_classes(self):
        self.assertGreaterEqual(len(self.cases), 3)
        self.assertEqual(len({case["id"] for case in self.cases}), len(self.cases))
        self.assertTrue({"correction_binding", "scope_control", "authority_resolution"}.issubset(
            {case["failure_class"] for case in self.cases}
        ))

    def test_each_case_has_direct_transcript_provenance_and_real_message_pair(self):
        for case in self.cases:
            transcript = ROOT / case["source_transcript"]
            self.assertTrue(transcript.is_file(), case["id"])
            user_role, user_body = _message(transcript, case["source_user_message"])
            assistant_role, assistant_body = _message(transcript, case["source_assistant_message"])
            self.assertEqual(user_role, "USER", case["id"])
            self.assertEqual(assistant_role, "ASSISTANT", case["id"])
            self.assertTrue(user_body, case["id"])
            self.assertTrue(assistant_body, case["id"])
            self.assertGreater(case["source_assistant_message"], case["source_user_message"])

    def test_each_case_pairs_to_existing_failure_fixture_and_matches_class(self):
        for case in self.cases:
            fixture_path = ROOT / case["pairs_with_fixture"]
            self.assertTrue(fixture_path.is_file(), case["id"])
            fixture = json.loads(fixture_path.read_text(encoding="utf-8-sig"))
            self.assertEqual(fixture["incident_class"], case["failure_class"], case["id"])

    def test_behavioral_delta_is_explicit_without_title_dependency(self):
        required = {
            "inherited_objective", "correction", "next_substantive_action",
            "preserved_state", "decisive_evidence", "discriminating_difference",
        }
        for case in self.cases:
            self.assertTrue(required.issubset(case), case["id"])
            self.assertGreaterEqual(len(case["preserved_state"]), 2, case["id"])
            self.assertGreaterEqual(len(case["decisive_evidence"]), 2, case["id"])
            self.assertGreater(len(case["discriminating_difference"]), 40, case["id"])
            self.assertNotIn("title", case["discriminating_difference"].lower(), case["id"])


if __name__ == "__main__":
    unittest.main()

