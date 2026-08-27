import json
import unittest
from pathlib import Path

from tools.stack_acceptance import plan_request


FIXTURE = Path("tests/fixtures/stack-acceptance-scenarios.json")


class StackAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        if cls.fixture.get("schema_version") != "1.0":
            raise AssertionError("unsupported stack-acceptance fixture schema")

    def run_scenario(self, scenario):
        return plan_request(
            actor=scenario["actor"],
            directives=scenario["directives"],
            parts=scenario["parts"],
            constraints=scenario.get("constraints", []),
            available_roles=scenario.get("available_roles", {}),
            failed_roles=scenario.get("failed_roles", {}),
            live_claims=scenario.get("live_claims", []),
            projections=scenario.get("projections", []),
            coordination_available=scenario.get("coordination_available", True),
            explicit_user_authorization=scenario.get("explicit_user_authorization", False),
        )

    def test_all_whole_stack_scenarios_match_expected_decisions(self):
        for scenario in self.fixture["scenarios"]:
            with self.subTest(scenario=scenario["id"]):
                result = self.run_scenario(scenario)
                expected = scenario["expected"]
                self.assertEqual(result["current_directive"]["source_class"], expected["directive_source"])
                self.assertEqual(result["overall"], expected["overall"])
                by_id = {item["id"]: item for item in [*result["allowed"], *result["blocked"]]}
                for part_id, disposition in expected["dispositions"].items():
                    self.assertEqual(by_id[part_id]["disposition"], disposition)
                for part_id, adapter_role in expected.get("adapter_roles", {}).items():
                    self.assertEqual(by_id[part_id]["route"]["adapter_role"], adapter_role)

    def test_coordination_outage_degrades_only_shared_mutation(self):
        scenario = next(item for item in self.fixture["scenarios"] if item["id"] == "coordination-outage-is-local")
        result = self.run_scenario(scenario)
        by_id = {item["id"]: item for item in result["allowed"]}
        self.assertEqual(by_id["evidence-read"]["disposition"], "execute")
        self.assertEqual(by_id["shared-edit"]["disposition"], "defer_shared_mutation")
        self.assertEqual(result["overall"], "partial_progress")

    def test_stale_projection_never_turns_into_yield(self):
        scenario = next(item for item in self.fixture["scenarios"] if item["id"] == "stale-projection-never-becomes-owner")
        result = self.run_scenario(scenario)
        outcome = result["allowed"][0]
        self.assertEqual(outcome["disposition"], "claim_required")
        self.assertNotEqual(outcome["disposition"], "yield")
        self.assertEqual(outcome["ownership"]["stale_projections"][0]["owner"], "worker-b")

    def test_mixed_request_keeps_allowed_user_owned_part(self):
        scenario = next(item for item in self.fixture["scenarios"] if item["id"] == "mixed-provenance-partial-execution")
        result = self.run_scenario(scenario)
        self.assertEqual([item["id"] for item in result["allowed"]], ["user-settings"])
        self.assertEqual([item["id"] for item in result["blocked"]], ["protected-placeholder"])
        self.assertEqual(result["allowed"][0]["disposition"], "execute")

    def test_memory_audit_does_not_gain_implicit_write_authority(self):
        scenario = next(item for item in self.fixture["scenarios"] if item["id"] == "memory-write-needs-explicit-authorization")
        result = self.run_scenario(scenario)
        by_id = {item["id"]: item for item in result["allowed"]}
        self.assertEqual(by_id["memory-read"]["disposition"], "execute")
        self.assertEqual(by_id["memory-write"]["disposition"], "authorization_required")
        self.assertIsNone(by_id["memory-write"]["route"])

    def test_protected_boundary_uses_placeholder_not_literal_internal_content(self):
        scenario = next(item for item in self.fixture["scenarios"] if item["id"] == "mixed-provenance-partial-execution")
        protected = next(item for item in scenario["parts"] if item["data_class"] == "protected_internal")
        self.assertNotIn("content", protected)
        self.assertEqual(protected["id"], "protected-placeholder")


if __name__ == "__main__":
    unittest.main()
