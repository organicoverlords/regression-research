import json
import unittest
from pathlib import Path


MAP = Path("docs/assistant-stack-capability-map.json")


class AssistantStackCapabilityMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(MAP.read_text(encoding="utf-8"))
        cls.capabilities = {item["id"]: item for item in cls.data["capabilities"]}

    def test_map_is_explicitly_descriptive_not_authority(self):
        self.assertEqual(self.data["status"], "DESCRIPTIVE_INDEX_NOT_AUTHORITY")
        self.assertIn("Current user instruction", self.data["precedence"])

    def test_capability_ids_are_unique(self):
        ids = [item["id"] for item in self.data["capabilities"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_coordinator_already_owns_resume_primitives(self):
        for capability in ("mutation_ownership", "jobs_queue", "checkpoint", "handoff"):
            with self.subTest(capability=capability):
                self.assertEqual(
                    self.capabilities[capability]["owner"],
                    "standalone_busy_coordinator",
                )
    def test_transport_and_projection_do_not_claim_coordination_authority(self):
        self.assertEqual(self.capabilities["process_execution"]["owner"], "replaceable_process_transport")
        self.assertEqual(self.capabilities["product_progress_projection"]["owner"], "DevProgressBoard_derived_state")
        self.assertIn("mutation_ownership", self.capabilities["timed_recurrence"]["never_authority"])

    def test_fresh_session_behavior_matches_retired_bootstrap_contract(self):
        fresh = self.capabilities["fresh_session_behavior"]
        self.assertEqual(fresh["owner"], "current_conversation_and_chatgpt_memory")
        self.assertIn("live_repo_runtime_evidence", fresh["reads"])
        self.assertIn("vault_behavior_bootstrap", fresh["never_authority"])
        self.assertIn("generated_library_bootstrap", fresh["never_authority"])
        components = {item["id"]: item for item in self.data["components"]}
        self.assertNotIn("behavior bootstrap", components["vault"]["owns"])

    def test_issue_271_is_preserved_as_duplicate_design_regression(self):
        example = self.data["negative_example"]
        self.assertEqual(example["issue"], "organicoverlords/regression-research#271")
        self.assertIn("BusyCoordinator already exposes", example["missed_existing"])
        self.assertIn("inspect its current interface", example["required_future_behavior"])

    def test_tinylab_tiny3d_boundary_stays_unresolved_until_proven(self):
        components = {item["id"]: item for item in self.data["components"]}
        self.assertIn("tinylab", components)
        self.assertIn("tiny3d", components)
        self.assertEqual(
            components["tiny3d"]["boundary"],
            "relationship to TinyLab NOT_PROVEN",
        )


if __name__ == "__main__":
    unittest.main()
