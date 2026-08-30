import unittest

from tools.stack_map_guard import HUMAN_MAP, MACHINE_MAP, architecture_changes, validate


class StackMapGuardTests(unittest.TestCase):
    def test_ordinary_feature_change_does_not_force_map_refresh(self):
        self.assertEqual(architecture_changes({"tests/test_feature_x.py"}), set())
        validate({"tests/test_feature_x.py"})

    def test_stack_change_requires_both_maps(self):
        changed = {"tools/stack_acceptance.py", HUMAN_MAP}
        with self.assertRaises(SystemExit) as caught:
            validate(changed)
        self.assertIn(MACHINE_MAP, str(caught.exception))

    def test_stack_change_passes_when_human_and_machine_maps_move(self):
        validate({"tools/memory_timeline.py", HUMAN_MAP, MACHINE_MAP})

    def test_busy_coordinator_core_is_map_bearing(self):
        path = "03 Fixtures and Experiments/issue125-busy-coordinator/python/busy_coordinator.py"
        self.assertEqual(architecture_changes({path}), {path})

    def test_live_worker_status_contract_is_map_bearing(self):
        changed = {"tools/live_worker_status.py"}
        self.assertEqual(architecture_changes(changed), changed)

    def test_bootstrap_distribution_contract_is_map_bearing(self):
        changed = {"tools/chatgpt_bootstrap_artifact.py"}
        self.assertEqual(architecture_changes(changed), changed)


if __name__ == "__main__":
    unittest.main()
