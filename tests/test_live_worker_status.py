import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tools.live_worker_status import summarize_live_worker_status
from tools.memory_timeline import build_fresh_session_startup_contract

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "live-worker-status-cases.json"


class LiveWorkerStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_replay_cases_use_execution_and_real_work_only(self):
        for case in self.fixture["cases"]:
            with self.subTest(case=case["id"]):
                result = summarize_live_worker_status(
                    case["evidence"],
                    execution_visibility=case["execution_visibility"],
                )
                self.assertEqual(result["status"], case["expected_status"])
                self.assertEqual(result["working_now"], case["working_now"])
                self.assertEqual(
                    result["work_events_in_claim_window"],
                    case["expected_work_events"],
                )
                if "expected_work_by_kind" in case:
                    self.assertEqual(result["work_by_kind"], case["expected_work_by_kind"])
                if "expected_last_work_at" in case:
                    self.assertEqual(result["last_work_at"], case["expected_last_work_at"])

    def test_recent_completed_commander_work_counts_as_active(self):
        now = datetime(2026, 8, 30, 13, 40, 0, tzinfo=timezone.utc)
        result = summarize_live_worker_status(
            [{"kind": "tool_completed", "at": "2026-08-30T13:38:30Z", "scope_match": True}],
            execution_visibility=True,
            now=now,
            activity_window_seconds=300,
        )
        self.assertEqual(result["status"], "working")
        self.assertTrue(result["working_now"])
        self.assertEqual(result["recent_activity_count"], 1)

    def test_old_completed_work_does_not_count_as_live(self):
        now = datetime(2026, 8, 30, 13, 40, 0, tzinfo=timezone.utc)
        result = summarize_live_worker_status(
            [{"kind": "tool_completed", "at": "2026-08-30T13:30:00Z", "scope_match": True}],
            execution_visibility=True,
            now=now,
            activity_window_seconds=300,
        )
        self.assertEqual(result["status"], "not_working")
        self.assertFalse(result["working_now"])

    def test_claim_metadata_has_zero_positive_weight(self):
        result = summarize_live_worker_status(
            [
                {"kind": "claim", "current": True},
                {"kind": "lease", "current": True},
                {"kind": "heartbeat", "current": True},
                {"kind": "checkpoint", "current": True},
                {"kind": "coordinator_active", "current": True},
            ],
            execution_visibility=True,
        )
        self.assertEqual(result["status"], "not_working")
        self.assertFalse(result["working_now"])
        self.assertEqual(result["work_events_in_claim_window"], 0)

    def test_bootstrap_contract_requires_recent_activity_window(self):
        contract = build_fresh_session_startup_contract()
        self.assertIn("zero positive weight", contract["worker_status_truth"])
        self.assertIn("five minutes", contract["worker_status_truth"])
        self.assertIn("do not require a child process", contract["worker_status_truth"])
        self.assertIn("claim timestamps may delimit", contract["worker_progress_truth"])
        self.assertIn("actual work", contract["worker_progress_truth"])

    def test_worker_launch_contract_uses_activity_window(self):
        launch = (
            ROOT / "04 Operating Contracts" / "fresh-worker-generation-launch.md"
        ).read_text(encoding="utf-8")
        self.assertIn("zero positive liveness or progress evidence", launch)
        self.assertIn("Claim timestamps may bound", launch)
        self.assertIn("bounded recent Commander/MCP activity window", launch)


if __name__ == "__main__":
    unittest.main()
