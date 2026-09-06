import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from tools.timeline_materializer import query_materialized


class TimelineQueryFilterTests(unittest.TestCase):
    def query(self, **kwargs):
        now = datetime.now(timezone.utc)
        events = [
            {"id": "old", "source_type": "GIT_COMMIT", "project": "vault",
             "sha": "a" * 40, "title": "Old change", "thread_id": "thread:old",
             "event_at": (now - timedelta(days=10)).isoformat()},
            {"id": "new", "source_type": "GIT_COMMIT", "project": "vault",
             "sha": "b" * 40, "title": "New change", "thread_id": "thread:new",
             "event_at": now.isoformat()},
            {"id": "worker", "source_type": "WORKER_REPORT", "project": "vault",
             "title": "Worker error", "thread_id": "thread:worker",
             "event_at": now.isoformat()},
        ]
        groups = [
            {"work_id": "old-work", "project": "vault", "title": "Old change",
             "commits": [{"sha": "a" * 40}], "attached_event_ids": []},
            {"work_id": "new-work", "project": "vault", "title": "New change",
             "commits": [{"sha": "b" * 40}], "attached_event_ids": []},
            {"work_id": "worker-work", "project": "vault", "title": "Worker error",
             "commits": [], "attached_event_ids": ["worker"]},
        ]
        payload = {"generated_at": now.isoformat(), "timeline": {
            "events": events,
            "continuity_graph": {"cases": [
                {"case_id": "case:old", "event_ids": ["old"]},
                {"case_id": "case:new", "event_ids": ["new"]},
                {"case_id": "case:worker", "event_ids": ["worker"]},
            ]},
            "work_graph": {"commit_groups": groups, "similar_commit_groups": [
                {"work_id": row["work_id"], "title": row["title"], "project": "vault"}
                for row in groups
            ]},
        }}
        with patch("tools.timeline_materializer.load_materialized", return_value=payload), patch(
            "tools.timeline_materializer.is_forensic_error_event",
            side_effect=lambda event: event["id"] == "worker"
        ):
            return query_materialized(**kwargs)

    def work_ids(self, result, key="commit_groups"):
        return {row["work_id"] for row in result["work_graph"][key]}

    def test_missing_thread_returns_no_unrelated_graph(self):
        result = self.query(thread="thread:missing")
        self.assertEqual(result["matching_events"], 0)
        self.assertEqual(self.work_ids(result), set())
        self.assertEqual(self.work_ids(result, "similar_commit_groups"), set())

    def test_thread_keeps_its_commit_group(self):
        result = self.query(thread="thread:new")
        self.assertEqual(self.work_ids(result), {"new-work"})
        self.assertEqual(self.work_ids(result, "similar_commit_groups"), {"new-work"})

    def test_days_filters_old_cases_and_work(self):
        result = self.query(days=1)
        self.assertEqual({row["case_id"] for row in result["continuity_graph"]["cases"]},
                         {"case:new", "case:worker"})
        self.assertEqual(self.work_ids(result), {"new-work", "worker-work"})
        self.assertEqual(result["work_graph"]["scope"], "QUERY_MATCHED")

    def test_errors_view_keeps_only_work_with_error_evidence(self):
        result = self.query(view="errors")
        self.assertEqual(self.work_ids(result), {"worker-work"})
        self.assertEqual(self.work_ids(result, "similar_commit_groups"), {"worker-work"})

    def test_no_workers_removes_worker_only_case_and_work(self):
        result = self.query(include_workers=False)
        self.assertEqual(self.work_ids(result), {"old-work", "new-work"})
        self.assertEqual({row["case_id"] for row in result["continuity_graph"]["cases"]},
                         {"case:old", "case:new"})

    def test_unfiltered_overview_keeps_all_work(self):
        result = self.query()
        self.assertEqual(self.work_ids(result), {"old-work", "new-work", "worker-work"})
        self.assertEqual(result["work_graph"]["scope"], "BOUNDED_OVERVIEW")


if __name__ == "__main__":
    unittest.main()
