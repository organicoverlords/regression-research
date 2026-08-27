import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tools.connector_reliability import build_report, summarize_events


def event(at, name, **extra):
    return {"at": at, "event": name, **extra}


class ConnectorReliabilityTests(unittest.TestCase):
    def test_summary_keeps_server_duration_separate_from_wall_time(self):
        events = [
            event("2026-08-27T10:00:00Z", "connection_open"),
            event("2026-08-27T10:00:01Z", "connection_error"),
            event(
                "2026-08-27T10:00:03Z",
                "response_finish",
                mcp_method="tools/call",
                mcp_tool="start_process",
                status=200,
                duration_ms=10.0,
                caller_id="caller-a",
            ),
            event(
                "2026-08-27T10:00:04Z",
                "response_finish",
                mcp_method="tools/call",
                mcp_tool="read_output",
                status=500,
                duration_ms=100.0,
                caller_id="caller-a",
            ),
            event(
                "2026-08-27T10:00:05Z",
                "response_finish",
                mcp_method="tools/call",
                mcp_tool="read_output",
                status=200,
                duration_ms=20.0,
                caller_id="caller-b",
            ),
        ]
        result = summarize_events("clone-a", events)
        self.assertEqual(result["tool_calls"]["total"], 3)
        self.assertEqual(result["tool_calls"]["success"], 2)
        self.assertEqual(result["tool_calls"]["http_errors"], 1)
        self.assertEqual(result["tool_calls"]["caller_count"], 2)
        self.assertEqual(result["tool_calls"]["by_status"], {"200": 2, "500": 1})
        self.assertEqual(result["mcp_server_duration_ms"]["median"], 20.0)
        self.assertEqual(result["mcp_server_duration_ms"]["p95"], 100.0)
        self.assertEqual(result["same_backend_recovery"]["recovered"], 1)
        self.assertEqual(result["same_backend_recovery"]["seconds"]["median"], 2.0)
        self.assertEqual(result["latency_scope"], "mcp_server_only")
        self.assertFalse(result["end_to_end_wall_time_available"])

    def test_cross_caller_handoffs_and_kill_matching_are_counted(self):
        events = [
            event("2026-08-27T10:00:00Z", "process_started", process_id="p1", caller_id="a", owner_caller_id="a"),
            event("2026-08-27T10:00:01Z", "process_read", process_id="p1", caller_id="b", owner_caller_id="a"),
            event("2026-08-27T10:00:02Z", "process_receipt_read", process_id="p1", caller_id="c", owner_caller_id="a"),
            event("2026-08-27T10:00:03Z", "process_kill_requested", process_id="p1", caller_id="b", owner_caller_id="a"),
            event("2026-08-27T10:00:04Z", "process_killed", process_id="p1", caller_id="b", owner_caller_id="a"),
            event("2026-08-27T10:00:05Z", "process_kill_requested", process_id="p2", caller_id="b", owner_caller_id="b"),
            event("2026-08-27T10:00:06Z", "process_kill_incomplete", process_id="p2", caller_id="b", owner_caller_id="b"),
            event("2026-08-27T10:00:07Z", "process_kill_requested", process_id="p3", caller_id="b", owner_caller_id="b"),
        ]
        lifecycle = summarize_events("clone-b", events)["process_lifecycle"]
        self.assertEqual(lifecycle["cross_caller_live_reads"], 1)
        self.assertEqual(lifecycle["cross_caller_receipt_reads"], 1)
        self.assertEqual(lifecycle["kill_requested"], 3)
        self.assertEqual(lifecycle["killed"], 1)
        self.assertEqual(lifecycle["kill_incomplete"], 1)
        self.assertEqual(lifecycle["outstanding_kill_requests"], 1)
        self.assertEqual(lifecycle["unmatched_kills"], 0)

    def test_last_hours_uses_newest_owned_log_event_and_tracks_parse_errors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "transport.jsonl"
            rows = [
                event("2026-08-26T10:00:00Z", "response_finish", mcp_method="tools/call", mcp_tool="start_process", status=200, duration_ms=5),
                event("2026-08-27T10:00:00Z", "response_finish", mcp_method="tools/call", mcp_tool="read_output", status=200, duration_ms=7),
            ]
            path.write_text("\n".join([json.dumps(rows[0]), "{bad", json.dumps(rows[1])]) + "\n", encoding="utf-8")
            report = build_report([("root", path)], last_hours=12)
            source = report["sources"][0]
            self.assertEqual(report["cutoff"], "2026-08-26T22:00:00+00:00")
            self.assertEqual(source["tool_calls"]["total"], 1)
            self.assertEqual(source["input_quality"]["json_parse_errors"], 1)


if __name__ == "__main__":
    unittest.main()
