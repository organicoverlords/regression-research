import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "02 Evidence" / "issue122-2026-08-26_1819-finalization-mechanism.json"


class Issue122FinalizationMechanismTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_source_and_scope_are_bound(self):
        self.assertEqual(self.data["issue"], 122)
        self.assertEqual(len(self.data["source"]["raw_sha256"]), 64)
        self.assertIn("CI rejects user-visible changes that skip it", self.data["scope_contract"]["assistant_contract_excerpt"])

    def test_last_launch_is_the_only_launch_not_followed_by_read(self):
        turn = self.data["failing_turn"]
        self.assertEqual(turn["start_process_count"], 51)
        self.assertEqual(turn["start_process_followed_by_read_output"], 50)
        self.assertEqual(turn["start_process_followed_by_final"], 1)
        self.assertEqual(turn["read_output_count"], 66)
        self.assertEqual(turn["api_tool_call_tool_count"], 120)
        self.assertEqual(turn["tool_surface_action_count_including_discovery"], 121)

    def test_mcp_contract_required_continuation(self):
        contract = self.data["mcp_start_contract"]["contract"]
        self.assertEqual(contract["running_process_state"], "RUNNING")
        self.assertEqual(contract["running_next_action"], "READ_SAME_PROCESS_ID")
        self.assertEqual(contract["completed_next_action"], "STOP_READING")

    def test_transport_proves_success_and_later_resume(self):
        events = self.data["transport"]["events"]
        self.assertTrue(any(e.get("event") == "response_finish" and e.get("status") == 200 and e.get("mcp_tool") == "start_process" for e in events))
        self.assertTrue(any(e.get("event") == "process_exit_observed" and e.get("exit_code") == 0 for e in events))
        self.assertTrue(any(e.get("event") == "process_read" for e in events))
        self.assertEqual(self.data["resume"]["resume_observation"], "previously started process completed successfully but updated only the staging helper, not any repo")

    def test_conclusion_does_not_overclaim_pressure_as_trigger(self):
        self.assertIn("completion-classification error", self.data["confirmed_mechanism"])
        self.assertIn("not a proven trigger", self.data["causal_limit"])
        self.assertIn("Persist unmet acceptance criteria", self.data["corrective_invariant"])


if __name__ == "__main__":
    unittest.main()
