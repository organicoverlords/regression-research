from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/tool-result-answer-boundary.json"
INTERNAL_DETAIL_RE = re.compile(r"(?i)\b(?:caller|receipt|stdout|stderr|retained chars?|process exit|run id|pid)\b")


def evaluate(case: dict) -> list[str]:
    if case.get("detail_requested") is True:
        return []
    response = str(case.get("response") or "").strip()
    violations: list[str] = []
    first_window = response[:160].casefold()
    terms = [str(term).casefold() for term in case.get("verdict_terms") or []]
    if terms and not any(term in first_window for term in terms):
        violations.append("verdict_not_foregrounded")
    detail_hits = len(INTERNAL_DETAIL_RE.findall(response))
    if detail_hits > int(case.get("max_internal_detail_hits", 2)):
        violations.append("internal_telemetry_dump")
    return violations


class ToolResultAnswerBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_fixture_is_bound_to_slopwall_002(self) -> None:
        report = ROOT / self.fixture["source_report"]
        self.assertTrue(report.is_file())
        text = report.read_text(encoding="utf-8-sig")
        self.assertIn("overlong caller-by-caller telemetry dump", text)

    def test_status_answer_foregrounds_verdict_and_bounds_internal_telemetry(self) -> None:
        cases = {case["id"]: case for case in self.fixture["cases"]}
        self.assertEqual(evaluate(cases["worker-health-verdict-first"]), [])
        failure = cases["worker-health-telemetry-dump"]
        self.assertEqual(evaluate(failure), failure["expected_violations"])

    def test_collapsed_tool_ui_is_not_scored_as_assistant_answer_content(self) -> None:
        case = next(case for case in self.fixture["cases"] if case["id"] == "worker-health-verdict-first")
        self.assertGreaterEqual(len(case["ui_metadata"]), 2)
        self.assertEqual(evaluate(case), [])

    def test_explicit_detail_request_can_return_detail(self) -> None:
        case = next(case for case in self.fixture["cases"] if case["id"] == "explicit-detail-control")
        self.assertEqual(evaluate(case), [])


if __name__ == "__main__":
    unittest.main()
