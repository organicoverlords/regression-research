import io
import json
import os
from contextlib import redirect_stdout
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from tools.cleanup_converger import Worktree, eligibility_reason, process_targets_path
from tools.stack_atlas import (
    _bootstrap_fleet_watch,
    CANONICAL_RECURRING_WORKERS,
    CANONICAL_RECURRING_WORKER_PARTITIONS,
    ATLAS_CONTRACT,
    BOOTSTRAP_MEMORY_CANDIDATE_LIMIT,
    BOOTSTRAP_MEMORY_OVERVIEW_MAX_BYTES,
    BOOTSTRAP_GLANCE_MAX_BYTES,
    BOOTSTRAP_MEMORY_TITLE_LIMIT,
    CANONICAL_RECURRING_WORKERS,
    CANONICAL_RECURRING_WORKER_PARTITIONS,
    blast_radius,
    build_bootstrap_atlas,
    build_live_bootstrap_glance,
    classify_process,
    component_details,
    atlas_lookup,
    find_features,
    full_inventory,
    main as stack_atlas_main,
    production_change_gate,
    render_manual,
    _bootstrap_pc_status,
    _bootstrap_execution_node_topology,
    _bind_pc_node_identity,
    _bootstrap_worker_status,
    _bootstrap_fleet_watch,
    _bootstrap_manual_sanity,
    _bootstrap_manual_current_status,
    _bootstrap_swarm_topology,
    _bootstrap_disk_trend,
    _append_bootstrap_performance_observation,
    bootstrap_performance_stats,
    _read_jsonl_tail,
    _remote_is_newer,
    _git_blob_sha_for_file,
    _git_remote_update_already_applied,
    _git_checkout_state,
    _bootstrap_source_freshness,
    _cwd_uses_worktree,
    _compact_memory_overview,
    _fit_memory_overview_budget,
    _fit_bootstrap_glance_budget,
    _bootstrap_memory_overview,
    _bootstrap_mcp_from_live_swarm,
    _bootstrap_agent_contract_version,
)

ROOT = Path(__file__).resolve().parents[1]


