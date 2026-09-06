import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from tools.repo_timeline import RepoSpec
from tools.timeline_materializer import (
    BOOTSTRAP_SCHEMA,
    DEFAULT_DELTA_REPO_EVENTS_PER_REPO,
    DEFAULT_OVERLAP_MINUTES,
    SCHEMA,
    build_work_graph,
    github_events,
    install_task,
    local_artifact_events,
    main,
    materialize,
    materialized_health,
    mcp_events,
    query_materialized,
    runner_log_events,
)


class TimelineMaterializerTests(unittest.TestCase):
    def commit_event(self, sha, title, at, *, patch_id=None, branches=None, anchors=None):
        row = {
            "id": f"git:p3:{sha}",
            "source_type": "GIT_COMMIT",
            "authority": "REPO_HISTORY",
            "event_at": at,
            "project": "p3",
            "projects": ["p3"],
            "title": title,
            "summary": title,
            "sha": sha,
            "short_sha": sha[:10],
            "refs": [],
            "anchors": anchors or [],
            "branch_refs": branches or [],
        }
        if patch_id:
            row["patch_id"] = patch_id
        return row

    def test_work_graph_groups_patch_equivalents_and_attaches_worker_and_action_efficiency(self):
        branch_sha = "a" * 40
        main_sha = "b" * 40
        patch_id = "c" * 40
        branch = self.commit_event(
            branch_sha,
            "[#803] Route avatar syncing through wait fallback",
            "2026-09-06T04:50:00+03:00",
            patch_id=patch_id,
            branches=["origin/chatgpt/hazel-803-avatar-sync-wait-20260906"],
        )
        main = self.commit_event(
            main_sha,
            "[#803] Route avatar syncing through wait fallback (#1884)",
            "2026-09-06T04:51:00+03:00",
            patch_id=patch_id,
            anchors=["github:organicoverlords/p3#1884"],
        )
        worker = {
            "id": "worker:hazel",
            "source_type": "WORKER_REPORT",
            "event_at": "2026-09-06T04:52:00+03:00",
            "project": "p3",
            "worker": "Repo Worker Hazel",
            "duration_minutes": 20.4,
            "target_utilization_pct": 85.0,
            "outcome": "merged #1884",
            "mutation": f"#1884 -> {main_sha}",
            "refs": [f"#1884 -> {main_sha}"],
            "anchors": [],
        }
        action = {
            "id": "github-action:p3#99",
            "source_type": "GITHUB_ACTION",
            "event_at": "2026-09-06T04:53:00+03:00",
            "project": "p3",
            "head_sha": main_sha,
            "conclusion": "success",
            "refs": [main_sha],
            "anchors": [f"gitsha:{main_sha}"],
        }
        graph = build_work_graph([branch, main, worker, action])
        self.assertEqual(graph["summary"]["commit_groups"], 1)
        self.assertEqual(graph["summary"]["equivalent_commit_groups"], 1)
        self.assertEqual(graph["summary"]["cross_branch_groups"], 1)
        group = graph["commit_groups"][0]
        self.assertEqual(group["commit_count"], 2)
        self.assertEqual({item["sha"] for item in group["commits"]}, {branch_sha, main_sha})
        self.assertEqual(group["workers"][0]["worker"], "Repo Worker Hazel")
        self.assertEqual(group["workers"][0]["allocated_duration_minutes"], 20.4)
        self.assertEqual(group["efficiency"]["action_runs"], 1)
        self.assertEqual(group["efficiency"]["action_conclusions"], {"success": 1})

    def test_subject_fallback_requires_nearby_branch_activity(self):
        title = "[#803] Explain defensive route control clearly"
        far_a = self.commit_event("1" * 40, title, "2026-08-01T10:00:00+03:00", branches=["topic/a"])
        far_b = self.commit_event("2" * 40, title, "2026-09-06T10:00:00+03:00")
        self.assertEqual(build_work_graph([far_a, far_b])["summary"]["commit_groups"], 2)
        near_a = self.commit_event("3" * 40, title, "2026-09-06T10:00:00+03:00", branches=["topic/a"])
        near_b = self.commit_event("4" * 40, title, "2026-09-06T11:00:00+03:00")
        self.assertEqual(build_work_graph([near_a, near_b])["summary"]["commit_groups"], 1)


    def test_explicit_pr_anchor_can_attach_without_github_object_snapshot(self):
        sha = "d" * 40
        commit = self.commit_event(
            sha, "Implement narrow fix (#1884)", "2026-09-06T05:00:00+03:00",
            anchors=["github:organicoverlords/p3#1884"],
        )
        memory = {
            "id": "mem:proof", "source_type": "VAULT_MEMORY", "event_at": "2026-09-06T05:01:00+03:00",
            "project": "p3", "title": "PR proof", "refs": [],
            "anchors": ["pr:github:organicoverlords/p3#1884"],
        }
        graph = build_work_graph([commit, memory])
        self.assertEqual(graph["summary"]["attached_observations"], 1)
        self.assertEqual(graph["commit_groups"][0]["attached_event_ids"], ["mem:proof"])

    def test_local_artifact_adapter_only_projects_untracked_files(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
            tracked = root / "01 Reports" / "tracked.md"
            tracked.parent.mkdir(parents=True)
            tracked.write_text("tracked", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "tracked"], check=True)
            local = root / "02 Evidence" / "fresh.log"
            local.parent.mkdir(parents=True)
            local.write_text("fresh", encoding="utf-8")
            events, coverage = local_artifact_events(root, since=datetime.now().astimezone() - timedelta(days=1))
            self.assertEqual([event["path"] for event in events], ["02 Evidence/fresh.log"])
            self.assertEqual(events[0]["authority"], "LOCAL_WIP_ARTIFACT_OBSERVATION")
            self.assertEqual(events[0]["artifact_type"], "evidence_log")
            self.assertEqual(coverage["events"], 1)

    def test_github_adapter_projects_issues_prs_and_actions_without_body_fetches(self):
        spec = RepoSpec("p3", Path("C:/fake/p3"))
        now = "2026-09-06T05:00:00Z"
        issue = [{"number": 803, "title": "Milestone", "state": "OPEN", "createdAt": now, "updatedAt": now, "closedAt": None, "url": "https://example/803"}]
        pr = [{"number": 1884, "title": "Avatar wait", "state": "MERGED", "createdAt": now, "updatedAt": now, "closedAt": now, "mergedAt": now, "url": "https://example/1884", "headRefName": "topic", "baseRefName": "main", "headRefOid": "a" * 40}]
        run = [{"databaseId": 99, "workflowName": "verify", "status": "completed", "conclusion": "success", "createdAt": now, "updatedAt": now, "headSha": "a" * 40, "headBranch": "topic", "event": "pull_request", "displayTitle": "Avatar wait", "url": "https://example/run/99"}]
        with patch("tools.timeline_materializer._github_slug", return_value="organicoverlords/p3"), patch(
            "tools.timeline_materializer._run_json", side_effect=[(issue, None), (pr, None), (run, None)]
        ) as run_json:
            events, coverage = github_events([spec], since=datetime(2026, 9, 5, tzinfo=timezone.utc))
        self.assertEqual({event["source_type"] for event in events}, {"GITHUB_ISSUE", "GITHUB_PR", "GITHUB_ACTION"})
        repo_cov = coverage["repos"]["organicoverlords/p3"]
        self.assertEqual(repo_cov["project"], "p3")
        self.assertEqual(repo_cov["issues"]["events"], 1)
        self.assertEqual(repo_cov["prs"]["events"], 1)
        self.assertEqual(repo_cov["actions"]["events"], 1)
        self.assertEqual(repo_cov["limit_per_kind"], repo_cov["issues"]["limit"])
        self.assertEqual(repo_cov["saturated_kinds"], [])
        self.assertFalse(coverage["saturated"])
        commands = [" ".join(call.args[0]) for call in run_json.call_args_list]
        self.assertTrue(all("body" not in command for command in commands))
        self.assertTrue(all("updated:>=2026-09-05T00:00:00Z" in command for command in commands[:2]))
        self.assertIn("created >=2026-09-05T00:00:00Z", commands[2])

    def test_github_adapter_marks_per_kind_saturation_at_query_limit(self):
        spec = RepoSpec("p3", Path("C:/fake/p3"))
        now = "2026-09-06T05:00:00Z"
        issue = [{"number": 1, "title": "one", "state": "OPEN", "createdAt": now, "updatedAt": now, "closedAt": None, "url": "https://example/1"}]
        pr = [{"number": 2, "title": "two", "state": "OPEN", "createdAt": now, "updatedAt": now, "closedAt": None, "mergedAt": None, "url": "https://example/2", "headRefName": "topic", "baseRefName": "main", "headRefOid": "a" * 40}]
        run = [{"databaseId": 3, "workflowName": "verify", "status": "completed", "conclusion": "success", "createdAt": now, "updatedAt": now, "headSha": "a" * 40, "headBranch": "topic", "event": "push", "displayTitle": "three", "url": "https://example/3"}]
        with patch("tools.timeline_materializer._github_slug", return_value="organicoverlords/p3"), patch(
            "tools.timeline_materializer._run_json", side_effect=[(issue, None), (pr, None), (run, None)]
        ):
            _, coverage = github_events([spec], since=datetime(2026, 9, 5, tzinfo=timezone.utc), limit_per_kind=1)
        repo = coverage["repos"]["organicoverlords/p3"]
        self.assertEqual(repo["saturated_kinds"], ["issues", "prs", "actions"])
        self.assertTrue(all(repo[kind]["saturated"] for kind in ("issues", "prs", "actions")))
        self.assertTrue(coverage["saturated"])

    def test_mcp_adapter_materializes_safe_metadata_not_raw_command(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"LOCALAPPDATA": d}):
            base = Path(d) / "ChatGPTMcpClean" / ".state"
            front = base / "front-door"
            receipts = base / "process-receipts"
            front.mkdir(parents=True)
            receipts.mkdir(parents=True)
            rows = [
                {"at": "2026-09-06T05:00:00Z", "event": "front_request_parsed", "request_id": "r1", "tool": "start_process", "process_id": "p1"},
                {"at": "2026-09-06T05:00:01Z", "event": "front_backend_select", "request_id": "r1", "tool": "start_process", "backend_generation": "g1"},
                {"at": "2026-09-06T05:00:02Z", "event": "front_request_finish", "request_id": "r1", "status": 200},
            ]
            (front / "request.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            secret_command = "git show " + "a" * 40 + " #1884 --token SUPERSECRET"
            (receipts / "p1.json").write_text(json.dumps({
                "process_id": "p1", "caller_id": "c1", "started_at": "2026-09-06T05:00:00Z",
                "finished_at": "2026-09-06T05:00:03Z", "exit_code": 0, "cwd": "C:/Users/Lauri/Documents/Unreal Projects/p3",
                "command": secret_command,
            }), encoding="utf-8")
            events, coverage = mcp_events(
                since=datetime(2026, 9, 5, tzinfo=timezone.utc),
                root=Path("C:/vault"),
                project_to_slug={"p3": "organicoverlords/p3"},
            )
            receipt = next(event for event in events if event.get("mcp_event") == "process_receipt")
            self.assertNotIn("command", receipt)
            self.assertNotIn("SUPERSECRET", json.dumps(receipt))
            self.assertEqual(receipt["command_kind"], "git")
            self.assertIn("github:organicoverlords/p3#1884", receipt["anchors"])
            self.assertEqual(coverage["request_logs"], 1)
            self.assertEqual(coverage["receipts"], 1)

    def test_runner_adapter_summarizes_and_does_not_copy_secret_lines(self):
        with tempfile.TemporaryDirectory() as d:
            diag = Path(d) / "runner" / "_diag"
            diag.mkdir(parents=True)
            sha = "b" * 40
            log = diag / "Runner_1.log"
            log.write_text(
                f"[INF] Running job for {sha}\n[WRN] warning\n[ERR] failure\nAuthorization: Bearer SECRET {sha}\n",
                encoding="utf-8",
            )
            with patch("tools.timeline_materializer._runner_diag_roots", return_value=[diag]):
                events, coverage = runner_log_events(since=datetime.now().astimezone() - timedelta(days=1))
            self.assertEqual(len(events), 1)
            event = events[0]
            self.assertIn(sha, event["refs"])
            self.assertNotIn("SECRET", json.dumps(event))
            self.assertIn("raw log body not materialized", event["summary"])
            self.assertEqual(coverage["events"], 1)

    def test_second_refresh_is_incremental_and_reuses_materialized_history(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "memory").mkdir()
            state = root / ".state" / "timeline"
            state.mkdir(parents=True)
            prior_at = datetime(2026, 9, 6, 5, 0, tzinfo=timezone.utc)
            old_sha = "1" * 40
            new_sha = "2" * 40
            old_event = self.commit_event(old_sha, "Old retained work", "2026-09-06T04:50:00+00:00")
            (state / "timeline-store.json").write_text(json.dumps({
                "schema": SCHEMA,
                "generated_at": prior_at.isoformat(),
                "horizon_days": 30,
                "source_watermarks": {name: prior_at.isoformat() for name in (
                    "repos", "workers", "artifacts", "local_artifacts", "github", "mcp", "runner_logs"
                )},
                "ingestion": {"backfill_incomplete_sources": ["github", "repos"]},
                "timeline": {"events": [old_event]},
            }), encoding="utf-8")
            new_event = self.commit_event(new_sha, "New delta work", "2026-09-06T05:04:00+00:00")
            minimal_overview = {"contract": "history only", "eligible_entries": 0, "incident_rollups": [], "recent": [], "projects": [], "recurring_tags": []}
            with patch("tools.timeline_materializer.discover_repo_specs", return_value=[RepoSpec("p3", root)]), patch(
                "tools.timeline_materializer._repo_maps", return_value=({"p3": "organicoverlords/p3"}, {"organicoverlords/p3": "p3"})
            ), patch("tools.timeline_materializer.load_bank", return_value=[]), patch(
                "tools.timeline_materializer.collect_repo_history",
                return_value={"events": [new_event], "coverage": {"p3": {"events": 1, "limit": DEFAULT_DELTA_REPO_EVENTS_PER_REPO, "saturated": False}}},
            ) as collect_repo, patch("tools.timeline_materializer.enrich_repo_events"), patch(
                "tools.timeline_materializer.worker_history_events", side_effect=[[], []]
            ) as worker_history, patch("tools.timeline_materializer.tracked_artifact_events", return_value=[]), patch(
                "tools.timeline_materializer.local_artifact_events", return_value=([], {"events": 0, "candidates": 0, "limit": 1000, "saturated": False})
            ), patch("tools.timeline_materializer.mcp_events", return_value=([], {"events": 0, "receipts_saturated": False, "errors": []})), patch(
                "tools.timeline_materializer.runner_log_events", return_value=([], {"events": 0, "saturated": False, "errors": []})
            ), patch("tools.timeline_materializer.build_overview", return_value=minimal_overview):
                result = materialize(
                    root=root,
                    include_github=False,
                    now=datetime(2026, 9, 6, 5, 5, tzinfo=timezone.utc),
                )
            self.assertEqual(result["refresh_mode"], "INCREMENTAL")
            self.assertEqual(result["delta_events"], 1)
            expected_since = prior_at - timedelta(minutes=DEFAULT_OVERLAP_MINUTES)
            self.assertEqual(collect_repo.call_args.kwargs["since"], expected_since)
            self.assertEqual(collect_repo.call_args.kwargs["limit_per_repo"], DEFAULT_DELTA_REPO_EVENTS_PER_REPO)
            self.assertTrue(all(call.kwargs["since"] == expected_since for call in worker_history.call_args_list))
            payload = json.loads((state / "timeline-store.json").read_text(encoding="utf-8"))
            ids = {event["id"] for event in payload["timeline"]["events"]}
            self.assertIn(old_event["id"], ids)
            self.assertIn(new_event["id"], ids)
            self.assertEqual(payload["ingestion"]["mode"], "INCREMENTAL")
            self.assertEqual(payload["ingestion"]["backfill_incomplete_sources"], ["github", "repos"])
            self.assertEqual(payload["timeline"]["materialized"]["backfill_incomplete_sources"], ["github", "repos"])
            self.assertEqual(payload["source_watermarks"]["repos"], "2026-09-06T05:05:00+00:00")

    def test_materialized_health_keeps_history_role_separate_from_live_truth(self):
        now = datetime(2026, 9, 6, 6, 0, tzinfo=timezone.utc)
        payload = {
            "generated_at": "2026-09-06T05:58:00+00:00",
            "horizon_days": 30,
            "ingestion": {
                "mode": "INCREMENTAL",
                "backfill_incomplete_sources": ["github", "runner_logs"],
                "saturated_sources": [],
                "retry_sources": [],
            },
            "timeline": {"materialized": {"refresh_minutes": 5}},
        }
        health = materialized_health(payload, now=now)
        self.assertEqual(health["status"], "FRESH")
        self.assertEqual(health["coverage_status"], "HISTORICAL_INCOMPLETE")
        self.assertEqual(health["backfill_incomplete_sources"], ["github", "runner_logs"])
        self.assertEqual(health["absence_semantics"], "NO_MATCH_IS_NOT_PROOF_OF_ABSENCE")
        self.assertTrue(health["live_truth_required"])

    def test_materialized_health_stale_or_retry_pending_never_proves_absence(self):
        now = datetime(2026, 9, 6, 6, 30, tzinfo=timezone.utc)
        stale = materialized_health({
            "generated_at": "2026-09-06T06:00:00+00:00",
            "horizon_days": 30,
            "ingestion": {"backfill_incomplete_sources": [], "retry_sources": []},
            "timeline": {"materialized": {"refresh_minutes": 5}},
        }, now=now)
        self.assertEqual(stale["status"], "STALE")
        self.assertEqual(stale["absence_semantics"], "NO_MATCH_IS_NOT_PROOF_OF_ABSENCE")
        self.assertIn("MATERIALIZATION_STALE", stale["absence_unsafe_reasons"])

        retry = materialized_health({
            "generated_at": "2026-09-06T06:29:00+00:00",
            "horizon_days": 30,
            "ingestion": {"backfill_incomplete_sources": [], "retry_sources": ["github"]},
            "timeline": {"materialized": {"refresh_minutes": 5}},
        }, now=now)
        self.assertEqual(retry["status"], "FRESH")
        self.assertEqual(retry["absence_semantics"], "NO_MATCH_IS_NOT_PROOF_OF_ABSENCE")
        self.assertIn("DELTA_RETRY_PENDING", retry["absence_unsafe_reasons"])

    def test_refresh_cli_treats_existing_refresh_lock_as_successful_noop(self):
        with patch("tools.timeline_materializer.build_parser") as build_parser, patch(
            "tools.timeline_materializer.materialize",
            return_value={"ok": False, "status": "ALREADY_RUNNING", "path": "refresh.lock"},
        ):
            build_parser.return_value.parse_args.return_value = type("Args", (), {
                "command": "refresh", "root": Path("."), "days": 30, "repo_events": 1000,
                "artifact_events": 2000, "max_events": 20000, "no_github": False,
                "rebuild": False, "quiet": True,
            })()
            self.assertEqual(main(), 0)

    def test_install_task_schedules_only_periodic_materializer(self):
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="SUCCESS", stderr="")
        with patch("tools.timeline_materializer.subprocess.run", return_value=completed) as run:
            result = install_task(minutes=5)
        command = run.call_args.args[0]
        rendered = " ".join(str(value) for value in command)
        self.assertTrue(result["ok"])
        self.assertIn("/SC MINUTE", rendered)
        self.assertIn("/MO 5", rendered)
        self.assertIn("timeline_materializer.py", rendered)
        self.assertIn("refresh --quiet", rendered)
        self.assertNotIn("memory_bank.py timeline", rendered)

    def test_materialize_writes_deep_store_and_small_projection_and_query_is_read_only(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "memory").mkdir()
            sha1, sha2, patch_id = "c" * 40, "d" * 40, "e" * 40
            repo_events = [
                self.commit_event(sha1, "Improve friend wait", "2026-09-06T04:00:00+03:00", patch_id=patch_id, branches=["topic"]),
                self.commit_event(sha2, "Improve friend wait (#10)", "2026-09-06T04:01:00+03:00", patch_id=patch_id),
            ]
            worker = {
                "id": "worker:test", "source_type": "WORKER_REPORT", "authority": "DERIVED_WORKER_HISTORY",
                "event_at": "2026-09-06T04:02:00+03:00", "recorded_at": "2026-09-06T04:02:00+03:00",
                "project": "p3", "worker": "Hazel", "duration_minutes": 20.0, "target_utilization_pct": 83.3,
                "title": "Hazel done", "summary": sha2, "refs": [sha2], "anchors": [],
            }
            minimal_overview = {"contract": "history only", "eligible_entries": 0, "incident_rollups": [], "recent": [], "projects": [], "recurring_tags": []}
            with patch("tools.timeline_materializer.discover_repo_specs", return_value=[RepoSpec("p3", root)]), patch(
                "tools.timeline_materializer._repo_maps", return_value=({"p3": "organicoverlords/p3"}, {"organicoverlords/p3": "p3"})
            ), patch("tools.timeline_materializer.load_bank", return_value=[]), patch(
                "tools.timeline_materializer.collect_repo_history", return_value={"events": repo_events, "coverage": {"p3": {"events": 2, "limit": 500, "saturated": False}}}
            ), patch("tools.timeline_materializer.enrich_repo_events"), patch(
                "tools.timeline_materializer.worker_history_events", side_effect=[[worker], []]
            ), patch("tools.timeline_materializer.tracked_artifact_events", return_value=[]), patch(
                "tools.timeline_materializer.local_artifact_events", return_value=([], {"events": 0, "candidates": 0, "limit": 1000, "saturated": False})
            ), patch("tools.timeline_materializer.mcp_events", return_value=([], {"events": 0})), patch(
                "tools.timeline_materializer.runner_log_events", return_value=([], {"events": 0})
            ), patch("tools.timeline_materializer.build_overview", return_value=minimal_overview) as build_overview:
                result = materialize(root=root, include_github=False, now=datetime(2026, 9, 6, 5, 0, tzinfo=timezone.utc))
            self.assertTrue(result["ok"])
            self.assertEqual(result["work_graph"]["equivalent_commit_groups"], 1)
            store_path = root / ".state" / "timeline" / "timeline-store.json"
            bootstrap_path = root / ".state" / "timeline" / "bootstrap-memory-overview.json"
            self.assertEqual(json.loads(store_path.read_text(encoding="utf-8"))["schema"], SCHEMA)
            bootstrap = json.loads(bootstrap_path.read_text(encoding="utf-8"))
            self.assertEqual(bootstrap["schema"], BOOTSTRAP_SCHEMA)
            self.assertLess(bootstrap_path.stat().st_size, 5000)
            build_overview.assert_called_once()
            self.assertEqual(build_overview.call_args.kwargs["limit"], 20)

            payload = json.loads(store_path.read_text(encoding="utf-8"))
            payload["ingestion"]["backfill_incomplete_sources"] = ["github"]
            payload["timeline"]["materialized"]["backfill_incomplete_sources"] = ["github"]
            payload["timeline"]["work_graph"]["similar_commit_groups"] = [
                {"work_id": "unrelated", "project": "p3", "title": "Completely unrelated build cleanup", "branch_refs": ["topic"]}
            ]
            store_path.write_text(json.dumps(payload), encoding="utf-8")
            with patch("tools.timeline_materializer.collect_repo_history", side_effect=AssertionError("reader must not collect")):
                query = query_materialized(root=root, query="friend", limit=20)
            self.assertIsNotNone(query)
            self.assertEqual(query["materialized"]["read_mode"], "MATERIALIZED_ONLY")
            self.assertEqual(query["materialized"]["coverage_status"], "HISTORICAL_INCOMPLETE")
            self.assertEqual(query["materialized"]["backfill_incomplete_sources"], ["github"])
            self.assertEqual(query["materialized"]["absence_semantics"], "NO_MATCH_IS_NOT_PROOF_OF_ABSENCE")
            self.assertTrue(query["materialized"]["live_truth_required"])
            self.assertEqual(query["debugging_boundary"]["timeline_role"], "HISTORICAL_ORIENTATION_AND_LINEAGE")
            self.assertGreaterEqual(query["matching_events"], 2)
            self.assertGreaterEqual(query["work_graph"]["summary"]["matched_commit_groups"], 1)
            self.assertEqual(query["work_graph"]["similar_commit_groups"], [])
            self.assertNotIn("attached_event_ids", query["work_graph"]["commit_groups"][0])


if __name__ == "__main__":
    unittest.main()
