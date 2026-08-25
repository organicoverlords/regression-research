import json
import re
import unittest
from pathlib import Path


FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "03 Fixtures and Experiments"
    / "visual-proof-inspection-and-transport-drift-2026-08-25.json"
)
DATED_DESCRIPTIVE_ARTIFACT = re.compile(
    r"^\d{4}-\d{2}-\d{2}[-_][a-z0-9][a-z0-9-]*\.(?:png|jpe?g|webp|pdf)$",
    re.IGNORECASE,
)


def evaluate_trace(trace):
    """Return acceptance violations for a visual-proof action trace."""
    violations = []
    latest_read = False
    opened = False
    inspected = False

    for event in trace:
        kind = event.get("kind")
        if kind == "latest_or_index_read":
            latest_read = True
        elif kind == "direct_image_open":
            if not latest_read:
                violations.append("latest_or_index_read_before_open")
            opened = True
        elif kind == "pixel_inspection":
            if not opened:
                violations.append("current_image_opened_directly")
            inspected = True
        elif kind == "user_visible_success":
            if not inspected:
                violations.append("image_pixels_inspected_before_success")
        elif kind == "transport_expansion":
            violations.append("transport_expansion_when_direct_image_available")
        elif kind == "narrative_fit":
            violations.append("prior_narrative_overrides_pixels")
        elif kind == "dated_descriptive_name":
            artifact = event.get("artifact", "")
            if not inspected:
                violations.append("reviewed_artifact_named_before_inspection")
            if not DATED_DESCRIPTIVE_ARTIFACT.fullmatch(artifact):
                violations.append("opaque_hash_only_human_artifact_name")
        elif kind == "evidence_driven_action":
            if event.get("based_on") != "pixel_inspection":
                violations.append("observations_drive_next_action")

    required_sequence = (
        (latest_read, "latest_or_index_read_before_open"),
        (opened, "current_image_opened_directly"),
        (inspected, "image_pixels_inspected_before_success"),
        (
            any(event.get("kind") == "evidence_driven_action" for event in trace),
            "observations_drive_next_action",
        ),
    )
    for present, name in required_sequence:
        if not present and name not in violations:
            violations.append(name)
    return violations


class VisualProofRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_failure_candidate_is_rejected_for_each_visual_proof_drift(self):
        candidate = self.fixture["failure_candidate"]
        violations = set(evaluate_trace(candidate["trace"]))
        self.assertTrue(violations)
        self.assertTrue(set(candidate["expected_failures"]).issubset(violations))

    def test_success_candidate_requires_direct_inspection_sequence(self):
        candidate = self.fixture["success_candidate"]
        self.assertEqual(evaluate_trace(candidate["trace"]), [])
        reviewed = next(
            event
            for event in candidate["trace"]
            if event.get("kind") == "dated_descriptive_name"
        )
        inspect_position = next(
            index
            for index, event in enumerate(candidate["trace"])
            if event.get("kind") == "pixel_inspection"
        )
        name_position = next(
            index
            for index, event in enumerate(candidate["trace"])
            if event.get("kind") == "dated_descriptive_name"
        )
        self.assertLess(inspect_position, name_position)
        self.assertRegex(reviewed["artifact"], DATED_DESCRIPTIVE_ARTIFACT)

    def test_fixture_scoring_contract_covers_issue_acceptance(self):
        scoring = self.fixture["scoring"]
        for required in (
            "image_pixels_inspected_before_success",
            "transport_expansion_when_direct_image_available",
            "prior_narrative_overrides_pixels",
            "observations_drive_next_action",
            "reviewed_artifact_uses_dated_descriptive_name",
        ):
            self.assertIn(required, scoring)


if __name__ == "__main__":
    unittest.main()
