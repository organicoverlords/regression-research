import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "memory" / "migrations" / "2026-08-25-negative-feedback-source-manifest.json"
CANDIDATES = ROOT / "memory" / "migrations" / "2026-08-25-negative-feedback-candidates.jsonl"
REPORT = ROOT / "memory" / "reports" / "2026-08-25-negative-feedback-population.json"


class NegativeFeedbackPopulationTests(unittest.TestCase):
    def test_population_is_bounded_reviewed_and_provisional(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        records = [json.loads(line) for line in CANDIDATES.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(report["source_files"], 2)
        self.assertEqual(report["selected_marker_turns"], 8)
        self.assertEqual(report["candidates"], 4)
        self.assertEqual(report["ambiguous_cases"], 4)
        self.assertEqual(len(manifest["review"]["accepted_turns"]), 4)
        self.assertTrue(all(r["state"] == "PROVISIONAL" for r in records))

    def test_candidates_keep_provenance_and_not_marker_text(self):
        records = [json.loads(line) for line in CANDIDATES.read_text(encoding="utf-8").splitlines() if line.strip()]
        expected_turns = {262, 394, 494, 1966}
        actual_turns = set()
        for record in records:
            evidence = record["evidence"][0]
            match = re.search(r"#turn-(\d+):line-(\d+)$", evidence)
            self.assertIsNotNone(match)
            actual_turns.add(int(match.group(1)))
            self.assertIn("negative-feedback", record["tags"])
            self.assertLessEqual(len(record["text"]), 800)
            lowered = record["text"].casefold()
            for marker in ("asshole", "fuck you", "asädasdnasdnda"):
                self.assertNotIn(marker, lowered)
        self.assertEqual(actual_turns, expected_turns)


if __name__ == "__main__":
    unittest.main()