class StackAtlasTests(unittest.TestCase):

    def test_bootstrap_agent_contract_version_requires_matching_headers(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "RULES.md").write_text("# Rules\n\nShared contract version: 7\n", encoding="utf-8")
            (root / "AGENTS.md").write_text("# Agents\n\nShared contract version: 7\n", encoding="utf-8")
            self.assertEqual(
                _bootstrap_agent_contract_version(root),
                {"status": "COHERENT", "version": 7, "rules_version": 7, "agents_version": 7},
            )
            (root / "AGENTS.md").write_text("# Agents\n\nShared contract version: 8\n", encoding="utf-8")
            mismatch = _bootstrap_agent_contract_version(root)
            self.assertEqual(mismatch["status"], "MISMATCH")
            self.assertIsNone(mismatch["version"])
            (root / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
            missing = _bootstrap_agent_contract_version(root)
            self.assertEqual(missing["status"], "MISSING")
            self.assertIsNone(missing["version"])

    def test_bootstrap_mcp_projection_identifies_mcpv4_multisource_evidence(self):
        snapshot = {
            "available": True,
            "summary": {"recent_callers": 2, "workspace_counts": {"Vault": 2}},
            "evidence": {
                "transport": "MCPv4",
                "transport_source_count": 2,
                "source_age_seconds": 0.5,
                "observation_window_complete": True,
                "activity_summary": {"starts": 2, "reads": 2},
            },
            "lanes": [],
        }
        projected = _bootstrap_mcp_from_live_swarm(snapshot)
        self.assertEqual(projected["transport"], "MCPv4")
        self.assertEqual(projected["transport_source_count"], 2)
        self.assertEqual(projected["active_session_count"], 2)

    def test_cleanup_convergence_is_discoverable_and_operator_only(self):
        result = find_features("cleanup worktree convergence")[0]
        self.assertEqual(result["id"], "cleanup.convergence")
        self.assertIn("operator-only", result["boundary"].lower())
        self.assertIn("git-ignored standard unreal", result["boundary"].lower())
        self.assertIn("content/saved/proof/evidence/source", result["boundary"].lower())
        self.assertTrue(any("cleanup_converger.py --apply --operator-ack" in item for item in result["entrypoints"]))

    def test_cleanup_guard_blocks_cross_cwd_process_target_and_locked_lane(self):
        lane = Worktree(Path(r"C:\Temp\p3-lane"), "abcd", "topic", False)
        processes = [{"ProcessId": 42, "CommandLine": r"dotnet.exe -Project=C:\Temp\p3-lane\p3.uproject"}]
        self.assertTrue(process_targets_path(lane.path, processes, self_pid=999))
        self.assertEqual(
            eligibility_reason(lane, recent_cwds=set(), processes=processes, clean=True, ref_matches=True),
            "external_process_targets_path",
        )
        locked = Worktree(Path(r"C:\Temp\locked"), "efgh", "topic2", False, "protected")
        self.assertEqual(
            eligibility_reason(locked, recent_cwds=set(), processes=[], clean=True, ref_matches=True),
            "git_worktree_locked:protected",
        )
    def test_compact_memory_overview_is_shallow_orientation_not_memory_detail(self):
        report = {
            "contract": "history only",
            "eligible_entries": 21,
            "incident_rollups": [{
                "thread_id": "thread:regression",
                "thread_source": "EXPLICIT_THREAD",
                "scope": "assistant-stack/bootstrap-memory",
                "observations": 20,
                "latest_event_at": "2026-09-09T10:41:08+03:00",
                "latest_event_id": "mem-20",
                "latest_title": "RED ALERT: bootstrap memory regression",
                "latest_disposition": "CURRENT_DURABLE",
                "summary": "Detailed narrative that must never enter bootstrap.",
                "projects": ["regression-research"],
                "entities": ["bootstrap"],
                "member_ids": [f"mem-{i}" for i in range(1, 21)],
                "drilldown": "python tools\\memory_bank.py timeline --thread thread:regression --limit 20 --no-workers",
            }],
            "recent": [
                {"id": "mem-20", "timestamp": "2026-09-09T10:41:08+03:00", "title": "Covered"},
                {"id": "other", "timestamp": "2026-09-09T10:40:00+03:00", "title": "Other"},
            ],
            "timeline_snapshots": {
                "authority": "DERIVED_HISTORY_ONLY",
                "narrative_contract": {"primary_unit": "CONTINUITY_CASE"},
                "windows": [{
                    "window": "24h",
                    "event_count": 42,
                    "continuity_case_summary": {"total": 4, "red": 1, "regression": 3},
                    "signal_observation_summary": {"total": 42, "red": 2, "regression": 21},
                    "source_counts": {"VAULT_MEMORY": 20, "GIT_COMMIT": 22},
                    "artifact_counts": {"report": 8},
                    "highlights": [{"title": "detailed highlight that must not survive"}],
                    "corroborated_anchors": [{"anchor": "github:repo#1", "role": "CONTEXT_ONLY"}],
                    "continuity_case_examples": [{
                        "case_id": "thread:regression", "severity": "RED", "traits": ["regression"],
                        "observation_count": 20, "source_families": ["memory", "repo"],
                        "evidence_forms": ["memory", "commit"], "classification_quality": "MIXED",
                        "latest_signal_at": "2026-09-09T10:41:08+03:00",
                        "latest_title": "RED ALERT: bootstrap memory regression",
                    }],
                }],
            },
            "projects": [{"name": "regression-research", "count": 20}],
            "recurring_tags": [{"name": "regression", "count": 20}],
            "worker_findings": {"detail": "never bootstrap this"},
        }
        compact = _compact_memory_overview(report, 3)
        self.assertLessEqual(len(json.dumps(compact, separators=(",", ":")).encode("utf-8")), BOOTSTRAP_MEMORY_OVERVIEW_MAX_BYTES)
        self.assertEqual(BOOTSTRAP_MEMORY_OVERVIEW_MAX_BYTES, 5_500)
        self.assertEqual([item["id"] for item in compact["recent"]], ["other"])
        rollup = compact["incident_rollups"][0]
        self.assertEqual(rollup["observations"], 20)
        for forbidden in ("summary", "projects", "entities", "member_ids"):
            self.assertNotIn(forbidden, rollup)
        self.assertNotIn("worker_findings", compact)
        snapshots = compact["timeline_snapshots"]
        self.assertNotIn("narrative", snapshots)
        window = snapshots["windows"][0]
        for forbidden in ("highlights", "sources", "artifacts", "context_only", "slice"):
            self.assertNotIn(forbidden, window)
        case = window["case_examples"][0]
        self.assertEqual(case["severity"], "RED")
        self.assertEqual(case["observations"], 20)
        self.assertLessEqual(set(case), {"id", "severity", "traits", "observations", "at", "title"})
        for forbidden in ("sources", "forms", "support", "summary"):
            self.assertNotIn(forbidden, case)

    def test_memory_glance_budget_drops_optional_index_items_not_detail_text(self):
        report = {
            "eligible_entries": 99,
            "incident_rollups": [{
                "thread_id": f"thread:bug-{i}", "scope": f"memory/bug-{i}", "observations": 20,
                "latest_event_at": f"2026-09-09T10:0{i}:00+03:00", "latest_event_id": f"bug-{i}",
                "latest_title": "x" * 400, "latest_disposition": "CURRENT_DURABLE",
                "summary": "narrative " * 500, "projects": ["p" * 500], "entities": ["e" * 500],
                "member_ids": [f"bug-{i}-{n}" for n in range(20)], "drilldown": "memory_bank timeline " + "z" * 500,
            } for i in range(3)],
            "recent": [{"id": f"r{i}", "timestamp": "2026-09-09", "title": "r" * 400} for i in range(3)],
            "projects": [{"name": "p" * 300, "count": 10} for _ in range(3)],
            "recurring_tags": [{"name": "t" * 300, "count": 10} for _ in range(3)],
            "timeline_snapshots": {"authority": "DERIVED_HISTORY_ONLY", "windows": []},
        }
        compact = _compact_memory_overview(report, 3)
        self.assertLessEqual(len(json.dumps(compact, separators=(",", ":")).encode("utf-8")), BOOTSTRAP_MEMORY_OVERVIEW_MAX_BYTES)
        self.assertTrue(all("summary" not in item for item in compact["incident_rollups"]))

    def test_materialized_metadata_is_health_only_in_bootstrap_memory(self):
        compact = _compact_memory_overview({
            "eligible_entries": 218,
            "timeline_snapshots": {"authority": "DERIVED_HISTORY_ONLY", "windows": [{
                "window": "24h", "event_count": 100,
                "continuity_case_summary": {"total": 3, "red": 1},
                "continuity_case_examples": [{
                    "case_id": "thread:red", "severity": "RED", "traits": ["regression"],
                    "observation_count": 3, "latest_signal_at": "2026-09-09T10:00:00+03:00",
                    "latest_title": "RED ALERT: recurrence",
                }],
            }]},
            "incident_rollups": [], "recent": [], "projects": [], "recurring_tags": [],
        }, 3)
        compact["timeline_materialized"] = {
            "status": "FRESH", "coverage_status": "HISTORICAL_INCOMPLETE", "live_truth_required": True,
            "backfill_incomplete_sources": ["github"], "historical_evidence_events": 500,
            "work_graph": {"semantics": "detail", "cross_branch_groups": 276},
        }
        fitted = _fit_memory_overview_budget(compact)
        self.assertEqual(fitted["timeline_materialized"]["status"], "FRESH")
        self.assertEqual(fitted["timeline_materialized"]["coverage_status"], "HISTORICAL_INCOMPLETE")
        self.assertNotIn("historical_evidence_events", fitted["timeline_materialized"])
        self.assertNotIn("work_graph", fitted["timeline_materialized"])
        self.assertEqual(fitted["timeline_snapshots"]["windows"][0]["case_examples"][0]["severity"], "RED")

    def test_bootstrap_memory_overview_reads_periodic_projection_without_rebuilding_sources(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = root / ".state" / "timeline" / "bootstrap-memory-overview.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({
                "schema": "vault.timeline.bootstrap.v1",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "overview": {
                    "contract": "history only",
                    "eligible_entries": 24,
                    "timeline_snapshots": {"authority": "DERIVED_HISTORY_ONLY", "windows": []},
                    "incident_rollups": [],
                    "recent": [{"id": "unrelated-1", "timestamp": "2026-09-06T02:59:00+03:00", "title": "Unrelated one"}],
                    "projects": [],
                    "recurring_tags": [],
                    "timeline_materialized": {
                        "refresh_minutes": 5, "horizon_days": 30,
                        "backfill_incomplete_sources": ["github", "runner_logs"],
                        "work_graph": {"cross_branch_groups": 7},
                    },
                },
            }), encoding="utf-8")
            with patch("tools.stack_atlas.ATLAS_LIVE_ROOT", root), patch(
                "tools.memory_bank.build_overview", side_effect=AssertionError("bootstrap must not rebuild timeline")
            ):
                compact = _bootstrap_memory_overview()
        self.assertEqual(compact["timeline_materialized"]["status"], "FRESH")
        self.assertEqual(compact["timeline_materialized"]["read_mode"], "MATERIALIZED_ONLY")
        self.assertNotIn("work_graph", compact["timeline_materialized"])
        self.assertEqual(compact["timeline_materialized"]["coverage_status"], "HISTORICAL_INCOMPLETE")
        self.assertEqual(compact["timeline_materialized"]["backfill_incomplete_sources"], ["github", "runner_logs"])
        self.assertEqual(compact["timeline_materialized"]["absence_semantics"], "NO_MATCH_IS_NOT_PROOF_OF_ABSENCE")
        self.assertTrue(compact["timeline_materialized"]["live_truth_required"])
        self.assertEqual([item["id"] for item in compact["recent"]], ["unrelated-1"])
        size = len(json.dumps(compact, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        self.assertLessEqual(size, BOOTSTRAP_MEMORY_OVERVIEW_MAX_BYTES)

    def test_bootstrap_memory_overview_reports_missing_projection_without_source_scan(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with patch("tools.stack_atlas.ATLAS_LIVE_ROOT", root), patch(
                "tools.memory_bank.build_overview", side_effect=AssertionError("bootstrap must not rebuild timeline")
            ):
                compact = _bootstrap_memory_overview()
        self.assertEqual(compact["timeline_materialized"]["status"], "MISSING")
        self.assertEqual(compact["timeline_snapshots"], {})
        self.assertIn("timeline_materializer.py", compact["timeline_materialized"]["refresh_command"])

    def test_bootstrap_notable_conditions_surface_timeline_history_debt_without_degrading_live_health(self):
        pc = {"disk": {"status": "OK", "free_gb": 100.0, "trend": {}}, "memory": {"status": "OK"}}
        workers = {"available": True}
        mcp = {"available": True, "status": "LIVE", "active_session_count": 0, "active_session_count_status": "COMPLETE", "workspace_counts": {}}
        vault = {"status": "OK"}
        github = {"status": "OK"}
        memory = {
            "timeline_materialized": {
                "status": "FRESH",
                "backfill_incomplete_sources": ["github", "runner_logs"],
                "retry_sources": [],
            },
            "recent": [],
        }
        with patch("tools.stack_atlas._bootstrap_pc_status", return_value=pc), \
             patch("tools.stack_atlas._bootstrap_worker_status", return_value=workers), \
             patch("tools.stack_atlas._bootstrap_mcp_status", return_value=mcp), \
             patch("tools.stack_atlas._bootstrap_memory_overview", return_value=memory), \
             patch("tools.stack_atlas._bootstrap_vault_status", return_value=vault), \
             patch("tools.stack_atlas._bootstrap_github_status", return_value=github), \
             patch("tools.stack_atlas._bootstrap_mcp_recovery_state", return_value={}):
            glance = build_live_bootstrap_glance()
        self.assertEqual(glance["bootstrap"]["status"], "OK")
        self.assertNotIn("notable_conditions", glance)
        self.assertEqual(glance["memory_overview"]["timeline_materialized"]["backfill_incomplete_sources"], ["github", "runner_logs"])

    def test_session_cwd_worktree_match_is_one_way(self):
        worktree = r"C:\Users\Lauri\AppData\Local\Temp\p3-941-control-hints"
        self.assertTrue(_cwd_uses_worktree(worktree, worktree))
        self.assertTrue(_cwd_uses_worktree(worktree + r"\Source\LaneWar", worktree))
        self.assertFalse(_cwd_uses_worktree(r"C:\Users\Lauri", worktree))
        self.assertFalse(_cwd_uses_worktree(r"C:\Users\Lauri\AppData\Local\Temp\other-worktree", worktree))

    def test_live_bootstrap_displays_machine_workers_and_active_sessions(self):
        sample_workers = {
            "available": True,
            "latest_archived_per_worker": [{"display_label": "Aspen", "duration_minutes": 5.0, "target_minutes": 24.0, "target_utilization_pct": 20.8, "classification": "SEVERELY_PREMATURE", "age_minutes": 10.0}],
            "manual_current": {
                "available": True,
                "evidence_semantics": "manual_current_report_state_and_purpose_only_not_process_liveness_or_scheduler_membership",
                "recent_running_report_count": 2,
                "recent_running_report_count_status": "COMPLETE",
                "recent_running_reports": [
                    {"run_id": "manual-a", "display_label": "Head Auditor continuation", "scope": "audit current stack", "state": "RUNNING", "age_minutes": 0.2},
                    {"run_id": "manual-b", "display_label": "P3 worker-population blindness audit", "scope": "audit worker population", "state": "RUNNING", "age_minutes": 0.4},
                ],
            },
            "attention": [{"worker": "Aspen", "duration_minutes": 5.0, "target_minutes": 24.0, "utilization_pct": 20.8, "classification": "SEVERELY_PREMATURE", "age_minutes": 10.0}],
        }
        with patch("tools.stack_atlas._bootstrap_worker_status", return_value=sample_workers):
            glance = build_live_bootstrap_glance()
        payload = json.dumps(glance, separators=(",", ":")).encode("utf-8")
        self.assertLessEqual(len(payload), BOOTSTRAP_GLANCE_MAX_BYTES)
        self.assertEqual(BOOTSTRAP_GLANCE_MAX_BYTES, 15_000)
        self.assertEqual(next(iter(glance)), "bootstrap_warning")
        self.assertEqual(next(reversed(glance)), "bootstrap_end")
        self.assertEqual(glance["bootstrap_end"]["status"], "COMPLETE")
        self.assertEqual(glance["bootstrap"]["payload_budget"]["max_bytes"], BOOTSTRAP_GLANCE_MAX_BYTES)
        self.assertIn("trend", glance["pc"]["disk"])
        memory = glance["pc"]["memory"]
        self.assertIn("commit_headroom_gb", memory)
        self.assertGreaterEqual(glance["mcp"]["active_session_count"], len(glance["mcp"]["active_sessions"]))
        self.assertEqual(glance["mcp"]["active_session_count_semantics"], "recent_callers_with_process_start_or_read_in_activity_window_not_current_running_processes")
        self.assertLessEqual(len(glance["mcp"]["active_sessions"]), glance["mcp"]["active_session_detail_limit"])
        self.assertIn("workspace_counts", glance["mcp"])
        for session in glance["mcp"]["active_sessions"]:
            self.assertIn("caller_id", session)
            self.assertIn("cwd", session)
            self.assertIn("workspace", session)
            self.assertIn("busy_titles", session)
            self.assertLessEqual(session["activity_age_seconds"], 300)
        self.assertNotIn("notable_conditions", glance)
        self.assertNotIn("latest_archived_per_worker", glance["workers"])
        self.assertNotIn("fleet", glance["workers"])
        self.assertNotIn("manual_current", glance["workers"])
        self.assertNotIn("Head Auditor continuation", json.dumps(glance["workers"]))
        self.assertNotIn('"state":"RUNNING"', json.dumps(glance["workers"], separators=(",", ":")))
        self.assertEqual(glance["workers"]["current_activity"]["authority"], "live_swarm_runtime_evidence")
        self.assertEqual(glance["workers"]["current_activity"]["population_scope"], "unified_recurring_and_manual_on_demand_activity")
        self.assertNotIn("fleet_watch", glance["workers"])
        self.assertNotIn("component_statuses", glance["bootstrap"])
        self.assertNotIn("recent_memory_titles", glance)
        self.assertNotIn("behavior", glance)
        self.assertEqual(glance["paths"]["rules"], r"C:\Users\Lauri\.agents\RULES.md")
        self.assertEqual(glance["paths"]["agents"], r"C:\Users\Lauri\.agents\AGENTS.md")
        contract = glance["bootstrap"]["agent_contract"]
        self.assertEqual(contract["status"], "COHERENT")
        self.assertGreaterEqual(contract["version"], 1)
        self.assertEqual(contract["version"], contract["rules_version"])
        self.assertEqual(contract["version"], contract["agents_version"])
        self.assertNotIn("mcp_hour", glance["commands"])
        self.assertIn("production_change_gate", glance["commands"])
        self.assertIn("memory_overview", glance["commands"])
        self.assertIn("tiny3d_asset_library", glance["commands"])
        self.assertIn("lookup tiny3d_library", glance["commands"]["tiny3d_asset_library"])
        self.assertNotIn("connector_reliability.py", json.dumps(glance))

    def test_bootstrap_cli_emits_the_budgeted_compact_utf8_representation(self):
        glance = _fit_bootstrap_glance_budget({
            "bootstrap": {"status": "OK"},
            "non_ascii_probe": "ä" * 4000,
        })
        output = io.StringIO()
        with patch("sys.argv", ["stack_atlas.py", "bootstrap-glance"]), \
                patch("tools.stack_atlas.build_live_bootstrap_glance", return_value=glance), \
                redirect_stdout(output):
            self.assertEqual(stack_atlas_main(), 0)
        raw = output.getvalue().encode("utf-8")
        self.assertLessEqual(len(raw), BOOTSTRAP_GLANCE_MAX_BYTES + 1)
        self.assertTrue(raw.startswith(b'{"bootstrap_warning":'))
        self.assertTrue(raw.rstrip().endswith(b'"bootstrap_end":{"status":"COMPLETE","schema":"bootstrap.v1"}}'))
        self.assertEqual(json.loads(raw), glance)

    def test_bootstrap_budget_compacts_drilldown_detail_before_live_truth(self):
        glance = {
            "bootstrap": {"status": "OK"},
            "mcp_recovery_state": {
                "path": r"C:\\vault\\mcp-recovery-state.json",
                "conditions": [
                    {
                        "type": f"Condition{i}", "status": "Unknown", "reason": "BoundedReason",
                        "message": "detail " * 120, "observed_generation": "g" * 80,
                        "last_transition_at": "2026-09-06T18:00:00Z",
                    }
                    for i in range(5)
                ],
            },
            "memory_overview": {
                "contract": "history only", "eligible_entries": 400,
                "timeline_snapshots": {
                    "authority": "DERIVED_HISTORY_ONLY",
                    "narrative": {"primary": "cases", "read_order": "cases>work_graph>evidence_density>context_only"},
                    "windows": [{
                        "window": "24h", "cases": {"total": 20, "red": 1}, "observations": 5000,
                        "case_examples": [{"id": "case:important", "title": "important case", "support": "mixed"}],
                        "highlights": [{"title": "x" * 500} for _ in range(8)],
                    }],
                },
                "timeline_materialized": {"status": "FRESH", "coverage_status": "HISTORICAL_INCOMPLETE"},
                "incident_rollups": [], "recent": [], "projects": [], "recurring_tags": [],
            },
            "source_freshness": {
                "available": True, "attention_required": True, "updates_pending": False,
                "meaning": "detail " * 120, "cache": {"used": True, "age_seconds": 1},
                "sources": {
                    "RULES.md": {"path": "p" * 500, "last_update_commit": "a" * 40, "last_updated_at": "2026-09-06T18:00:00Z", "local_last_committed_at": "2026-09-06T18:00:00Z", "local_matches_remote_main": False, "local_differs_from_remote_main": True, "updates_pending": False},
                },
            },
            "mcp": {
                "active_session_count": 9, "active_session_count_status": "COMPLETE", "workspace_counts": {"Vault": 9},
                "active_sessions": [{"caller_id": f"caller-{i}", "cwd": "C:\\" + ("x" * 350), "workspace": "Vault", "busy_titles": []} for i in range(4)],
            },
            "workers": {
                "attention": [{"worker": f"w{i}", "detail": "x" * 300} for i in range(4)], "stale_reports": [],
                "manual_sanity": {
                    "available": True, "path": "p" * 500, "baseline_id": "baseline", "boundary_at": "2026-09-06T21:26:41+03:00",
                    "status": "PROVISIONAL", "score_delta": 42.0, "direction": "IMPROVED", "post_run_count": 7,
                    "minimum_post_runs_for_provisional": 5, "minimum_post_runs_for_comparable": 20,
                    "components": {"median_report_bytes": {"baseline": 1000, "current": 500, "delta_points": 20}},
                    "semantics": "diagnostic detail " * 100,
                },
            },
            "paths": {"mcp_recovery_state": r"C:\\vault\\mcp-recovery-state.json"},
            "commands": {"stack_owner": "python tools/stack_atlas.py lookup <id>"},
        }
        memory_before = json.loads(json.dumps(glance["memory_overview"]))
        fitted = _fit_bootstrap_glance_budget(glance)
        size = len(json.dumps(fitted, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        self.assertLessEqual(size, BOOTSTRAP_GLANCE_MAX_BYTES)
        self.assertTrue(fitted["bootstrap"]["payload_budget"]["compacted"])
        self.assertEqual(fitted["mcp"]["active_session_count"], 9)
        self.assertEqual(fitted["mcp"]["workspace_counts"], {"Vault": 9})
        self.assertEqual(fitted["mcp_recovery_state"]["conditions"][0], {"type": "Condition0", "status": "Unknown", "reason": "BoundedReason"})
        self.assertTrue(fitted["source_freshness"]["attention_required"])
        self.assertTrue(fitted["source_freshness"]["sources"]["RULES.md"]["local_differs_from_remote_main"])
        self.assertEqual(fitted["workers"]["manual_sanity"]["status"], "PROVISIONAL")
        self.assertEqual(fitted["workers"]["manual_sanity"]["post_run_count"], 7)
        self.assertIn("case:important", json.dumps(fitted["memory_overview"]))
        self.assertEqual(fitted["memory_overview"], memory_before)

    def test_bootstrap_budget_compacts_manual_sanity_before_session_samples(self):
        glance = {
            "bootstrap": {"status": "OK"},
            "workers": {"manual_sanity": {
                "available": True, "path": "p" * 500, "baseline_id": "baseline",
                "boundary_at": "2026-09-06T21:26:41+03:00", "status": "PROVISIONAL",
                "score_delta": 42.0, "direction": "IMPROVED", "post_run_count": 7,
                "minimum_post_runs_for_provisional": 5, "minimum_post_runs_for_comparable": 20,
                "components": {"median_report_bytes": {"baseline": 1000, "current": 500, "delta_points": 20}},
                "semantics": "diagnostic detail " * 200,
            }},
            "mcp": {
                "active_session_count": 4, "active_session_count_status": "COMPLETE", "workspace_counts": {"Vault": 4},
                "active_sessions": [{"caller_id": f"c{i}", "cwd": "C:/" + ("x" * 250), "workspace": "Vault", "busy_titles": []} for i in range(4)],
            },
        }
        fitted = _fit_bootstrap_glance_budget(glance, 2_200)
        size = len(json.dumps(fitted, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        self.assertLessEqual(size, 2_200)
        self.assertEqual(len(fitted["mcp"]["active_sessions"]), 4)
        self.assertEqual(fitted["mcp"]["active_session_count"], 4)
        self.assertEqual(fitted["workers"]["manual_sanity"]["status"], "PROVISIONAL")
        self.assertEqual(fitted["workers"]["manual_sanity"]["post_run_count"], 7)
        self.assertNotIn("components", fitted["workers"]["manual_sanity"])

    def test_production_change_gate_requires_specific_scope_basis(self):
        mcp = {
            "available": True, "status": "LIVE", "active_session_count": 20,
            "active_session_count_status": "COMPLETE", "active_sessions": [{"caller_id": "c1"}],
        }
        busy = {"available": True, "claim": {"actor": "ChatGPT:test"}, "job": None}
        gate = production_change_gate(
            "mcpv3", actor="ChatGPT:test", busy_scope="mcp-production:vps-caddy-routing",
            explicit_user_authorization=False, independent_rollback_verified=True, offpath_proof_verified=True,
            mcp_status=mcp, busy_status=busy,
        )
        self.assertEqual(gate["verdict"], "BLOCK")
        self.assertIn("missing_live_production_scope_basis", gate["reasons"])
        self.assertTrue(gate["semantics"]["routine_scoped_advance_does_not_require_redundant_user_approval"])
        self.assertEqual(gate["live_dependencies"]["mcp"]["active_session_count"], 20)

        routine = production_change_gate(
            "mcpv3", actor="ChatGPT:test", busy_scope="mcp-production:vps-caddy-routing",
            explicit_user_authorization=False, routine_scoped_advance=True,
            independent_rollback_verified=True, offpath_proof_verified=True,
            mcp_status=mcp, busy_status=busy,
        )
        self.assertEqual(routine["verdict"], "PASS")
        self.assertEqual(routine["reasons"], [])
        self.assertEqual(routine["checks"]["scope_authorization_source"], "ROUTINE_SCOPED_ADVANCE")

    def test_production_change_gate_covers_shared_agent_rules_serving_root(self):
        busy = {"available": True, "claim": {"actor": "ChatGPT:test"}, "job": None}
        blocked = production_change_gate(
            "agent_rules", actor="ChatGPT:test", busy_scope="agents:RULES.md",
            explicit_user_authorization=False, independent_rollback_verified=True, offpath_proof_verified=True,
            busy_status=busy,
        )
        self.assertEqual(blocked["verdict"], "BLOCK")
        self.assertTrue(blocked["target"]["shared_production"])
        self.assertEqual(blocked["reasons"], ["missing_live_production_scope_basis"])
        self.assertEqual(blocked["live_dependencies"], {})

        allowed = production_change_gate(
            "agent_rules", actor="ChatGPT:test", busy_scope="agents:RULES.md",
            explicit_user_authorization=True, independent_rollback_verified=True, offpath_proof_verified=True,
            busy_status=busy,
        )
        self.assertEqual(allowed["verdict"], "PASS")
        self.assertEqual(allowed["reasons"], [])
        self.assertTrue(allowed["target"]["shared_production"])

    def test_production_change_gate_blocks_without_independent_rollback(self):
        mcp = {
            "available": True, "status": "LIVE", "active_session_count": 3,
            "active_session_count_status": "COMPLETE", "active_sessions": [],
        }
        busy = {"available": True, "claim": {"actor": "ChatGPT:test"}, "job": None}
        gate = production_change_gate(
            "vps_edge_ingress", actor="ChatGPT:test", busy_scope="mcp-vps:/etc/caddy/Caddyfile",
            explicit_user_authorization=True, independent_rollback_verified=False, offpath_proof_verified=True,
            mcp_status=mcp, busy_status=busy,
        )
        self.assertEqual(gate["verdict"], "BLOCK")
        self.assertIn("independent_rollback_control_route_not_verified", gate["reasons"])

    def test_production_change_gate_blocks_foreign_busy_claim(self):
        mcp = {
            "available": True, "status": "LIVE", "active_session_count": 1,
            "active_session_count_status": "COMPLETE", "active_sessions": [],
        }
        busy = {"available": True, "claim": {"actor": "ChatGPT:other"}, "job": None}
        gate = production_change_gate(
            "mcp_front_door", actor="ChatGPT:test", busy_scope="mcp-production:front-door",
            explicit_user_authorization=True, independent_rollback_verified=True, offpath_proof_verified=True,
            mcp_status=mcp, busy_status=busy,
        )
        self.assertEqual(gate["verdict"], "BLOCK")
        self.assertIn("busy_scope_claimed_by_other_actor", gate["reasons"])

    def test_production_change_gate_passes_only_with_complete_evidence_and_reports_dependents(self):
        mcp = {
            "available": True, "status": "LIVE", "active_session_count": 20,
            "active_session_count_status": "COMPLETE", "active_sessions": [{"caller_id": "c1"}, {"caller_id": "c2"}],
        }
        busy = {"available": True, "claim": {"actor": "ChatGPT:test"}, "job": None}
        gate = production_change_gate(
            "mcpv3", actor="ChatGPT:test", busy_scope="mcp-production:vps-caddy-routing",
            explicit_user_authorization=True, independent_rollback_verified=True, offpath_proof_verified=True,
            mcp_status=mcp, busy_status=busy,
        )
        self.assertEqual(gate["verdict"], "PASS")
        self.assertEqual(gate["reasons"], [])
        self.assertIn("recent_mcp_activity_present", gate["warnings"])
        self.assertNotIn("active_mcp_dependents_present", gate["warnings"])
        self.assertEqual(gate["live_dependencies"]["mcp"]["active_session_count"], 20)
        self.assertEqual(gate["live_dependencies"]["mcp"]["active_session_count_semantics"], None)

    def test_production_change_gate_reads_canonical_mcpv4_live_swarm_not_legacy_scanner(self):
        snapshot = {
            "available": True,
            "summary": {"recent_callers": 3, "workspace_counts": {"Vault": 3}},
            "evidence": {
                "transport": "MCPv4", "transport_source_count": 2,
                "source_age_seconds": 0.2, "observation_window_complete": True,
                "activity_summary": {"starts": 3, "reads": 3},
            },
            "lanes": [],
        }
        busy = {"available": True, "claim": {"actor": "ChatGPT:test"}, "job": None}
        with (
            patch("tools.stack_atlas.build_live_swarm_snapshot", return_value=snapshot),
            patch("tools.stack_atlas._bootstrap_mcp_status", side_effect=AssertionError("legacy status path must not run")),
        ):
            gate = production_change_gate(
                "mcpv3", actor="ChatGPT:test", busy_scope="mcp-production:vps-caddy-routing",
                explicit_user_authorization=True, independent_rollback_verified=True, offpath_proof_verified=True,
                busy_status=busy,
            )
        self.assertEqual(gate["verdict"], "PASS")
        dep = gate["live_dependencies"]["mcp"]
        self.assertEqual(dep["authority"], "live_swarm_runtime_evidence")
        self.assertEqual(dep["transport"], "MCPv4")
        self.assertEqual(dep["transport_source_count"], 2)
        self.assertEqual(dep["active_session_count"], 3)

    def test_fleet_watch_has_one_implementation(self):
        source = (ROOT / "tools" / "stack_atlas.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("def _bootstrap_fleet_watch("), 1)

    def test_fleet_watch_flags_missing_and_stale_running_from_local_evidence_only(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "worker-reports" / "current"
            supervision = root / "worker-reports" / ".supervision"
            current.mkdir(parents=True)
            supervision.mkdir(parents=True)
            now = datetime.now(timezone.utc)

            missing_id, _ = CANONICAL_RECURRING_WORKERS[0]
            stale_id, _ = CANONICAL_RECURRING_WORKERS[1]
            for index, (worker_id, label) in enumerate(CANONICAL_RECURRING_WORKERS[1:], start=1):
                age = 85 if worker_id == stale_id else 20
                state = "RUNNING" if worker_id == stale_id else "RUN_FINISHED"
                started = now - timedelta(minutes=age)
                (current / f"{worker_id}.md").write_text(
                    f"automation_id: {worker_id}\n"
                    f"display_label: {label}\n"
                    f"started_at: {started.isoformat()}\n"
                    f"last_activity_at: {started.isoformat()}\n"
                    f"state: {state}\n",
                    encoding="utf-8",
                )
                if worker_id == stale_id:
                    (supervision / f"{worker_id}.start.json").write_text("{}", encoding="utf-8")

            with patch("tools.stack_atlas.ATLAS_LIVE_ROOT", root):
                watch = _bootstrap_fleet_watch(now)

        self.assertEqual(watch["scheduler_probe"], "not_performed")
        self.assertEqual(watch["observed_worker_reports"], len(CANONICAL_RECURRING_WORKERS) - 1)
        self.assertEqual(watch["status"], "SUSPECT_DEGRADED")
        suspect_ids = {item["automation_id"] for item in watch["suspect_workers"]}
        self.assertIn(missing_id, suspect_ids)
        self.assertIn(stale_id, suspect_ids)
        self.assertEqual(watch["recovery_candidate_count"], 2)

    def test_fleet_watch_running_worker_uses_last_activity_for_freshness(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "worker-reports" / "current"
            supervision = root / "worker-reports" / ".supervision"
            current.mkdir(parents=True)
            supervision.mkdir(parents=True)
            now = datetime.now(timezone.utc)
            target_id, _ = CANONICAL_RECURRING_WORKERS[0]
            for worker_id, label in CANONICAL_RECURRING_WORKERS:
                started = now - timedelta(minutes=95 if worker_id == target_id else 20)
                last_activity = now - timedelta(minutes=3) if worker_id == target_id else started
                state = "RUNNING" if worker_id == target_id else "RUN_FINISHED"
                (current / f"{worker_id}.md").write_text(
                    f"automation_id: {worker_id}\n"
                    f"display_label: {label}\n"
                    f"started_at: {started.isoformat()}\n"
                    f"last_activity_at: {last_activity.isoformat()}\n"
                    f"state: {state}\n",
                    encoding="utf-8",
                )
                if worker_id == target_id:
                    (supervision / f"{worker_id}.start.json").write_text("{}", encoding="utf-8")
            with patch("tools.stack_atlas.ATLAS_LIVE_ROOT", root):
                watch = _bootstrap_fleet_watch(now)
        self.assertEqual(watch["running_with_start_receipt"], 1)
        self.assertNotIn(target_id, {item["automation_id"] for item in watch["suspect_workers"]})

    def test_bootstrap_execution_node_topology_distinguishes_gpu_machine_from_laptop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract = root / "04 Operating Contracts" / "execution-node-topology.json"
            contract.parent.mkdir(parents=True)
            contract.write_text(json.dumps({
                "schema": "swarm.execution-node-topology.v1",
                "authority": "CANONICAL_EXECUTION_NODE_IDENTITY",
                "nodes": {
                    "kone-gpu-desktop": {
                        "display_name": "KONE GPU desktop",
                        "user_alias": "GPU machine",
                        "route_label": "windows",
                        "hostnames": ["KONE"],
                        "machine_class": "desktop",
                        "os_family": "windows",
                        "system_model": "HP Pavilion Gaming Desktop TG01-2xxx",
                        "gpu": "NVIDIA GeForce GTX 1660 SUPER",
                    },
                    "omen-linux-laptop": {
                        "display_name": "OMEN Linux laptop",
                        "user_alias": "laptop",
                        "route_label": "omen",
                        "hostnames": ["aatuska-OMEN-by-HP-Laptop-15-dc0xxx"],
                        "machine_class": "laptop",
                        "os_family": "linux",
                        "system_model": "HP OMEN by HP Laptop 15-dc0xxx",
                        "gpu": "NVIDIA GeForce GTX 1070 with Max-Q Design",
                    },
                },
            }), encoding="utf-8")
            with patch("tools.stack_atlas.ATLAS_LIVE_ROOT", root), patch("tools.stack_atlas.platform.node", return_value="KONE"):
                topology = _bootstrap_execution_node_topology()

        self.assertEqual(topology["status"], "OK")
        self.assertEqual(topology["local_node_id"], "kone-gpu-desktop")
        self.assertEqual(topology["nodes"]["kone-gpu-desktop"]["user_alias"], "GPU machine")
        self.assertEqual(topology["nodes"]["kone-gpu-desktop"]["machine_class"], "desktop")
        self.assertEqual(topology["nodes"]["omen-linux-laptop"]["user_alias"], "laptop")
        self.assertEqual(topology["nodes"]["omen-linux-laptop"]["machine_class"], "laptop")
        self.assertNotEqual(topology["nodes"]["kone-gpu-desktop"]["gpu"], topology["nodes"]["omen-linux-laptop"]["gpu"])

    def test_bootstrap_missing_execution_node_registry_is_visible_and_not_guessed(self):
        with tempfile.TemporaryDirectory() as tmp, patch("tools.stack_atlas.ATLAS_LIVE_ROOT", Path(tmp)), patch("tools.stack_atlas.platform.node", return_value="KONE"):
            topology = _bootstrap_execution_node_topology()
        self.assertFalse(topology["available"])
        self.assertEqual(topology["status"], "MISSING")
        self.assertIsNone(topology["local_node_id"])
        self.assertEqual(topology["local_observed_hostname"], "KONE")

    def test_pc_telemetry_is_bound_to_canonical_kone_node(self):
        pc = {"gpu": {"utilization_pct": 46}, "memory": {"status": "OK"}, "disk": {"status": "OK"}}
        topology = {
            "status": "OK",
            "local_node_id": "kone-gpu-desktop",
            "local_observed_hostname": "KONE",
            "nodes": {
                "kone-gpu-desktop": {
                    "display_name": "KONE GPU desktop",
                    "user_alias": "GPU machine",
                    "route_label": "windows",
                    "machine_class": "desktop",
                    "os_family": "windows",
                    "gpu": "NVIDIA GeForce GTX 1660 SUPER",
                },
                "omen-linux-laptop": {
                    "display_name": "OMEN Linux laptop",
                    "user_alias": "laptop",
                    "route_label": "omen",
                    "machine_class": "laptop",
                    "os_family": "linux",
                    "gpu": "NVIDIA GeForce GTX 1070 with Max-Q Design",
                },
            },
        }
        bound = _bind_pc_node_identity(pc, topology)
        self.assertEqual(bound["node_identity"]["status"], "VERIFIED_CANONICAL")
        self.assertEqual(bound["node_identity"]["node_id"], "kone-gpu-desktop")
        self.assertEqual(bound["node_identity"]["user_alias"], "GPU machine")
        self.assertEqual(bound["node_identity"]["machine_class"], "desktop")
        self.assertEqual(bound["gpu"]["utilization_pct"], 46)
        self.assertNotEqual(bound["node_identity"]["node_id"], "omen-linux-laptop")

    def test_bootstrap_glance_surfaces_execution_nodes_and_binds_local_pc(self):
        execution_nodes = {
            "authority": "CANONICAL_EXECUTION_NODE_IDENTITY",
            "available": True,
            "status": "OK",
            "local_observed_hostname": "KONE",
            "local_node_id": "kone-gpu-desktop",
            "nodes": {
                "kone-gpu-desktop": {
                    "display_name": "KONE GPU desktop", "user_alias": "GPU machine",
                    "route_label": "windows", "machine_class": "desktop", "os_family": "windows",
                    "gpu": "NVIDIA GeForce GTX 1660 SUPER",
                },
                "omen-linux-laptop": {
                    "display_name": "OMEN Linux laptop", "user_alias": "laptop",
                    "route_label": "omen", "machine_class": "laptop", "os_family": "linux",
                    "gpu": "NVIDIA GeForce GTX 1070 with Max-Q Design",
                },
            },
        }
        pc = {"disk": {"status": "OK", "free_gb": 100.0, "trend": {}}, "memory": {"status": "OK"}, "gpu": {"utilization_pct": 46}}
        workers = {"available": True}
        live_swarm = {"available": True, "summary": {"recent_callers": 0, "lanes": 0, "busy_owners": 0}, "evidence": {"activity_window_seconds": 300, "observation_window_complete": True, "source_age_seconds": 0.0}, "lanes": []}
        mcp = {"available": True, "status": "LIVE", "active_session_count": 0, "active_session_count_status": "COMPLETE", "workspace_counts": {}}
        with patch("tools.stack_atlas._bootstrap_execution_node_topology", return_value=execution_nodes),              patch("tools.stack_atlas._bootstrap_pc_status", return_value=pc),              patch("tools.stack_atlas._bootstrap_worker_status", return_value=workers),              patch("tools.stack_atlas.build_live_swarm_snapshot", return_value=live_swarm),              patch("tools.stack_atlas._bootstrap_memory_overview", return_value={}),              patch("tools.stack_atlas._bootstrap_vault_status", return_value={"status": "OK"}),              patch("tools.stack_atlas._bootstrap_github_status", return_value={"status": "OK"}),              patch("tools.stack_atlas._bootstrap_source_freshness", return_value={}),              patch("tools.stack_atlas._bootstrap_mcp_from_live_swarm", return_value=mcp),              patch("tools.stack_atlas._bootstrap_mcp_recovery_state", return_value={}),              patch("tools.stack_atlas._bootstrap_swarm_topology", return_value={"authority": "USER_EXPLICIT_TOPOLOGY_AND_OPERATOR_HANDOFF"}):
            glance = build_live_bootstrap_glance()
        self.assertEqual(glance["swarm_topology"]["execution_nodes"]["local_node_id"], "kone-gpu-desktop")
        self.assertEqual(glance["swarm_topology"]["execution_nodes"]["nodes"]["omen-linux-laptop"]["user_alias"], "laptop")
        self.assertEqual(glance["pc"]["node_identity"]["node_id"], "kone-gpu-desktop")
        self.assertEqual(glance["pc"]["node_identity"]["user_alias"], "GPU machine")
        self.assertEqual(glance["pc"]["node_identity"]["machine_class"], "desktop")
        self.assertEqual(glance["pc"]["gpu"]["utilization_pct"], 46)
        self.assertLessEqual(len(json.dumps(glance, separators=(",", ":")).encode("utf-8")), BOOTSTRAP_GLANCE_MAX_BYTES)

    def test_bootstrap_swarm_topology_includes_manual_population_and_primary_s2_handoff(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract = root / "04 Operating Contracts" / "chatgpt-swarm-topology.json"
            contract.parent.mkdir(parents=True)
            contract.write_text(json.dumps({
                "authority": "USER_EXPLICIT_TOPOLOGY_AND_OPERATOR_HANDOFF",
                "subscriptions": {
                    "S1": {"recurring_worker_slots": 5, "operator_control": "DEGRADED_TEMPORARILY"},
                    "S2": {"recurring_worker_slots": 5, "operator_control": "PRIMARY"},
                },
                "recurring_worker_partition_rule": "Five recurring scheduler workers per ChatGPT subscription partition; no cross-partition sibling administration.",
                "manual_workers": {
                    "population": "SEPARATE_ON_DEMAND",
                    "counts_against_recurring_slots": False,
                    "total_swarm_semantics": "10 recurring workers plus any concurrently active manual/on-demand workers",
                },
                "handoff": {"primary_operator_subscription": "S2"},
            }), encoding="utf-8")
            manual_root = root / "worker-reports" / "manual" / "current"
            manual_root.mkdir(parents=True)
            now = datetime(2026, 9, 7, 16, 30, tzinfo=timezone.utc)
            with patch("tools.stack_atlas.ATLAS_LIVE_ROOT", root):
                topology = _bootstrap_swarm_topology(now)

        self.assertEqual(topology["chatgpt_subscription_count"], 2)
        self.assertEqual(topology["recurring_worker_partitions"], {"S1": 5, "S2": 5})
        self.assertEqual(topology["recurring_workers_total"], 10)
        self.assertEqual(topology["operator_handoff"]["primary_operator_subscription"], "S2")
        self.assertEqual(topology["routine_recurring_recovery"]["scheduler_role"], "RECURRENCE_ONLY")
        self.assertEqual(
            topology["routine_recurring_recovery"]["authority"],
            "DISTRIBUTED_SAME_PARTITION_WORKERS_AND_SUPERVISING_CHAT",
        )
        self.assertFalse(topology["manual_workers"]["counts_against_recurring_slots"])
        self.assertIn("10 recurring workers plus", topology["manual_workers"]["total_swarm_semantics"])

    def test_recurring_worker_recovery_is_peer_supervised_and_scheduler_is_recurrence_only(self):
        topology = component_details("swarm_topology")
        workers = component_details("execution_workers")
        scheduler = component_details("chatgpt_automations")

        self.assertIn("same-partition recurring workers", topology["supervisor"])
        self.assertIn("chatgpt_automations", topology["dependents"])
        self.assertNotIn("scheduler", topology["dependents"])
        self.assertIn("peer", topology["self_heal"])
        self.assertIn("BusyCoordinator is exact mutation collision control only", workers["supervisor"])
        self.assertNotIn("BusyCoordinator ownership", workers["supervisor"])
        self.assertIn("does not supervise worker health", scheduler["supervisor"])
        self.assertEqual(scheduler["self_heal"], "not_swarm_supervision")
        self.assertTrue(any("worker_recovery_guard.py" in route for route in topology["independent_recovery"]))
        self.assertTrue(any("worker_recovery_guard" in route for route in scheduler["independent_recovery"]))

        timed = find_features("timed runs", limit=5)
        match = next(item for item in timed if item["id"] == "worker.swarm_topology")
        self.assertIn("scheduler provides recurrence only", match["boundary"])
        self.assertIn("user is not the worker supervisor", match["boundary"])

    def test_fleet_watch_models_two_five_worker_subscription_partitions_and_scopes_recovery(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "worker-reports" / "current"
            current.mkdir(parents=True)
            now = datetime(2026, 9, 7, 16, 30, tzinfo=timezone.utc)
            s2_workers = CANONICAL_RECURRING_WORKER_PARTITIONS["S2"]
            missing_s2_id = s2_workers[0][0]
            acting_s2_id = s2_workers[1][0]
            for worker_id, label in CANONICAL_RECURRING_WORKERS:
                if worker_id == missing_s2_id:
                    continue
                started = now - timedelta(minutes=20)
                (current / f"{worker_id}.md").write_text(
                    f"automation_id: {worker_id}\n"
                    f"display_label: {label}\n"
                    f"started_at: {started.isoformat()}\n"
                    f"last_activity_at: {started.isoformat()}\n"
                    f"state: RUN_FINISHED\n",
                    encoding="utf-8",
                )
            with patch("tools.stack_atlas.ATLAS_LIVE_ROOT", root):
                global_watch = _bootstrap_fleet_watch(now)
                s2_watch = _bootstrap_fleet_watch(now, worker_id=acting_s2_id)

        self.assertEqual(len(CANONICAL_RECURRING_WORKER_PARTITIONS), 2)
        self.assertEqual({name: len(workers) for name, workers in CANONICAL_RECURRING_WORKER_PARTITIONS.items()}, {"S1": 5, "S2": 5})
        self.assertEqual(global_watch["subscription_count"], 2)
        self.assertEqual(global_watch["expected_recurring_workers"], 10)
        self.assertEqual(global_watch["expected_recurring_workers_total"], 10)
        self.assertEqual(global_watch["worker_partitions"]["S1"]["expected_recurring_workers"], 5)
        self.assertEqual(global_watch["worker_partitions"]["S2"]["expected_recurring_workers"], 5)
        self.assertEqual(s2_watch["subscription_scope"], "S2")
        self.assertEqual(s2_watch["expected_recurring_workers"], 5)
        self.assertEqual(s2_watch["expected_recurring_workers_total"], 10)
        self.assertEqual(s2_watch["recovery_candidate_count"], 1)
        self.assertEqual(s2_watch["recovery_candidates"][0]["automation_id"], missing_s2_id)
        self.assertEqual(s2_watch["recovery_candidates"][0]["subscription_partition"], "S2")

    def test_fleet_watch_does_not_recover_new_worker_before_first_expected_start_plus_grace(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "worker-reports" / "current"
            current.mkdir(parents=True)
            contract = root / "04 Operating Contracts" / "chatgpt-swarm-topology.json"
            contract.parent.mkdir(parents=True)
            now = datetime(2026, 9, 7, 16, 35, tzinfo=timezone.utc)
            target_id, target_label = CANONICAL_RECURRING_WORKER_PARTITIONS["S2"][0]
            actor_id, _ = CANONICAL_RECURRING_WORKER_PARTITIONS["S2"][1]
            first_expected = now + timedelta(minutes=1)
            contract.write_text(json.dumps({
                "subscriptions": {
                    "S2": {
                        "workers": [{
                            "automation_id": target_id,
                            "label": target_label,
                            "first_expected_start_at": first_expected.isoformat(),
                        }]
                    }
                }
            }), encoding="utf-8")
            for worker_id, label in CANONICAL_RECURRING_WORKER_PARTITIONS["S2"]:
                if worker_id == target_id:
                    continue
                started = now - timedelta(minutes=20)
                (current / f"{worker_id}.md").write_text(
                    f"automation_id: {worker_id}\n"
                    f"display_label: {label}\n"
                    f"started_at: {started.isoformat()}\n"
                    f"last_activity_at: {started.isoformat()}\n"
                    f"state: RUN_FINISHED\n",
                    encoding="utf-8",
                )
            with patch("tools.stack_atlas.ATLAS_LIVE_ROOT", root):
                pending = _bootstrap_fleet_watch(now, worker_id=actor_id)
                degraded = _bootstrap_fleet_watch(first_expected + timedelta(minutes=11), worker_id=actor_id)

        pending_target = next(item for item in pending.get("suspect_workers", []) if item.get("automation_id") == target_id) if any(item.get("automation_id") == target_id for item in pending.get("suspect_workers", [])) else None
        self.assertIsNone(pending_target)
        self.assertEqual(pending["first_start_pending"], 1)
        self.assertEqual(pending["recovery_candidate_count"], 0)
        degraded_target = next(item for item in degraded["suspect_workers"] if item["automation_id"] == target_id)
        self.assertEqual(degraded_target["reason"], "NO_LOCAL_START_EVIDENCE")
        self.assertTrue(degraded_target["recovery_actionable"])

    def test_fleet_watch_running_without_start_receipt_uses_short_race_grace_then_flags_recovery(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "worker-reports" / "current"
            current.mkdir(parents=True)
            now = datetime(2026, 9, 7, 3, 30, tzinfo=timezone.utc)
            target_id, _ = CANONICAL_RECURRING_WORKERS[0]
            for worker_id, label in CANONICAL_RECURRING_WORKERS:
                started = now - timedelta(minutes=1 if worker_id == target_id else 20)
                state = "RUNNING" if worker_id == target_id else "RUN_FINISHED"
                (current / f"{worker_id}.md").write_text(
                    f"automation_id: {worker_id}\n"
                    f"display_label: {label}\n"
                    f"started_at: {started.isoformat()}\n"
                    f"last_activity_at: {started.isoformat()}\n"
                    f"state: {state}\n",
                    encoding="utf-8",
                )
            with patch("tools.stack_atlas.ATLAS_LIVE_ROOT", root):
                pending = _bootstrap_fleet_watch(now)
                degraded = _bootstrap_fleet_watch(now + timedelta(minutes=2))

        self.assertEqual(pending["status"], "CURRENT_LOCAL_EVIDENCE")
        self.assertEqual(pending["start_receipt_pending"], 1)
        self.assertEqual(pending["running_without_start_receipt"], 0)
        self.assertEqual(pending["recovery_candidate_count"], 0)
        suspect = next(item for item in degraded["suspect_workers"] if item["automation_id"] == target_id)
        self.assertEqual(suspect["reason"], "RUNNING_WITHOUT_START_RECEIPT")
        self.assertEqual(suspect["recovery_status"], "RECOVERY_NEEDED")
        self.assertTrue(suspect["recovery_actionable"])
        self.assertEqual(degraded["running_without_start_receipt"], 1)
        self.assertEqual(degraded["recovery_candidate_count"], 1)
        self.assertEqual(degraded["scheduler_probe"], "not_performed")

    def test_fleet_watch_suppresses_duplicate_reenable_after_recent_worker_success(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "worker-reports" / "current"
            current.mkdir(parents=True)
            now = datetime.now(timezone.utc)
            stale_id, stale_label = CANONICAL_RECURRING_WORKERS[0]
            actor_id, actor_label = CANONICAL_RECURRING_WORKERS[1]

            for worker_id, label in CANONICAL_RECURRING_WORKERS:
                age = 85 if worker_id == stale_id else 20
                started = now - timedelta(minutes=age)
                findings = ""
                if worker_id == actor_id:
                    recovered_at = now - timedelta(minutes=5)
                    findings = (
                        f"findings: Peer recovery: sibling={stale_id} action=is_enabled=true "
                        f"result=success at={recovered_at.isoformat()}; fleet-watch reason=fixture\n"
                    )
                (current / f"{worker_id}.md").write_text(
                    f"automation_id: {worker_id}\n"
                    f"display_label: {label}\n"
                    f"started_at: {started.isoformat()}\n"
                    f"last_activity_at: {started.isoformat()}\n"
                    f"state: RUN_FINISHED\n"
                    f"{findings}",
                    encoding="utf-8",
                )

            with patch("tools.stack_atlas.ATLAS_LIVE_ROOT", root):
                watch = _bootstrap_fleet_watch(now)

        suspect = next(item for item in watch["suspect_workers"] if item["automation_id"] == stale_id)
        self.assertEqual(suspect["recovery_status"], "RECOVERY_PENDING")
        self.assertFalse(suspect["recovery_actionable"])
        self.assertEqual(suspect["last_recovery"]["actor_id"], actor_id)
        self.assertEqual(watch["recovery_candidate_count"], 0)
        self.assertEqual(watch["recovery_candidates"], [])
        self.assertEqual(watch["scheduler_probe"], "not_performed")

    def test_fleet_watch_accepts_pre_token_success_finding_for_cooldown(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "worker-reports" / "current"
            current.mkdir(parents=True)
            now = datetime.now(timezone.utc)
            stale_id, stale_label = CANONICAL_RECURRING_WORKERS[0]
            actor_id, actor_label = CANONICAL_RECURRING_WORKERS[1]

            for worker_id, label in CANONICAL_RECURRING_WORKERS:
                age = 85 if worker_id == stale_id else 20
                started = now - timedelta(minutes=age)
                findings = ""
                if worker_id == actor_id:
                    findings = (
                        f"findings: Peer recovery: re-enabled canonical sibling {stale_label} ({stale_id}) "
                        "after fleet-watch reported MISSED_EXPECTED_HOURLY_CADENCE; "
                        "targeted is_enabled=true succeeded with prompt/title/schedule/timezone preserved.\n"
                    )
                (current / f"{worker_id}.md").write_text(
                    f"automation_id: {worker_id}\n"
                    f"display_label: {label}\n"
                    f"started_at: {started.isoformat()}\n"
                    f"last_activity_at: {(now - timedelta(minutes=5)).isoformat()}\n"
                    f"state: RUN_FINISHED\n"
                    f"{findings}",
                    encoding="utf-8",
                )

            with patch("tools.stack_atlas.ATLAS_LIVE_ROOT", root):
                watch = _bootstrap_fleet_watch(now)

        suspect = next(item for item in watch["suspect_workers"] if item["automation_id"] == stale_id)
        self.assertEqual(suspect["recovery_status"], "RECOVERY_PENDING")
        self.assertEqual(suspect["last_recovery"]["actor_id"], actor_id)
        self.assertEqual(suspect["last_recovery"]["recovered_at"], (now - timedelta(minutes=20)).isoformat())
        self.assertEqual(watch["recovery_candidate_count"], 0)

    def test_fleet_watch_retries_after_recovered_worker_misses_next_observed_hourly_phase(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "worker-reports" / "current"
            current.mkdir(parents=True)
            now = datetime(2026, 9, 7, 3, 26, tzinfo=timezone.utc)
            stale_id, stale_label = CANONICAL_RECURRING_WORKERS[0]
            actor_id, actor_label = CANONICAL_RECURRING_WORKERS[1]
            stale_started = datetime(2026, 9, 7, 1, 15, tzinfo=timezone.utc)
            recovered_at = datetime(2026, 9, 7, 3, 10, tzinfo=timezone.utc)
            for worker_id, label in CANONICAL_RECURRING_WORKERS:
                started = stale_started if worker_id == stale_id else now - timedelta(minutes=20)
                findings = ""
                if worker_id == actor_id:
                    findings = (
                        f"findings: Peer recovery: sibling={stale_id} action=is_enabled=true "
                        f"result=success at={recovered_at.isoformat()}\n"
                    )
                (current / f"{worker_id}.md").write_text(
                    f"automation_id: {worker_id}\n"
                    f"display_label: {label}\n"
                    f"started_at: {started.isoformat()}\n"
                    f"last_activity_at: {started.isoformat()}\n"
                    f"state: RUN_FINISHED\n"
                    f"{findings}",
                    encoding="utf-8",
                )
            with patch("tools.stack_atlas.ATLAS_LIVE_ROOT", root):
                watch = _bootstrap_fleet_watch(now)

        suspect = next(item for item in watch["suspect_workers"] if item["automation_id"] == stale_id)
        self.assertEqual(suspect["recovery_status"], "RECOVERY_RETRY_NEEDED")
        self.assertTrue(suspect["recovery_actionable"])
        self.assertEqual(
            suspect["recovery_pending_until"],
            datetime(2026, 9, 7, 3, 25, tzinfo=timezone.utc).isoformat(),
        )
        self.assertEqual(watch["recovery_candidate_count"], 1)

    def test_fleet_watch_old_recovery_does_not_suppress_newer_start_then_later_miss(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "worker-reports" / "current"
            current.mkdir(parents=True)
            now = datetime(2026, 9, 7, 5, 30, tzinfo=timezone.utc)
            stale_id, stale_label = CANONICAL_RECURRING_WORKERS[0]
            actor_id, actor_label = CANONICAL_RECURRING_WORKERS[1]
            recovered_at = datetime(2026, 9, 7, 3, 10, tzinfo=timezone.utc)
            newer_start = datetime(2026, 9, 7, 4, 15, tzinfo=timezone.utc)
            for worker_id, label in CANONICAL_RECURRING_WORKERS:
                started = newer_start if worker_id == stale_id else now - timedelta(minutes=20)
                findings = ""
                if worker_id == actor_id:
                    findings = (
                        f"findings: Peer recovery: sibling={stale_id} action=is_enabled=true "
                        f"result=success at={recovered_at.isoformat()}\n"
                    )
                (current / f"{worker_id}.md").write_text(
                    f"automation_id: {worker_id}\n"
                    f"display_label: {label}\n"
                    f"started_at: {started.isoformat()}\n"
                    f"last_activity_at: {started.isoformat()}\n"
                    f"state: RUN_FINISHED\n"
                    f"{findings}",
                    encoding="utf-8",
                )
            with patch("tools.stack_atlas.ATLAS_LIVE_ROOT", root):
                watch = _bootstrap_fleet_watch(now)

        suspect = next(item for item in watch["suspect_workers"] if item["automation_id"] == stale_id)
        self.assertEqual(suspect["recovery_status"], "RECOVERY_NEEDED")
        self.assertTrue(suspect["recovery_actionable"])
        self.assertNotIn("last_recovery", suspect)
        self.assertEqual(watch["recovery_candidate_count"], 1)


    def test_worker_status_reads_live_timed_metrics_without_history_or_timeline_scan(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source_root = root / "source"
            live_root = root / "live"
            source_root.mkdir()
            metrics = live_root / "worker-reports" / "metrics.json"
            metrics.parent.mkdir(parents=True)
            now = datetime.now(timezone.utc)
            latest = [
                {
                    "automation_id": CANONICAL_RECURRING_WORKERS[index][0], "display_label": CANONICAL_RECURRING_WORKERS[index][1],
                    "finished_at": now.isoformat(), "duration_minutes": 20.0 + index,
                    "target_utilization_pct": 83.3 + index,
                }
                for index in range(5)
            ]
            metrics.write_text(json.dumps({
                "schema": "worker-report-metrics.v1", "population": "timed",
                "generated_at": now.isoformat(), "window_hours": 24.0, "latest_reports": latest,
            }), encoding="utf-8")
            stale_timeline = live_root / ".state" / "timeline" / "bootstrap-memory-overview.json"
            stale_timeline.parent.mkdir(parents=True)
            stale_timeline.write_text(json.dumps({
                "generated_at": "2026-09-06T12:00:00+00:00",
                "workers": {"archive_sample": {"sampled_worker_count": 1}},
            }), encoding="utf-8")
            with patch("tools.stack_atlas.ROOT", source_root), patch("tools.stack_atlas.ATLAS_LIVE_ROOT", live_root), patch(
                "tools.worker_report_history.load_history_metadata", side_effect=AssertionError("bootstrap must not scan worker history")
            ) as load_history:
                workers = _bootstrap_worker_status()
            load_history.assert_not_called()
            self.assertTrue(workers["available"])
            self.assertEqual(workers["status"], "CURRENT")
            self.assertEqual(workers["read_mode"], "DIRECT_METRICS")
            self.assertEqual(workers["archive_sample"]["sampled_worker_count"], 5)
            self.assertEqual(workers["archive_sample"]["selection"], "five_most_recent_latest_timed_archives_from_live_metrics")
            self.assertEqual(workers["generated_at"], now.isoformat())
            self.assertEqual(Path(workers["projection_path"]), metrics)
            self.assertIn("historical context only", workers["historical_timeline_semantics"])

    def test_worker_direct_metrics_preserve_archived_quality_not_liveness_semantics(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            metrics = root / "worker-reports" / "metrics.json"
            metrics.parent.mkdir(parents=True)
            now = datetime.now(timezone.utc)
            metrics.write_text(json.dumps({
                "schema": "worker-report-metrics.v1", "population": "timed",
                "generated_at": now.isoformat(), "window_hours": 24.0,
                "latest_reports": [
                    {"automation_id": CANONICAL_RECURRING_WORKERS[0][0], "display_label": "Recent", "finished_at": (now - timedelta(minutes=30)).isoformat(), "duration_minutes": 12.0, "target_utilization_pct": 50.0},
                    {"automation_id": CANONICAL_RECURRING_WORKERS[1][0], "display_label": "Stale", "finished_at": (now - timedelta(minutes=120)).isoformat(), "duration_minutes": 4.0, "target_utilization_pct": 16.7},
                ],
            }), encoding="utf-8")
            with patch("tools.stack_atlas.ATLAS_LIVE_ROOT", root):
                workers = _bootstrap_worker_status()
        self.assertEqual(workers["evidence_semantics"], "current_archived_timed_run_quality_not_process_liveness_or_scheduler_membership")
        self.assertEqual(workers["attention"][0]["worker"], "Recent")
        self.assertEqual(workers["stale_reports"][0]["worker"], "Stale")

    def test_worker_status_missing_live_metrics_fails_closed_without_history_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("tools.stack_atlas.ATLAS_LIVE_ROOT", root), patch(
                "tools.worker_report_history.load_history_metadata", side_effect=AssertionError("missing metrics must not trigger history scan")
            ) as load_history:
                workers = _bootstrap_worker_status()
            load_history.assert_not_called()
        self.assertFalse(workers["available"])
        self.assertEqual(workers["status"], "MISSING")
        self.assertEqual(workers["read_mode"], "DIRECT_METRICS")
        self.assertNotIn("refresh_command", workers)

    def test_manual_current_diagnostic_surfaces_recent_running_purpose_without_claiming_liveness(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manual_current = root / "worker-reports" / "manual" / "current"
            manual_current.mkdir(parents=True)
            now = datetime.now(timezone.utc)

            def write_report(run_id: str, label: str, state: str, activity: datetime, scope: str) -> Path:
                report = manual_current / f"{run_id}.md"
                report.write_text(
                    "\n".join([
                        f"run_id: {run_id}", f"display_label: {label}",
                        f"started_at: {(activity - timedelta(minutes=1)).isoformat()}",
                        f"last_activity_at: {activity.isoformat()}", r"repo: C:\repo",
                        f"scope: {scope}", f"state: {state}", "outcome: in progress",
                        "mutation: none", "validation: none", "remaining_gate: continue",
                        "finding_tags: none", "findings: none", "",
                    ]), encoding="utf-8",
                )
                ts = activity.timestamp(); os.utime(report, (ts, ts)); return report

            write_report("manual-a", "Head Auditor continuation", "RUNNING", now - timedelta(minutes=1), "audit current stack")
            write_report("manual-b", "P3 worker-population blindness audit", "RUNNING", now - timedelta(minutes=2), "audit worker population")
            write_report("manual-stale", "Stale audit", "RUNNING", now - timedelta(minutes=45), "old audit")
            write_report("manual-finished", "Finished audit", "RUN_FINISHED", now - timedelta(minutes=1), "finished audit")
            malformed = write_report("manual-malformed", "Malformed audit", "RUNNING", now - timedelta(minutes=1), "bad timestamp")
            malformed.write_text(malformed.read_text(encoding="utf-8").replace(
                f"last_activity_at: {(now - timedelta(minutes=1)).isoformat()}", "last_activity_at: 2026-09-06T00.15.18+03:00"
            ), encoding="utf-8")
            with patch("tools.stack_atlas.ATLAS_LIVE_ROOT", root):
                manual = _bootstrap_manual_current_status(now)

        self.assertTrue(manual["available"])
        self.assertEqual(manual["running_reports_in_scan"], 3)
        self.assertEqual(manual["recent_running_report_count"], 2)
        self.assertEqual(manual["recent_running_report_count_status"], "COMPLETE")
        self.assertEqual([item["display_label"] for item in manual["recent_running_reports"]], ["Head Auditor continuation", "P3 worker-population blindness audit"])
        self.assertNotIn("Stale audit", json.dumps(manual))
        self.assertEqual(manual["malformed_running_reports_in_scan"], 1)
        self.assertIn("not_process_liveness", manual["evidence_semantics"])

    def test_manual_recent_count_is_complete_when_scan_cap_reaches_stale_mtime(self):
        from datetime import datetime, timedelta, timezone
        from tools.stack_atlas import BOOTSTRAP_MANUAL_CURRENT_SCAN_LIMIT, _bootstrap_manual_current_status

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "worker-reports" / "manual" / "current"
            current.mkdir(parents=True)
            now = datetime.now(timezone.utc)

            def write_report(run_id: str, state: str, activity: datetime) -> None:
                report = current / f"{run_id}.md"
                report.write_text(
                    "\n".join([
                        f"run_id: {run_id}",
                        f"last_activity_at: {activity.isoformat()}",
                        r"repo: C:\repo",
                        "scope: bounded freshness test",
                        f"state: {state}",
                        "",
                    ]),
                    encoding="utf-8",
                )
                ts = activity.timestamp()
                os.utime(report, (ts, ts))

            write_report("manual-recent", "RUNNING", now - timedelta(minutes=1))
            for index in range(BOOTSTRAP_MANUAL_CURRENT_SCAN_LIMIT):
                write_report(
                    f"manual-old-{index:03d}",
                    "RUN_FINISHED",
                    now - timedelta(minutes=60, seconds=index),
                )

            with patch("tools.stack_atlas.ATLAS_LIVE_ROOT", root):
                manual = _bootstrap_manual_current_status(now)

        self.assertEqual(manual["current_report_file_count"], BOOTSTRAP_MANUAL_CURRENT_SCAN_LIMIT + 1)
        self.assertEqual(manual["scanned_report_file_count"], BOOTSTRAP_MANUAL_CURRENT_SCAN_LIMIT)
        self.assertTrue(manual["scan_truncated"])
        self.assertTrue(manual["recent_scan_cutoff_reached"])
        self.assertEqual(manual["recent_running_report_count"], 1)
        self.assertEqual(manual["recent_running_report_count_status"], "COMPLETE")

    def test_manual_recent_count_stays_lower_bound_when_scan_cap_is_all_recent(self):
        from datetime import datetime, timedelta, timezone
        from tools.stack_atlas import BOOTSTRAP_MANUAL_CURRENT_SCAN_LIMIT, _bootstrap_manual_current_status

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "worker-reports" / "manual" / "current"
            current.mkdir(parents=True)
            now = datetime.now(timezone.utc)

            for index in range(BOOTSTRAP_MANUAL_CURRENT_SCAN_LIMIT + 1):
                run_id = f"manual-recent-{index:03d}"
                activity = now - timedelta(seconds=index)
                report = current / f"{run_id}.md"
                report.write_text(
                    "\n".join([
                        f"run_id: {run_id}",
                        f"last_activity_at: {activity.isoformat()}",
                        r"repo: C:\repo",
                        "scope: bounded freshness test",
                        "state: RUNNING",
                        "",
                    ]),
                    encoding="utf-8",
                )
                ts = activity.timestamp()
                os.utime(report, (ts, ts))

            with patch("tools.stack_atlas.ATLAS_LIVE_ROOT", root):
                manual = _bootstrap_manual_current_status(now)

        self.assertTrue(manual["scan_truncated"])
        self.assertFalse(manual["recent_scan_cutoff_reached"])
        self.assertEqual(manual["recent_running_report_count"], BOOTSTRAP_MANUAL_CURRENT_SCAN_LIMIT)
        self.assertEqual(manual["recent_running_report_count_status"], "LOWER_BOUND")

    def test_direct_worker_metrics_are_not_presented_as_current_scheduler_fleet(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            metrics = root / "worker-reports" / "metrics.json"
            metrics.parent.mkdir(parents=True)
            now = datetime.now(timezone.utc)
            metrics.write_text(json.dumps({
                "schema": "worker-report-metrics.v1", "population": "timed",
                "generated_at": now.isoformat(), "window_hours": 24.0,
                "latest_reports": [
                    {"automation_id": CANONICAL_RECURRING_WORKERS[index][0], "display_label": CANONICAL_RECURRING_WORKERS[index][1], "finished_at": now.isoformat(), "duration_minutes": 20.0, "target_utilization_pct": 83.3}
                    for index in range(5)
                ],
            }), encoding="utf-8")
            with patch("tools.stack_atlas.ATLAS_LIVE_ROOT", root):
                workers = _bootstrap_worker_status()
        self.assertNotIn("fleet", workers)
        self.assertFalse(workers["current_scheduler_membership"]["available"])
        self.assertEqual(workers["current_scheduler_membership"]["authority"], "ChatGPT Automations state")
        self.assertEqual(workers["archive_sample"]["worker_ids_in_metrics_sample"], 5)
        self.assertEqual(workers["archive_sample"]["sampled_worker_count"], 5)
        self.assertEqual(workers["archive_sample"]["selection"], "five_most_recent_latest_timed_archives_from_live_metrics")

    def test_disk_trend_can_report_approx_24h_loss(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "observations.jsonl"
            now = datetime.now(timezone.utc)
            rows = [
                {"at": (now - timedelta(hours=24)).isoformat(), "free_gb": 115.0},
                {"at": (now - timedelta(hours=2)).isoformat(), "free_gb": 70.0},
            ]
            path.write_text("\n".join(json.dumps(x) for x in rows) + "\n", encoding="utf-8")
            with patch("tools.stack_atlas.BOOTSTRAP_OBSERVATION_PATH", path):
                trend = _bootstrap_disk_trend(55.0)
            self.assertEqual(trend["previous"]["lost_gb"], 15.0)
            self.assertEqual(trend["approx_24h"]["lost_gb"], 60.0)

    def test_disk_trend_persists_rich_scalar_machine_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "observations.jsonl"
            with patch("tools.stack_atlas.BOOTSTRAP_OBSERVATION_PATH", path):
                _bootstrap_disk_trend(60.25, observation={
                    "disk_used_gb": 415.1, "commit_headroom_gb": 39.1,
                    "physical_free_gb": 1.4, "vram_free_mb": 5086,
                    "gpu_sample_status": "LIVE", "nested": {"must": "not persist"},
                })
            row = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
            self.assertEqual(row["free_gb"], 60.25)
            self.assertEqual(row["commit_headroom_gb"], 39.1)
            self.assertEqual(row["physical_free_gb"], 1.4)
            self.assertEqual(row["vram_free_mb"], 5086)
            self.assertEqual(row["gpu_sample_status"], "LIVE")
            self.assertNotIn("nested", row)

    def test_bootstrap_performance_observations_are_typed_throttled_and_summarized(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "observations.jsonl"
            now = datetime(2026, 9, 9, 9, 0, tzinfo=timezone.utc)
            with patch("tools.stack_atlas.BOOTSTRAP_OBSERVATION_PATH", path):
                self.assertTrue(_append_bootstrap_performance_observation({
                    "bootstrap_elapsed_ms": 100.0,
                    "source_freshness_latency_ms": 200.0,
                    "github_latency_ms": 10.0,
                    "vault_latency_ms": 50.0,
                    "live_swarm_elapsed_ms": 70.0,
                    "github_cache_used": True,
                    "github_cache_age_seconds": 3.0,
                    "source_head": "abc123",
                    "node_id": "kone-gpu-desktop",
                }, now=now))
                self.assertFalse(_append_bootstrap_performance_observation({
                    "bootstrap_elapsed_ms": 999.0,
                }, now=now + timedelta(minutes=1)))
                self.assertTrue(_append_bootstrap_performance_observation({
                    "bootstrap_elapsed_ms": 120.0,
                    "source_freshness_latency_ms": 140.0,
                    "github_latency_ms": 12.0,
                    "vault_latency_ms": 55.0,
                    "live_swarm_elapsed_ms": 80.0,
                    "github_cache_used": False,
                    "github_cache_age_seconds": 1.0,
                    "source_head": "def456",
                    "node_id": "kone-gpu-desktop",
                }, now=now + timedelta(minutes=5)))
                stats = bootstrap_performance_stats(1, now=now + timedelta(minutes=6))

            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["schema"], "stack-atlas.bootstrap-observation.v1")
            self.assertEqual(rows[0]["kind"], "bootstrap_performance")
            self.assertEqual(stats["sample_count"], 2)
            self.assertEqual(stats["metrics"]["bootstrap_elapsed_ms"]["p50"], 110.0)
            self.assertEqual(stats["metrics"]["bootstrap_elapsed_ms"]["p95"], 120.0)
            self.assertEqual(stats["github_cache"]["used_pct"], 50.0)
            self.assertTrue(stats["dimensions"]["mixed_source_heads"])
            self.assertEqual(stats["dimensions"]["node_ids"], ["kone-gpu-desktop"])

    def test_mcp_transport_tail_does_not_parse_historical_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "transport.jsonl"
            historical = [json.dumps({"event": "historical", "n": i}) for i in range(20000)]
            recent = [json.dumps({"event": "recent", "n": i}) for i in range(400)]
            path.write_text("\n".join(historical + recent) + "\n", encoding="utf-8")
            real_loads = json.loads
            with patch("tools.stack_atlas.json.loads", wraps=real_loads) as loads:
                rows = _read_jsonl_tail(path, 400)
            self.assertEqual(len(rows), 400)
            self.assertTrue(all(row["event"] == "recent" for row in rows))
            self.assertEqual(loads.call_count, 400)

    def test_mcp_status_is_compatibility_projection_over_canonical_live_swarm(self):
        from tools.stack_atlas import _bootstrap_mcp_status

        snapshot = {
            "available": True,
            "summary": {"recent_callers": 2, "workspace_counts": {"Vault": 2}},
            "evidence": {
                "transport": "MCPv4",
                "transport_source_count": 2,
                "source_age_seconds": 0.5,
                "observation_window_complete": True,
                "activity_summary": {"starts": 2, "reads": 2},
            },
            "lanes": [
                {"worktree": {"path": r"C:\work"}, "busy": [], "callers": [
                    {"caller_id": "c1", "last_activity_age_seconds": 1.0, "workspace": "Vault"},
                    {"caller_id": "c2", "last_activity_age_seconds": 2.0, "workspace": "Vault"},
                ]},
            ],
        }
        health = {"available": True, "status": "LIVE", "backend_generation": "backend-current", "pid": 4242}
        with (
            patch("tools.stack_atlas.build_live_swarm_snapshot", return_value=snapshot),
            patch("tools.stack_atlas._bootstrap_mcp_backend_health", return_value=health) as health_probe,
        ):
            status = _bootstrap_mcp_status()
        health_probe.assert_called_once_with()
        self.assertEqual(status["authority"], "live_swarm_runtime_evidence")
        self.assertEqual(status["transport"], "MCPv4")
        self.assertEqual(status["transport_source_count"], 2)
        self.assertEqual(status["active_session_count"], 2)
        self.assertEqual(status["active_session_count_status"], "COMPLETE")
        self.assertEqual(status["service_health"]["backend_generation"], "backend-current")
        self.assertEqual(status["service_health"]["pid"], 4242)

    def test_mcp_status_health_fallback_does_not_invent_caller_completeness(self):
        from tools.stack_atlas import _bootstrap_mcp_status

        snapshot = {"available": False, "summary": {"recent_callers": 0}, "evidence": {"transport": "MCPv4", "transport_source_count": 0}, "lanes": []}
        health = {"available": True, "status": "LIVE", "backend_generation": "backend-test"}
        with (
            patch("tools.stack_atlas.build_live_swarm_snapshot", return_value=snapshot),
            patch("tools.stack_atlas._bootstrap_mcp_backend_health", return_value=health),
        ):
            status = _bootstrap_mcp_status()
        self.assertTrue(status["available"])
        self.assertEqual(status["status"], "LIVE")
        self.assertEqual(status["service_health"]["backend_generation"], "backend-test")
        self.assertEqual(status["active_session_count"], 0)
        self.assertEqual(status["active_session_count_status"], "LOWER_BOUND")
        self.assertEqual(status["authority"], "live_swarm_runtime_evidence")

    def test_gpu_fast_path_uses_nvml_not_nvidia_smi_subprocess(self):
        import os
        from tools.stack_atlas import _bootstrap_pc_status
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"LOCALAPPDATA": tmp}), \
             patch("tools.stack_atlas.ctypes.WinDLL", side_effect=OSError("no nvml")), \
             patch("tools.stack_atlas.subprocess.run", side_effect=AssertionError("nvidia-smi subprocess forbidden")):
            status = _bootstrap_pc_status()
        self.assertEqual(status["gpu"]["sample_status"], "FAST_PROBE_UNAVAILABLE")

    def test_github_bootstrap_success_uses_one_api_call_and_shared_cache(self):
        import subprocess
        from tools.stack_atlas import _bootstrap_github_status
        rate_limit = {
            "resources": {
                "core": {"limit": 5000, "remaining": 4900, "used": 100, "reset": 1788650000}
            }
        }
        completed = subprocess.CompletedProcess([], 0, stdout=json.dumps(rate_limit), stderr="")
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict(os.environ, {"LOCALAPPDATA": tmp}), \
             patch("tools.stack_atlas.shutil.which", return_value=r"C:\gh.exe"), \
             patch("tools.stack_atlas.subprocess.run", return_value=completed) as run:
            first = _bootstrap_github_status()
            with patch("tools.stack_atlas.subprocess.run", side_effect=AssertionError("warm cache must not spawn gh")):
                second = _bootstrap_github_status()

        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0], [r"C:\gh.exe", "api", "rate_limit"])
        self.assertTrue(first["authenticated"])
        self.assertTrue(first["api_reachable"])
        self.assertTrue(first["available"])
        self.assertEqual(first["status"], "OK")
        self.assertFalse(first["cache"]["used"])
        self.assertTrue(second["cache"]["used"])
        self.assertEqual(second["rate_limit"]["remaining"], 4900)

    def test_github_bootstrap_prefers_gh_swarm_for_rate_limit_read(self):
        import subprocess
        from tools.stack_atlas import _bootstrap_github_status
        rate_limit = {"resources": {"core": {"limit": 5000, "remaining": 4800, "used": 200, "reset": 1788650000}}}
        completed = subprocess.CompletedProcess([], 0, stdout=json.dumps(rate_limit), stderr="")
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict(os.environ, {"LOCALAPPDATA": tmp}), \
             patch("tools.stack_atlas.shutil.which", return_value=r"C:\gh.exe"), \
             patch("tools.stack_atlas._gh_swarm_bin", return_value=r"C:\gh-swarm.exe"), \
             patch("tools.stack_atlas.subprocess.run", return_value=completed) as run:
            status = _bootstrap_github_status()
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0], [r"C:\gh-swarm.exe", "api", "rate_limit"])
        self.assertTrue(status["available"])
        self.assertEqual(status["rate_limit"]["remaining"], 4800)

    def test_github_bootstrap_falls_back_to_real_gh_after_proxy_failure(self):
        import subprocess
        from tools.stack_atlas import _bootstrap_github_status
        proxy_failure = subprocess.CompletedProcess([], 1, stdout="", stderr="proxy unavailable")
        rate_limit = {"resources": {"core": {"limit": 5000, "remaining": 4700, "used": 300, "reset": 1788650000}}}
        real_success = subprocess.CompletedProcess([], 0, stdout=json.dumps(rate_limit), stderr="")
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict(os.environ, {"LOCALAPPDATA": tmp}), \
             patch("tools.stack_atlas.shutil.which", return_value=r"C:\gh.exe"), \
             patch("tools.stack_atlas._gh_swarm_bin", return_value=r"C:\gh-swarm.exe"), \
             patch("tools.stack_atlas.subprocess.run", side_effect=[proxy_failure, real_success]) as run:
            status = _bootstrap_github_status()
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].args[0][0], r"C:\gh-swarm.exe")
        self.assertEqual(run.call_args_list[1].args[0], [r"C:\gh.exe", "api", "rate_limit"])
        self.assertTrue(status["available"])
        self.assertEqual(status["rate_limit"]["remaining"], 4700)

    def test_source_freshness_routes_graphql_read_through_gh_buffer(self):
        import subprocess
        payload = {
            "data": {
                "agents": {
                    "ref": {"target": {
                        "oid": "remote-main",
                        "agentsHistory": {"nodes": [{"oid": "agents-commit", "committedDate": "2026-09-09T00:00:00Z"}]},
                        "rulesHistory": {"nodes": [{"oid": "rules-commit", "committedDate": "2026-09-09T00:00:00Z"}]},
                    }},
                    "agentsBlob": {"oid": "agents-blob"},
                    "rulesBlob": {"oid": "rules-blob"},
                },
                "vault": {
                    "ref": {"target": {
                        "workerHistory": {"nodes": [{"oid": "worker-commit", "committedDate": "2026-09-09T00:00:00Z"}]}
                    }},
                    "workerBlob": {"oid": "worker-blob"},
                },
            }
        }
        completed = subprocess.CompletedProcess([], 0, stdout=json.dumps(payload), stderr="")
        coherent_checkout = {"coherent": True, "available": True}
        with patch("tools.stack_atlas._bootstrap_cache_read_any", return_value=(None, None)), \
             patch("tools.stack_atlas._bootstrap_cache_refresh_view", return_value=(None, False)), \
             patch("tools.stack_atlas.shutil.which", return_value=r"C:\gh.exe"), \
             patch("tools.stack_atlas._github_read_cli", return_value=completed) as read_cli, \
             patch("tools.stack_atlas._bootstrap_cache_write"), \
             patch("tools.stack_atlas._git_checkout_state", return_value=coherent_checkout), \
             patch("tools.stack_atlas._git_blob_sha_for_file", side_effect=["agents-blob", "rules-blob", "worker-blob"]), \
             patch("tools.stack_atlas._git_last_committed_at") as last_committed:
            result = _bootstrap_source_freshness()

        last_committed.assert_not_called()
        self.assertTrue(result["available"])
        self.assertFalse(result["updates_pending"])
        self.assertEqual(read_cli.call_count, 1)
        args = read_cli.call_args.args
        self.assertEqual(args[0], r"C:\gh.exe")
        self.assertEqual(args[1][:3], ["api", "graphql", "-f"])
        self.assertTrue(args[1][3].startswith("query=query {"))

    def test_github_bootstrap_auth_probe_is_failure_only_and_failure_cache_is_short(self):
        import subprocess
        from tools.stack_atlas import (
            BOOTSTRAP_GITHUB_FAILURE_CACHE_SECONDS,
            _bootstrap_github_status,
        )
        api_failure = subprocess.CompletedProcess([], 1, stdout="", stderr="api down")
        auth_ok = subprocess.CompletedProcess([], 0, stdout="github.com", stderr="")
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict(os.environ, {"LOCALAPPDATA": tmp}), \
             patch("tools.stack_atlas.shutil.which", return_value=r"C:\gh.exe"), \
             patch("tools.stack_atlas.subprocess.run", side_effect=[api_failure, auth_ok]) as run:
            status = _bootstrap_github_status()

        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].args[0], [r"C:\gh.exe", "api", "rate_limit"])
        self.assertEqual(
            run.call_args_list[1].args[0],
            [r"C:\gh.exe", "auth", "status", "--active", "--hostname", "github.com"],
        )
        self.assertTrue(status["authenticated"])
        self.assertFalse(status["api_reachable"])
        self.assertFalse(status["available"])
        self.assertEqual(status["status"], "DEGRADED")
        self.assertEqual(status["cache"]["max_age_seconds"], BOOTSTRAP_GITHUB_FAILURE_CACHE_SECONDS)

    def test_live_powershell_probe_is_bounded(self):
        completed = __import__("subprocess").CompletedProcess([], 0, stdout="[]", stderr="")
        with patch("tools.stack_atlas.subprocess.run", return_value=completed) as run:
            __import__("tools.stack_atlas", fromlist=["_powershell_json"])._powershell_json("Get-Process")
        self.assertEqual(run.call_args.kwargs["timeout"], 5)

    def test_live_powershell_probe_timeout_is_explicit(self):
        timeout = __import__("subprocess").TimeoutExpired(["powershell"], 5)
        with patch("tools.stack_atlas.subprocess.run", side_effect=timeout):
            with self.assertRaisesRegex(RuntimeError, "timed out after 5s"):
                __import__("tools.stack_atlas", fromlist=["_powershell_json"])._powershell_json("Get-Process")

    def test_bootstrap_atlas_is_small_directory_not_live_status_cache(self):
        atlas = build_bootstrap_atlas()
        self.assertEqual(atlas["schema"], "atlas.v1")
        self.assertIn("load canonical inventory before reasoning/answer/change", atlas["must"])
        self.assertIn("touched components for live proof", atlas["must"])
        self.assertIn("blocks disruption", atlas["must"])
        self.assertNotIn("live_overlay", atlas)
        self.assertEqual(atlas["find"], "find <query>")
        self.assertLess(len(json.dumps(atlas)), 12000)

    def test_work_intake_search_routes_to_existing_issue_git_and_busy_contract(self):
        result = find_features("issue first busy claim dirty handoff")[0]
        self.assertEqual(result["id"], "work.intake")
        self.assertEqual(result["owner_components"], ["agent_rules", "github", "local_git", "busy_coordinator"])
        joined = " ".join(result["entrypoints"])
        self.assertIn("matching issue/PR", joined)
        self.assertIn("continue the matching issue or create one", joined)
        self.assertIn("live git status/HEAD", joined)
        expected_busy = str(Path(os.path.expandvars(r"%LOCALAPPDATA%\BusyCoordinator\busy-python.cmd")))
        self.assertIn(expected_busy, joined)
        self.assertIn("before yielding", joined)
        self.assertIn("not a queue", result["boundary"])
        self.assertIn("collision control only", result["boundary"])

    @patch("tools.stack_atlas.subprocess.run")
    @patch("tools.stack_atlas.shutil.which", return_value="git")
    def test_git_checkout_state_reuses_status_tracking_relation(self, _which, run):
        run.return_value = type("Proc", (), {
            "returncode": 0,
            "stdout": "# branch.oid abc123\n# branch.head main\n# branch.upstream origin/main\n# branch.ab +0 -0\n",
        })()
        state = _git_checkout_state(Path(r"C:\repo"), "abc123")
        self.assertTrue(state["coherent"])
        self.assertTrue(state["head_matches_local_tracking_main"])
        self.assertEqual(state["local_tracking_main"], "abc123")
        self.assertEqual(run.call_count, 1)

    def test_git_checkout_state_distinguishes_cached_remote_from_local_tracking_main(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess = __import__("subprocess")
            subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
            path = repo / "AGENTS.md"
            path.write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "AGENTS.md"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "base"], check=True)
            base = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
            subprocess.run(["git", "-C", str(repo), "update-ref", "refs/remotes/origin/main", base], check=True)

            current = _git_checkout_state(repo, base)
            self.assertTrue(current["coherent"])
            self.assertTrue(current["head_matches_remote_main"])
            self.assertTrue(current["head_matches_local_tracking_main"])
            self.assertEqual(current["coherence_basis"], "cached_remote_exact")

            path.write_text("dirty\n", encoding="utf-8")
            dirty = _git_checkout_state(repo, base)
            self.assertFalse(dirty["coherent"])
            self.assertTrue(dirty["dirty"])
            self.assertEqual(dirty["coherence_basis"], "dirty")
            subprocess.run(["git", "-C", str(repo), "restore", "AGENTS.md"], check=True)

            path.write_text("canonical-newer\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "commit", "-qam", "canonical newer"], check=True)
            canonical_newer = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
            subprocess.run(["git", "-C", str(repo), "update-ref", "refs/remotes/origin/main", canonical_newer], check=True)

            cache_lag = _git_checkout_state(repo, base)
            self.assertTrue(cache_lag["coherent"])
            self.assertFalse(cache_lag["head_matches_remote_main"])
            self.assertTrue(cache_lag["head_matches_local_tracking_main"])
            self.assertTrue(cache_lag["cached_remote_is_ancestor_of_local"])
            self.assertTrue(cache_lag["remote_metadata_lags_local_tracking"])
            self.assertEqual(cache_lag["coherence_basis"], "local_tracking_descends_cached_remote")

            path.write_text("local-only\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "commit", "-qam", "local only"], check=True)
            local_only = _git_checkout_state(repo, base)
            self.assertFalse(local_only["coherent"])
            self.assertTrue(local_only["cached_remote_is_ancestor_of_local"])
            self.assertFalse(local_only["head_matches_local_tracking_main"])
            self.assertEqual(local_only["coherence_basis"], "local_head_differs_tracking_main")

            subprocess.run(["git", "-C", str(repo), "reset", "--hard", "-q", base], check=True)
            behind = _git_checkout_state(repo, canonical_newer)
            self.assertFalse(behind["coherent"])
            self.assertFalse(behind["head_matches_remote_main"])
            self.assertFalse(behind["head_matches_local_tracking_main"])

            subprocess.run(["git", "-C", str(repo), "switch", "-q", "-c", "local-diverge", base], check=True)
            path.write_text("diverged\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "commit", "-qam", "diverged"], check=True)
            subprocess.run(["git", "-C", str(repo), "branch", "-M", "main"], check=True)
            diverged = _git_checkout_state(repo, canonical_newer)
            self.assertFalse(diverged["coherent"])
            self.assertFalse(diverged["cached_remote_is_ancestor_of_local"])

            subprocess.run(["git", "-C", str(repo), "reset", "--hard", "-q", canonical_newer], check=True)
            subprocess.run(["git", "-C", str(repo), "switch", "-q", "-c", "feature"], check=True)
            wrong_branch = _git_checkout_state(repo, canonical_newer)
            self.assertFalse(wrong_branch["coherent"])
            self.assertTrue(wrong_branch["head_matches_remote_main"])
            self.assertEqual(wrong_branch["coherence_basis"], "wrong_branch")

    def test_source_freshness_marks_hybrid_agents_checkout_pending_even_when_policy_blobs_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agents = root / "agents"
            vault = root / "vault"
            subprocess = __import__("subprocess")
            for repo in (agents, vault):
                subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
                subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
                subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)

            for name in ("AGENTS.md", "RULES.md"):
                (agents / name).write_text(f"base-{name}\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(agents), "add", "AGENTS.md", "RULES.md"], check=True)
            subprocess.run(["git", "-C", str(agents), "commit", "-q", "-m", "base"], check=True)
            base = subprocess.check_output(["git", "-C", str(agents), "rev-parse", "HEAD"], text=True).strip()
            for name in ("AGENTS.md", "RULES.md"):
                (agents / name).write_text(f"remote-{name}\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(agents), "commit", "-qam", "remote policy"], check=True)
            remote = subprocess.check_output(["git", "-C", str(agents), "rev-parse", "HEAD"], text=True).strip()
            agents_blob = subprocess.check_output(["git", "-C", str(agents), "rev-parse", f"{remote}:AGENTS.md"], text=True).strip()
            rules_blob = subprocess.check_output(["git", "-C", str(agents), "rev-parse", f"{remote}:RULES.md"], text=True).strip()
            subprocess.run(["git", "-C", str(agents), "reset", "--hard", "-q", base], check=True)
            (agents / "AGENTS.md").write_text("remote-AGENTS.md\n", encoding="utf-8")
            (agents / "RULES.md").write_text("remote-RULES.md\n", encoding="utf-8")

            contract = vault / "04 Operating Contracts" / "fresh-worker-generation-launch.md"
            contract.parent.mkdir(parents=True)
            contract.write_text("worker contract\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(vault), "add", str(contract.relative_to(vault))], check=True)
            subprocess.run(["git", "-C", str(vault), "commit", "-q", "-m", "worker contract"], check=True)
            worker_blob = subprocess.check_output(
                ["git", "-C", str(vault), "rev-parse", "HEAD:04 Operating Contracts/fresh-worker-generation-launch.md"],
                text=True,
            ).strip()

            remote_metadata = {
                "canonical_agents_checkout": {"remote_main": remote},
                "AGENTS.md": {"remote_blob": agents_blob, "last_updated_at": "2026-09-09T00:00:00Z", "last_update_commit": remote},
                "RULES.md": {"remote_blob": rules_blob, "last_updated_at": "2026-09-09T00:00:00Z", "last_update_commit": remote},
                "worker_report_contract": {"remote_blob": worker_blob, "last_updated_at": "2026-09-09T00:00:00Z", "last_update_commit": None},
            }
            with patch("tools.stack_atlas.AGENT_RULES_ROOT", str(agents)), \
                 patch("tools.stack_atlas.ROOT", vault), \
                 patch("tools.stack_atlas._bootstrap_cache_read_any", return_value=(remote_metadata, 0.1)), \
                 patch("tools.stack_atlas._bootstrap_cache_refresh_view", return_value=(remote_metadata, False)):
                result = _bootstrap_source_freshness()

            self.assertTrue(result["available"])
            self.assertTrue(result["attention_required"])
            self.assertTrue(result["updates_pending"])
            self.assertFalse(result["canonical_checkout"]["coherent"])
            self.assertFalse(result["canonical_checkout"]["head_matches_remote_main"])
            self.assertTrue(result["canonical_checkout"]["dirty"])
            self.assertEqual(result["canonical_checkout"]["local_head"], base)
            self.assertEqual(result["canonical_checkout"]["remote_main"], remote)
            self.assertFalse(result["sources"]["AGENTS.md"]["updates_pending"])
            self.assertFalse(result["sources"]["RULES.md"]["updates_pending"])

    def test_source_freshness_pending_means_remote_is_newer(self):
        self.assertTrue(_remote_is_newer("2026-09-06T18:16:33Z", "2026-09-05T09:50:28+03:00"))
        self.assertFalse(_remote_is_newer("2026-09-05T12:36:29Z", "2026-09-06T09:50:28+03:00"))
        self.assertFalse(_remote_is_newer("bad", "2026-09-06T09:50:28+03:00"))

    def test_source_freshness_recognizes_fetched_remote_delta_already_in_dirty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess = __import__("subprocess")
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
            path = repo / "policy.md"
            path.write_text("one\nold\nthree\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "policy.md"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "base"], check=True)
            base = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
            path.write_text("one\nnew\nthree\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "commit", "-qam", "remote update"], check=True)
            remote = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
            subprocess.run(["git", "-C", str(repo), "reset", "--hard", "-q", base], check=True)

            path.write_text("local-only\none\nnew\nthree\n", encoding="utf-8")
            self.assertTrue(_git_remote_update_already_applied(repo, "policy.md", remote))

            path.write_text("local-only\none\nold\nthree\n", encoding="utf-8")
            self.assertFalse(_git_remote_update_already_applied(repo, "policy.md", remote))

    def test_source_freshness_hash_normalizes_windows_crlf_like_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.txt"
            path.write_bytes(b"one\r\ntwo\r\n")
            normalized = b"one\ntwo\n"
            import hashlib
            expected = hashlib.sha1(f"blob {len(normalized)}\0".encode("ascii") + normalized).hexdigest()
            self.assertEqual(_git_blob_sha_for_file(path), expected)

    def test_bootstrap_surfaces_behavior_source_freshness_without_reading_policy_bodies(self):
        sample = {
            "available": True,
            "attention_required": True,
            "updates_pending": True,
            "sources": {
                "AGENTS.md": {"last_updated_at": "2026-09-05T12:36:29Z", "updates_pending": False},
                "RULES.md": {"last_updated_at": "2026-09-06T18:16:33Z", "updates_pending": True},
                "worker_report_contract": {"last_updated_at": "2026-09-06T14:21:15Z", "updates_pending": False},
            },
        }
        with patch("tools.stack_atlas._bootstrap_source_freshness", return_value=sample):
            glance = build_live_bootstrap_glance()
        self.assertTrue(glance["source_freshness"]["available"])
        self.assertTrue(glance["source_freshness"]["attention_required"])
        self.assertTrue(glance["source_freshness"]["updates_pending"])
        self.assertIn("RULES.md", glance["source_freshness"]["sources"])
        self.assertTrue(glance["source_freshness"]["sources"]["RULES.md"]["updates_pending"])
        self.assertIn("worker_report_contract", glance["source_freshness"]["sources"])
        self.assertEqual(sample["sources"]["RULES.md"]["last_updated_at"], "2026-09-06T18:16:33Z")

    def test_bootstrap_points_to_canonical_issue_first_contract_without_policy_copy(self):
        with patch("tools.stack_atlas._bootstrap_pc_status", return_value={}), \
             patch("tools.stack_atlas._bootstrap_worker_status", return_value={}), \
             patch("tools.stack_atlas._bootstrap_mcp_status", return_value={}), \
             patch("tools.stack_atlas._bootstrap_memory_overview", return_value={"contract": "history only", "eligible_entries": 2, "recent": [], "projects": [{"name": "p3", "count": 2}], "recurring_tags": []}):
            glance = build_live_bootstrap_glance()
        self.assertEqual(glance["paths"]["issue_first_work_intake"], r"C:\Users\Lauri\.agents\RULES.md")
        self.assertEqual(glance["memory_overview"]["eligible_entries"], 2)
        self.assertEqual(glance["memory_overview"]["projects"][0]["name"], "p3")
        self.assertNotIn("behavior", glance)

    def test_feature_search_surfaces_existing_owner_before_archaeology(self):
        timeline = find_features("vault timeline")[0]
        self.assertEqual(timeline["id"], "vault.history")
        self.assertEqual(timeline["owner_components"], ["memory_bank"])
        self.assertIn("memory_bank.py timeline", timeline["entrypoints"])
        self.assertIn("never recursive Vault scans", timeline["boundary"])

        checkpoint = find_features("checkpoint resume")[0]
        self.assertEqual(checkpoint["id"], "coordination.checkpoint_context")
        self.assertIn("busy_coordinator", checkpoint["owner_components"])
        self.assertIn("never retained after release/recovery/expiry", checkpoint["boundary"])
        self.assertIn("never backlog", checkpoint["boundary"])

        commander = find_features("commander fallback")[0]
        self.assertEqual(commander["id"], "execution.transport")
        commander_routes = " ".join(commander["entrypoints"])
        self.assertIn("Remote Desktop Commander", commander_routes)
        self.assertIn("approved standby break-glass fallback", commander_routes)
        self.assertIn("fallback-only/not primary, not forbidden", commander_routes)
        self.assertNotIn("retired Remote Desktop Commander", commander_routes)
        self.assertIn("changed state or new evidence", commander_routes)
        self.assertIn("does not retire, obsolete, or authorize deletion", commander["boundary"])
        self.assertIn("preserve its recovery path", commander["boundary"])

        reports = find_features("worker reports")[0]
        self.assertEqual(reports["id"], "worker.reports")
        self.assertIn("worker_reports", reports["owner_components"])
        self.assertIn("PENDING_REVIEW", reports["boundary"])
        self.assertIn("reviewed.json", " ".join(component_details("worker_reports")["live_status"]))
        self.assertIn(r"C:\P3Proofs", " ".join(component_details("worker_reports")["live_status"]))
        self.assertIn("worker-reports/current/<automation-id>.md", " ".join(component_details("worker_reports")["resources"]))
        self.assertIn("history/_reports", " ".join(component_details("worker_reports")["resources"]))
        self.assertNotIn("metrics.json", " ".join(component_details("worker_reports")["resources"]))

    def test_p3_unreal_search_is_navigation_only_not_product_authority(self):
        p3 = find_features("p3 unreal")[0]
        self.assertEqual(p3["id"], "project.p3_unreal_navigation")
        self.assertEqual(p3["owner_components"], ["local_git", "github"])
        joined = " ".join(p3["entrypoints"])
        self.assertIn(r"C:\Users\Lauri\Documents\Unreal Projects\p3", joined)
        self.assertIn("p3_bridge_guard.py", joined)
        self.assertIn("Test-P3WorkerEditorPreflight.ps1", joined)
        self.assertIn("Navigation only", p3["boundary"])
        self.assertIn("P3 product direction lives in organicoverlords/agents@main", p3["boundary"])
        self.assertIn("remain implementation/runtime authority", p3["boundary"])
        self.assertIn("rather than trusting Saved/UE_MCP_Bridge/port.json alone", p3["boundary"])
        with self.assertRaises(KeyError):
            component_details("p3")
        self.assertNotIn("p3", full_inventory()["components"])

    def test_busycoordinator_literal_name_resolves_to_standalone_busy_ownership(self):
        result = find_features("BusyCoordinator")[0]
        self.assertEqual(result["id"], "coordination.ownership")
        self.assertEqual(result["owner_components"], ["busy_coordinator"])
        self.assertIn("busy-python.cmd", " ".join(result["entrypoints"]))

    def test_busy_feature_entrypoints_are_directly_executable_paths(self):
        expected = str(Path(os.path.expandvars(r"%LOCALAPPDATA%\BusyCoordinator\busy-python.cmd")))
        ownership = find_features("busy collision control")[0]
        self.assertEqual(ownership["id"], "coordination.ownership")
        self.assertTrue(ownership["entrypoints"])
        self.assertTrue(all(entry.startswith(expected) for entry in ownership["entrypoints"]))
        checkpoint = find_features("checkpoint resume")[0]
        self.assertTrue(all(entry.startswith(expected) for entry in checkpoint["entrypoints"]))
        details = component_details("busy")
        self.assertTrue(all(command.startswith(expected) for command in details["live_status"]))
        self.assertTrue(all(command.startswith(expected) for command in details["independent_recovery"]))
        self.assertIn(expected, details["canonical_sources"])
        self.assertTrue(Path(expected).exists())

    def test_feature_search_is_bounded_and_non_authoritative(self):
        self.assertEqual(find_features(""), [])
        self.assertEqual(find_features("definitely-unknown-capability"), [])
        self.assertEqual(find_features("plugin2"), [])
        results = find_features("current state", limit=2)
        self.assertLessEqual(len(results), 2)
        self.assertTrue(all(item["authority"] == ATLAS_CONTRACT["authority"] for item in results))

    def test_linux_omen_is_default_execution_target_under_shared_routing_cohort(self):
        details = component_details("linux_omen_node")
        self.assertEqual(details["role"], "primary_lan_execution_node")
        self.assertTrue(any("swarm-routing-cohort.md" in source for source in details["canonical_sources"]))
        self.assertIn("shared swarm routing cohort", details["self_heal"])
        feature = atlas_lookup("execution.linux_omen_node")
        self.assertIn("Default execution node", feature["boundary"])
        self.assertIn("saturated/unavailable", feature["boundary"])
        self.assertTrue(any("swarm_route.py route" in entry for entry in feature["entrypoints"]))

    def test_pid_is_lookup_key_not_component_identity(self):
        self.assertIn("ephemeral live lookup key", ATLAS_CONTRACT["pid_semantics"])
        self.assertIn("stable identity", ATLAS_CONTRACT["pid_semantics"])

    def test_unknown_process_is_never_disposable(self):
        processes = [{
            "pid": 4444,
            "ppid": 1,
            "name": "node.exe",
            "command_line": "node.exe unknown.js",
        }]
        result = blast_radius(4444, processes)
        self.assertEqual(result["status"], "UNRESOLVED")
        self.assertEqual(result["destructive_verdict"], "BLOCK_UNKNOWN_TOPOLOGY")
        self.assertIn("stable_component_identity", result["unknowns"])

    def test_mcp_minimal_clone_distinguishes_chatgpt_plugin_from_internal_full_profile(self):
        details = component_details("mcp_minimal_clone")
        surface = details["chatgpt_plugin_surface"]
        self.assertEqual(surface["profile"], "process")
        self.assertEqual(surface["tools"], ["start_process", "read_output", "kill_process"])
        self.assertEqual(surface["conditional_ui"]["when"], "MCP_VISUAL_PROOF_UI=1")
        self.assertEqual(surface["conditional_ui"]["tools"], ["open_visual_proof"])
        self.assertEqual(surface["conditional_ui"]["resource"], "ui://visual-proof/inline-v1.html")
        self.assertEqual(surface["conditional_ui"]["mime_type"], "text/html;profile=mcp-app")
        self.assertIn("fresh ChatGPT connector handshake", surface["conditional_ui"]["session_refresh"])
        self.assertEqual(surface["internal_only_profiles"], ["full"])
        self.assertIn("busy_list", surface["boundary"])
        self.assertIn("view_image", surface["boundary"])
        self.assertIn("open_visual_proof", surface["boundary"])
        status = " ".join(details["live_status"])
        self.assertIn("MCP_TOOL_PROFILE=process", status)
        self.assertIn("MCP_VISUAL_PROOF_UI=1", status)
        self.assertIn("open_visual_proof", status)

    def test_mcp_front_door_requires_inactive_generation_update_path(self):
        details = component_details("mcp_front_door")
        self.assertIn("inactive backend generation", " ".join(details["independent_recovery"]))
        self.assertIn("exact tool contract", " ".join(details["live_status"]))

    def test_vps_edge_process_classifies_and_blocks_disruption(self):
        process = {
            "pid": 480, "ppid": 1, "name": "python.exe",
            "command_line": r"python.exe C:\Users\Lauri\AppData\Local\McpVpsEdge\vps_mcp_reverse_tunnel.py",
        }
        result = blast_radius(480, [process])
        self.assertEqual(result["identity"]["component"], "vps_edge_ingress")
        self.assertEqual(result["destructive_verdict"], "BLOCK_ACTIVE_TRANSPORT")

    def test_vps_edge_current_topology_is_wireguard_primary_with_ssh_fallbacks(self):
        details = component_details("vps_edge_ingress")
        status = " ".join(details["live_status"])
        resources = " ".join(details["resources"])
        self.assertIn("WireGuard", status)
        self.assertIn("only 10.203.0.2:3011", status)
        self.assertIn("3101-3104", status)
        self.assertIn("explicit-recovery", status)
        self.assertIn("does not select them automatically", status)
        self.assertIn("WireGuard UDP 51820", resources)

    def test_vps_edge_monitoring_is_discoverable_and_preserves_primary_recovery_semantics(self):
        result = find_features("monitoring")[0]
        self.assertEqual(result["id"], "mcp.edge_monitoring")
        self.assertEqual(result["owner_components"], ["vps_edge_ingress"])
        self.assertIn("healthy/primary_healthy", result["boundary"])
        self.assertIn("recovery_available", result["boundary"])
        self.assertIn("wireguard_handshake_age_seconds", result["boundary"])
        self.assertTrue(any("edge-status" in item for item in result["entrypoints"]))

    def test_vps_edge_observer_lists_freshness_fields_and_deployed_owners(self):
        details = component_details("vps_edge_ingress")
        status = " ".join(details["live_status"])
        resources = " ".join(details["resources"])
        self.assertIn("primary_backend_http=200", status)
        self.assertIn("wireguard_handshake_age_seconds", status)
        self.assertIn("wireguard_peer_fresh", status)
        self.assertIn("0-180 seconds", status)
        self.assertIn("fallback_3101_http through fallback_3104_http", status)
        self.assertIn("McpVpsEdgeTunnel", status)
        self.assertIn("mcp-edge-health.service", status)
        self.assertIn("mcp-edge-health.timer", status)
        self.assertIn("/usr/local/bin/mcp-edge-health", resources)
        self.assertIn("/var/lib/mcp-edge/status.json", resources)

    def test_vps_edge_native_ssh_fallback_lane_classifies_as_transport(self):
        process = {
            "pid": 25428, "ppid": 1, "name": "ssh.exe",
            "command_line": r'"C:\Program Files\Git\usr\bin\ssh.exe" -N -T -i C:\Users\Lauri\.ssh\tietokettu_edge -R 127.0.0.1:3101:127.0.0.1:3011 root@5.61.91.127',
        }
        result = blast_radius(25428, [process])
        self.assertEqual(result["identity"]["component"], "vps_edge_ingress")
        self.assertEqual(result["destructive_verdict"], "BLOCK_ACTIVE_TRANSPORT")

    def test_vps_origin_listener_wrapper_classifies_as_minimal_clone(self):
        listener = {
            "pid": 11328, "ppid": 5376, "name": "node.exe",
            "command_line": r"node.exe dist/index.js",
        }
        launcher = {
            "pid": 5376, "ppid": 1, "name": "powershell.exe",
            "command_line": r"powershell.exe -File C:\Users\Lauri\AppData\Local\Temp\launch-mcp-vps-origin.ps1",
        }
        mapping = {item["pid"]: item for item in (listener, launcher)}
        self.assertEqual(classify_process(listener, mapping)["component"], "mcp_minimal_clone")

    def test_natural_component_aliases_resolve(self):
        self.assertEqual(component_details("mcp")["id"], "mcp_minimal_clone")
        self.assertEqual(component_details("webgpt")["id"], "chatgpt_session")
        self.assertEqual(component_details("coordinator")["id"], "busy_coordinator")
        self.assertEqual(component_details("BusyCoordinator")["id"], "busy_coordinator")
        self.assertEqual(component_details("busy coordinator")["id"], "busy_coordinator")
        self.assertEqual(component_details("webgpt")["role"], "session:user-facing")
        self.assertEqual(component_details("rules")["id"], "agent_rules")
        self.assertEqual(component_details("orchestrator")["id"], "agent_rules")
        self.assertEqual(component_details("operator")["id"], "agent_rules")
        self.assertEqual(component_details("atlas")["id"], "stack_atlas")
        self.assertEqual(component_details("stack atlas")["id"], "stack_atlas")
        atlas = component_details("stack_atlas")
        self.assertEqual(atlas["authority"], ATLAS_CONTRACT["authority"])
        self.assertIn("STACK_ATLAS_NORTH_STAR.md", " ".join(atlas["canonical_sources"]))
        self.assertIn("not a permission gate", " ".join(atlas["independent_recovery"]))
        orchestrator = find_features("orchestrator")[0]
        self.assertEqual(orchestrator["id"], "orchestration.operator")
        self.assertEqual(orchestrator["owner_components"], ["agent_rules"])
        self.assertIn("not a daemon", orchestrator["boundary"])

    def test_stack_atlas_self_lookup_and_find_are_derived_navigation(self):
        details = component_details("stack atlas")
        self.assertEqual(details["id"], "stack_atlas")
        self.assertEqual(details["authority"], "DERIVED_OPERATIONAL_VIEW_NOT_AUTHORITY")
        self.assertIn("derived", details["role"])
        self.assertTrue(any("STACK_ATLAS_NORTH_STAR.md" in source for source in details["canonical_sources"]))

        results = find_features("stack atlas north star", limit=3)
        match = next(item for item in results if item["id"] == "component.stack_atlas")
        self.assertEqual(match["owner_components"], ["stack_atlas"])
        self.assertEqual(match["authority"], ATLAS_CONTRACT["authority"])
        self.assertIn("leave Atlas and work at that owner", match["boundary"])

    def test_bootstrap_directory_covers_major_stack_surfaces(self):
        atlas = build_bootstrap_atlas()
        ids = set(__import__("tools.stack_atlas", fromlist=["COMPONENTS"]).COMPONENTS)
        expected = {
            "busy_coordinator", "mcp_front_door", "mcp_backend", "mcp_minimal_clone",
            "agent_rules", "repo_rule_pointer", "north_star", "chatgpt_memory", "memory_bank",
            "chatgpt_session", "execution_workers", "chatgpt_automations", "local_git", "github",
            "github_actions", "github_runner", "worker_reports",
        }
        self.assertTrue(expected.issubset(ids), sorted(expected - ids))
        self.assertNotIn("operator_live", ids)

    def test_tiny3d_library_navigation_exposes_showroom_and_durable_visual_proof(self):
        for alias in ("tiny3d_library", "asset_catalogue", "showroom", "visual_proof_library"):
            with self.subTest(alias=alias):
                details = atlas_lookup(alias)
                self.assertEqual(details["id"], "project.tiny3d_asset_library")
                self.assertEqual(details["kind"], "feature_navigation")
                self.assertEqual(details["workspace"], r"C:\Users\Lauri\Desktop\Tiny3D_LIBRARY")
                self.assertIn("showroom-v2-catalog-v1.json", details["catalogue_sources"]["showroom"])
                self.assertIn("p3_proof_bundles", details["proof_contract"]["bundle"])
                self.assertIn("durable_visual_proof", details["proof_contract"]["runtime_gate"])
                self.assertIn("NOT_RECORDED is not visual acceptance", details["proof_contract"]["visual_review"])
                self.assertIn("Do not recursively scan", details["boundary"])

        self.assertEqual(find_features("showroom", limit=1)[0]["id"], "project.tiny3d_asset_library")
        self.assertEqual(find_features("asset library", limit=1)[0]["id"], "project.tiny3d_asset_library")
        generic = component_details("visual proof")
        self.assertIn("not durable proof authority", generic["boundary"])
        with self.assertRaises(KeyError):
            component_details("tiny3d_library")

    def test_shared_visual_library_integration_reconciles_existing_proof_owners(self):
        for alias in ("shared_visual_library", "chatgpt_visual_library", "shared_chat_proof"):
            with self.subTest(alias=alias):
                details = atlas_lookup(alias)
                self.assertEqual(details["id"], "project.shared_visual_library_integration")
                self.assertEqual(details["kind"], "feature_navigation")
                self.assertEqual(details["related_features"]["task_history"], "vault.history")
                self.assertEqual(details["related_features"]["tiny3d_library"], "project.tiny3d_asset_library")
                self.assertEqual(details["related_features"]["p3_visual_evidence"], "project.p3_visual_evidence")
                self.assertEqual(details["related_features"]["chatgpt_library_consumer"], "first_party_google_drive_library")
                self.assertNotIn("chatgpt_plugin_surface", details["related_features"])
                self.assertEqual(details["shared_chat_display_state"], "NATIVE_GOOGLE_DRIVE_LIBRARY_OPEN_REQUIRED")
                self.assertTrue(any("memory_bank.py context" in item for item in details["entrypoints"]))
                self.assertTrue(any("lookup tiny3d_library" in item for item in details["entrypoints"]))
                self.assertTrue(any("ChatGPT Library -> connected Google Drive My Drive" in item for item in details["entrypoints"]))
                self.assertTrue(any("historical/non-canonical review lineage only" in item for item in details["entrypoints"]))
                self.assertIn("Google Drive My Drive root index", details["boundary"])
                self.assertIn("first-party connected Google Drive surface in ChatGPT Library", details["boundary"])
                self.assertIn("native Library file to open/render", details["boundary"])
                self.assertIn("consumer gate unmet", details["boundary"])
                self.assertIn("Do not substitute MCP media payloads, base64, custom HTTP, Git/LFS", details["boundary"])
                self.assertIn("historical/non-canonical transport work, not the #2809 route", details["boundary"])

        result = find_features(
            "make the library integrated so I can inspect a stored proof picture and show the same picture here",
            limit=1,
        )
        self.assertEqual(result[0]["id"], "project.shared_visual_library_integration")

    def test_generic_library_queries_do_not_route_to_tiny3d(self):
        self.assertEqual(find_features("library"), [])
        for query in ("python standard library", "music library", "book library"):
            with self.subTest(query=query):
                ids = {item["id"] for item in find_features(query)}
                self.assertNotIn("project.tiny3d_asset_library", ids)

        self.assertEqual(find_features("tiny3d library", limit=1)[0]["id"], "project.tiny3d_asset_library")
        self.assertEqual(find_features("asset library", limit=1)[0]["id"], "project.tiny3d_asset_library")

    @patch("tools.stack_atlas.project_tiny3d_current")
    def test_tiny3d_lookup_query_attaches_current_projection_in_one_bounded_lookup(self, projector):
        projector.return_value = {
            "schema": "stack-atlas.tiny3d-current.v1",
            "authority": "READ_ONLY_MATERIALIZED_TINY3D_ORIENTATION",
            "query": "android",
            "count": 1,
            "entries": [{
                "asset_id": "60c984",
                "showroom": {"state": "LINKED_MATERIALIZED_CATALOGUE"},
                "proof": {
                    "strongest_state": "TINY3D_VERIFIED",
                    "durable_visual": {"state": "NOT_DECLARED", "present": False},
                    "independent_review_state": "NOT_RECORDED",
                },
            }],
        }

        details = atlas_lookup("tiny3d_library", query="android")

        self.assertEqual(details["id"], "project.tiny3d_asset_library")
        self.assertEqual(details["current_projection"]["entries"][0]["asset_id"], "60c984")
        self.assertEqual(details["current_projection"]["entries"][0]["proof"]["strongest_state"], "TINY3D_VERIFIED")
        projector.assert_called_once_with("android", r"C:\Users\Lauri\Desktop\Tiny3D_LIBRARY", limit=8)

    @patch("tools.stack_atlas.project_tiny3d_current", side_effect=ValueError("source missing"))
    def test_tiny3d_lookup_query_fails_closed_when_current_projection_is_unavailable(self, _projector):
        details = atlas_lookup("showroom", query="android")

        current = details["current_projection"]
        self.assertEqual(current["status"], "UNKNOWN_SOURCE_UNAVAILABLE")
        self.assertIn("Fail closed", current["boundary"])
        self.assertNotIn("entries", current)

    def test_atlas_is_product_agnostic_and_product_repos_are_not_lookup_authorities(self):
        atlas = __import__("tools.stack_atlas", fromlist=["COMPONENTS"])
        self.assertIn("STACK_INFRA_MAP_ONLY", ATLAS_CONTRACT["scope"])
        self.assertFalse(hasattr(atlas, "PRODUCT_COMPONENTS"))
        self.assertFalse(hasattr(atlas, "PRODUCT_ROOTS"))
        self.assertFalse(hasattr(atlas, "PRODUCT_FLOW"))
        for product in ("lowvram", "asset_library", "tiny3d", "p3"):
            with self.subTest(product=product):
                with self.assertRaises(KeyError):
                    component_details(product)
        inventory = full_inventory()
        self.assertNotIn("product_flow", inventory)
        self.assertTrue({"lowvram", "asset_library", "tiny3d", "p3"}.isdisjoint(inventory["components"]))

    def test_generated_operational_manual_matches_atlas(self):
        manual = ROOT / "docs" / "assistant-stack-operational-atlas.md"
        self.assertEqual(manual.read_text(encoding="utf-8"), render_manual() + "\n")
        text = manual.read_text(encoding="utf-8")
        self.assertNotIn("desktop_commander", text.casefold())
        self.assertIn("### `mcp_front_door`", text)
        self.assertIn("Independent recovery", text)
        self.assertIn("Supervisor", text)
        self.assertIn("Resources", text)

    def test_vault_agents_is_pointer_only_to_canonical_rules(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(len(agents.rstrip().splitlines()), 7)
        self.assertIn(r"C:\Users\Lauri\.agents\RULES.md", agents)
        self.assertIn(r"C:\Users\Lauri\.agents\AGENTS.md", agents)
        self.assertNotIn("contexts", agents.casefold())
        self.assertIn("pointer-only", agents)
        self.assertNotIn("SHARED-AGENT-POLICY", agents)
        self.assertNotIn("### Navigation minimap", agents)

    def test_memory_bank_publishes_only_through_dedicated_memory_branch(self):
        memory = component_details("memory_bank")
        joined = " ".join([*memory["canonical_sources"], *memory["live_status"]])
        self.assertIn("origin/memory/live", joined)
        self.assertIn("forbidden publication targets", joined)

    def test_every_component_declares_its_own_live_truth_and_recovery_routes(self):
        atlas = __import__("tools.stack_atlas", fromlist=["COMPONENTS"])
        for component in atlas.COMPONENTS:
            with self.subTest(component=component):
                details = component_details(component)
                for field in ("canonical_sources", "live_status", "supervisor", "self_heal", "independent_recovery", "resources", "dependents", "runbook"):
                    self.assertIn(field, details)
                    self.assertIsNotNone(details[field])
                self.assertTrue(details["live_status"])
                self.assertTrue(details["canonical_sources"])
                if not details["runbook"]:
                    self.assertTrue(str(details.get("role") or "").startswith("context:disabled-"))
                    self.assertFalse(details["resources"])
                    self.assertFalse(details["dependents"])
                else:
                    self.assertTrue(details["runbook"])

    def test_bootstrap_case_sample_prioritizes_canonical_red_incident_over_scope_only_red_cases(self):
        report = {
            "contract": "history only",
            "eligible_entries": 20,
            "timeline_snapshots": {
                "authority": "DERIVED_HISTORY_ONLY",
                "narrative_contract": {"primary_unit": "CONTINUITY_CASE"},
                "windows": [{
                    "window": "24h",
                    "event_count": 20,
                    "continuity_case_summary": {"total": 3, "red": 3, "incident": 3},
                    "signal_observation_summary": {"total": 3, "red": 3, "incident": 3},
                    "continuity_case_examples": [
                        {
                            "case_id": "scope:newer-red",
                            "severity": "RED",
                            "traits": ["regression"],
                            "observation_count": 1,
                            "source_families": ["memory"],
                            "evidence_forms": ["memory"],
                            "latest_signal_at": "2026-09-06T20:41:00+03:00",
                            "latest_title": "Newer scope-only red",
                            "classification_quality": "STRUCTURED",
                        },
                        {
                            "case_id": "incident:inc-20260906-live-stack",
                            "severity": "RED",
                            "traits": ["incident", "regression"],
                            "observation_count": 2,
                            "source_families": ["artifact", "memory"],
                            "evidence_forms": ["report", "memory"],
                            "latest_signal_at": "2026-09-06T20:18:00+03:00",
                            "latest_title": "RED ALERT: recurring live MCP stack disruption",
                            "classification_quality": "STRUCTURED",
                        },
                        {
                            "case_id": "scope:older-red",
                            "severity": "RED",
                            "traits": ["regression"],
                            "observation_count": 1,
                            "source_families": ["memory"],
                            "evidence_forms": ["memory"],
                            "latest_signal_at": "2026-09-06T20:10:00+03:00",
                            "latest_title": "Older scope-only red",
                            "classification_quality": "STRUCTURED",
                        },
                    ],
                }],
            },
            "incident_rollups": [], "recent": [], "projects": [], "recurring_tags": [],
        }
        compact = _compact_memory_overview(report, 3)
        window = compact["timeline_snapshots"]["windows"][0]
        self.assertEqual(window["case_examples"][0]["id"], "incident:inc-20260906-live-stack")
        self.assertEqual(window["case_examples"][0]["title"], "RED ALERT: recurring live MCP stack disruption")

class Issue394StackVisibilityTests(unittest.TestCase):
    def test_human_aliases_cover_invisible_stack_seams(self):
        self.assertEqual(component_details("tailscale")["id"], "tailscale_ingress")
        self.assertEqual(component_details("transfer")["id"], "file_transfer")
        self.assertEqual(component_details("file transfer")["id"], "file_transfer")
        self.assertEqual(component_details("visual proof")["id"], "visual_proof")
        self.assertEqual(component_details("workers")["id"], "execution_workers")

class McpRecoveryStateVisibilityTests(unittest.TestCase):
    def test_bootstrap_surfaces_canonical_mcp_freeze_and_reroute_log_paths(self):
        import tools.stack_atlas as atlas
        recovery_path = ROOT / "04 Operating Contracts" / "mcp-recovery-state.json"
        with patch.object(atlas, "MCP_RECOVERY_STATE_PATH", recovery_path):
            glance = build_live_bootstrap_glance()
        self.assertIn("mcp_recovery_state", glance)
        if glance["mcp_recovery_state"]["available"]:
            self.assertEqual(glance["mcp_recovery_state"]["read_state"], "OK")
            self.assertEqual(len(glance["mcp_recovery_state"]["recovery_invariants"]), 6)
            self.assertEqual(glance["mcp_recovery_state"]["latest_topology_restore"]["after_transport"], "wireguard")
            payload = json.dumps(glance, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            self.assertLessEqual(len(payload), BOOTSTRAP_GLANCE_MAX_BYTES)
            summary = {item["type"]: item["status"] for item in glance["mcp_recovery_state"]["conditions"]}
            self.assertEqual(summary["SecurityReroutesReduced"], "Unknown")
            self.assertEqual(summary["SecurityReroutesEliminated"], "False")
            self.assertEqual(summary["LongRunStable"], "False")
        self.assertTrue(glance["paths"]["mcp_recovery_state"].endswith("mcp-recovery-state.json"))
        self.assertTrue(glance["paths"]["mcp_security_routing_log"].endswith("mcp-security-routing-events.jsonl"))
        self.assertTrue(glance["paths"]["mcp"].endswith("ChatGPTMcpMinimal"))

    def test_freeze_contract_exposes_restore_first_policy(self):
        import tools.stack_atlas as atlas
        freeze_path = ROOT / "04 Operating Contracts" / "mcp-recovery-state.json"
        with patch.object(atlas, "MCP_RECOVERY_STATE_PATH", freeze_path):
            state = atlas._bootstrap_mcp_recovery_state()
        self.assertTrue(state["restore_first_on_regression"])
        self.assertTrue(state["post_restore_no_mcp_request_in_flight"])
        self.assertEqual(state["automatic_routing"], "WireGuard only")
        self.assertIn("explicit recovery only", state["ssh_role"])
        self.assertTrue(any("keep the selected recovery target fixed" in item for item in state["recovery_invariants"]))
        self.assertTrue(any("502" in item and "Node/backend" in item for item in state["recovery_invariants"]))
        self.assertIn("preserve unique work", state["preservation_rule"])
        self.assertIn("authorized by go/continue", state["authorization_rule"])
        self.assertIn("do not ask for redundant per-cutover approval", state["authorization_rule"])
        self.assertIn("scope-widening", state["authorization_rule"])
        self.assertTrue(any("2026-09-05 replacement procedure" in item for item in state["replacement_safety_rules"]))
        latest = state["latest_topology_restore"]
        self.assertEqual(latest["incident_id"], "INC-20260906-2017-EEST-live-mcp-stack-disruption-recurrence")
        self.assertEqual(latest["before_transport"], "reverse_ssh")
        self.assertEqual(latest["after_transport"], "wireguard")
        self.assertTrue(latest["backend_artifact_matches_selected_recovery"])
        self.assertEqual(latest["failed_replacement_status"], "ROLLED_BACK_CANDIDATE_DRAIN_PENDING")
        self.assertEqual(latest["public_health_statuses"], [200, 200, 200, 200, 200])
        self.assertEqual(latest["fresh_mcp_process_call"], "PASS")
        summary = {item["type"]: item["status"] for item in state["conditions"]}
        self.assertEqual(summary["SecurityReroutesReduced"], "Unknown")
        self.assertEqual(summary["SecurityReroutesEliminated"], "False")
        raw = json.loads(freeze_path.read_text(encoding="utf-8"))
        first_step = raw["recovery_target"]["policy"]["required_order"][0]
        self.assertIn("user explicitly asks", first_step)
        self.assertIn("do not persist them", first_step)

    def test_freeze_and_security_reroute_features_are_discoverable(self):
        freeze = find_features("known good refreeze")[0]
        self.assertEqual(freeze["id"], "mcp.recovery_state")
        self.assertIn("True/False/Unknown", freeze["boundary"])
        self.assertNotIn("CANDIDATE_KNOWN_GOOD", freeze["boundary"])
        self.assertNotIn("PROVEN_KNOWN_GOOD", freeze["boundary"])
        reroute = find_features("security reroute")[0]
        self.assertEqual(reroute["id"], "mcp.security_reroute_log")
        self.assertIn("must be logged", reroute["boundary"])
        self.assertIn("user explicitly asks", reroute["boundary"])
        self.assertIn("do not persist them", reroute["boundary"])
        recovery = find_features("restore working MCP")[0]
        self.assertEqual(recovery["id"], "mcp.regression_recovery")
        self.assertIn("Restore-first", recovery["boundary"])
        self.assertIn("user explicitly asks", recovery["boundary"])
        self.assertIn("source SHA alone is insufficient", recovery["boundary"])
        self.assertIn("no MCP request in flight", recovery["boundary"])

class ChatgptPluginSurfaceVisibilityTests(unittest.TestCase):
    def test_chatgpt_plugin_surface_search_routes_to_process_baseline_plus_visual_app(self):
        for query in (
            "ChatGPT plugin tool contract busy_list process profile",
            "busy_list plugin command",
            "view_image plugin",
            "open_visual_proof",
        ):
            with self.subTest(query=query):
                result = find_features(query)[0]
                self.assertEqual(result["id"], "mcp.chatgpt_plugin_surface")
                self.assertEqual(result["owner_components"], ["mcp_minimal_clone"])
                self.assertIn("MCP_TOOL_PROFILE=process", result["boundary"])
                self.assertIn("open_visual_proof", result["boundary"])
                self.assertIn("MCP_VISUAL_PROOF_UI=1", result["boundary"])
                self.assertIn("busy_list", result["boundary"])
                self.assertIn("legacy view_image", result["boundary"])
                self.assertIn("fresh-session inline rendering", result["boundary"])
        sources = component_details("mcp_minimal_clone")["canonical_sources"]
        self.assertTrue(any(item.endswith(r"\config\process-tool-contract.json") for item in sources))
        self.assertTrue(any(item.endswith(r"\src\lib\visual-proof-app.ts") for item in sources))

class VaultUsefulnessRoutingTests(unittest.TestCase):
    def test_vague_vault_usefulness_routes_to_overview_first(self):
        results = find_features("make vault more useful")
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "vault.overview")
        self.assertIn("memory_bank.py overview", " ".join(results[0]["entrypoints"]))

    def test_automatic_aggregation_routes_to_vault_overview(self):
        results = find_features("automatic vault aggregation")
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "vault.overview")

    def test_vague_aggregation_query_does_not_pull_unrelated_single_word_component(self):
        results = find_features("more automatic aggregation and asking atlas should work better", limit=3)
        self.assertEqual(results[0]["id"], "vault.overview")
        self.assertNotIn("component.mcp_minimal_clone", [item["id"] for item in results])

    def test_find_can_return_direct_component_without_prior_schema_knowledge(self):
        results = find_features("generation pinned process transport clone", limit=1)
        self.assertEqual(results[0]["id"], "component.mcp_minimal_clone")
        self.assertEqual(results[0]["owner_components"], ["mcp_minimal_clone"])


class ManualSanityBootstrapTests(unittest.TestCase):
    def test_bootstrap_manual_sanity_reads_existing_metrics_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            metrics = root / "worker-reports" / "manual" / "metrics.json"
            metrics.parent.mkdir(parents=True)
            metrics.write_text(json.dumps({"sanity": {
                "available": True, "baseline_id": "insanity", "boundary_at": "2026-09-06T21:26:41+03:00",
                "status": "PROVISIONAL", "score_delta": 42.0, "direction": "IMPROVED", "post_run_count": 7,
                "minimum_post_runs_for_provisional": 5, "minimum_post_runs_for_comparable": 20,
                "descriptive_delta": 43.0,
                "axes": {"friction": {"score_delta": 50.0}, "operational": {"score_delta": 42.0}},
                "guardrails": {"short_run_lt5_pct": {"status": "REGRESSED", "scored": False}},
                "continuation": {"status": "INSUFFICIENT_DATA", "post_run_count": 2, "baseline_run_count": 7},
                "components": {"median_report_bytes": {"delta_points": 20.0}}, "semantics": "diagnostic only",
            }}), encoding="utf-8")
            with patch("tools.stack_atlas.ATLAS_LIVE_ROOT", root):
                result = _bootstrap_manual_sanity()
            self.assertTrue(result["available"])
            self.assertEqual(result["score_delta"], 42.0)
            self.assertEqual(result["direction"], "IMPROVED")
            self.assertEqual(result["descriptive_delta"], 43.0)
            self.assertEqual(result["axes"]["operational"]["score_delta"], 42.0)
            self.assertEqual(result["guardrails"]["short_run_lt5_pct"]["status"], "REGRESSED")
            self.assertEqual(result["continuation"]["post_run_count"], 2)
            self.assertEqual(result["continuation"]["status"], "INSUFFICIENT_DATA")
            self.assertEqual(result["post_run_count"], 7)

class TestFleetWatchSubscription(unittest.TestCase):
    def test_recovery_candidates_stay_in_callers_subscription_partition(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "worker-reports" / "current"
            current.mkdir(parents=True)
            now = datetime(2026, 9, 7, 16, 30, tzinfo=timezone.utc)
            s2 = CANONICAL_RECURRING_WORKER_PARTITIONS["S2"]
            missing_id = s2[0][0]
            actor_id = s2[1][0]
            for worker_id, label in CANONICAL_RECURRING_WORKERS:
                if worker_id == missing_id:
                    continue
                started = now - timedelta(minutes=20)
                (current / f"{worker_id}.md").write_text(
                    f"automation_id: {worker_id}\n"
                    f"display_label: {label}\n"
                    f"started_at: {started.isoformat()}\n"
                    f"last_activity_at: {started.isoformat()}\n"
                    "state: RUN_FINISHED\n",
                    encoding="utf-8",
                )
            with patch("tools.stack_atlas.ATLAS_LIVE_ROOT", root):
                watch = _bootstrap_fleet_watch(now, worker_id=actor_id)
        self.assertEqual(watch["subscription_scope"], "S2")
        self.assertEqual(watch["expected_recurring_workers"], 5)
        self.assertEqual(watch["expected_recurring_workers_total"], 10)
        self.assertEqual(watch["recovery_candidate_count"], 1)
        self.assertEqual(watch["recovery_candidates"][0]["automation_id"], missing_id)
        self.assertTrue(all(item["subscription_partition"] == "S2" for item in watch["recovery_candidates"]))

    def test_new_worker_is_not_recoverable_before_first_expected_start_plus_grace(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "worker-reports" / "current"
            current.mkdir(parents=True)
            contract = root / "04 Operating Contracts" / "chatgpt-swarm-topology.json"
            contract.parent.mkdir(parents=True)
            now = datetime(2026, 9, 7, 16, 35, tzinfo=timezone.utc)
            target_id, target_label = CANONICAL_RECURRING_WORKER_PARTITIONS["S2"][0]
            actor_id = CANONICAL_RECURRING_WORKER_PARTITIONS["S2"][1][0]
            first_expected = now + timedelta(minutes=1)
            contract.write_text(json.dumps({"subscriptions": {"S2": {"workers": [{
                "automation_id": target_id,
                "label": target_label,
                "first_expected_start_at": first_expected.isoformat(),
            }]}}}), encoding="utf-8")
            for worker_id, label in CANONICAL_RECURRING_WORKER_PARTITIONS["S2"]:
                if worker_id == target_id:
                    continue
                started = now - timedelta(minutes=20)
                (current / f"{worker_id}.md").write_text(
                    f"automation_id: {worker_id}\n"
                    f"display_label: {label}\n"
                    f"started_at: {started.isoformat()}\n"
                    f"last_activity_at: {started.isoformat()}\n"
                    "state: RUN_FINISHED\n",
                    encoding="utf-8",
                )
            with patch("tools.stack_atlas.ATLAS_LIVE_ROOT", root):
                pending = _bootstrap_fleet_watch(now, worker_id=actor_id)
                overdue = _bootstrap_fleet_watch(first_expected + timedelta(minutes=11), worker_id=actor_id)
        self.assertEqual(pending["status"], "CURRENT_LOCAL_EVIDENCE")
        self.assertEqual(pending["first_start_pending"], 1)
        self.assertEqual(pending["recovery_candidates"], [])
        target = next(item for item in overdue["suspect_workers"] if item["automation_id"] == target_id)
        self.assertEqual(target["reason"], "NO_LOCAL_START_EVIDENCE")
        self.assertTrue(target["recovery_actionable"])
