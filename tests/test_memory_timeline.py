import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from tools.memory_timeline import build_recurrence_context, build_timeline, needs_timeline_fallback


ROOT = Path(__file__).resolve().parents[1]


class MemoryTimelineTests(unittest.TestCase):
    @staticmethod
    def e(memory_id, timestamp, text, *, kind="lesson", scope="global", state="PROVEN", title=None, tags=None, evidence=None, supersedes=None, project=None, event_at=None):
        out = {
            "id": memory_id, "timestamp": timestamp, "kind": kind, "scope": scope,
            "tags": list(tags or []), "text": text, "state": state,
            "evidence": list(evidence or ["report:x"]), "supersedes": list(supersedes or []),
        }
        if title:
            out["title"] = title
        if project:
            out["project"] = project
        if event_at:
            out["event_at"] = event_at
        return out

    def test_event_time_is_distinct_from_record_time_when_explicit(self):
        entry = self.e("x", "2026-08-29T03:00:00+03:00", "Observed earlier", event_at="2026-08-28T20:00:00+03:00")
        event = build_timeline([entry], limit=5)["events"][0]
        self.assertEqual(event["event_at"], "2026-08-28T20:00:00+03:00")
        self.assertEqual(event["recorded_at"], "2026-08-29T03:00:00+03:00")
        self.assertEqual(event["event_time_source"], "EXPLICIT_EVENT_AT")

    def test_same_scope_builds_chronological_thread_without_claiming_causality(self):
        old = self.e("old", "2026-08-28T20:00:00+03:00", "First incident", scope="assistant-orchestration/error-a", title="First")
        new = self.e("new", "2026-08-29T02:00:00+03:00", "Recurrence", scope="assistant-orchestration/error-a", title="Again")
        report = build_timeline([old, new], view="errors", limit=10)
        self.assertEqual(report["matching_threads"], 1)
        self.assertEqual(report["threads"][0]["event_count"], 2)
        newest = report["events"][0]
        self.assertEqual(newest["id"], "new")
        self.assertEqual(newest["previous_in_thread"], "old")
        self.assertEqual(newest["thread_source"], "SPECIFIC_SCOPE")
        self.assertIn("no causal edge", report["contract"]["relationships"])

    def test_broad_scope_does_not_falsely_merge_unrelated_incidents(self):
        a = self.e("a", "2026-08-28T20:00:00+03:00", "One incident", scope="response-quality", title="One incident")
        b = self.e("b", "2026-08-29T02:00:00+03:00", "Different incident", scope="response-quality", title="Different incident")
        report = build_timeline([a, b], view="errors", limit=10)
        self.assertEqual(report["matching_threads"], 2)
        self.assertTrue(all(event["thread_source"] == "EVENT_ONLY" for event in report["events"]))

    def test_explicit_thread_can_join_events_across_scopes(self):
        a = self.e("a", "2026-08-28T20:00:00+03:00", "Root incident", scope="response-quality", title="Root")
        b = self.e("b", "2026-08-29T02:00:00+03:00", "Recurrence", scope="mcp", title="Recurrence")
        a["thread"] = "incident-family-42"
        b["thread"] = "incident-family-42"
        report = build_timeline([a, b], view="errors", limit=10)
        self.assertEqual(report["matching_threads"], 1)
        self.assertEqual(report["threads"][0]["event_count"], 2)
        self.assertTrue(all(event["thread_source"] == "EXPLICIT_THREAD" for event in report["events"]))

    def test_supersession_is_explicit_and_history_is_preserved(self):
        old = self.e("old", "2026-08-28T20:00:00+03:00", "Old theory", scope="mcp/error")
        new = self.e("new", "2026-08-29T02:00:00+03:00", "Correction", kind="correction", scope="mcp/error", supersedes=["old"])
        report = build_timeline([old, new], view="errors", limit=10)
        by_id = {event["id"]: event for event in report["events"]}
        self.assertEqual(by_id["old"]["disposition"], "SUPERSEDED")
        self.assertEqual(by_id["old"]["superseded_by"], ["new"])
        self.assertEqual(by_id["new"]["supersedes"], ["old"])

    def test_project_view_distinguishes_explicit_project_from_entity_mention(self):
        explicit = self.e("p3", "2026-08-29T01:00:00+03:00", "P3 build event", scope="p3/build", project="p3")
        linked = self.e("linked", "2026-08-29T02:00:00+03:00", "A cross-project incident affected P3 and Tiny3D.", scope="assistant-orchestration/incident", title="Cross-project incident")
        other = self.e("other", "2026-08-29T02:30:00+03:00", "LowVRAM only", scope="lowvram/build", project="lowvram")
        report = build_timeline([explicit, linked, other], view="project", project="p3", limit=10)
        by_id = {event["id"]: event for event in report["events"]}
        self.assertEqual(set(by_id), {"p3", "linked"})
        self.assertEqual(by_id["p3"]["project_linkage"], "EXPLICIT_PROJECT")
        self.assertEqual(by_id["linked"]["project_linkage"], "ENTITY_MENTION")
        self.assertEqual(by_id["linked"]["projects"], [])

    def test_timeline_has_no_full_conversation_archive_dependency(self):
        source = (ROOT / "tools" / "memory_timeline.py").read_text(encoding="utf-8")
        self.assertNotIn("conversation_search", source)
        self.assertNotIn("conversation_corpus", source)
        self.assertNotIn("memory/conversations", source)

    def test_general_and_project_timeline_include_worker_history_without_promoting_it(self):
        memory = self.e("mem", "2026-08-29T01:00:00+03:00", "Durable decision", scope="p3/decision", project="p3")
        worker_event = {
            "id": "worker:Cedar:abc", "source_type": "WORKER_REPORT", "authority": "DERIVED_WORKER_HISTORY",
            "event_at": "2026-08-29T02:00:00+03:00", "recorded_at": "2026-08-29T02:00:01+03:00",
            "project": "p3", "worker": "Cedar", "title": "Cedar: SUBSTANTIVE_PROGRESS ? p3#414",
            "summary": "PR #764 merged", "refs": ["p3#414", "PR #764"],
            "duration_minutes": 23.0, "target_run_minutes": 24.0, "target_utilization_pct": 95.8,
        }
        general = build_timeline([memory], worker_events=[worker_event], limit=10)
        self.assertEqual(general["worker_events"], 1)
        self.assertEqual(general["events"][0]["source_type"], "WORKER_REPORT")
        project = build_timeline([memory], view="project", project="p3", worker_events=[worker_event], limit=10)
        self.assertEqual(project["worker_events"], 1)
        self.assertEqual(project["events"][0]["target_utilization_pct"], 95.8)
        errors = build_timeline([memory], view="errors", worker_events=[worker_event], limit=10)
        self.assertEqual(errors["worker_events"], 0)

    def test_error_view_does_not_infer_incidents_from_commit_titles(self):
        incident = self.e("err", "2026-08-29T01:00:00+03:00", "Incident", scope="p3/error", tags=["error"])
        repo_event = {
            "id": "git:p3:def", "source_type": "GIT_COMMIT", "authority": "REPO_HISTORY",
            "event_at": "2026-08-29T02:00:00+03:00", "project": "p3", "projects": ["p3"],
            "title": "fix error handling", "summary": "fix error handling", "sha": "def", "short_sha": "def",
            "refs": [], "thread_id": "repo:p3", "thread_source": "PROJECT_REPO_STREAM",
        }
        report = build_timeline([incident], view="errors", repo_events=[repo_event], limit=10)
        self.assertEqual(report["repo_events"], 0)
        self.assertEqual([event["id"] for event in report["events"]], ["err"])

    def test_vague_error_recurrence_returns_recent_error_threads_without_keywords(self):
        self.assertTrue(needs_timeline_fallback("omg this error again"))
        root = self.e("root", "2026-08-28T20:00:00+03:00", "Fabricated receipt incident", kind="correction", scope="assistant-orchestration/red-critical-receipts", title="Critical receipt incident")
        recurrence = self.e("again", "2026-08-29T02:00:00+03:00", "Recurrence", scope="assistant-orchestration/red-critical-receipts", state="PROVISIONAL", title="Recurrence")
        unrelated = self.e("other", "2026-08-28T19:00:00+03:00", "Other incident", scope="mcp/security-incident", title="Other")
        threads = build_recurrence_context([root, recurrence, unrelated], "omg this error again", max_threads=2)
        self.assertEqual(threads[0]["event_count"], 2)
        self.assertEqual([event["id"] for event in threads[0]["events"]], ["root", "again"])

    def test_cli_is_bounded_and_derived(self):
        with tempfile.TemporaryDirectory() as d:
            bank = Path(d) / "bank.jsonl"
            rows = [self.e(f"e{i}", f"2026-08-29T0{i}:00:00+03:00", f"Event {i}", scope="p3/build", project="p3") for i in range(1, 4)]
            bank.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            proc = subprocess.run([sys.executable, str(ROOT / "tools" / "memory_bank.py"), "--bank", str(bank), "timeline", "--view", "project", "--project", "p3", "--limit", "2", "--no-workers"], capture_output=True, text=True, encoding="utf-8", check=True)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["authority"], "DERIVED_HISTORY_ONLY")
            self.assertEqual(len(payload["events"]), 2)
            self.assertTrue(payload["truncated"])


if __name__ == "__main__":
    unittest.main()
