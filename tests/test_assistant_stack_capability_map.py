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

    def test_coordinator_owns_only_mutation_and_exact_scope_context(self):
        self.assertEqual(self.capabilities["mutation_ownership"]["owner"], "standalone_busy_coordinator")
        self.assertEqual(self.capabilities["checkpoint"]["owner"], "standalone_busy_coordinator")
        self.assertEqual(self.capabilities["delivery_backlog"]["owner"], "github_project_delivery_state")
        self.assertEqual(self.capabilities["actionable_fan_in"]["owner"], "github_project_delivery_state")
        self.assertIn("busy_coordinator", self.capabilities["delivery_backlog"]["never_authority"])
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
        self.assertIn("BusyCoordinator already exposed exact-scope", example["missed_existing"])
        self.assertIn("inspect its current interface", example["required_future_behavior"])

    def test_product_stage_ownership_follows_current_repo_architecture(self):
        components = {item["id"]: item for item in self.data["components"]}
        self.assertEqual(components["lowvram"]["role"], "generator")
        self.assertEqual(components["tiny3d"]["role"], "post_generation_product")
        self.assertEqual(components["tinylab"]["role"], "historical_compatibility_name")
        self.assertEqual(components["asset_library"]["owner"], "tiny3d")
        self.assertEqual(components["asset_library"]["path"], r"C:\Users\Lauri\Desktop\Tiny3D_LIBRARY")
        self.assertEqual(self.data["product_dependencies"], [["lowvram", "tiny3d"], ["tiny3d", "p3"]])
        boundary = self.capabilities["product_stage_ownership"]
        self.assertEqual(boundary["owner"], "current_product_repo_architecture_contracts")
        self.assertIn("historical_migration_issue", boundary["never_authority"])
        self.assertIn("DevProgressBoard_projection", boundary["never_authority"])
        self.assertNotIn("live_overlay", self.data)

    def test_human_maps_do_not_reintroduce_obsolete_tinylab_pipeline(self):
        for relative in ("docs/assistant-stack-capability-map.md", "docs/assistant-stack-human-map.md"):
            text = Path(relative).read_text(encoding="utf-8")
            self.assertIn("LowVRAM -> Tiny3D -> P3", text)
            self.assertNotIn("LowVRAM -> Asset Library + TinyLab -> P3", text)
            self.assertNotIn("relationship to TinyLab NOT_PROVEN", text)


if __name__ == "__main__":
    unittest.main()
