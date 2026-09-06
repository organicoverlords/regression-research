import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from tools.memory_timeline import build_incident_rollups, build_recurrence_context, build_timeline, needs_timeline_fallback


ROOT = Path(__file__).resolve().parents[1]


class MemoryTimelineTests(unittest.TestCase):
    @staticmethod
    def e(memory_id, timestamp, text, *, kind="lesson", scope="global", state="PROVEN", title=None, tags=None, evidence=None, supersedes=None, project=None, event_at=None, thread=None):
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
        if thread:
            out["thread"] = thread
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

    def test_single_stable_github_evidence_anchor_joins_broad_scopes(self):
        a = self.e("a", "2026-08-28T20:00:00+03:00", "Root incident", scope="response-quality", title="Root", evidence=["github:organicoverlords/regression-research#125"])
        b = self.e("b", "2026-08-29T02:00:00+03:00", "Recurrence", scope="mcp", title="Recurrence", evidence=["https://github.com/organicoverlords/regression-research/issues/125"])
        report = build_timeline([a, b], view="errors", limit=10)
        self.assertEqual(report["matching_threads"], 1)
        self.assertEqual(report["threads"][0]["event_count"], 2)
        self.assertEqual(report["events"][0]["thread_source"], "EVIDENCE_ANCHOR")
        self.assertEqual(report["events"][0]["thread_id"], "evidence:github:organicoverlords/regression-research#125")

    def test_ambiguous_evidence_anchors_do_not_merge_broad_scope_events(self):
        a = self.e("a", "2026-08-28T20:00:00+03:00", "One incident", scope="response-quality", title="One", evidence=["github:organicoverlords/regression-research#125", "github:organicoverlords/regression-research#122"])
        b = self.e("b", "2026-08-29T02:00:00+03:00", "Other incident", scope="response-quality", title="Other", evidence=["github:organicoverlords/regression-research#125", "github:organicoverlords/regression-research#122"])
        report = build_timeline([a, b], view="errors", limit=10)
        self.assertEqual(report["matching_threads"], 2)
        self.assertTrue(all(event["thread_source"] == "EVENT_ONLY" for event in report["events"]))

    def test_explicit_non_error_learning_thread_rolls_up(self):
        decision = self.e(
            "decision", "2026-09-06T03:29:46+03:00",
            "Automatic learning uses compact rollups", scope="memory", title="Decision",
            kind="decision", thread="vault-memory-bootstrap-automatic-learning", tags=["memory"],
        )
        lesson = self.e(
            "lesson", "2026-09-06T03:34:19+03:00",
            "Deleted mirror blocked publication", scope="memory", title="Lesson",
            kind="lesson", thread="vault-memory-bootstrap-automatic-learning", tags=["memory", "sync"],
        )
        rollups = build_incident_rollups([decision, lesson], limit=3)
        self.assertEqual(len(rollups), 1)
        self.assertEqual(rollups[0]["thread_id"], "thread:vault-memory-bootstrap-automatic-learning")
        self.assertEqual(rollups[0]["thread_source"], "EXPLICIT_THREAD")
        self.assertEqual(rollups[0]["observations"], 2)
        self.assertEqual(rollups[0]["latest_event_id"], "lesson")

    def test_non_error_specific_scope_does_not_roll_up_without_explicit_lineage(self):
        a = self.e("a", "2026-09-06T03:00:00+03:00", "ordinary note", scope="memory/topic", title="A", kind="fact", tags=["memory"])
        b = self.e("b", "2026-09-06T03:01:00+03:00", "another ordinary note", scope="memory/topic", title="B", kind="fact", tags=["memory"])
        self.assertEqual(build_incident_rollups([a, b], limit=3), [])

    def test_incident_rollup_compacts_twenty_observations_with_drilldown(self):
        entries = [
            self.e(
                f"e{i:02d}",
                f"2026-08-29T{(i // 60):02d}:{(i % 60):02d}:00+03:00",
                f"Regression observation {i}",
                scope="mcp",
                title=f"Regression {i}",
                tags=["regression"],
                evidence=["github:organicoverlords/regression-research#125"],
            )
            for i in range(20)
        ]
        rollups = build_incident_rollups(entries, limit=3)
        self.assertEqual(len(rollups), 1)
        rollup = rollups[0]
        self.assertEqual(rollup["observations"], 20)
        self.assertEqual(rollup["latest_event_id"], "e19")
        self.assertEqual(len(rollup["member_ids"]), 20)
        self.assertIn("timeline --thread", rollup["drilldown"])
        self.assertIn("evidence:github:organicoverlords/regression-research#125", rollup["drilldown"])

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

    def test_multi_source_snapshots_emphasize_24h_and_use_incremental_older_slices(self):
        now = datetime.fromisoformat("2026-09-06T04:00:00+03:00")
        memory = self.e(
            "mem", "2026-09-06T03:00:00+03:00", "Latest durable lesson",
            evidence=["github:organicoverlords/regression-research#125"],
        )
        repo_event = {
            "id": "git:vault:abc", "source_type": "GIT_COMMIT", "authority": "REPO_HISTORY",
            "event_at": "2026-09-06T02:00:00+03:00", "project": "vault", "projects": ["vault"],
            "title": "timeline work (#125)", "summary": "timeline work", "refs": ["#125"],
            "anchors": ["github:organicoverlords/regression-research#125"],
        }
        screenshot = {
            "id": "artifact:screenshot", "source_type": "TRACKED_ARTIFACT", "authority": "PRESERVED_REPO_ARTIFACT_HISTORY",
            "event_at": "2026-09-04T12:00:00+03:00", "project": "regression-research",
            "title": "screenshot: binding.png", "artifact_type": "screenshot", "path": "02 Evidence/binding.png",
            "anchors": ["artifact:02 evidence/binding.png"],
        }
        proof_artifact = {
            "id": "artifact:proof", "source_type": "TRACKED_ARTIFACT", "authority": "PRESERVED_REPO_ARTIFACT_HISTORY",
            "event_at": "2026-09-01T11:00:00+03:00", "project": "regression-research",
            "title": "proof: proof.png", "artifact_type": "proof", "path": "02 Evidence/proof.png",
            "anchors": ["artifact:02 evidence/proof.png"],
        }
        worker = {
            "id": "worker:proof", "source_type": "WORKER_REPORT", "authority": "DERIVED_WORKER_HISTORY",
            "event_at": "2026-09-01T12:00:00+03:00", "project": "regression-research",
            "title": "worker proof", "summary": "proof archived", "proof_artifact": "02 Evidence/proof.png",
        }
        report = build_timeline(
            [memory], repo_events=[repo_event], worker_events=[worker],
            artifact_events=[screenshot, proof_artifact], limit=20, snapshot_now=now,
        )
        windows = {item["window"]: item for item in report["snapshots"]["windows"]}
        self.assertEqual(windows["24h"]["event_count"], 2)
        self.assertEqual(windows["24h"]["source_counts"], {"GIT_COMMIT": 1, "VAULT_MEMORY": 1})
        self.assertEqual([item["id"] for item in windows["24h"]["highlights"]], ["git:vault:abc", "mem"])
        gh_context = next(item for item in windows["24h"]["corroborated_anchors"] if item["anchor"] == "github:organicoverlords/regression-research#125")
        self.assertEqual(gh_context["role"], "CONTEXT_ONLY")
        self.assertFalse(gh_context["case_identity"])
        self.assertEqual(report["snapshots"]["narrative_contract"]["primary_unit"], "CONTINUITY_CASE")
        self.assertEqual(report["snapshots"]["narrative_contract"]["answer_order"][0], "CONTINUITY_CASES")
        self.assertEqual(report["snapshots"]["narrative_contract"]["broad_github_anchors"], "CONTEXT_ONLY_NEVER_CASE_IDENTITY")

        self.assertEqual(windows["3d"]["event_count"], 3)
        self.assertEqual(windows["3d"]["slice"], "24h-72h")
        self.assertEqual([item["id"] for item in windows["3d"]["highlights"]], ["artifact:screenshot"])
        self.assertEqual(windows["3d"]["artifact_counts"], {"screenshot": 1})

        self.assertEqual(windows["7d"]["event_count"], 5)
        self.assertEqual(windows["7d"]["slice"], "72h-168h")
        self.assertEqual({item["id"] for item in windows["7d"]["highlights"]}, {"worker:proof", "artifact:proof"})
        proof_link = next(item for item in windows["7d"]["corroborated_anchors"] if item["anchor"] == "artifact:02 evidence/proof.png")
        self.assertEqual(proof_link["role"], "CASE_LINK_SUPPORT")
        self.assertTrue(proof_link["case_identity"])
        self.assertIn("continuity cases are the primary incident unit", report["snapshots"]["contract"])

    def test_continuity_case_unifies_red_memory_report_and_screenshot_by_strong_anchors(self):
        now = datetime.fromisoformat("2026-09-06T04:00:00+03:00")
        report_path = "01 Reports/2026-09-06_red_case.md"
        memory = self.e(
            "red-memory", "2026-09-06T03:47:00+03:00", "Structured correction",
            kind="correction", scope="mcp/reroute", title="RED ALERT: bad policy regression",
            tags=["red-alert", "regression"], evidence=[report_path], thread="mcp-reroute-case",
        )
        report_event = {
            "id": "artifact:report", "source_type": "TRACKED_ARTIFACT", "authority": "PRESERVED_REPO_ARTIFACT_HISTORY",
            "event_at": "2026-09-06T03:48:00+03:00", "project": "regression-research",
            "title": "report: preserved case report", "artifact_type": "report", "path": report_path,
            "incident_id": "INC-20260906-CASE", "evidence_type": "evidence_bounded_incident_report",
            "anchors": ["artifact:" + report_path.casefold(), "incident:inc-20260906-case"],
        }
        screenshot_event = {
            "id": "artifact:screenshot", "source_type": "TRACKED_ARTIFACT", "authority": "PRESERVED_REPO_ARTIFACT_HISTORY",
            "event_at": "2026-09-06T03:49:00+03:00", "project": "regression-research",
            "title": "screenshot: proof.png", "artifact_type": "screenshot", "path": "02 Evidence/proof.png",
            "incident_id": "INC-20260906-CASE", "evidence_type": "incident_evidence",
            "anchors": ["incident:inc-20260906-case", "artifact:02 evidence/proof.png"],
        }
        legacy_worker = {
            "id": "worker:legacy-red", "source_type": "WORKER_REPORT", "authority": "DERIVED_WORKER_HISTORY",
            "event_at": "2026-09-06T03:50:00+03:00", "title": "Red-alert batching policy revert",
            "finding_tags": ["regression"], "summary": "same work, but no explicit case anchor",
        }
        result = build_timeline(
            [memory], artifact_events=[report_event, screenshot_event], worker_events=[legacy_worker],
            limit=20, snapshot_now=now,
        )
        window = result["snapshots"]["windows"][0]
        self.assertEqual(window["signal_observation_summary"]["red"], 1)
        self.assertEqual(window["continuity_case_summary"]["red"], 1)
        red_case = next(case for case in window["continuity_cases"] if case["severity"] == "RED")
        self.assertEqual(red_case["case_id"], "incident:inc-20260906-case")
        self.assertEqual(red_case["source_families"], ["artifact", "memory"])
        self.assertEqual(red_case["evidence_forms"], ["memory", "report", "screenshot"])
        self.assertEqual(red_case["observation_count"], 3)
        self.assertFalse(red_case["legacy_inferred"])
        self.assertEqual(red_case["classification_quality"], "STRUCTURED")
        self.assertFalse(red_case["legacy_support_present"])
        self.assertEqual(red_case["legacy_dependent_fields"], [])
        worker_event = next(event for event in result["events"] if event["id"] == "worker:legacy-red")
        self.assertEqual(worker_event["continuity"]["severity"], "NORMAL")
        self.assertEqual(worker_event["continuity"]["traits"], ["regression"])
        self.assertFalse(worker_event["continuity"]["legacy_inferred"])

    def test_mixed_case_is_not_legacy_dependent_when_structured_members_support_every_case_semantic(self):
        now = datetime.fromisoformat("2026-09-06T06:00:00+03:00")
        report_path = "01 Reports/2026-09-06_red_case.md"
        memory = self.e(
            "red-memory", "2026-09-06T04:00:00+03:00", "Structured correction",
            kind="correction", scope="mcp/reroute", title="Policy correction",
            tags=["red-alert", "regression"], evidence=[report_path], thread="mcp-reroute-case",
        )
        report_event = {
            "id": "artifact:red-report", "source_type": "TRACKED_ARTIFACT", "authority": "PRESERVED_REPO_ARTIFACT_HISTORY",
            "event_at": "2026-09-06T05:00:00+03:00", "project": "regression-research",
            "title": "report: RED ALERT preserved incident report", "artifact_type": "report", "path": report_path,
            "evidence_type": "incident_report", "anchors": ["artifact:" + report_path.casefold()],
        }
        result = build_timeline([memory], artifact_events=[report_event], limit=20, snapshot_now=now)
        case = next(case for case in result["snapshots"]["windows"][0]["continuity_cases"] if case["severity"] == "RED")
        self.assertEqual(case["classification_quality"], "MIXED")
        self.assertTrue(case["legacy_support_present"])
        self.assertEqual(case["legacy_dependent_fields"], [])
        self.assertFalse(case["legacy_inferred"])
        report = next(event for event in result["events"] if event["id"] == "artifact:red-report")
        self.assertTrue(report["continuity"]["legacy_severity_inferred"])
        self.assertNotIn("legacy_traits_inferred", report["continuity"])

    def test_case_remains_legacy_dependent_when_no_structured_member_supports_red_severity(self):
        now = datetime.fromisoformat("2026-09-06T06:00:00+03:00")
        report_path = "01 Reports/2026-09-06_legacy_red_case.md"
        report_event = {
            "id": "artifact:legacy-red", "source_type": "TRACKED_ARTIFACT", "authority": "PRESERVED_REPO_ARTIFACT_HISTORY",
            "event_at": "2026-09-06T05:00:00+03:00", "project": "regression-research",
            "title": "report: RED ALERT old incident report", "artifact_type": "report", "path": report_path,
            "evidence_type": "incident_report", "anchors": ["artifact:" + report_path.casefold()],
        }
        result = build_timeline([], artifact_events=[report_event], limit=20, snapshot_now=now)
        case = result["snapshots"]["windows"][0]["continuity_cases"][0]
        self.assertEqual(case["classification_quality"], "LEGACY_DEPENDENT")
        self.assertTrue(case["legacy_support_present"])
        self.assertEqual(case["legacy_dependent_fields"], ["severity:red"])
        self.assertTrue(case["legacy_inferred"])

    def test_broad_github_anchor_is_corroboration_not_case_identity(self):
        now = datetime.fromisoformat("2026-09-06T04:00:00+03:00")
        a = self.e(
            "a", "2026-09-06T03:00:00+03:00", "First red case", title="RED ALERT: first",
            tags=["red-alert", "regression"], evidence=["github:organicoverlords/regression-research#125"], thread="case-a",
        )
        b = self.e(
            "b", "2026-09-06T03:10:00+03:00", "Second red case", title="RED ALERT: second",
            tags=["red-alert", "regression"], evidence=["github:organicoverlords/regression-research#125"], thread="case-b",
        )
        repo_event = {
            "id": "git:vault:125", "source_type": "GIT_COMMIT", "authority": "REPO_HISTORY",
            "event_at": "2026-09-06T03:20:00+03:00", "project": "vault", "projects": ["vault"],
            "title": "umbrella issue update", "summary": "umbrella issue update",
            "anchors": ["github:organicoverlords/regression-research#125"], "refs": ["#125"],
        }
        result = build_timeline([a, b], repo_events=[repo_event], limit=20, snapshot_now=now)
        window = result["snapshots"]["windows"][0]
        self.assertEqual(window["continuity_case_summary"]["red"], 2)
        self.assertEqual({case["case_id"] for case in window["continuity_cases"]}, {"thread:case-a", "thread:case-b"})
        anchor = next(item for item in window["corroborated_anchors"] if item["anchor"] == "github:organicoverlords/regression-research#125")
        self.assertEqual(anchor["role"], "CONTEXT_ONLY")
        self.assertFalse(anchor["case_identity"])
        self.assertEqual(result["snapshots"]["narrative_contract"]["context_wording"], "DO_NOT_CALL_CONTEXT_ONLY_ANCHOR_THE_CASE_OR_THREAD")

    def test_modern_structured_memory_title_cannot_create_incident_trait_from_prose(self):
        now = datetime.fromisoformat("2026-09-06T06:00:00+03:00")
        entry = self.e(
            "modern-correction", "2026-09-06T05:00:00+03:00", "Correction about taxonomy language.",
            kind="correction", scope="vault/timeline/taxonomy", title="Taxonomy lesson is not itself an incident",
            tags=["timeline", "taxonomy", "assistant-recorded", "verbatim-source"],
            thread="vault-timeline-multisource-continuity",
        )
        result = build_timeline([entry], limit=10, snapshot_now=now)
        event = result["events"][0]
        self.assertEqual(event["continuity"]["traits"], [])
        self.assertEqual(event["continuity"]["severity"], "NORMAL")
        self.assertFalse(event["continuity"]["legacy_inferred"])
        self.assertEqual(result["snapshots"]["windows"][0]["continuity_case_summary"]["total"], 0)

    def test_modern_structured_status_scope_cannot_create_incident_trait(self):
        now = datetime.fromisoformat("2026-09-06T06:00:00+03:00")
        entry = self.e(
            "modern-status", "2026-09-06T05:00:00+03:00", "Current historical observation.",
            kind="status", scope="assistant-orchestration/incident-followup",
            title="Security reroute still occurs after restore",
            tags=["security-reroute", "platform-routing", "assistant-recorded", "verbatim-source"],
            thread="mcp-security-reroute-causality",
        )
        result = build_timeline([entry], limit=10, snapshot_now=now)
        self.assertEqual(result["events"][0]["continuity"]["traits"], [])
        self.assertEqual(result["snapshots"]["windows"][0]["continuity_case_summary"]["total"], 0)

    def test_generic_evidence_filename_cannot_create_regression_case(self):
        event = {
            "id": "artifact:matrix", "source_type": "TRACKED_ARTIFACT", "authority": "PRESERVED_REPO_ARTIFACT_HISTORY",
            "event_at": "2026-09-06T05:00:00+03:00", "project": "regression-research",
            "title": "evidence: regression-coverage-matrix.csv", "artifact_type": "evidence",
            "path": "02 Evidence/regression-coverage-matrix.csv",
            "anchors": ["artifact:02 evidence/regression-coverage-matrix.csv"],
        }
        result = build_timeline([], artifact_events=[event], limit=10, snapshot_now=datetime.fromisoformat("2026-09-06T06:00:00+03:00"))
        self.assertEqual(result["events"][0]["continuity"]["traits"], [])
        self.assertEqual(result["snapshots"]["windows"][0]["continuity_case_summary"]["total"], 0)

    def test_structured_research_report_named_regression_research_is_not_regression_case(self):
        event = {
            "id": "artifact:research", "source_type": "TRACKED_ARTIFACT", "authority": "PRESERVED_REPO_ARTIFACT_HISTORY",
            "event_at": "2026-09-06T05:00:00+03:00", "project": "regression-research",
            "title": "report: Regression Research #125 - timeline convergence research", "artifact_type": "report",
            "path": "01 Reports/timeline_convergence_research.md", "evidence_type": "research_report",
            "anchors": ["artifact:01 reports/timeline_convergence_research.md"],
        }
        result = build_timeline([], artifact_events=[event], limit=10, snapshot_now=datetime.fromisoformat("2026-09-06T06:00:00+03:00"))
        self.assertEqual(result["events"][0]["continuity"]["event_class"], "EVIDENCE")
        self.assertEqual(result["events"][0]["continuity"]["traits"], [])
        self.assertEqual(result["snapshots"]["windows"][0]["continuity_case_summary"]["total"], 0)

    def test_old_unstructured_report_can_still_recover_recurrence_trait(self):
        event = {
            "id": "artifact:old-recurrence", "source_type": "TRACKED_ARTIFACT", "authority": "PRESERVED_REPO_ARTIFACT_HISTORY",
            "event_at": "2026-09-06T05:00:00+03:00", "project": "regression-research",
            "title": "report: MCP half-alive tunnel recurrence and fix", "artifact_type": "report",
            "path": "01 Reports/old_recurrence.md", "anchors": ["artifact:01 reports/old_recurrence.md"],
        }
        result = build_timeline([], artifact_events=[event], limit=10, snapshot_now=datetime.fromisoformat("2026-09-06T06:00:00+03:00"))
        event_out = result["events"][0]
        self.assertEqual(event_out["continuity"]["traits"], ["regression"])
        self.assertTrue(event_out["continuity"]["legacy_inferred"])

    def test_structured_worker_findings_block_title_only_red_promotion(self):
        event = {
            "id": "worker:structured-regression", "source_type": "WORKER_REPORT", "authority": "DERIVED_WORKER_HISTORY",
            "event_at": "2026-09-06T05:00:00+03:00", "title": "Red-alert policy revert",
            "finding_tags": ["regression"], "summary": "A regression was corrected.",
        }
        result = build_timeline([], worker_events=[event], limit=10, snapshot_now=datetime.fromisoformat("2026-09-06T06:00:00+03:00"))
        semantics = result["events"][0]["continuity"]
        self.assertEqual(semantics["severity"], "NORMAL")
        self.assertEqual(semantics["traits"], ["regression"])
        self.assertFalse(semantics["legacy_inferred"])

    def test_incidental_body_word_does_not_override_structured_non_incident_metadata(self):
        now = datetime.fromisoformat("2026-09-06T04:00:00+03:00")
        entry = self.e(
            "policy", "2026-09-06T03:00:00+03:00",
            "This workflow policy discusses how old slopwall reports used to be handled.",
            kind="decision", scope="assistant-orchestration/presentation", title="Response gate policy",
            tags=["presentation", "policy"],
        )
        result = build_timeline([entry], limit=20, snapshot_now=now)
        event = result["events"][0]
        self.assertEqual(event["continuity"]["severity"], "NORMAL")
        self.assertEqual(event["continuity"]["traits"], [])
        self.assertFalse(event["continuity"]["legacy_inferred"])
        self.assertEqual(result["snapshots"]["windows"][0]["continuity_case_summary"].get("slopwall", 0), 0)

    def test_preserved_memory_history_retains_red_observations_outside_seven_day_snapshot(self):
        now = datetime.fromisoformat("2026-09-06T04:00:00+03:00")
        old = self.e(
            "old-red", "2026-08-20T03:00:00+03:00", "Old alert", title="RED ALERT: old",
            tags=["red-alert", "incident"], scope="assistant-orchestration/old-red",
        )
        recent = self.e(
            "recent-red", "2026-09-06T03:00:00+03:00", "Recent alert", title="RED ALERT: recent",
            tags=["red-alert", "regression"], scope="assistant-orchestration/recent-red",
        )
        result = build_timeline([old, recent], limit=20, since=datetime.fromisoformat("2026-08-30T04:00:00+03:00"), snapshot_now=now)
        self.assertEqual(result["snapshots"]["windows"][0]["continuity_case_summary"]["red"], 1)
        self.assertEqual(result["snapshots"]["preserved_memory_history"]["red_observations"], 2)

    def test_superseded_and_rejected_memories_remain_in_chronology_but_do_not_inflate_active_signal_cases(self):
        now = datetime.fromisoformat("2026-09-06T05:00:00+03:00")
        bad = self.e(
            "bad", "2026-09-06T04:00:00+03:00", "Taxonomy lesson", kind="lesson",
            scope="vault/timeline/taxonomy", title="RED ALERT taxonomy lesson",
            tags=["red-alert", "incident", "slopwall"], thread="timeline-taxonomy",
        )
        correction = self.e(
            "correction", "2026-09-06T04:10:00+03:00", "Remove topical incident tags", kind="correction",
            scope="vault/timeline/taxonomy", title="Taxonomy lesson is not an incident",
            tags=["timeline", "taxonomy"], supersedes=["bad"], thread="timeline-taxonomy",
        )
        rejected = self.e(
            "rejected", "2026-09-06T04:20:00+03:00", "Rejected alert hypothesis", kind="lesson",
            scope="vault/timeline/rejected", title="RED ALERT rejected hypothesis",
            tags=["red-alert", "incident"], state="REJECTED", thread="rejected-alert",
        )
        result = build_timeline([bad, correction, rejected], limit=20, snapshot_now=now)
        by_id = {event["id"]: event for event in result["events"]}
        self.assertEqual(by_id["bad"]["disposition"], "SUPERSEDED")
        self.assertEqual(by_id["rejected"]["disposition"], "REJECTED")
        self.assertEqual(set(by_id), {"bad", "correction", "rejected"})
        window = result["snapshots"]["windows"][0]
        self.assertNotIn("red", window["signal_observation_summary"])
        self.assertNotIn("red", window["continuity_case_summary"])
        self.assertEqual(result["snapshots"]["preserved_memory_history"]["red_observations"], 0)

    def test_invalid_external_timestamps_are_skipped_and_counted(self):
        entry = self.e("mem", "2026-09-06T03:00:00+03:00", "valid")
        broken_worker = {
            "id": "worker:broken", "source_type": "WORKER_REPORT", "authority": "DERIVED_WORKER_HISTORY",
            "event_at": "2026-09-03T12.32.58.6884719+03:00", "title": "bad timestamp",
        }
        report = build_timeline([entry], worker_events=[broken_worker], limit=10)
        self.assertEqual(report["worker_events"], 0)
        self.assertEqual(report["invalid_source_events"], {"WORKER_REPORT": 1})
        self.assertEqual([event["id"] for event in report["events"]], ["mem"])

    def test_supplemental_sources_join_canonical_timeline_without_keyword_incident_inference(self):
        event = {
            "id": "github-pr:p3#10",
            "source_type": "GITHUB_PR",
            "authority": "GITHUB_HISTORY_SNAPSHOT",
            "event_at": "2026-09-06T04:00:00+03:00",
            "recorded_at": "2026-09-06T04:00:00+03:00",
            "project": "p3",
            "projects": ["p3"],
            "title": "PR #10: incident wording in ordinary change title",
            "summary": "state=MERGED",
            "github_kind": "pr",
            "refs": ["#10"],
            "anchors": ["github:organicoverlords/p3#10", "pr:github:organicoverlords/p3#10"],
        }
        result = build_timeline([], supplemental_events=[event], limit=10)
        self.assertEqual(result["supplemental_events"], 1)
        self.assertEqual(result["events"][0]["evidence_form"], "pull_request")
        self.assertEqual(result["events"][0]["continuity"]["traits"], [])
        self.assertFalse(result["events"][0]["continuity"]["legacy_inferred"])
        self.assertEqual(result["snapshots"]["windows"][0]["source_counts"], {"GITHUB_PR": 1})

    def test_default_timeline_read_fails_closed_when_materialization_is_missing(self):
        state = ROOT / ".state" / "timeline" / "timeline-store.json"
        if state.exists():
            self.skipTest("test requires a clean worktree without local materialized state")
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "memory_bank.py"), "timeline", "--limit", "2", "--no-workers"],
            capture_output=True, text=True, encoding="utf-8", check=False,
        )
        self.assertEqual(proc.returncode, 2)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "MISSING")
        self.assertEqual(payload["read_mode"], "MATERIALIZED_ONLY")
        self.assertIn("timeline_materializer.py refresh", payload["refresh_command"])

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
