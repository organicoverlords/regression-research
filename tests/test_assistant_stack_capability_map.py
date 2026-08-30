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

    def test_worker_status_uses_recent_activity_window_not_ownership(self):
        status = self.capabilities["worker_execution_status"]
        self.assertEqual(status["owner"], "bounded_recent_commander_mcp_activity_evidence")
        self.assertEqual(status["default_activity_window_seconds"], 300)
        self.assertTrue(any("recent_completed" in item for item in status["reads"]))
        self.assertIn("busy_claim", status["never_authority"])

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


class AssistantStackMaintenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(MAP.read_text(encoding="utf-8"))

    def test_user_model_is_one_loop_with_five_internal_responsibilities(self):
        model = self.data["user_model"]
        self.assertEqual(model["normal_loop"], "user -> ChatGPT -> work -> proof -> result")
        self.assertEqual(model["assistant_responsibilities"], ["KNOW", "COORDINATE", "EXECUTE", "RECOVER", "PROVE"])

    def test_map_maintenance_is_bootstrap_and_ci_enforced(self):
        maintenance = self.data["maintenance"]
        self.assertIn("stack_map_glance", maintenance["bootstrap_reading"])
        self.assertEqual(maintenance["guard"], "tools/stack_map_guard.py")
        self.assertIn("docs/assistant-stack-human-map.md", maintenance["required_same_change"])
        self.assertIn("docs/assistant-stack-capability-map.json", maintenance["required_same_change"])

    def test_human_map_stays_user_facing(self):
        text = Path("docs/assistant-stack-human-map.md").read_text(encoding="utf-8")
        self.assertIn("YOU", text)
        self.assertIn("KNOW", text)
        self.assertIn("COORDINATE", text)
        self.assertIn("EXECUTE", text)
        self.assertIn("RECOVER", text)
        self.assertIn("PROVE", text)
        self.assertLess(len(text.splitlines()), 120)


if __name__ == "__main__":
    unittest.main()
