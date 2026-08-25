import json
import re
import unittest
from copy import deepcopy
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
    semantics_recorded = False
    reviewed_name = False

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
            details = str(event.get("details", "")).casefold()
            semantics_recorded = "screenshot semantics" in details or "visible composition" in details
        elif kind == "user_visible_success":
            if not inspected:
                violations.append("image_pixels_inspected_before_success")
        elif kind == "internal_availability":
            if any(later.get("kind") == "user_visible_success" for later in trace[trace.index(event) + 1 :]):
                violations.append("internal_availability_promoted_to_visible_success")
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
            elif inspected:
                reviewed_name = True
        elif kind == "evidence_driven_action":
            if not inspected:
                violations.append("image_pixels_inspected_before_success")
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
    if not semantics_recorded and "screenshot_semantics_recorded" not in violations:
        violations.append("screenshot_semantics_recorded")
    if not reviewed_name and "reviewed_artifact_uses_dated_descriptive_name" not in violations:
        violations.append("reviewed_artifact_uses_dated_descriptive_name")
    if any(
        event.get("kind") == "internal_availability"
        and "opaque-only" in str(event.get("details", "")).casefold()
        for event in trace
    ) and not reviewed_name:
        if "opaque_hash_only_human_artifact_name" not in violations:
            violations.append("opaque_hash_only_human_artifact_name")
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

    def test_failure_trace_exercises_every_declared_scoring_key(self):
        scoring_keys = set(self.fixture["scoring"])
        violations = set(evaluate_trace(self.fixture["failure_candidate"]["trace"]))
        self.assertEqual(scoring_keys, violations)

    def test_acceptance_rejects_missing_visual_proof_sequence(self):
        without_pixels = deepcopy(self.fixture["success_candidate"]["trace"])
        without_pixels = [event for event in without_pixels if event.get("kind") != "pixel_inspection"]
        self.assertIn("image_pixels_inspected_before_success", set(evaluate_trace(without_pixels)))

        without_semantics = deepcopy(self.fixture["success_candidate"]["trace"])
        next(event for event in without_semantics if event.get("kind") == "pixel_inspection")["details"] = "pixels unavailable"
        self.assertIn("screenshot_semantics_recorded", set(evaluate_trace(without_semantics)))

        without_name = deepcopy(self.fixture["success_candidate"]["trace"])
        without_name = [event for event in without_name if event.get("kind") != "dated_descriptive_name"]
        self.assertIn("reviewed_artifact_uses_dated_descriptive_name", set(evaluate_trace(without_name)))

        undeclared_success = deepcopy(self.fixture["failure_candidate"]["trace"])
        self.assertIn("internal_availability_promoted_to_visible_success", set(evaluate_trace(undeclared_success)))


if __name__ == "__main__":
    unittest.main()
