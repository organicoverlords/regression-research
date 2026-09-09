import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from tools.memory_timeline import build_continuity_graph
from tools.repo_timeline import RepoSpec
from tools.timeline_materializer import (
    BOOTSTRAP_SCHEMA,
    DEFAULT_DELTA_REPO_EVENTS_PER_REPO,
    DEFAULT_GITHUB_EVENTS_PER_KIND,
    DEFAULT_MAX_EVENTS,
    DEFAULT_OVERLAP_MINUTES,
    DEFAULT_REPO_EVENTS,
    DEFAULT_RUNNER_LOG_EVENTS,
    HISTORICAL_EVIDENCE_FLOOR,
    SCHEMA,
    build_parser,
    build_work_graph,
    build_worker_archive_summary,
    coordinator_events,
    github_events,
    install_task,
    library_artifact_events,
    local_artifact_events,
    main,
    machine_observation_events,
    materialize,
    materialized_health,
    mcp_events,
    mcp_replacement_events,
    query_materialized,
    runner_log_events,
    _bootstrap_correction_trigger_projection,
    _github_read_cli,
    _lesson_packet,
    _merge_materialized_events,
    _run_json,
    _run_process,
)


class TimelineMaterializerTests(unittest.TestCase):
    def test_github_read_cli_prefers_gh_swarm_on_path(self):
        def which(name):
            return "C:/tools/gh-swarm.exe" if name == "gh-swarm" else "C:/tools/gh.exe"

        with patch("tools.timeline_materializer.shutil.which", side_effect=which):
            self.assertEqual(_github_read_cli(), "C:/tools/gh-swarm.exe")

    def test_github_read_cli_falls_back_to_real_gh(self):
        def which(name):
            return None if name == "gh-swarm" else "C:/tools/gh.exe"

        with patch("tools.timeline_materializer.shutil.which", side_effect=which), patch(
            "tools.timeline_materializer.Path.is_file", return_value=False
        ):
            self.assertEqual(_github_read_cli(), "C:/tools/gh.exe")

    def test_run_json_routes_literal_gh_through_selected_read_cli(self):
        completed = subprocess.CompletedProcess([], 0, '{"ok":true}\n', "")
        with patch("tools.timeline_materializer._github_read_cli", return_value="gh-swarm"), patch(
            "tools.timeline_materializer._run_process", return_value=completed
        ) as run:
            payload, error = _run_json(["gh", "api", "rate_limit"], timeout=1)
        self.assertEqual(payload, {"ok": True})
        self.assertIsNone(error)
        self.assertEqual(run.call_args.args[0], ["gh-swarm", "api", "rate_limit"])
        self.assertEqual(run.call_args.kwargs["timeout"], 1)

    def test_lesson_packet_collapses_copied_lineage_and_preserves_provenance(self):
        seed = {
            "id": "seed", "source_type": "VAULT_MEMORY", "project": "vault",
            "event_at": "2026-09-09T00:00:00+00:00",
            "title": "camera framing output seed",
            "summary": "camera framing output bridgealpha bridgebeta assistant presentation orchestration",
            "scope": "camera framing output bridgealpha bridgebeta assistant presentation orchestration",
            "anchors": ["memory:seed"],
        }

        def commit(event_id, project, title, body, sha):
            return {
                "id": event_id, "source_type": "GIT_COMMIT", "project": project,
                "event_at": "2026-09-08T00:00:00+00:00", "title": title, "summary": title,
                "body": body, "sha": sha, "changed_paths": ["AGENTS.md"],
            }

        copied_body = "bridgealpha bridgebeta assistant presentation orchestration camera framing shared fixed broken failure repair guard"
        copied_title = "camera framing shared policy"
        copy_a = commit("copy-a", "vault", copied_title, copied_body, "a" * 40)
        copy_b = commit("copy-b", "tiny3d", copied_title, copied_body, "b" * 40)
        unique = {
            "id": "unique", "source_type": "GITHUB_PR", "project": "p3",
            "event_at": "2026-09-08T01:00:00+00:00",
            "title": "PR #778: camera framing output owner map",
            "summary": "state=MERGED bridgealpha bridgebeta integration owner mapping",
            "anchors": ["github:example/repo#778"],
        }
        filler = {
            "id": "filler", "source_type": "GITHUB_PR", "project": "agents",
            "event_at": "2026-09-08T02:00:00+00:00",
            "title": "PR #779: camera framing output alternate owner map",
            "summary": "state=MERGED bridgealpha bridgebeta integration alternate mapping",
            "anchors": ["github:example/repo#779"],
        }

        packet = _lesson_packet(
            "camera framing output", selected=[seed],
            candidates=[seed, copy_a, copy_b, unique, filler], query_index=None, limit=3,
        )

        self.assertEqual(packet["status"], "READY")
        self.assertEqual(len(packet["items"]), 3)
        self.assertEqual({item["source_event_id"] for item in packet["items"][:2]}, {"unique", "filler"})
        self.assertFalse({"assistant", "presentation", "orchestration"} & set(packet["expansion_terms"]))
        copied = next(item for item in packet["items"] if item["title"] == copied_title)
        self.assertEqual(set(copied["lineage_event_ids"]), {"copy-a", "copy-b"})
        self.assertEqual(set(copied["lineage_projects"]), {"vault", "tiny3d"})
        self.assertEqual(copied["lineage_copy_count"], 2)
        self.assertEqual(copied["lineage_semantics"], "COPIED_LINEAGE_NOT_INDEPENDENT_SUPPORT")
        self.assertEqual(
            set(copied["evidence_anchors"]),
            {"gitsha:" + "a" * 40, "gitsha:" + "b" * 40},
        )
        self.assertIn("PR #778: camera framing output owner map", {item["title"] for item in packet["items"]})

    def test_bootstrap_projects_canonical_slopwall_and_asshole_correction_triggers(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            agents = root / "AGENTS.md"
            agents.write_text(
                "- User-corrected assistant missteps are mandatory local Vault learning. "
                "The literal user signal `slopwall` always qualifies as a correction incident: record it before returning control, inspect the immediately preceding answer, then continue the inherited task. "
                "The literal user signal `asshole`, when clearly directed at the assistant's immediately preceding answer or action, always qualifies as a lightweight correction event: inspect that action, identify the concrete mistake, and record one compact correction with tag `asshole`. "
                "This marker is smaller than `slopwall`: do not create an incident report solely because it fired.\n",
                encoding="utf-8",
            )
            projected = _bootstrap_correction_trigger_projection(root)
        self.assertEqual(projected["status"], "READY")
        self.assertIn("record it before returning control", projected["slopwall"])
        self.assertIn("continue the inherited task", projected["slopwall"])
        self.assertIn("identify the concrete mistake", projected["asshole"])
        self.assertIn("smaller than `slopwall`", projected["asshole"])
        self.assertEqual(projected["authority"], "DERIVED_PROJECTION_ONLY")

    def test_default_backfill_capacity_covers_current_large_history_shape(self):
        self.assertGreaterEqual(DEFAULT_REPO_EVENTS, 5000)
        self.assertGreaterEqual(DEFAULT_GITHUB_EVENTS_PER_KIND, 5000)
        self.assertGreaterEqual(DEFAULT_RUNNER_LOG_EVENTS, 8000)
        self.assertGreaterEqual(DEFAULT_MAX_EVENTS, 50000)
        args = build_parser().parse_args(["refresh"])
        self.assertEqual(args.repo_events, DEFAULT_REPO_EVENTS)
        self.assertEqual(args.github_events, DEFAULT_GITHUB_EVENTS_PER_KIND)
        self.assertEqual(args.runner_events, DEFAULT_RUNNER_LOG_EVENTS)
        self.assertEqual(args.max_events, DEFAULT_MAX_EVENTS)

    def test_child_processes_use_windows_no_window_wrapper(self):
        with patch("tools.timeline_materializer.subprocess.run") as run:
            _run_process(["gh", "--version"], capture_output=True, check=False)
        kwargs = run.call_args.kwargs
        if os.name == "nt":
            self.assertEqual(kwargs["creationflags"], getattr(subprocess, "CREATE_NO_WINDOW", 0))
            startupinfo = kwargs["startupinfo"]
            self.assertTrue(startupinfo.dwFlags & getattr(subprocess, "STARTF_USESHOWWINDOW", 0))
            self.assertEqual(startupinfo.wShowWindow, getattr(subprocess, "SW_HIDE", 0))
        else:
            self.assertNotIn("creationflags", kwargs)
            self.assertNotIn("startupinfo", kwargs)
        source = (Path(__file__).resolve().parents[1] / "tools" / "timeline_materializer.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("subprocess.run("), 1)

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
            "finding_tags": ["proof", "bug"],
            "findings": "runtime proof showed the fallback avoided the stale avatar path",
            "validation": "focused avatar regression 7/7 PASS",
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
        self.assertEqual(group["workers"][0]["finding_tags"], ["proof", "bug"])
        self.assertIn("stale avatar path", group["workers"][0]["findings"])
        self.assertEqual(group["workers"][0]["validation"], "focused avatar regression 7/7 PASS")
        self.assertEqual(group["efficiency"]["action_runs"], 1)
        self.assertEqual(group["efficiency"]["action_conclusions"], {"success": 1})

    def test_work_graph_sha_index_preserves_exact_and_ambiguous_prefix_attachment(self):
        sha_a = "1234567" + "a" * 33
        sha_b = "1234567" + "b" * 33
        commit_a = self.commit_event(sha_a, "Index alpha commit", "2026-09-06T04:50:00+03:00")
        commit_b = self.commit_event(sha_b, "Index beta commit", "2026-09-06T04:51:00+03:00")
        exact_prefix = {
            "id": "mem:exact-prefix", "source_type": "VAULT_MEMORY", "event_at": "2026-09-06T04:52:00+03:00",
            "project": "p3", "title": "Exact prefix evidence", "refs": [sha_a[:12]], "anchors": [],
        }
        ambiguous_prefix = {
            "id": "mem:ambiguous-prefix", "source_type": "VAULT_MEMORY", "event_at": "2026-09-06T04:53:00+03:00",
            "project": "p3", "title": "Ambiguous prefix evidence", "refs": [sha_a[:7]], "anchors": [],
        }
        graph = build_work_graph([commit_a, commit_b, exact_prefix, ambiguous_prefix])
        groups = {row["commits"][0]["sha"]: row for row in graph["commit_groups"]}
        self.assertIn("mem:exact-prefix", groups[sha_a]["attached_event_ids"])
        self.assertNotIn("mem:exact-prefix", groups[sha_b]["attached_event_ids"])
        self.assertIn("mem:ambiguous-prefix", groups[sha_a]["attached_event_ids"])
        self.assertIn("mem:ambiguous-prefix", groups[sha_b]["attached_event_ids"])

    def test_worker_archive_summary_uses_timed_materialized_events_only(self):
        now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
        events = [
            {
                "id": "worker:fir-old", "source_type": "WORKER_REPORT", "population": "timed",
                "automation_id": "fir", "display_label": "Fir",
                "event_at": (now - timedelta(minutes=180)).isoformat(),
                "duration_minutes": 24.0, "target_run_minutes": 24.0, "target_utilization_pct": 100.0,
            },
            {
                "id": "worker:fir-new", "source_type": "WORKER_REPORT", "population": "timed",
                "automation_id": "fir", "display_label": "Fir",
                "event_at": (now - timedelta(minutes=120)).isoformat(),
                "duration_minutes": 3.68, "target_run_minutes": 24.0, "target_utilization_pct": 15.3,
            },
            {
                "id": "worker:hazel", "source_type": "WORKER_REPORT", "population": "timed",
                "automation_id": "hazel", "display_label": "Hazel",
                "event_at": (now - timedelta(minutes=10)).isoformat(),
                "duration_minutes": 10.0, "target_run_minutes": 24.0, "target_utilization_pct": 41.7,
            },
            *[
                {
                    "id": f"worker:w{index}", "source_type": "WORKER_REPORT", "population": "timed",
                    "automation_id": f"worker-{index}", "display_label": f"Worker {index}",
                    "event_at": (now - timedelta(minutes=(200 if index == 3 else 20 + index))).isoformat(),
                    "duration_minutes": 20.0, "target_run_minutes": 24.0, "target_utilization_pct": 83.3,
                }
                for index in range(4)
            ],
            {
                "id": "worker:manual", "source_type": "WORKER_REPORT", "population": "manual",
                "automation_id": "manual-should-not-count", "display_label": "Manual",
                "event_at": (now - timedelta(minutes=1)).isoformat(), "duration_minutes": 1.0,
            },
        ]
        summary = build_worker_archive_summary(events, now=now, horizon_days=30)
        self.assertEqual(summary["read_mode"], "MATERIALIZED_ONLY")
        self.assertEqual(summary["population_scope"], "timed_worker_reports_in_materialized_horizon")
        self.assertEqual(summary["archive_sample"]["historical_worker_ids_seen"], 6)
        self.assertEqual(summary["archive_sample"]["sampled_worker_count"], 5)
        self.assertEqual(summary["archive_sample"]["sample_limit"], 5)
        self.assertEqual(summary["archive_sample"]["selection"], "five_most_recent_latest_timed_archives_in_materialized_horizon")
        self.assertEqual([item["worker"] for item in summary["attention"]], ["Hazel"])
        self.assertEqual(summary["stale_reports"], [{
            "worker": "Fir", "age_minutes": 120.0,
            "last_archived_classification": "SEVERELY_PREMATURE",
        }])
        fir = next(item for item in summary["latest_archived_per_worker"] if item["display_label"] == "Fir")
        self.assertEqual(fir["classification"], "SEVERELY_PREMATURE")
        self.assertNotIn("Manual", json.dumps(summary))
        self.assertFalse(summary["current_scheduler_membership"]["available"])

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

    def test_library_artifact_adapter_expands_screenshot_corpus_and_generated_artifacts(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            evidence = root / "02 Evidence"
            evidence.mkdir(parents=True)
            screenshot_id = "file_00000000abc"
            first = {
                "file_id": screenshot_id, "filename": "screen.png",
                "created_at_utc": "2026-09-06T03:00:00Z",
                "subject": "first observation", "classification": "CONVERSATION_SCREENSHOT_NEW",
                "review_status": "VISUALLY_REVIEWED", "tags": ["ui"],
            }
            duplicate = dict(first, subject="same Library file in later corpus shard")
            generated = {
                "file_id": "file_00000000def", "filename": "generated-note.md",
                "created_at_utc": "2026-09-06T03:01:00Z", "source_kind": "generated",
                "model_generated": True, "size_bytes": 1234,
            }
            (evidence / "2026-08-26_library_screenshot_shard_000.jsonl").write_text(
                json.dumps(first) + "\n", encoding="utf-8"
            )
            (evidence / "2026-08-27_library_screenshot_text_occurrences_003.jsonl").write_text(
                json.dumps(duplicate) + "\n" + json.dumps(generated) + "\n", encoding="utf-8"
            )
            events, coverage = library_artifact_events(root, since=datetime(2026, 9, 5, tzinfo=timezone.utc))
            self.assertEqual(len(events), 2)
            self.assertEqual(coverage["files"], 2)
            self.assertEqual(coverage["rows"], 3)
            screenshot = next(event for event in events if event["library_file_id"] == screenshot_id)
            self.assertEqual(screenshot["source_type"], "LIBRARY_ARTIFACT")
            self.assertEqual(screenshot["artifact_type"], "screenshot")
            self.assertIn(f"library-file:{screenshot_id}", screenshot["anchors"])
            generated_event = next(event for event in events if event["library_file_id"] == "file_00000000def")
            self.assertEqual(generated_event["artifact_type"], "library_artifact")
            self.assertTrue(generated_event["model_generated"])
            self.assertEqual(generated_event["source_kind"], "generated")

    def test_machine_observation_adapter_accepts_legacy_and_rich_rows(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"LOCALAPPDATA": d}):
            path = Path(d) / "ChatGPTMcpClean" / ".state" / "bootstrap-observations.jsonl"
            path.parent.mkdir(parents=True)
            rows = [
                {"at": "2026-09-06T03:00:00Z", "free_gb": 61.5},
                {
                    "at": "2026-09-06T03:05:00Z", "free_gb": 60.9, "disk_used_gb": 414.9,
                    "physical_free_gb": 1.4, "commit_headroom_gb": 39.1, "commit_used_pct": 38.3,
                    "vram_free_mb": 5086, "gpu_utilization_pct": 3,
                },
            ]
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            events, coverage = machine_observation_events(since=datetime(2026, 9, 5, tzinfo=timezone.utc))
            self.assertEqual(len(events), 2)
            self.assertEqual(coverage["rows"], 2)
            rich = events[0]
            self.assertEqual(rich["source_type"], "MACHINE_OBSERVATION")
            self.assertEqual(rich["artifact_type"], "machine_snapshot")
            self.assertEqual(rich["commit_headroom_gb"], 39.1)
            self.assertEqual(rich["vram_free_mb"], 5086)
            legacy = events[1]
            self.assertEqual(legacy["free_gb"], 61.5)
            self.assertIsNone(legacy["commit_headroom_gb"])

    def test_github_adapter_projects_issues_prs_and_actions_without_body_fetches(self):
        spec = RepoSpec("p3", Path("C:/fake/p3"))
        now = "2026-09-06T05:00:00Z"
        issue = [{"number": 803, "title": "Milestone", "state": "OPEN", "createdAt": now, "updatedAt": now, "closedAt": None, "url": "https://example/803"}]
        pr = [{"number": 1884, "title": "Avatar wait", "state": "MERGED", "createdAt": now, "updatedAt": now, "closedAt": now, "mergedAt": now, "url": "https://example/1884", "headRefName": "topic", "baseRefName": "main", "headRefOid": "a" * 40}]
        run = [{"databaseId": 99, "workflowName": "verify", "status": "completed", "conclusion": "success", "createdAt": now, "updatedAt": now, "headSha": "a" * 40, "headBranch": "topic", "event": "pull_request", "displayTitle": "Avatar wait", "url": "https://example/run/99"}]
        with patch("tools.timeline_materializer._github_slug", return_value="organicoverlords/p3"), patch(
            "tools.timeline_materializer._run_json", side_effect=[(issue, None), (pr, None), (run, None), ([], None)]
        ) as run_json:
            events, coverage = github_events([spec], since=datetime(2026, 9, 5, tzinfo=timezone.utc))
        self.assertEqual({event["source_type"] for event in events}, {"GITHUB_ISSUE", "GITHUB_PR", "GITHUB_ACTION", "GITHUB_ACTION_SUMMARY"})
        repo_cov = coverage["repos"]["organicoverlords/p3"]
        self.assertEqual(repo_cov["project"], "p3")
        self.assertEqual(repo_cov["issues"]["events"], 1)
        self.assertEqual(repo_cov["prs"]["events"], 1)
        self.assertEqual(repo_cov["actions"]["events"], 1)
        self.assertTrue(repo_cov["queue"]["available"])
        self.assertTrue(repo_cov["queue"]["complete"])
        summary = next(event for event in events if event["source_type"] == "GITHUB_ACTION_SUMMARY")
        self.assertTrue(summary["current_only"])
        self.assertTrue(summary["live_truth_required"])
        self.assertEqual(summary["queue_counts"]["absence_semantics"], "NO_ACTIVE_RUNS_IN_COMPLETE_SNAPSHOT")
        self.assertEqual(summary["build_counts"]["scope"], "since_source_watermark")
        self.assertEqual(repo_cov["limit_per_kind"], repo_cov["issues"]["limit"])
        self.assertEqual(repo_cov["saturated_kinds"], [])
        self.assertFalse(coverage["saturated"])
        commands = [" ".join(call.args[0]) for call in run_json.call_args_list]
        self.assertTrue(all("body" not in command for command in commands))
        self.assertTrue(all("updated:>=2026-09-05T00:00:00Z" in command for command in commands[:2]))
        self.assertIn("created >=2026-09-05T00:00:00Z", commands[2])
        self.assertNotIn("--created", commands[3])

    def test_github_adapter_marks_per_kind_saturation_at_query_limit(self):
        spec = RepoSpec("p3", Path("C:/fake/p3"))
        now = "2026-09-06T05:00:00Z"
        issue = [{"number": 1, "title": "one", "state": "OPEN", "createdAt": now, "updatedAt": now, "closedAt": None, "url": "https://example/1"}]
        pr = [{"number": 2, "title": "two", "state": "OPEN", "createdAt": now, "updatedAt": now, "closedAt": None, "mergedAt": None, "url": "https://example/2", "headRefName": "topic", "baseRefName": "main", "headRefOid": "a" * 40}]
        run = [{"databaseId": 3, "workflowName": "verify", "status": "completed", "conclusion": "success", "createdAt": now, "updatedAt": now, "headSha": "a" * 40, "headBranch": "topic", "event": "push", "displayTitle": "three", "url": "https://example/3"}]
        with patch("tools.timeline_materializer._github_slug", return_value="organicoverlords/p3"), patch(
            "tools.timeline_materializer._run_json", side_effect=[(issue, None), (pr, None), (run, None), ([], None)]
        ):
            _, coverage = github_events([spec], since=datetime(2026, 9, 5, tzinfo=timezone.utc), limit_per_kind=1)
        repo = coverage["repos"]["organicoverlords/p3"]
        self.assertEqual(repo["saturated_kinds"], ["issues", "prs", "actions"])
        self.assertTrue(all(repo[kind]["saturated"] for kind in ("issues", "prs", "actions")))
        self.assertTrue(coverage["saturated"])

    def test_github_actions_primary_error_can_fall_back_without_marking_history_missing(self):
        spec = RepoSpec("p3", Path("C:/fake/p3"))
        now = "2026-09-06T05:00:00Z"
        run = [{
            "databaseId": 99, "workflowName": "verify", "status": "completed", "conclusion": "success",
            "createdAt": now, "updatedAt": now, "headSha": "a" * 40, "headBranch": "main",
            "event": "push", "displayTitle": "fallback run", "url": "https://example/run/99",
        }]
        with patch("tools.timeline_materializer._github_slug", return_value="organicoverlords/p3"), patch(
            "tools.timeline_materializer._run_json",
            side_effect=[([], None), ([], None), (None, "primary too large"), (run, None), ([], None)],
        ) as run_json:
            events, coverage = github_events(
                [spec], since=datetime(2026, 9, 5, tzinfo=timezone.utc), limit_per_kind=1000
            )
        self.assertEqual(coverage["errors"], [])
        self.assertEqual(coverage["warnings"][0]["source"], "actions")
        self.assertEqual(coverage["warnings"][0]["fallback_limit"], 200)
        self.assertTrue(any(event["source_type"] == "GITHUB_ACTION" for event in events))
        commands = [call.args[0] for call in run_json.call_args_list]
        self.assertEqual(commands[2][commands[2].index("--limit") + 1], "1000")
        self.assertEqual(commands[3][commands[3].index("--limit") + 1], "200")
        repo = coverage["repos"]["organicoverlords/p3"]
        self.assertFalse(repo["actions"]["saturated"])
        self.assertNotIn("actions", repo["saturated_kinds"])


    def test_github_actions_fallback_at_effective_cap_preserves_historical_retry(self):
        spec = RepoSpec("p3", Path("C:/fake/p3"))
        now = "2026-09-06T05:00:00Z"
        fallback_limit = 200
        runs = [{
            "databaseId": index, "workflowName": "verify", "status": "completed", "conclusion": "success",
            "createdAt": now, "updatedAt": now, "headSha": "a" * 40, "headBranch": "main",
            "event": "push", "displayTitle": f"fallback run {index}", "url": f"https://example/run/{index}",
        } for index in range(fallback_limit)]
        with patch("tools.timeline_materializer._github_slug", return_value="organicoverlords/p3"), patch(
            "tools.timeline_materializer._run_json",
            side_effect=[([], None), ([], None), (None, "primary too large"), (runs, None), ([], None)],
        ):
            _, coverage = github_events(
                [spec], since=datetime(2026, 9, 5, tzinfo=timezone.utc), limit_per_kind=1000
            )
        repo = coverage["repos"]["organicoverlords/p3"]
        self.assertTrue(repo["actions"]["saturated"])
        self.assertIn("actions", repo["saturated_kinds"])
        self.assertTrue(coverage["saturated"])
        self.assertTrue(repo["queue"]["complete"])
        self.assertNotIn("queue", repo["bounded_snapshot_kinds"])

    def test_queue_snapshot_cap_does_not_poison_historical_github_retry(self):
        spec = RepoSpec("p3", Path("C:/fake/p3"))
        now = "2026-09-06T05:00:00Z"
        completed = [{
            "databaseId": index, "workflowName": "verify", "status": "completed", "conclusion": "success",
            "createdAt": now, "updatedAt": now, "headSha": "a" * 40, "headBranch": "main",
            "event": "push", "displayTitle": f"run {index}", "url": f"https://example/run/{index}",
        } for index in range(50)]
        with patch("tools.timeline_materializer._github_slug", return_value="organicoverlords/p3"), patch(
            "tools.timeline_materializer._run_json", side_effect=[([], None), ([], None), ([], None), (completed, None)]
        ):
            events, coverage = github_events([spec], since=datetime(2026, 9, 5, tzinfo=timezone.utc))
        repo = coverage["repos"]["organicoverlords/p3"]
        self.assertEqual(repo["saturated_kinds"], [])
        self.assertEqual(repo["bounded_snapshot_kinds"], ["queue"])
        self.assertFalse(coverage["saturated"])
        self.assertTrue(repo["queue"]["bounded"])
        self.assertFalse(repo["queue"]["complete"])
        self.assertEqual(repo["queue"]["events"], 0)
        summary = next(event for event in events if event["source_type"] == "GITHUB_ACTION_SUMMARY")
        self.assertEqual(summary["queue_counts"]["absence_semantics"], "NO_MATCH_IS_NOT_PROOF_QUEUE_IS_EMPTY")
        self.assertIn("queue sample 0 queued/0 in progress", summary["title"])

    def test_queue_snapshot_error_is_orientation_unknown_not_historical_retry(self):
        spec = RepoSpec("p3", Path("C:/fake/p3"))
        with patch("tools.timeline_materializer._github_slug", return_value="organicoverlords/p3"), patch(
            "tools.timeline_materializer._run_json", side_effect=[([], None), ([], None), ([], None), (None, "queue unavailable")]
        ):
            events, coverage = github_events([spec], since=datetime(2026, 9, 5, tzinfo=timezone.utc))
        repo = coverage["repos"]["organicoverlords/p3"]
        self.assertFalse(repo["queue"]["available"])
        self.assertFalse(repo["queue"]["complete"])
        self.assertEqual(coverage["errors"], [])
        self.assertEqual(coverage["snapshot_errors"][0]["source"], "queue")
        self.assertFalse(coverage["saturated"])
        summary = next(event for event in events if event["source_type"] == "GITHUB_ACTION_SUMMARY")
        self.assertIn("queue unknown", summary["title"])
        self.assertFalse(summary["queue_counts"]["available"])
        self.assertEqual(summary["queue_counts"]["absence_semantics"], "NO_MATCH_IS_NOT_PROOF_QUEUE_IS_EMPTY")

    def test_coordinator_snapshot_counts_only_unexpired_active_jobs(self):
        now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"LOCALAPPDATA": d}):
            store = Path(d) / "ChatGPTMcpClean" / ".state" / "busy-claims.json"
            store.parent.mkdir(parents=True)
            store.write_text(json.dumps({
                "claims": [
                    {"actor": "old", "scope": "old-scope", "timestamp": "2026-09-06T08:00:00Z"},
                    {"actor": "live", "scope": "live-scope", "timestamp": "2026-09-06T11:50:00Z"},
                ],
                "coordinator": {
                    "jobs": {
                        "live-scope": {"scope": "live-scope", "state": "active", "lease_expires_at": "2026-09-06T12:30:00Z"},
                        "expired-scope": {"scope": "expired-scope", "state": "active", "lease_expires_at": "2026-09-06T11:59:00Z"},
                        "unknown-scope": {"scope": "unknown-scope", "state": "active", "lease_expires_at": "not-a-time"},
                        "finished-scope": {"scope": "finished-scope", "state": "finished", "lease_expires_at": "2026-09-06T12:30:00Z"},
                    },
                    "operations": {"op-1": {"status": "done"}},
                },
            }), encoding="utf-8")
            events, coverage = coordinator_events(since=now - timedelta(days=1), snapshot_now=now)
        self.assertEqual(coverage["stored_claim_records"], 2)
        self.assertEqual(coverage["stored_jobs"], 4)
        self.assertEqual(coverage["active_jobs"], 1)
        self.assertEqual(coverage["active_claim_scopes"], 1)
        self.assertEqual(coverage["expired_active_jobs"], 1)
        self.assertEqual(coverage["uncertain_active_jobs"], 1)
        event = events[0]
        self.assertEqual(event["coordinator_state"]["active_scopes"], ["live-scope"])
        self.assertTrue(event["current_only"])
        self.assertTrue(event["live_truth_required"])
        self.assertIn("COLLISION_ORIENTATION_ONLY", event["evidence_semantics"])
        self.assertNotIn("old-scope", json.dumps(event))
        self.assertNotIn("expired-scope", event["refs"])

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

    def test_mcp_adapter_projects_historical_production_version_replacements(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"LOCALAPPDATA": d}):
            root = Path(d) / "ChatGPTMcpClean" / ".state" / "production-replacement"
            root.mkdir(parents=True)
            old_head, new_head = "d6e2972" + "0" * 33, "4b95aa4" + "1" * 33
            receipt = {
                "request_id": "replacement-1", "recorded_at": "2026-09-06T03:00:00Z",
                "status": "SUCCEEDED", "runtime_changed": True,
                "old_head": old_head, "new_head": new_head,
                "old_generation": "backend-3011-old", "new_generation": "backend-3011-new",
                "old_dist_sha256": "a" * 64, "new_dist_sha256": "b" * 64,
                "candidate_port": 3012, "secret": "DO_NOT_COPY",
            }
            (root / "receipt-replacement-1.json").write_text(json.dumps(receipt), encoding="utf-8")
            events, coverage = mcp_replacement_events(
                since=datetime(2026, 9, 5, tzinfo=timezone.utc)
            )
            replacement = next(event for event in events if event.get("mcp_event") == "production_replacement")
            self.assertEqual(replacement["old_head"], old_head)
            self.assertEqual(replacement["new_head"], new_head)
            self.assertEqual(replacement["old_generation"], "backend-3011-old")
            self.assertEqual(replacement["new_generation"], "backend-3011-new")
            self.assertIn(new_head[:7], replacement["refs"])
            self.assertNotIn("DO_NOT_COPY", json.dumps(replacement))
            self.assertEqual(coverage["events"], 1)

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

    def test_incremental_merge_drops_stale_current_only_snapshots_unless_reemitted(self):
        since = datetime(2026, 9, 6, 4, 0, tzinfo=timezone.utc)
        historical = {
            "id": "git:vault:abc",
            "source_type": "GIT_COMMIT",
            "event_at": "2026-09-06T04:30:00+00:00",
        }
        stale_coordinator = {
            "id": "coordinator-state-snapshot",
            "source_type": "COORDINATOR_EVENT",
            "event_at": "2026-09-06T04:31:00+00:00",
            "current_only": True,
            "refs": ["stale-scope"],
        }
        stale_queue = {
            "id": "github-action-summary:organicoverlords/regression-research",
            "source_type": "GITHUB_ACTION_SUMMARY",
            "event_at": "2026-09-06T04:32:00+00:00",
            "current_only": True,
            "queue_counts": {"queued": 9},
        }
        fresh_queue = {
            **stale_queue,
            "event_at": "2026-09-06T05:00:00+00:00",
            "queue_counts": {"queued": 1},
        }

        merged = _merge_materialized_events(
            [historical, stale_coordinator, stale_queue],
            [fresh_queue],
            since=since,
        )
        by_id = {event["id"]: event for event in merged}

        self.assertIn(historical["id"], by_id)
        self.assertNotIn(stale_coordinator["id"], by_id)
        self.assertEqual(by_id[stale_queue["id"]]["queue_counts"]["queued"], 1)
        self.assertEqual(by_id[stale_queue["id"]]["event_at"], fresh_queue["event_at"])

    def test_second_refresh_is_incremental_and_reuses_materialized_history(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "memory").mkdir()
            state = root / ".state" / "timeline"
            state.mkdir(parents=True)
            prior_at = datetime(2026, 9, 6, 5, 0, tzinfo=timezone.utc)
            old_sha = "1" * 40
            new_sha = "2" * 40
            old_event = self.commit_event(old_sha, "Old retained work", "2026-07-01T04:50:00+00:00")
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
            repaired_old = dict(old_event, body="Historical Hummingbird wing deformation lesson", changed_paths=["rigging/avian.py"], _search_text="Historical Hummingbird wing deformation lesson rigging/avian.py")
            minimal_overview = {"contract": "history only", "eligible_entries": 0, "incident_rollups": [], "recent": [], "projects": [], "recurring_tags": []}
            with patch("tools.timeline_materializer.discover_repo_specs", return_value=[RepoSpec("p3", root)]), patch(
                "tools.timeline_materializer._repo_maps", return_value=({"p3": "organicoverlords/p3"}, {"organicoverlords/p3": "p3"})
            ), patch("tools.timeline_materializer.load_bank", return_value=[]), patch(
                "tools.timeline_materializer.collect_repo_history",
                side_effect=[
                    {"events": [repaired_old], "coverage": {"p3": {"events": 1, "limit": DEFAULT_REPO_EVENTS, "saturated": False}}},
                    {"events": [new_event], "coverage": {"p3": {"events": 1, "limit": DEFAULT_DELTA_REPO_EVENTS_PER_REPO, "saturated": False}}},
                ],
            ) as collect_repo, patch("tools.timeline_materializer.enrich_repo_events"), patch(
                "tools.timeline_materializer.worker_history_events", side_effect=[[], []]
            ) as worker_history, patch("tools.timeline_materializer.tracked_artifact_events", return_value=[]), patch(
                "tools.timeline_materializer.local_artifact_events", return_value=([], {"events": 0, "candidates": 0, "limit": 1000, "saturated": False})
            ), patch(
                "tools.timeline_materializer.library_artifact_events", return_value=([], {"events": 0, "saturated": False, "errors": []})
            ) as library_artifacts, patch(
                "tools.timeline_materializer.machine_observation_events", return_value=([], {"events": 0, "saturated": False, "errors": []})
            ) as machine_observations, patch("tools.timeline_materializer.mcp_events", return_value=([], {"events": 0, "receipts_saturated": False, "errors": []})), patch(
                "tools.timeline_materializer.mcp_replacement_events", return_value=([], {"events": 0, "saturated": False, "errors": []})
            ) as mcp_history, patch(
                "tools.timeline_materializer.runner_log_events", return_value=([], {"events": 0, "saturated": False, "errors": []})
            ), patch(
                "tools.timeline_materializer.coordinator_events", return_value=([], {"events": 0, "errors": [], "current_only": True})
            ), patch("tools.timeline_materializer.build_overview", return_value=minimal_overview):
                result = materialize(
                    root=root,
                    include_github=False,
                    now=datetime(2026, 9, 6, 5, 5, tzinfo=timezone.utc),
                )
            self.assertEqual(result["refresh_mode"], "INCREMENTAL")
            self.assertEqual(result["delta_events"], 2)
            expected_since = prior_at - timedelta(minutes=DEFAULT_OVERLAP_MINUTES)
            self.assertEqual(len(collect_repo.call_args_list), 2)
            self.assertEqual(collect_repo.call_args_list[0].kwargs["since"], HISTORICAL_EVIDENCE_FLOOR)
            self.assertEqual(collect_repo.call_args_list[0].kwargs["limit_per_repo"], DEFAULT_REPO_EVENTS)
            self.assertEqual(collect_repo.call_args_list[1].kwargs["since"], expected_since)
            self.assertEqual(collect_repo.call_args_list[1].kwargs["limit_per_repo"], DEFAULT_DELTA_REPO_EVENTS_PER_REPO)
            self.assertTrue(all(call.kwargs["since"] == expected_since for call in worker_history.call_args_list))
            expected_unbounded_source_since = datetime(2000, 1, 1, tzinfo=timezone.utc)
            self.assertEqual(library_artifacts.call_args.kwargs["since"], expected_unbounded_source_since)
            self.assertEqual(machine_observations.call_args.kwargs["since"], expected_unbounded_source_since)
            self.assertEqual(mcp_history.call_args.kwargs["since"], expected_unbounded_source_since)
            payload = json.loads((state / "timeline-store.json").read_text(encoding="utf-8"))
            events_by_id = {event["id"]: event for event in payload["timeline"]["events"]}
            self.assertIn(old_event["id"], events_by_id)
            self.assertIn(new_event["id"], events_by_id)
            self.assertEqual(events_by_id[old_event["id"]]["body"], repaired_old["body"])
            self.assertEqual(events_by_id[old_event["id"]]["changed_paths"], ["rigging/avian.py"])
            self.assertEqual(payload["ingestion"]["mode"], "INCREMENTAL")
            self.assertEqual(payload["ingestion"]["backfill_incomplete_sources"], ["github", "repos"])
            self.assertEqual(payload["timeline"]["materialized"]["backfill_incomplete_sources"], ["github", "repos"])
            self.assertEqual(payload["source_watermarks"]["repos"], "2026-09-06T05:05:00+00:00")
            self.assertIsNone(payload["horizon_days"])
            self.assertIsNone(payload["timeline"]["materialized"]["horizon_days"])

    def test_refresh_defaults_to_age_unbounded_but_explicit_days_remain_available(self):
        default_args = build_parser().parse_args(["refresh"])
        explicit_args = build_parser().parse_args(["refresh", "--days", "30"])
        self.assertIsNone(default_args.days)
        self.assertEqual(explicit_args.days, 30)

    def test_materialized_health_reports_age_unbounded_complete_history(self):
        now = datetime(2026, 9, 6, 6, 0, tzinfo=timezone.utc)
        payload = {
            "generated_at": "2026-09-06T05:58:00+00:00",
            "horizon_days": None,
            "ingestion": {"mode": "INCREMENTAL", "backfill_incomplete_sources": [], "retry_sources": []},
            "timeline": {"materialized": {"refresh_minutes": 5, "horizon_days": None}},
        }
        health = materialized_health(payload, now=now)
        self.assertEqual(health["coverage_status"], "COMPLETE_MATERIALIZED_HISTORY")
        self.assertEqual(health["absence_semantics"], "NO_MATCH_MEANS_NO_MATCH_IN_THE_MATERIALIZED_HISTORY_AND_ENABLED_SOURCES_ONLY")
        self.assertIsNone(health["horizon_days"])

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

        truncated = materialized_health({
            "generated_at": "2026-09-06T06:29:00+00:00",
            "horizon_days": 30,
            "ingestion": {"backfill_incomplete_sources": [], "retry_sources": []},
            "timeline": {"truncated": True, "materialized": {"refresh_minutes": 5}},
        }, now=now)
        self.assertTrue(truncated["timeline_truncated"])
        self.assertEqual(truncated["coverage_status"], "HISTORICAL_INCOMPLETE")
        self.assertEqual(truncated["absence_semantics"], "NO_MATCH_IS_NOT_PROOF_OF_ABSENCE")
        self.assertIn("MATERIALIZED_EVENT_CAP_TRUNCATED", truncated["absence_unsafe_reasons"])

        retry = materialized_health({
            "generated_at": "2026-09-06T06:29:00+00:00",
            "horizon_days": 30,
            "ingestion": {"backfill_incomplete_sources": [], "retry_sources": ["github"]},
            "timeline": {"materialized": {"refresh_minutes": 5}},
        }, now=now)
        self.assertEqual(retry["status"], "FRESH")
        self.assertEqual(retry["absence_semantics"], "NO_MATCH_IS_NOT_PROOF_OF_ABSENCE")
        self.assertIn("DELTA_RETRY_PENDING", retry["absence_unsafe_reasons"])

    def test_query_cli_defaults_to_compact_projection_and_preserves_full_detail_escape_hatch(self):
        parsed = build_parser().parse_args(["query", "needle"])
        self.assertFalse(parsed.full_detail)
        parsed_full = build_parser().parse_args(["query", "needle", "--full-detail"])
        self.assertTrue(parsed_full.full_detail)

        base_args = {
            "command": "query", "root": Path("."), "query": "needle", "view": "general", "project": None,
            "thread": None, "days": None, "limit": 20, "no_workers": False,
        }
        rich = {"events": [{"id": "one", "summary": "x" * 2000}]}
        compact = {"events": [{"id": "one"}], "detail": "COMPACT_AGENT_FACING; use --full-detail for forensic projection"}

        with patch("tools.timeline_materializer.build_parser") as parser, patch(
            "tools.timeline_materializer.query_materialized", return_value=rich
        ), patch("tools.timeline_materializer._compact_timeline_report", return_value=compact) as compact_call:
            parser.return_value.parse_args.return_value = type("Args", (), {**base_args, "full_detail": False})()
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(main(), 0)
            self.assertEqual(json.loads(stdout.getvalue()), compact)
            compact_call.assert_called_once_with(rich, limit=20)

        with patch("tools.timeline_materializer.build_parser") as parser, patch(
            "tools.timeline_materializer.query_materialized", return_value=rich
        ), patch("tools.timeline_materializer._compact_timeline_report") as compact_call:
            parser.return_value.parse_args.return_value = type("Args", (), {**base_args, "full_detail": True})()
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(main(), 0)
            self.assertEqual(json.loads(stdout.getvalue()), rich)
            compact_call.assert_not_called()

    def test_refresh_cli_treats_existing_refresh_lock_as_successful_noop(self):
        with patch("tools.timeline_materializer.build_parser") as build_parser, patch(
            "tools.timeline_materializer.materialize",
            return_value={"ok": False, "status": "ALREADY_RUNNING", "path": "refresh.lock"},
        ):
            build_parser.return_value.parse_args.return_value = type("Args", (), {
                "command": "refresh", "root": Path("."), "days": 30, "repo_events": 1000,
                "artifact_events": 2000, "max_events": 20000, "no_github": False,
                "github_events": 1000, "runner_events": 300,
                "rebuild": False, "quiet": True,
            })()
            self.assertEqual(main(), 0)
    def test_query_materialized_searches_bounded_historical_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            state = root / ".state" / "timeline"
            state.mkdir(parents=True)
            recent = {
                "id": "recent:1", "source_type": "MCP_EVENT", "event_at": "2026-09-06T03:00:00+00:00",
                "recorded_at": "2026-09-06T03:00:00+00:00", "title": "recent transport", "summary": "recent",
                "project": None, "refs": [], "anchors": [],
            }
            old = {
                "id": "library-artifact:file_old", "source_type": "LIBRARY_ARTIFACT",
                "event_at": "2026-05-18T15:17:35+00:00", "recorded_at": "2026-08-26T10:00:00+00:00",
                "title": "screenshot: old-proof.png", "summary": "Claude Code notification permission screenshot",
                "artifact_type": "screenshot", "library_file_id": "file_old", "project": None,
                "refs": ["file_old"], "anchors": ["library-file:file_old"], "retain_history": True,
            }
            (state / "timeline-store.json").write_text(json.dumps({
                "schema": SCHEMA, "generated_at": "2026-09-06T03:05:00+00:00", "horizon_days": 30,
                "timeline": {"schema_version": 2, "authority": "DERIVED_HISTORY_ONLY", "contract": {},
                    "events": [recent], "historical_evidence_events": [old], "work_graph": {}},
            }), encoding="utf-8")
            result = query_materialized(root=root, query="notification permission", limit=20)
            self.assertEqual(result["matching_events"], 1)
            self.assertEqual(result["events"][0]["id"], old["id"])
            self.assertEqual(result["events"][0]["event_at"], "2026-05-18T15:17:35+00:00")
            self.assertEqual(result["debugging_boundary"]["continuity_graph"], "FULL_MATERIALIZED_HORIZON_QUERYABLE")

            payload = json.loads((state / "timeline-store.json").read_text(encoding="utf-8"))
            payload["generated_at"] = "2026-09-06T03:06:00+00:00"
            payload["horizon_days"] = None
            (state / "timeline-store.json").write_text(json.dumps(payload), encoding="utf-8")
            full_history = query_materialized(root=root, query="notification permission", limit=20)
            self.assertEqual(full_history["debugging_boundary"]["continuity_graph"], "FULL_MATERIALIZED_HISTORY_QUERYABLE")

    def test_query_materialized_uses_full_case_graph_and_canonical_forensic_error_selector(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            state = root / ".state" / "timeline"
            state.mkdir(parents=True)
            tagged = {
                "id": "mem:signal", "source_type": "VAULT_MEMORY", "authority": "DERIVED_MEMORY_HISTORY",
                "event_at": "2026-09-06T08:00:00+03:00", "recorded_at": "2026-09-06T08:00:00+03:00",
                "title": "Verified incident", "summary": "Verified incident", "scope": "vault/case",
                "tags": ["incident", "assistant-recorded", "verbatim-source"], "semantic_category": "INCIDENT",
                "thread_id": "thread:case-x", "thread_source": "EXPLICIT_THREAD", "anchors": [], "refs": [],
            }
            context = {
                "id": "mem:context", "source_type": "VAULT_MEMORY", "authority": "DERIVED_MEMORY_HISTORY",
                "event_at": "2026-09-06T08:01:00+03:00", "recorded_at": "2026-09-06T08:01:00+03:00",
                "title": "Case x follow-up", "summary": "Context only", "scope": "vault/case",
                "tags": ["timeline", "assistant-recorded", "verbatim-source"], "semantic_category": "INCIDENT",
                "thread_id": "thread:case-x", "thread_source": "EXPLICIT_THREAD", "anchors": [], "refs": [],
            }
            taxonomy_only = {
                "id": "mem:taxonomy", "source_type": "VAULT_MEMORY", "authority": "DERIVED_MEMORY_HISTORY",
                "event_at": "2026-09-06T08:02:00+03:00", "recorded_at": "2026-09-06T08:02:00+03:00",
                "title": "Taxonomy incident lesson", "summary": "Lesson about incident classification", "scope": "vault/taxonomy",
                "tags": ["timeline", "assistant-recorded", "verbatim-source"], "semantic_category": "INCIDENT",
                "thread_id": "thread:taxonomy", "thread_source": "EXPLICIT_THREAD", "anchors": [], "refs": [],
            }
            old_forensic = {
                "id": "mem:old", "source_type": "VAULT_MEMORY", "authority": "DERIVED_MEMORY_HISTORY",
                "event_at": "2026-08-28T20:00:00+03:00", "recorded_at": "2026-08-28T20:00:00+03:00",
                "title": "One incident", "summary": "Old unstructured note", "scope": "response-quality",
                "tags": ["quick-note"], "semantic_category": "INCIDENT",
                "thread_id": "event:mem:old", "thread_source": "EVENT_ONLY", "anchors": [], "refs": [],
            }
            tagged["project"] = "p3"
            context["project"] = "p3"
            tagged["projects"] = ["p3"]
            context["projects"] = ["p3"]
            other_project = {
                "id": "mem:tiny", "source_type": "VAULT_MEMORY", "authority": "DERIVED_MEMORY_HISTORY",
                "event_at": "2026-09-06T08:03:00+03:00", "recorded_at": "2026-09-06T08:03:00+03:00",
                "title": "Tiny incident", "summary": "Separate project signal", "scope": "tiny3d/case",
                "project": "tiny3d", "projects": ["tiny3d"],
                "tags": ["incident", "assistant-recorded", "verbatim-source"], "semantic_category": "INCIDENT",
                "thread_id": "thread:tiny-case", "thread_source": "EXPLICIT_THREAD", "anchors": [], "refs": [],
            }
            events = [tagged, context, taxonomy_only, old_forensic, other_project]
            graph = build_continuity_graph(events)
            (state / "timeline-store.json").write_text(json.dumps({
                "schema": SCHEMA, "generated_at": datetime.now(timezone.utc).isoformat(), "horizon_days": 30,
                "timeline": {"schema_version": 3, "authority": "DERIVED_HISTORY_ONLY", "contract": {},
                    "events": events, "historical_evidence_events": [], "continuity_graph": graph, "work_graph": {}},
            }), encoding="utf-8")

            query = query_materialized(root=root, query="case x", limit=20)
            self.assertEqual(query["continuity_graph"]["summary"]["matched_cases"], 1)
            self.assertEqual(query["continuity_graph"]["summary"]["store_cases"], 2)
            case = query["continuity_graph"]["cases"][0]
            self.assertEqual(case["case_id"], "thread:case-x")
            self.assertEqual(set(case["event_ids"]), {"mem:signal", "mem:context"})
            self.assertEqual(case["signal_event_ids"], ["mem:signal"])
            self.assertEqual(query["debugging_boundary"]["snapshot_case_arrays"], "BOUNDED_EXAMPLES_NOT_COMPLETE_GRAPH")
            self.assertEqual(query["debugging_boundary"]["continuity_graph"], "FULL_MATERIALIZED_HORIZON_QUERYABLE")

            project_query = query_materialized(root=root, project="p3", limit=20)
            self.assertEqual(project_query["continuity_graph"]["summary"]["matched_cases"], 1)
            self.assertEqual(project_query["continuity_graph"]["cases"][0]["case_id"], "thread:case-x")

            modern_errors = query_materialized(root=root, view="errors", query="taxonomy incident", limit=20)
            self.assertEqual(modern_errors["matching_events"], 0)
            old_errors = query_materialized(root=root, view="errors", query="one incident", limit=20)
            self.assertEqual(old_errors["matching_events"], 1)
            self.assertEqual(old_errors["events"][0]["id"], "mem:old")

    def test_query_materialized_ranks_semantic_history_and_preserves_causal_correction(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            state = root / ".state" / "timeline"
            state.mkdir(parents=True)
            stamp = datetime.now(timezone.utc).isoformat()
            primary = {
                "id": "worker:primary", "source_type": "WORKER_REPORT", "event_at": stamp,
                "title": "Fix P3 paging build failure chain under healthy memory headroom",
                "summary": "P3 build pressure classification", "project": "p3", "refs": [], "anchors": [],
            }
            falsifier = {
                "id": "mem:falsifier", "source_type": "VAULT_MEMORY", "event_at": stamp,
                "title": "MCP stress correction", "summary": "Causal correction from stress tests",
                "_search_text": "2.5 GB memory hold and moderate paging not sufficient; per-connection transient not_proven",
                "project": "p3", "refs": [], "anchors": [],
            }
            generic = {
                "id": "git:generic", "source_type": "GIT_COMMIT", "event_at": stamp,
                "title": "P3 build update with RAM paging pressure", "summary": "generic project token overlap",
                "project": "p3", "refs": [], "anchors": [],
            }
            (state / "timeline-store.json").write_text(json.dumps({
                "schema": SCHEMA, "generated_at": stamp, "horizon_days": 30,
                "timeline": {"schema_version": 3, "authority": "DERIVED_HISTORY_ONLY", "contract": {},
                    "events": [generic, falsifier, primary], "historical_evidence_events": [],
                    "continuity_graph": {"cases": [], "summary": {}}, "work_graph": {}},
            }), encoding="utf-8")
            result = query_materialized(
                root=root,
                query="why did P3 builds stop under RAM paging pressure with healthy headroom",
                limit=20,
            )
            ids = [event["id"] for event in result["events"]]
            self.assertEqual(ids[0], "worker:primary")
            self.assertIn("mem:falsifier", ids[:3])

    def test_install_task_schedules_only_periodic_materializer(self):
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with patch("tools.timeline_materializer._scheduled_python_executable", return_value=r"C:\Python\pythonw.exe"), patch(
            "tools.timeline_materializer.subprocess.run", return_value=completed
        ) as run:
            result = install_task(minutes=5, root=Path(r"C:\Users\Lauri\Desktop\vault"))
        command = run.call_args.args[0]
        rendered = " ".join(str(value) for value in command)
        self.assertTrue(result["ok"])
        self.assertEqual(result["execution_limit_seconds"], 240)
        self.assertTrue(result["headless"])
        self.assertIn("powershell", str(command[0]).casefold())
        self.assertIn("New-ScheduledTaskTrigger", rendered)
        self.assertIn("New-ScheduledTaskSettingsSet", rendered)
        self.assertIn("New-TimeSpan -Minutes 5", rendered)
        self.assertIn("New-TimeSpan -Seconds 240", rendered)
        self.assertIn("MultipleInstances IgnoreNew", rendered)
        self.assertIn("-Hidden", rendered)
        self.assertIn("pythonw.exe", rendered)
        self.assertIn("timeline_materializer.py", rendered)
        self.assertIn("refresh", rendered)
        self.assertIn("--root", rendered)
        self.assertIn("--quiet", rendered)
        self.assertNotIn("memory_bank.py timeline", rendered)

    def test_install_task_runtime_limit_stays_below_one_minute_cadence(self):
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with patch("tools.timeline_materializer._scheduled_python_executable", return_value=r"C:\Python\pythonw.exe"), patch(
            "tools.timeline_materializer.subprocess.run", return_value=completed
        ):
            result = install_task(minutes=1, root=Path(r"C:\Vault"))
        self.assertEqual(result["execution_limit_seconds"], 50)

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
                "project": "p3", "population": "timed", "automation_id": "hazel",
                "display_label": "Hazel", "worker": "Hazel", "duration_minutes": 20.0,
                "target_run_minutes": 24.0, "target_utilization_pct": 83.3,
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
            ), patch(
                "tools.timeline_materializer.library_artifact_events", return_value=([], {"events": 0, "saturated": False, "errors": []})
            ), patch(
                "tools.timeline_materializer.machine_observation_events", return_value=([], {"events": 0, "saturated": False, "errors": []})
            ), patch("tools.timeline_materializer.mcp_events", return_value=([], {"events": 0})), patch(
                "tools.timeline_materializer.mcp_replacement_events", return_value=([], {"events": 0, "saturated": False, "errors": []})
            ), patch(
                "tools.timeline_materializer.runner_log_events", return_value=([], {"events": 0})
            ), patch("tools.timeline_materializer.build_overview", return_value=minimal_overview) as build_overview, patch(
                "tools.timeline_materializer._bootstrap_correction_trigger_projection",
                return_value={"authority": "DERIVED_PROJECTION_ONLY", "status": "READY", "slopwall": "slop", "asshole": "small"},
            ):
                result = materialize(root=root, include_github=False, now=datetime(2026, 9, 6, 5, 0, tzinfo=timezone.utc))
            self.assertTrue(result["ok"])
            self.assertEqual(result["work_graph"]["equivalent_commit_groups"], 1)
            store_path = root / ".state" / "timeline" / "timeline-store.json"
            bootstrap_path = root / ".state" / "timeline" / "bootstrap-memory-overview.json"
            self.assertEqual(json.loads(store_path.read_text(encoding="utf-8"))["schema"], SCHEMA)
            bootstrap = json.loads(bootstrap_path.read_text(encoding="utf-8"))
            self.assertEqual(bootstrap["schema"], BOOTSTRAP_SCHEMA)
            self.assertEqual(bootstrap["overview"]["correction_triggers"]["status"], "READY")
            self.assertNotIn("slopwall", bootstrap["overview"]["correction_triggers"])
            self.assertNotIn("asshole", bootstrap["overview"]["correction_triggers"])
            self.assertEqual(bootstrap["overview"]["contract"].split(";")[0], "BOOTSTRAP_MEMORY_GLANCE_ONLY")
            self.assertNotIn("work_graph", bootstrap["overview"]["timeline_materialized"])
            self.assertEqual(bootstrap["workers"]["read_mode"], "MATERIALIZED_ONLY")
            self.assertEqual(bootstrap["workers"]["archive_sample"]["sampled_worker_count"], 1)
            self.assertEqual(bootstrap["workers"]["archive_sample"]["average_latest_utilization_pct"], 83.3)
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
            self.assertEqual(query["debugging_boundary"]["narrative_order"], "CONTINUITY_CASES>WORK_GRAPH>EVIDENCE_DENSITY>CONTEXT_ONLY_CORROBORATION")
            self.assertEqual(query["debugging_boundary"]["broad_github_anchor_semantics"], "CONTEXT_ONLY_NEVER_CASE_IDENTITY")
            self.assertEqual(query["evidence_density"]["matching_observations"], query["matching_events"])
            self.assertEqual(query["evidence_density"]["semantics"], "OBSERVATION_VOLUME_IS_EVIDENCE_DENSITY_NOT_CASE_COUNT")
            self.assertGreaterEqual(query["matching_events"], 2)
            self.assertEqual(query["work_graph"]["semantics"], "IMPLEMENTATION_EQUIVALENCE_NOT_INCIDENT_IDENTITY")
            self.assertGreaterEqual(query["work_graph"]["summary"]["matched_commit_groups"], 1)
            self.assertEqual(query["work_graph"]["similar_commit_groups"], [])
            self.assertNotIn("attached_event_ids", query["work_graph"]["commit_groups"][0])


    def test_hummingbird_query_surfaces_real_lowvram_rigging_lessons_without_old_keywords(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            state = root / ".state" / "timeline"
            state.mkdir(parents=True)
            stamp = "2026-09-06T20:00:00+03:00"
            seed = {
                "id": "worker:hummingbird", "source_type": "WORKER_REPORT", "authority": "DERIVED_WORKER_HISTORY",
                "event_at": stamp, "project": "tiny3d", "projects": ["tiny3d"],
                "title": "Hummingbird qualification failed unchanged deformation QA",
                "summary": "Welded avian region counts were checked before another rigging attempt.",
                "findings": (
                    "Hummingbird is already source-rigged and skinned with compatible body wing and tail chains. "
                    "Tiny3D geometric rebind produced extreme deformation; preserve no hypothesis without measured QA. "
                    "Weights, welded regions, rig validation, proof, and exported animation all need direct evidence. "
                    "Incidental process notes also mention asset chains and queue cleanup while collecting proof."
                ),
                "refs": [], "anchors": [],
            }
            lessons = [
                {
                    "sha": "97ff891a4ca48faf77c334f80678133ea263c16f", "title": "Bone placement from the mesh, and weights over the surface",
                    "body": (
                        "Euclidean nearest-bone reaches across gaps and claims the wrong leg vertices. bind_geodesic measures distance over the surface "
                        "using adjacency from welded vertex positions. GLB duplicates vertices at every UV seam, so raw index connectivity lies about the surface. "
                        "Better weights alone were insufficient; measured leg axes were also required for deformation."
                    ), "changed_paths": ["blender/rig_animate.py"],
                },
                {
                    "sha": "8ad2a7ba8d3bbc92bca3bd09af798e17e7db99a4", "title": "Rigged exports lost their skin at the export call",
                    "body": (
                        "export_apply consumed the Armature modifier, leaving weights and animation but no skin binding, so a broken rig exited zero and could not deform. "
                        "The repair verifies actually weighted vertices and exported rig state instead of trusting the operator."
                    ), "changed_paths": ["blender/common.py", "blender/rig_animate.py"],
                },
                {
                    "sha": "0e7bef0fa56bea230d1830ec2757dcf7c1413496", "title": "The five-pose verifier posed the wrong limb and called it a pass",
                    "body": (
                        "Opposite-side aliases resolved real bones, so proof rendered a rig flexing the wrong limb and returned pass. "
                        "The verifier must validate its own same-side bindings and report the exact posed bone before judging deformation."
                    ), "changed_paths": ["blender/five_pose_proof.py"],
                },
                {
                    "sha": "6b6d1e3495a760839e0d53e998d86fce3dc4225d", "title": "fix: semantic weight repair for free-arm cape bleed",
                    "body": (
                        "The deformation cause was compute_weights, not animation curves. Semantic regions are defined first and arm reach is excluded from torso and cape, "
                        "preventing tiny weight overlap from normalising into full wrong-region influence."
                    ), "changed_paths": ["blender/shaman_proxy_rig.py", "proof/shaman-rig/latest/semantic_weight_report.json"],
                },
                {
                    "sha": "b26c3cba9e10589eab87884b866cfe251d29d9b7", "title": "rig: separate appendages from cloth with a local shape test",
                    "body": (
                        "Surface distance alone selected a cloak hem instead of the tail. Local shape separates sheet-like cloth from tube-like appendages. "
                        "A deformation proof render is required because 100 percent weighted vertices do not prove the tail bound to the tail."
                    ), "changed_paths": ["blender/rig_animate.py", "blender/rig_appendage_proof.py"],
                },
            ]
            lessons.append({
                "sha": "c01c166da2c951bb75cb23abefe0e1017058530b", "title": "Add asset supervisor, Unreal showroom build and matte/grade workers",
                "body": (
                    "The asset supervisor replaces chained one-shot jobs. One wait path was wrong, the tail of the queue stopped, and the GPU was idle. "
                    "The workflow deletes completed receipts and dispatches rig, proof, and animation workers, but it contains no asset-quality diagnosis."
                ), "changed_paths": ["workers/asset_supervisor.sh"],
            })
            corrective_bridge_noise_title = "Fix CUDA numeric weight proof regression"
            lessons.append({
                "sha": "ce405b9a850ccbc2f3866b3a3ce41261f1aa96b9", "title": corrective_bridge_noise_title,
                "body": (
                    "A rejected deterministic CUDA compile path fixed an invalid zero-weight proof failure. "
                    "The repair prevented a broken numeric test from failing again and only verified tensor finiteness."
                ), "changed_paths": ["tests/test_numeric_backend.py"],
            })
            events = [seed]
            for index, raw in enumerate(lessons):
                events.append({
                    "id": f"git:lowvram:{raw['sha']}", "source_type": "GIT_COMMIT", "authority": "REPO_HISTORY",
                    "event_at": f"2026-08-{8 + index:02d}T12:00:00+03:00", "project": "lowvram", "projects": ["lowvram"],
                    "title": raw["title"], "summary": raw["title"], "body": raw["body"], "changed_paths": raw["changed_paths"],
                    "sha": raw["sha"], "short_sha": raw["sha"][:10], "refs": [], "anchors": [],
                })
            weak_bridge_title = "Weights animation proof resolver record"
            events.append({
                "id": "worker:p3-bridge-only-proof", "source_type": "WORKER_REPORT", "authority": "DERIVED_WORKER_HISTORY",
                "event_at": "2026-08-20T12:00:00+03:00", "project": "p3", "projects": ["p3"],
                "title": weak_bridge_title, "summary": "Identity resolver receipt recorded.",
                "findings": "Resolver candidate validation proof recorded exact identity compiler receipt and artifact lineage.",
                "refs": [], "anchors": [],
            })
            payload = {
                "schema": SCHEMA, "generated_at": stamp, "horizon_days": 30, "ingestion": {},
                "timeline": {
                    "schema_version": "1", "authority": "HISTORICAL_EVIDENCE_ONLY", "contract": "history only",
                    "events": events, "historical_evidence_events": [], "work_graph": build_work_graph(events),
                    "continuity_graph": {"cases": [], "summary": {}}, "materialized": {},
                },
            }
            (state / "timeline-store.json").write_text(json.dumps(payload), encoding="utf-8")
            result = query_materialized(root=root, query="hummingbird wing deformation", limit=8)
        self.assertIsNotNone(result)
        packet = result["lesson_packet"]
        self.assertEqual(packet["status"], "READY")
        self.assertEqual(packet["authority"], "DERIVED_HISTORICAL_PRIORS_ONLY")
        self.assertEqual(packet["validation"], "SLICE1_RETRIEVAL_ONLY_NOT_VALIDATED")
        self.assertTrue(packet["live_truth_required"])
        self.assertLessEqual(len(packet["items"]), 8)
        titles = {item["title"] for item in packet["items"]}
        self.assertIn("Bone placement from the mesh, and weights over the surface", titles)
        self.assertIn("Rigged exports lost their skin at the export call", titles)
        self.assertIn("The five-pose verifier posed the wrong limb and called it a pass", titles)
        self.assertIn("fix: semantic weight repair for free-arm cape bleed", titles)
        self.assertIn("rig: separate appendages from cloth with a local shape test", titles)
        self.assertNotIn("Add asset supervisor, Unreal showroom build and matte/grade workers", titles)
        self.assertNotIn(corrective_bridge_noise_title, titles)
        self.assertNotIn(weak_bridge_title, titles)
        self.assertTrue(all(item.get("evidence_anchors") for item in packet["items"] if item["source_type"] == "GIT_COMMIT"))
        serialized = json.dumps(packet, ensure_ascii=False)
        self.assertLess(len(serialized), 9000)



if __name__ == "__main__":
    unittest.main()
