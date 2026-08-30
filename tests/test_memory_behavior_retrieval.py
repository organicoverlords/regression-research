import json
import subprocess
import sys
import unittest
from pathlib import Path

from tools.memory_bank import load_bank, search_behavior_memory

ROOT = Path(__file__).resolve().parents[1]


class BehaviorRetrievalTests(unittest.TestCase):
    def test_natural_paraphrases_recall_current_behavior_rules(self):
        cases = [
            ("keep reports concise without doing less work", "mem-20260829-c7b2539a"),
            ("a correction should not make you abandon the task you were already doing", "mem-20260829-f8a09d2b"),
            ("new user messages should interrupt ongoing work immediately", "mem-20260829-3e8b16f7"),
            ("do not accept my causal theory just because I suggested it", "mem-20260829-15f349c0"),
            ("if a tool path breaks, continue through another usable route rather than declaring the task dead", "mem-20260829-d38a8b65"),
            ("verify live state before making claims about what is currently true", "mem-20260829-d9cee13b"),
        ]
        entries = load_bank()
        for query, expected in cases:
            with self.subTest(query=query):
                ids = [entry["id"] for entry in search_behavior_memory(entries, query, limit=8)]
                self.assertIn(expected, ids)

    def test_behavior_search_never_returns_advisory_incident(self):
        hits = search_behavior_memory(load_bank(), "slopwall incident", limit=8)
        self.assertTrue(hits)
        self.assertTrue(all(hit["behavioral_authority"]["may_change_behavior"] for hit in hits))

    def test_cli_exposes_behavior_lane(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "memory_bank.py"), "behavior-search", "new user messages interrupt work", "--limit", "8"],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True,
        )
        ids = [entry["id"] for entry in json.loads(proc.stdout)]
        self.assertIn("mem-20260829-3e8b16f7", ids)


if __name__ == "__main__":
    unittest.main()
