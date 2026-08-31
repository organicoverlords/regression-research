from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.worker_supervision import candidate_events, event_id, parse_report, receipt_path


class WorkerSupervisionTests(unittest.TestCase):
    def test_event_identity_changes_with_report_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Alder.md"
            path.write_text("worker: Alder\nstate: DONE\nlast_activity_at: 2026-08-31T04:00:00+03:00\n", encoding="utf-8")
            first = parse_report(path)
            path.write_text("worker: Alder\nstate: DONE\nlast_activity_at: 2026-08-31T04:01:00+03:00\n", encoding="utf-8")
            second = parse_report(path)
            self.assertNotEqual(first["report_sha256"], second["report_sha256"])
            self.assertNotEqual(event_id("Alder", "completed", first["report_sha256"]), event_id("Alder", "completed", second["report_sha256"]))

    def test_stale_running_gets_separate_event(self):
        report = {"worker": "Cedar", "state": "RUNNING", "activity_age_minutes": 30.0, "report_sha256": "a" * 64}
        kinds = [event["event_kind"] for event in candidate_events(report, stale_minutes=20)]
        self.assertEqual(kinds, ["report_update", "stale_running"])

    def test_receipts_are_per_event_not_shared_cursor(self):
        base = Path("C:/tmp/worker-reports")
        first = receipt_path(base, "a" * 64)
        second = receipt_path(base, "b" * 64)
        self.assertNotEqual(first, second)
        self.assertIn(".supervision", first.parts)
        self.assertIn("handled", first.parts)


if __name__ == "__main__":
    unittest.main()
