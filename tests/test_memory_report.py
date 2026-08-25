from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.memory_report import (
    EXPOSURE_STATUS,
    MAX_OUTPUT_CHARS,
    ReportError,
    _provenance_view,
    build_report,
    build_status,
    corpus_receipt,
)


ROOT = Path(__file__).resolve().parents[1]


class MemoryReportTests(unittest.TestCase):
    def test_status_is_validated_and_receipt_is_deterministic(self) -> None:
        first = build_status()
        second = build_status()
        self.assertEqual(first, second)
        self.assertEqual(first["service_status"], "PROVEN")
        self.assertEqual(first["integration_status"], EXPOSURE_STATUS)
        self.assertEqual(first["corpus"]["status"], "PROVEN")
        self.assertEqual(first["corpus"]["provenance"]["broken_paths"], [])
        self.assertEqual(first["receipt"]["report_id"], second["receipt"]["report_id"])

    def test_status_fails_closed_when_provenance_validator_rejects(self) -> None:
        with patch(
            "tools.memory_report.validate_provenance",
            return_value=(False, ["entries[0]: duplicate incident_id 'INC-TEST'"], {"errors": 1}),
        ) as validator:
            payload = build_status()

        validator.assert_called_once()
        self.assertEqual(payload["corpus"]["status"], "NOT_PROVEN")
        self.assertEqual(payload["corpus"]["provenance"]["validator"]["status"], "NOT_PROVEN")
        self.assertIn("duplicate incident_id", payload["corpus"]["provenance"]["validator"]["errors"][0])

    def test_report_is_relevance_first_and_bounded(self) -> None:
        payload = build_report("MCP safety routing")
        self.assertEqual(payload["integration_status"], EXPOSURE_STATUS)
        self.assertGreater(payload["summary"]["memory_matches"], 0)
        self.assertLessEqual(len(payload["findings"]), 5)
        self.assertTrue(all(item["text"] for item in payload["findings"]))
        self.assertIn("raw transcripts are not opened", " ".join(payload["limitations"]))

    def test_history_can_show_rejected_entry_but_ordinary_recall_cannot(self) -> None:
        ordinary = build_report("6KB MCP threshold")
        historical = build_report("6KB MCP threshold", history=True)
        self.assertNotIn("mem-20260825-mcp-6kb-hard", {item["id"] for item in ordinary["findings"]})
        self.assertIn("mem-20260825-mcp-6kb-hard", {item["id"] for item in historical["findings"]})
        self.assertIn("REJECTED", historical["summary"]["claim_states"])

    def test_blank_query_is_rejected_to_prevent_context_flood(self) -> None:
        with self.assertRaises(ReportError):
            build_report(" ")

    def test_path_confinement_keeps_provenance_pointer_only(self) -> None:
        view = _provenance_view(
            {
                "report_path": "..\\secret.txt",
                "title": "bounded",
                "raw_transcripts": ["C:\\Users\\secret.txt", "90 Raw Transcripts/ok.txt"],
            }
        )
        self.assertIsNone(view["report_path"])
        self.assertEqual(view["raw_transcripts"], ["90 Raw Transcripts/ok.txt"])

    def test_direct_cli_emits_under_six_thousand_chars(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "memory_report.py"),
                "report",
                "--query",
                "MCP safety routing",
                "--history",
                "--limit",
                "20",
                "--format",
                "text",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLessEqual(len(result.stdout), MAX_OUTPUT_CHARS)
        self.assertIn("Integration status: NOT_PROVEN", result.stdout)
        self.assertIn("Receipt:", result.stdout)

    def test_direct_cli_json_is_machine_readable(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "memory_report.py"), "status", "--format", "json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["service_status"], "PROVEN")
        self.assertEqual(payload["integration_status"], EXPOSURE_STATUS)

    def test_receipt_contains_only_canonical_relative_sources(self) -> None:
        receipt = corpus_receipt()
        self.assertEqual(
            [item["path"] for item in receipt["files"]],
            ["memory/memory-bank.jsonl", "memory/sources.json", "provenance.json"],
        )
        self.assertTrue(all("\\" not in item["path"] and not item["path"].startswith("/") for item in receipt["files"]))


if __name__ == "__main__":
    unittest.main()
