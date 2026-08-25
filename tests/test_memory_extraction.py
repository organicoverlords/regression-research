import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.extract_memory_candidates import extract_candidates, extract_negative_feedback_candidates

FIXTURE = Path("tests/fixtures/memory-source-snippets.jsonl")


class MemoryCandidateExtractionTests(unittest.TestCase):
    def sources(self):
        return [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_extracts_required_source_families_and_provenance(self):
        out = extract_candidates(self.sources())
        self.assertEqual({x["source_id"] for x in out}, {"agents-repo","regression-research","codex-history","traycer-artifacts"})
        self.assertTrue(all(x["source_class"] and x["source_timestamp"] for x in out))
        self.assertTrue(all(x["evidence"] for x in out))

    def test_classifies_high_signal_forms(self):
        out = extract_candidates(self.sources())
        by_text = {x["text"]: x for x in out}
        self.assertEqual(by_text["NEVER DELETE UNCOMMITTED DATA."]["kind"], "preference")
        self.assertEqual(by_text["Desktop Commander is the primary machine route."]["kind"], "decision")
        self.assertEqual(by_text["the 6KB threshold theory was not supported by evidence."]["kind"], "correction")
        self.assertEqual(by_text["retrying the identical blocked call causes churn."]["kind"], "lesson")
        self.assertEqual(by_text["module-only build passed before the full target validation."]["kind"], "status")

    def test_is_deterministic_and_bounds_oversized_signal(self):
        source = {"source_id":"claude-history","source_class":"HISTORICAL_CONTEXT","scope":"global","source_timestamp":"2026-08-25T10:04:00+03:00","evidence":"claude-history:turn-1","text":"RULE: " + ("x" * 5000)}
        first = extract_candidates([source])
        second = extract_candidates([source])
        self.assertEqual(first, second)
        self.assertEqual(len(first), 1)
        self.assertLessEqual(len(first[0]["text"]), 800)

    def test_negative_feedback_extracts_behavior_not_insult(self):
        for marker in ("ASSHOLE", "FUCK YOU", "asädasdnasdnda"):
            source = {
                "source_id":"chat-history", "source_class":"HISTORICAL_CONTEXT", "scope":"memory",
                "source_timestamp":"2026-08-25T12:00:00+03:00", "evidence":"chat:conversation-1",
                "turns":[
                    {"role":"assistant","text":"I retried the same failed command again."},
                    {"role":"user","text":marker,"evidence":f"chat:conversation-1:user-{marker}"},
                    {"role":"assistant","text":"I switched route and bounded the retry."},
                ],
            }
            out = extract_negative_feedback_candidates([source])
            self.assertEqual(len(out), 1)
            self.assertEqual(out[0]["state"], "PROVISIONAL")
            self.assertIn("I retried the same failed command again.", out[0]["text"])
            self.assertIn("I switched route and bounded the retry.", out[0]["text"])
            self.assertNotIn(marker, out[0]["text"])
            self.assertEqual(out[0]["evidence"], [f"chat:conversation-1:user-{marker}"])
            self.assertIn("negative-feedback", out[0]["tags"])

    def test_negative_feedback_is_bounded_and_configurable(self):
        source = {
            "source_id":"chat-history", "source_class":"HISTORICAL_CONTEXT", "source_timestamp":"2026-08-25T12:00:00+03:00",
            "turns":[{"role":"assistant","text":"x" * 2000},{"role":"user","text":"CUSTOM PANIC"}],
        }
        self.assertEqual(extract_negative_feedback_candidates([source]), [])
        out = extract_negative_feedback_candidates([source], markers=["CUSTOM PANIC"])
        self.assertEqual(len(out), 1)
        self.assertLessEqual(len(out[0]["text"]), 800)

    def test_cli_is_byte_deterministic_for_fixture(self):
        with tempfile.TemporaryDirectory() as td:
            a, b = Path(td)/"a.jsonl", Path(td)/"b.jsonl"
            for output in (a, b):
                subprocess.run([sys.executable,"tools/extract_memory_candidates.py",str(FIXTURE),str(output)],check=True,capture_output=True,text=True)
            self.assertEqual(a.read_bytes(), b.read_bytes())
            records=[json.loads(line) for line in a.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(records), 6)


if __name__ == "__main__":
    unittest.main()
