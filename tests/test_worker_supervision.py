from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from tools.worker_supervision import candidate_events, claim_events, event_id, parse_report, receipt_path


class WorkerSupervisionTests(unittest.TestCase):
    def test_event_identity_changes_with_report_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Alder.md"
            path.write_text("worker: Alder\nstate: DONE\nlast_activity_at: 2026-08-31T04:00:00+03:00\n", encoding="utf-8")
            first = parse_report(path)
            path.write_text("worker: Alder\nstate: DONE\nlast_activity_at: 2026-08-31T04:01:00+03:00\n", encoding="utf-8")
            second = parse_report(path)
            self.assertNotEqual(first["report_sha256"], second["report_sha256"])
            self.assertNotEqual(event_id("completed", first["report_sha256"]), event_id("completed", second["report_sha256"]))

    def test_event_identity_is_invariant_to_display_name(self):
        digest = "b" * 64
        self.assertEqual(event_id("completed", digest), event_id("completed", digest))
        first = {"worker": "Alder", "state": "COMPLETE", "activity_age_minutes": 1.0, "report_sha256": digest}
        second = {"worker": "Renamed", "state": "COMPLETE", "activity_age_minutes": 1.0, "report_sha256": digest}
        self.assertEqual(candidate_events(first, stale_minutes=20)[0]["event_id"], candidate_events(second, stale_minutes=20)[0]["event_id"])
        self.assertEqual(candidate_events(first, stale_minutes=20)[0]["event_kind"], "completed")

    def test_stale_running_gets_separate_event(self):
        report = {"worker": "Cedar", "state": "RUNNING", "activity_age_minutes": 30.0, "report_sha256": "a" * 64}
        kinds = [event["event_kind"] for event in candidate_events(report, stale_minutes=20)]
        self.assertEqual(kinds, ["report_update", "stale_running"])

    def test_claim_events_uses_only_automation_id_current_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_dir = Path(tmp) / "worker-reports"
            current = report_dir / "current"
            current.mkdir(parents=True)
            (report_dir / "LegacyName.md").write_text(
                "worker: LegacyName\nstate: COMPLETE\nlast_activity_at: 2099-01-01T00:00:00+00:00\n",
                encoding="utf-8",
            )
            (current / "automation-123.md").write_text(
                "automation_id: automation-123\ndisplay_label: CurrentWorker\nstate: COMPLETE\nlast_activity_at: 2099-01-01T00:01:00+00:00\n",
                encoding="utf-8",
            )
            with patch("tools.worker_supervision._busy_call", return_value=(0, {"ok": True}, "")):
                result = claim_events(
                    report_dir,
                    actor="ChatGPT-test",
                    busy=Path("busy.cmd"),
                    stale_minutes=20,
                    lease_seconds=60,
                    scope_prefix="worker-supervision",
                )
            self.assertEqual(result["claimed_count"], 1)
            self.assertEqual(result["events"][0]["automation_id"], "automation-123")
            self.assertEqual(result["events"][0]["display_label"], "CurrentWorker")
            self.assertIn(str(current), result["events"][0]["report_path"])

    def test_receipts_are_per_event_not_shared_cursor(self):
        base = Path("C:/tmp/worker-reports")
        first = receipt_path(base, "a" * 64)
        second = receipt_path(base, "b" * 64)
        self.assertNotEqual(first, second)
        self.assertIn(".supervision", first.parts)
        self.assertIn("handled", first.parts)


if __name__ == "__main__":
    unittest.main()
