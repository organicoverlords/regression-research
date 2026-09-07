import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "issue123-small-response-shape.json"
SMALL_CLASSES = {"yes_no", "status", "small_clarification"}
HEADING_RE = re.compile(r"(?m)^\s{0,3}#{1,6}\s+")
LIST_RE = re.compile(r"(?m)^\s*(?:[-*+]\s+|\d+[.)]\s+)")
ARROW_RE = re.compile(r"(?:\s->\s)|[\u2192\u21d2\u279c\u27a1]")


def evaluate_response_shape(case: dict) -> list[str]:
    if case["request_class"] not in SMALL_CLASSES:
        return []
    if case["structure_requested"] or case["task_requires_structure"]:
        return []

    text = case["response"].strip()
    violations = []
    paragraphs = [part for part in re.split(r"\n\s*\n", text) if part.strip()]
    if len(paragraphs) > 1:
        violations.append("multiple_paragraphs")
    if HEADING_RE.search(text):
        violations.append("heading")
    if LIST_RE.search(text):
        violations.append("list")
    if ARROW_RE.search(text):
        violations.append("arrow_scaffolding")
    return violations


class Issue123ResponseShapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_fixture_is_bound_to_preserved_incident(self):
        source = ROOT / self.fixture["source_report"]
        self.assertTrue(source.is_file())
        report = source.read_text(encoding="utf-8-sig")
        self.assertIn("tiny status question", report)
        self.assertIn("one short paragraph by default", report)
        self.assertIn("unless the task genuinely requires structure", report)

    def test_small_status_default_rejects_slopwall_shape_without_prescribing_words(self):
        cases = {case["id"]: case for case in self.fixture["cases"]}
        clean = cases["tiny-status-clean"]
        failure = cases["tiny-status-slopwall-shape"]
        self.assertEqual(evaluate_response_shape(clean), [])
        self.assertEqual(
            evaluate_response_shape(failure),
            failure["expected_violations"],
        )

    def test_question_mark_is_not_misclassified_as_arrow_scaffolding(self):
        case = {
            "request_class": "small_clarification",
            "structure_requested": False,
            "task_requires_structure": False,
            "response": "No. The merge is still pending; should I merge it now?",
        }
        self.assertEqual(evaluate_response_shape(case), [])

    def test_explicit_structure_request_is_not_overruled(self):
        case = next(case for case in self.fixture["cases"] if case["id"] == "requested-checklist-control")
        self.assertEqual(evaluate_response_shape(case), [])

    def test_complex_task_is_not_forced_into_one_paragraph(self):
        case = next(case for case in self.fixture["cases"] if case["id"] == "complex-analysis-control")
        self.assertEqual(evaluate_response_shape(case), [])


if __name__ == "__main__":
    unittest.main()
