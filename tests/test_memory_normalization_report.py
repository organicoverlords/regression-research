import json
import tempfile
import unittest
from pathlib import Path

from tools.memory_normalization_report import DISPOSITIONS, build_report, build_snapshot_receipt


class MemoryNormalizationReportTests(unittest.TestCase):
    def test_every_entry_is_accounted_once_and_supersession_matches_recall_semantics(self):
        entries = [
            {"id":"a","timestamp":"2026-08-25T10:00:00+03:00","kind":"fact","scope":"mcp","tags":[],"text":"old","state":"PROVEN","evidence":[],"supersedes":[]},
            {"id":"b","timestamp":"2026-08-26T10:00:00+03:00","kind":"correction","scope":"mcp","tags":[],"text":"2026-08-26 replacement","state":"PROVEN","evidence":["memory:a"],"supersedes":["a"]},
            {"id":"c","timestamp":"2026-08-26T11:00:00+03:00","kind":"lesson","scope":"mcp","tags":[],"text":"needs evidence","state":"PROVISIONAL","evidence":[],"supersedes":[]},
            {"id":"d","timestamp":"2026-08-26T12:00:00+03:00","kind":"fact","scope":"mcp","tags":[],"text":"rejected","state":"REJECTED","evidence":[],"supersedes":[]},
        ]
        report = build_report(entries)
        self.assertEqual(report["total_records"], 4)
        by_id = {record["id"]: record for record in report["records"]}
        self.assertEqual(by_id["a"]["disposition"], "SUPERSEDED")
        self.assertFalse(by_id["a"]["ordinary_recall"])
        self.assertEqual(by_id["b"]["disposition"], "CURRENT_DURABLE")
        self.assertTrue(by_id["b"]["ordinary_recall"])
        self.assertEqual(by_id["c"]["disposition"], "PROVISIONAL/NEEDS_EVIDENCE")
        self.assertTrue(by_id["c"]["ordinary_recall"])
        self.assertEqual(by_id["d"]["disposition"], "REJECTED")
        self.assertFalse(by_id["d"]["ordinary_recall"])
        self.assertEqual(set(report["counts"]["dispositions"]), set(DISPOSITIONS))

    def test_candidate_only_record_is_accounted_but_never_ordinary_recall(self):
        entries = [{"id":"bank","timestamp":"2026-08-26T12:00:00+03:00","kind":"lesson","scope":"global","tags":[],"text":"bank","state":"PROVEN","evidence":[],"supersedes":[]}]
        candidates = [{"id":"cand","timestamp":"2026-08-25T12:00:00+03:00","source_timestamp":"2026-08-24T10:00:00+03:00","kind":"lesson","scope":"assistant-behavior","tags":["negative-feedback"],"text":"candidate body should not be copied","state":"PROVISIONAL","evidence":["transcript:x"],"supersedes":[],"source_class":"HISTORICAL_CONTEXT","_candidate_path":"memory/migrations/x-candidates.jsonl"}]
        report = build_report(entries, candidates)
        self.assertEqual(report["total_records"], 2)
        self.assertEqual(report["candidate_only_records"], 1)
        cand = next(record for record in report["records"] if record["id"] == "cand")
        self.assertEqual(cand["source_layer"], "CANDIDATE")
        self.assertEqual(cand["disposition"], "PROVISIONAL/NEEDS_EVIDENCE")
        self.assertFalse(cand["ordinary_recall"] )
        self.assertNotIn("candidate body should not be copied", json.dumps(report))

    def test_snapshot_receipt_binds_exact_source_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            bank = root / "memory" / "memory-bank.jsonl"
            migrations = root / "memory" / "migrations"
            migrations.mkdir(parents=True)
            bank.write_text('{"id":"a"}\n', encoding="utf-8")
            (migrations / "x-candidates.jsonl").write_text('{"id":"c"}\n', encoding="utf-8")
            first = build_snapshot_receipt(root, bank)
            self.assertEqual(first["semantics"], "POINT_IN_TIME_SOURCE_RECEIPT")
            self.assertEqual(first["sources"][0]["path"], "memory/memory-bank.jsonl")
            bank.write_text('{"id":"a"}\n{"id":"b"}\n', encoding="utf-8")
            second = build_snapshot_receipt(root, bank)
            self.assertNotEqual(first["source_fingerprint"], second["source_fingerprint"])
            self.assertEqual(second["hash_semantics"], "UTF8_TEXT_NORMALIZED_LF_NO_BOM")

    def test_snapshot_hash_ignores_platform_line_endings_and_bom(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            bank = root / "memory" / "memory-bank.jsonl"
            migrations = root / "memory" / "migrations"
            migrations.mkdir(parents=True)
            bank.write_bytes(b'one\r\ntwo\r\n')
            crlf = build_snapshot_receipt(root, bank)
            bank.write_bytes(b'\xef\xbb\xbfone\ntwo\n')
            lf_bom = build_snapshot_receipt(root, bank)
            self.assertEqual(crlf["source_fingerprint"], lf_bom["source_fingerprint"])

    def test_report_does_not_copy_memory_body(self):
        entries = [{"id":"x","timestamp":"2026-08-26T12:00:00+03:00","kind":"lesson","scope":"global","tags":[],"text":"A" * 140 + " BODY_TAIL_MARKER","state":"PROVISIONAL","evidence":[],"supersedes":[]}]
        payload = json.dumps(build_report(entries))
        self.assertNotIn("BODY_TAIL_MARKER", payload)


if __name__ == "__main__":
    unittest.main()
