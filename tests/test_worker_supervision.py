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

    def test_current_delivery_states_map_to_meaningful_events(self):
        base = {"worker": "Juniper", "activity_age_minutes": 1.0, "report_sha256": "b" * 64}
        self.assertEqual(candidate_events({**base, "state": "COMPLETE"}, stale_minutes=20)[0]["event_kind"], "completed")
        self.assertEqual(candidate_events({**base, "state": "WAITING"}, stale_minutes=20)[0]["event_kind"], "waiting")
        self.assertEqual(candidate_events({**base, "state": "BLOCKED"}, stale_minutes=20)[0]["event_kind"], "blocked")

    def test_parse_report_derives_duration_from_existing_timestamps(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Cedar.md"
            path.write_text(
                "worker: Cedar\nstate: COMPLETE\nstarted_at: 2026-09-02T18:00:00+03:00\n"
                "last_activity_at: 2026-09-02T18:23:30+03:00\n",
                encoding="utf-8",
            )
            report = parse_report(path)
            self.assertEqual(report["duration_minutes"], 23.5)
            self.assertEqual(report["started_at"], "2026-09-02T18:00:00+03:00")

    def test_parse_report_surfaces_stop_and_tool_drop_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Juniper.md"
            path.write_text(
                "worker: Juniper\nstate: WAITING\nstarted_at: 2026-09-02T20:00:00+03:00\n"
                "last_activity_at: 2026-09-02T20:08:00+03:00\nstop_reason: TOOL_BLOCKED\n"
                "stop_detail: required route remained unavailable\ntransport_drops: 2\n"
                "binding_drops: 1\nsafety_blocks: 4\nother_tool_failures: 0\n"
                "tool_failure_effect: BLOCKED_REQUIRED_ROUTE\n",
                encoding="utf-8",
            )
            report = parse_report(path)
            self.assertEqual(report["stop_reason"], "TOOL_BLOCKED")
            self.assertEqual(report["stop_detail"], "required route remained unavailable")
            self.assertEqual(report["transport_drops"], "2")
            self.assertEqual(report["binding_drops"], "1")
            self.assertEqual(report["safety_blocks"], "4")
            self.assertEqual(report["other_tool_failures"], "0")
            self.assertEqual(report["tool_failure_effect"], "BLOCKED_REQUIRED_ROUTE")

    def test_receipts_are_per_event_not_shared_cursor(self):
        base = Path("C:/tmp/worker-reports")
        first = receipt_path(base, "a" * 64)
        second = receipt_path(base, "b" * 64)
        self.assertNotEqual(first, second)
        self.assertIn(".supervision", first.parts)
        self.assertIn("handled", first.parts)


if __name__ == "__main__":
    unittest.main()
