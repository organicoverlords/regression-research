import json
import unittest
from pathlib import Path

from tools.memory_authority import behavioral_context
from tools.memory_bank import load_bank
from tools.memory_timeline import build_behavior_bootstrap


class MemoryBootstrapTests(unittest.TestCase):
    def test_bootstrap_contains_every_current_rule_without_history_payload(self):
        entries = load_bank()
        current = behavioral_context(entries)
        payload = build_behavior_bootstrap(entries)
        expected = {entry["id"]: entry["text"] for entry in current}
        actual = {
            item["id"]: item["text"]
            for item in [*payload["behavior_profile"], *payload["canonical_policy_profile"]]
        }
        self.assertEqual(actual, expected)
        self.assertTrue(payload["contract"]["complete_behavior_semantics"])
        self.assertFalse(payload["contract"]["history_included"])
        self.assertNotIn("recent_events", payload)
        self.assertNotIn("projects", payload)

    def test_bootstrap_carries_fresh_session_operating_cycle_without_turning_rehydration_into_a_loop(self):
        payload = build_behavior_bootstrap(load_bank())
        startup = payload["fresh_session_startup"]
        self.assertIn("fresh normal conversation only", startup["applies"])
        self.assertIn("must not retrigger this sweep", startup["rehydration"])
        self.assertIn("wake-up/context selector", startup["wake_up_semantics"])
        self.assertIn("scheduled-worker state/recent runs", startup["live_orientation"])
        self.assertIn("recent meaningful commits/PRs/checks", startup["live_orientation"])
        self.assertIn("repair or contain it first", startup["anomaly_handling"])
        self.assertIn("compact delta-only startup report", startup["startup_report"])
        self.assertIn("status dump is never task completion", startup["continuation"])
        self.assertEqual(startup["source_contract"], "04 Operating Contracts/fresh-chat-startup-orientation.md")
        self.assertTrue((Path(__file__).resolve().parents[1] / startup["source_contract"]).is_file())
        self.assertTrue((Path(__file__).resolve().parents[1] / startup["personal_instructions_bridge"]).is_file())

    def test_bootstrap_uses_current_five_worker_launch_supervision_rule(self):
        payload = build_behavior_bootstrap(load_bank())
        active = {item["id"]: item["text"] for item in payload["behavior_profile"]}
        self.assertIn("mem-20260829-d3594411", active)
        self.assertNotIn("mem-20260829-59cf4996", active)
        rule = active["mem-20260829-d3594411"]
        self.assertIn("arm all five workers", rule)
        self.assertIn("reports the arm immediately", rule)
        self.assertIn("repo work instead of silently waiting", rule)
        self.assertIn("repeat work-and-verify until Worker 1 is proven healthy", rule)

        contract = (Path(__file__).resolve().parents[1] / "04 Operating Contracts/fresh-worker-generation-launch.md").read_text(encoding="utf-8")
        self.assertIn("Arm the full five-worker generation", contract)
        self.assertIn("Report the arm immediately", contract)
        self.assertIn("Do not hang around waiting for Worker 1", contract)
        self.assertIn("A failed first launch starts an immediate repair loop", contract)
        self.assertIn("do not create a verifier timer as a substitute", contract)

    def test_bootstrap_has_a_bounded_startup_budget(self):
        rendered = json.dumps(build_behavior_bootstrap(load_bank()), ensure_ascii=False)
        self.assertLessEqual(len(rendered), 20000)


if __name__ == "__main__":
    unittest.main()
