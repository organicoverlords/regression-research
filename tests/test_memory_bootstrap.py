import json
import unittest

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

    def test_bootstrap_has_a_bounded_startup_budget(self):
        rendered = json.dumps(build_behavior_bootstrap(load_bank()), ensure_ascii=False)
        self.assertLessEqual(len(rendered), 20000)


if __name__ == "__main__":
    unittest.main()
