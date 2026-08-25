from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from tools.memory_population import MAX_OUTPUT_CHARS, build_population_report


ROOT = Path(__file__).resolve().parents[1]


class MemoryPopulationTests(unittest.TestCase):
    def test_population_is_substantially_beyond_initial_bank_and_counted(self) -> None:
        report = build_population_report()
        self.assertEqual(report["status"], "PROVEN")
        self.assertEqual(report["population"]["initial_bank_entries"], 16)
        self.assertGreater(report["population"]["bank_entries_after_population"], 16)
        self.assertEqual(report["population"]["candidates"], 14)
        self.assertEqual(report["population"]["curated"], 14)
        self.assertEqual(report["population"]["growth"], 14)
        bank_total = report["population"]["bank_entries_after_population"]
        self.assertGreaterEqual(bank_total, 32)
        self.assertEqual(sum(report["counts"]["state"].values()), bank_total)
        self.assertEqual(sum(report["counts"]["kind"].values()), bank_total)
        self.assertEqual(sum(report["counts"]["source"].values()), bank_total)
        self.assertIn("VERIFIED_EVIDENCE", report["counts"]["class"])
        self.assertIn("regression", report["counts"]["source"])

    def test_required_queries_and_recall_bounds_are_proven(self) -> None:
        report = build_population_report()
        recall = report["recall_acceptance"]
        self.assertEqual(recall["status"], "PROVEN")
        self.assertTrue(all(item["status"] == "PROVEN" for item in recall["queries"]))
        self.assertTrue(all(recall["checks"].values()))
        rejected = next(item for item in recall["queries"] if item["id"] == "rejected_historical_theories")
        self.assertIn("mem-20260825-mcp-6kb-hard", rejected["matched_ids"])
        superseded = {
            edge["target"] for edge in report["duplicate_and_supersession"]["bank_supersessions"]
        }
        self.assertIn("mem-20260825-mcp-6kb-hard", superseded)

    def test_audit_preserves_provisional_candidates_and_records_supersession_stats(self) -> None:
        report = build_population_report()
        self.assertEqual(report["duplicate_and_supersession"]["duplicate_collapses"], 0)
        self.assertEqual(report["duplicate_and_supersession"]["bank_supersession_edges"], 2)
        self.assertEqual(
            report["population"]["provisional_candidates_not_auto_promoted"],
            [
                "mem-20260825-missing-metadata-no-widen",
                "mem-20260825-tool-prereq-before-promise",
                "mem-20260825-tool-route-health-test",
            ],
        )
        self.assertTrue(report["acceptance"]["checks"]["candidate_provisional_state_preserved"])

    def test_cli_emits_bounded_machine_readable_report(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "memory_population.py"), "--format", "json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLessEqual(len(result.stdout), MAX_OUTPUT_CHARS)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "PROVEN")
        self.assertEqual(payload["integration_status"], "NOT_PROVEN")
        self.assertEqual(payload["acceptance"]["issue"], 18)


if __name__ == "__main__":
    unittest.main()
