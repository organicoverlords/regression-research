import io
import json
import os
import subprocess
import sys
import time
from contextlib import redirect_stdout
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from tools.cleanup_converger import Worktree, eligibility_reason, process_targets_path
from tools.memory_recent_projection import write_recent_projection

TEST_RECURRING_WORKER_PARTITIONS = {
    "S1": tuple((str(index) * 32, f"S1 Test Worker {index}") for index in range(1, 6)),
    "S2": tuple((char * 32, f"S2 Test Worker {index}") for index, char in enumerate("abcde", start=1)),
}
TEST_RECURRING_WORKERS = tuple(worker for workers in TEST_RECURRING_WORKER_PARTITIONS.values() for worker in workers)

def _write_test_slot_registry(root: Path) -> None:
    bindings = {}
    for partition, workers in TEST_RECURRING_WORKER_PARTITIONS.items():
        for index, (automation_id, label) in enumerate(workers, start=1):
            bindings[f"{partition}/{index}"] = {
                "automation_id": automation_id,
                "label": label,
                "bound_at": "2026-09-13T00:00:00+00:00",
                "first_expected_start_at": None,
            }
    path = root / "worker-reports" / ".supervision" / "recurring-slot-bindings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema": "recurring-worker-slot-bindings.v1",
        "updated_at": "2026-09-13T00:00:00+00:00",
        "authority": "MUTABLE_OPERATIONAL_SLOT_BINDINGS_NOT_LIVENESS",
        "bindings": bindings,
    }), encoding="utf-8")
from tools.stack_atlas import (
    _run_process,
    _bootstrap_fleet_watch,
    ATLAS_CONTRACT,
    BOOTSTRAP_MEMORY_CANDIDATE_LIMIT,
    BOOTSTRAP_MEMORY_OVERVIEW_MAX_BYTES,
    BOOTSTRAP_GLANCE_COMPACTION_TARGET_BYTES,
    BOOTSTRAP_GLANCE_MAX_BYTES,
    BOOTSTRAP_GLANCE_HEADROOM_RESERVE_BYTES,
    BOOTSTRAP_MCP_SERVICE_HEALTH_SOURCE_LIMIT,
    BOOTSTRAP_MEMORY_TITLE_LIMIT,
    blast_radius,
    build_bootstrap_atlas,
    build_live_bootstrap_glance,
    classify_process,
    component_details,
    atlas_lookup,
    find_features,
    unified_find,
    _timeline_discovery_hits,
    _live_discovery_hits,
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
    _read_jsonl_tail,
    _remote_is_newer,
    _git_blob_sha_for_file,
    _git_remote_update_already_applied,
    _git_checkout_state,
    _bootstrap_source_freshness,
    _bootstrap_vault_status,
    _cwd_uses_worktree,
    _compact_memory_overview,
    _fit_memory_overview_budget,
    _fit_bootstrap_glance_budget,
    _bootstrap_memory_overview,
    _bootstrap_mcp_from_live_swarm,
    _bootstrap_agent_contract_version,
    _bootstrap_slopwall_contract,
    _bootstrap_critical_guidance,
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

    def test_bootstrap_slopwall_contract_requires_learning_and_durability(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "RULES.md").write_text(
                "`slopwall` is a **mandatory correction-and-learning incident**\n"
                "re-read this canonical Slopwall rule and the matching AGENTS.md correction owner before finalizing the correction\n"
                "compare the failed reply/action directly against the inherited objective\n"
                "identify the concrete core proposition, decision, action, or evidence the user needed foregrounded\n"
                "identify what displaced that core\n"
                "infer the best-supported mechanism or decision failure\n"
                "derive one reusable prevention lesson\n"
                "persist one compact durable correction\n"
                "The durable correction is mandatory for literal `slopwall`\n"
                "The durable correction must name the lost core and the displacement\n"
                "A slopwall is not defined by length\n",
                encoding="utf-8",
            )
            (root / "AGENTS.md").write_text(
                "literal `slopwall` additionally requires a bounded durable learning loop\n"
                "re-read the canonical Slopwall rule plus this correction owner\n"
                "identify the lost core proposition/decision/action/evidence and what displaced it\n"
                "The Slopwall record is mandatory\n"
                "do not store merely `be concise`, `answer better`\n"
                "bounded uncertainty instead of fabricating a root cause\n"
                "after durability is secured, continue or finish the inherited task\n",
                encoding="utf-8",
            )
            contract = _bootstrap_slopwall_contract(root)
            self.assertEqual(contract["status"], "ENFORCED")
            self.assertIn("reread_canonical_rule", contract["process"])
            self.assertIn("recover_lost_core", contract["process"])
            self.assertIn("identify_displacement", contract["process"])
            self.assertIn("best_supported_mechanism", contract["process"])
            self.assertIn("condition/action_prevention", contract["process"])
            self.assertIn("repair_task", contract["process"])
            self.assertIn("mandatory_durable_correction", contract["process"])
            self.assertIn("not brevity/apology", contract["process"])
            self.assertNotIn("missing", contract)

            (root / "AGENTS.md").write_text(
                "literal `slopwall` additionally requires a bounded durable learning loop\n"
                "The Slopwall record is mandatory\n",
                encoding="utf-8",
            )
            drifted = _bootstrap_slopwall_contract(root)
            self.assertEqual(drifted["status"], "DRIFTED")
            self.assertIn("AGENTS:reread", drifted["missing"])
            self.assertIn("AGENTS:lost_core", drifted["missing"])
            self.assertIn("AGENTS:uncertainty", drifted["missing"])
            self.assertIn("AGENTS:inherit", drifted["missing"])

    def test_bootstrap_critical_guidance_projects_prevention_and_recovery_without_phrase_matching(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "RULES.md").write_text("canonical rules can be reworded freely\n", encoding="utf-8")
            (root / "AGENTS.md").write_text("canonical agents guidance can be reworded freely\n", encoding="utf-8")
            guidance = _bootstrap_critical_guidance(root)
            self.assertEqual(guidance["mode"], "HINT_ONLY")
            self.assertIn("material data/constraints/uncertainty", guidance["eli5"])
            self.assertIn("RULES:ELI5", guidance["eli5"])
            self.assertIn("no filler/process/proxy displacement", guidance["slopwall"])
            self.assertIn("mandatory correction before final", guidance["slopwall"])
            self.assertIn("corrected result first", guidance["asshole"])
            self.assertIn("mandatory lightweight marker", guidance["asshole"])
            self.assertIn("one decision-relevant unknown", guidance["stack_find"])
            self.assertIn("narrow same unknown once", guidance["stack_find"])
            self.assertIn("RULE_GAP vs RULE_VIOLATION", guidance["shared_correction"])
            self.assertIn("no 'this chat/from now on' promise", guidance["shared_correction"])
            self.assertIn("durable canonical proof", guidance["shared_correction"])
            self.assertIn("discuss first/no mutation", guidance["shared_correction"])
            security = guidance["security_evidence"]
            self.assertEqual(security["mode"], "CLASSIFY_BEFORE_CAUSALITY")
            self.assertEqual(security["source"], "RULES:platform-security-boundary")
            self.assertEqual(
                security["classes"]["tool_policy_rejection"],
                "tool invocation rejected before MCP dispatch",
            )
            self.assertIn(
                "tool_policy_rejection != platform_security_reroute",
                security["non_equivalence"],
            )
            self.assertIn("shared log path/name is not a classification", security["causality_gate"])
            self.assertNotIn("missing", guidance)

            (root / "AGENTS.md").unlink()
            missing = _bootstrap_critical_guidance(root)
            self.assertEqual(missing["mode"], "UNAVAILABLE")
            self.assertEqual(missing["missing"], ["serving_rules_unreadable"])

    def test_bootstrap_mcp_projection_identifies_mcpv4_multisource_evidence(self):
        snapshot = {
            "available": True,
            "summary": {"recent_callers": 2, "workspace_counts": {"Vault": 2}, "caller_modes": {"PLAN_ONLY": 1, "UNKNOWN": 1}, "activity_buckets": {"0_15s": 1, "15_60s": 1}},
            "evidence": {
                "transport": "MCPv4",
                "transport_source_count": 2,
                "source_age_seconds": 0.5,
                "observation_window_complete": False,
                "activity_window_complete": True,
                "activity_summary": {"starts": 2, "reads": 2},
            },
            "lanes": [{
                "worktree": {"path": "C:/Vault"},
                "busy": [],
                "callers": [{"caller_id": "caller-plan", "last_activity_age_seconds": 3, "workspace": "Vault", "mode": "PLAN_ONLY", "action_class": "content_plan", "activity_target": {"type": "project", "id": "p3"}}],
            }],
        }
        projected = _bootstrap_mcp_from_live_swarm(snapshot)
        self.assertEqual(projected["transport"], "MCPv4")
        self.assertEqual(projected["transport_source_count"], 2)
        self.assertEqual(projected["active_session_count"], 2)
        self.assertEqual(projected["active_session_count_status"], "COMPLETE")
        self.assertEqual(projected["activity_evidence_status"], "FRESH")
        self.assertEqual(projected["caller_modes"], {"PLAN_ONLY": 1, "UNKNOWN": 1})
        self.assertEqual(projected["activity_buckets"], {"0_15s": 1, "15_60s": 1})
        self.assertEqual(projected["active_sessions"][0]["mode"], "PLAN_ONLY")
        self.assertEqual(projected["active_sessions"][0]["action_class"], "content_plan")
        self.assertEqual(projected["active_sessions"][0]["activity_target"]["id"], "p3")

    def test_cleanup_convergence_is_discoverable_and_operator_only(self):
        result = find_features("cleanup worktree convergence")[0]
        self.assertEqual(result["id"], "cleanup.convergence")
        self.assertIn("operator-only", result["boundary"].lower())
        self.assertIn("git-ignored standard unreal", result["boundary"].lower())
        self.assertIn("content/saved/proof/evidence/source", result["boundary"].lower())
        self.assertTrue(any("cleanup_converger.py --apply --operator-ack" in item for item in result["entrypoints"]))

    def test_disk_cleanup_routes_to_disk_pressure_not_worktree_convergence(self):
        results = find_features("disk cleanup")
        self.assertTrue(results)
        self.assertEqual(results[0]["id"], "resource.disk_pressure")
        self.assertIn("provenance-first", results[0]["boundary"])

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

    def test_bootstrap_memory_overview_prefers_canonical_external_projection_over_stale_legacy_copy(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "vault"
            external = Path(d) / "VaultTimeline"
            legacy = root / ".state" / "timeline"
            external.mkdir(parents=True)
            legacy.mkdir(parents=True)
            (external / "timeline-store.json").write_text("{}", encoding="utf-8")
            now = datetime.now(timezone.utc)

            def projection(path: Path, *, marker: str, generated_at: datetime) -> None:
                path.write_text(json.dumps({
                    "schema": "vault.timeline.bootstrap.v1",
                    "generated_at": generated_at.isoformat(),
                    "overview": {
                        "contract": "history only",
                        "eligible_entries": 1,
                        "timeline_snapshots": {"authority": "DERIVED_HISTORY_ONLY", "windows": []},
                        "incident_rollups": [],
                        "recent": [],
                        "projects": [{"name": marker, "count": 1}],
                        "recurring_tags": [],
                        "timeline_materialized": {"as_of": generated_at.isoformat()},
                    },
                }), encoding="utf-8")

            projection(legacy / "bootstrap-memory-overview.json", marker="legacy-stale", generated_at=now - timedelta(hours=12))
            projection(external / "bootstrap-memory-overview.json", marker="canonical-live", generated_at=now)
            with patch.dict(os.environ, {"VAULT_TIMELINE_STATE_ROOT": str(external)}), \
                    patch("tools.stack_atlas.ATLAS_LIVE_ROOT", root), \
                    patch("tools.memory_bank.build_overview", side_effect=AssertionError("bootstrap must not rebuild timeline")):
                compact = _bootstrap_memory_overview()

        self.assertEqual(compact["projects"][0]["name"], "canonical-live")
        self.assertEqual(compact["timeline_materialized"]["status"], "FRESH")

    def test_bootstrap_memory_overview_overlays_current_recent_projection_without_rebuilding_history(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            timeline_path = root / ".state" / "timeline" / "bootstrap-memory-overview.json"
            timeline_path.parent.mkdir(parents=True)
            timeline_path.write_text(json.dumps({
                "schema": "vault.timeline.bootstrap.v1",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "overview": {
                    "contract": "history only",
                    "eligible_entries": 24,
                    "timeline_snapshots": {"authority": "DERIVED_HISTORY_ONLY", "windows": []},
                    "incident_rollups": [],
                    "recent": [{"id": "stale", "timestamp": "2026-09-09T20:00:00+03:00", "title": "stale timeline title"}],
                    "projects": [],
                    "recurring_tags": [],
                },
            }), encoding="utf-8")
            seed = root / "memory" / "memory-bank.jsonl"
            seed.parent.mkdir(parents=True)
            seed.write_text("seed\n", encoding="utf-8")
            overlay = root / "memory-bank.local.jsonl"
            overlay.write_text("overlay\n", encoding="utf-8")
            write_recent_projection(
                seed_path=seed, overlay_path=overlay,
                recent=[{"id": "fresh", "timestamp": "2026-09-10T01:00:00+03:00", "title": "fresh local memory"}],
            )
            with patch("tools.stack_atlas.ATLAS_LIVE_ROOT", root), \
                    patch("tools.stack_atlas.default_local_bank_path", return_value=overlay), \
                    patch("tools.memory_bank.build_overview", side_effect=AssertionError("bootstrap must not rebuild timeline")):
                compact = _bootstrap_memory_overview()
        self.assertEqual([item["id"] for item in compact["recent"]], ["fresh"])
        self.assertEqual(compact["recent_source"]["authority"], "DIRECT_LOCAL_EFFECTIVE_MEMORY_PROJECTION")
        self.assertEqual(compact["recent_source"]["status"], "CURRENT_FOR_EFFECTIVE_MEMORY_FILES")
        self.assertEqual(compact["timeline_snapshots"]["authority"], "DERIVED_HISTORY_ONLY")

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
        self.assertIn("critical_guidance", glance["bootstrap"])
        self.assertEqual(glance["bootstrap"]["critical_guidance"]["mode"], "HINT_ONLY")
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
        self.assertEqual(BOOTSTRAP_GLANCE_MAX_BYTES, 25_000)
        self.assertEqual(BOOTSTRAP_GLANCE_COMPACTION_TARGET_BYTES, 15_000)
        self.assertEqual(next(iter(glance)), "bootstrap_warning")
        self.assertEqual(next(reversed(glance)), "bootstrap_end")
        self.assertEqual(glance["bootstrap_end"]["status"], "COMPLETE")
        self.assertEqual(glance["bootstrap"]["payload_budget"]["max_bytes"], BOOTSTRAP_GLANCE_MAX_BYTES)
        self.assertEqual(glance["bootstrap"]["payload_budget"]["compaction_target_bytes"], BOOTSTRAP_GLANCE_COMPACTION_TARGET_BYTES)
        self.assertIn("trend", glance["pc"]["disk"])
        memory = glance["pc"]["memory"]
        self.assertIn("commit_headroom_gb", memory)
        self.assertGreaterEqual(glance["mcp"]["active_session_count"], len(glance["mcp"]["active_sessions"]))
        self.assertEqual(glance["mcp"]["active_session_count_semantics"], "recent_callers_with_process_start_or_read_in_activity_window_not_current_running_processes")
        self.assertLessEqual(len(glance["mcp"]["active_sessions"]), glance["mcp"]["active_session_details"]["limit"])
        self.assertEqual(glance["mcp"]["active_session_details"]["returned"], len(glance["mcp"]["active_sessions"]))
        self.assertNotIn("active_sessions_truncated", glance["mcp"])
        self.assertNotIn("lanes_truncated", glance["live_swarm"])
        self.assertEqual(glance["live_swarm"]["lane_details"]["returned"], len(glance["live_swarm"]["lanes"]))
        self.assertEqual(glance["live_swarm"]["lane_details"]["semantics"], "bootstrap_detail_bound_not_evidence_truncation")
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
        visual = glance["bootstrap"]["visual_acceptance"]
        self.assertEqual(visual["status"], "HARD_GATE")
        self.assertIn("exact candidate pixels/frames", visual["rule"])
        self.assertIn("never substitute for pixel inspection", visual["metrics"])
        self.assertIn("REJECTED/NOT_PROVEN", visual["failure"])
        self.assertIn("UNKNOWN/NOT_PROVEN", visual["failure"])
        contract = glance["bootstrap"]["agent_contract"]
        self.assertEqual(contract["status"], "COHERENT")
        self.assertGreaterEqual(contract["version"], 1)
        self.assertEqual(contract["version"], contract["rules_version"])
        self.assertEqual(contract["version"], contract["agents_version"])
        slopwall = glance["bootstrap"]["slopwall_contract"]
        self.assertEqual(slopwall["status"], "ENFORCED")
        self.assertIn(slopwall["version"], {"LEGACY_V84", "V2"})
        if slopwall["version"] == "V2":
            self.assertEqual(slopwall["triggers"], ["slopwall", "incident_report"])
            self.assertIn("VISIBLE_CONTEXT_ONLY", slopwall["capture"])
            self.assertIn("no_full_conversation_reload_or_backfill", slopwall["capture"])
            self.assertIn("failed_boundary", slopwall["process"])
            self.assertIn("inspect_governing_guidance_and_evidence", slopwall["process"])
            self.assertIn("bounded_user_visible_diagnosis", slopwall["process"])
            self.assertIn("repair_inherited_objective", slopwall["process"])
            self.assertIn("persist_incident_replay_score_memory_contract_review", slopwall["process"])
        else:
            self.assertIn("recover_lost_core", slopwall["process"])
            self.assertIn("identify_displacement", slopwall["process"])
            self.assertIn("best_supported_mechanism", slopwall["process"])
            self.assertIn("condition/action_prevention", slopwall["process"])
            self.assertIn("mandatory_durable_correction", slopwall["process"])
            self.assertIn("not brevity/apology", slopwall["process"])
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

    def test_runtime_graph_cli_routes_explain_and_path_commands(self):
        explain_value = {"schema": "stack-atlas.runtime-explain.v1", "status": "OK"}
        explain_output = io.StringIO()
        with patch("sys.argv", ["stack_atlas.py", "runtime-explain", "node-x", "--surface", "surface-x"]), \
                patch("tools.stack_atlas._runtime_graph_explain_safe", return_value=explain_value) as explain_call, \
                redirect_stdout(explain_output):
            self.assertEqual(stack_atlas_main(), 0)
        explain_call.assert_called_once_with("node-x", surface_id="surface-x")
        self.assertEqual(json.loads(explain_output.getvalue()), explain_value)

        path_value = {"schema": "stack-atlas.runtime-path.v1", "status": "OK", "distance": 2}
        path_output = io.StringIO()
        with patch("sys.argv", ["stack_atlas.py", "runtime-path", "node-a", "node-b", "--surface", "surface-y"]), \
                patch("tools.stack_atlas._runtime_graph_path_safe", return_value=path_value) as path_call, \
                redirect_stdout(path_output):
            self.assertEqual(stack_atlas_main(), 0)
        path_call.assert_called_once_with("node-a", "node-b", surface_id="surface-y")
        self.assertEqual(json.loads(path_output.getvalue()), path_value)

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

    def test_bootstrap_soft_target_preserves_bounded_live_status_detail_under_hard_cap(self):
        lanes = [{"basis": "worktree", "workspace": f"w{i}", "worktree": {"path": f"C:/w{i}"}, "callers": [{"caller_id": f"c{i}"}], "busy": []} for i in range(4)]
        sessions = [{"caller_id": f"c{i}", "cwd": f"C:/w{i}", "workspace": f"w{i}", "busy_titles": []} for i in range(3)]
        glance = {
            "bootstrap": {"status": "OK"},
            "live_swarm": {
                "summary": {"recent_callers": 4, "lanes": 4},
                "evidence": {"activity_window_complete": True, "observation_window_complete": True},
                "lanes": lanes,
                "lane_details": {"policy": "most_recent", "limit": 4, "returned": 4, "total": 4, "bounded": False, "semantics": "bootstrap_detail_bound_not_evidence_truncation"},
            },
            "mcp": {
                "active_session_count": 4, "active_session_count_status": "COMPLETE",
                "active_sessions": sessions,
                "active_session_details": {"policy": "most_recent", "limit": 3, "returned": 3, "total": 4, "bounded": True, "semantics": "bootstrap_detail_bound_not_evidence_truncation"},
            },
            "synthetic_uncompacted_detail": "x" * 16_000,
        }
        fitted = _fit_bootstrap_glance_budget(glance)
        size = len(json.dumps(fitted, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        self.assertGreater(size, BOOTSTRAP_GLANCE_COMPACTION_TARGET_BYTES)
        self.assertLessEqual(size, BOOTSTRAP_GLANCE_MAX_BYTES)
        self.assertEqual(len(fitted["live_swarm"]["lanes"]), 4)
        self.assertEqual(len(fitted["mcp"]["active_sessions"]), 3)
        self.assertNotIn("lanes_truncated", fitted["live_swarm"])
        self.assertNotIn("active_sessions_truncated", fitted["mcp"])
        self.assertTrue(fitted["mcp"]["active_session_details"]["bounded"])

    def test_bootstrap_headroom_compaction_keeps_reserve_under_high_live_detail(self):
        lanes = [
            {
                "basis": "worktree", "state": "ACTIVE", "workspace": f"w{i}",
                "worktree": {"path": "C:/" + (f"lane{i}-" * 90), "branch": f"b{i}", "head": "a" * 40},
                "callers": [{"caller_id": f"caller_{i}", "last_activity_age_seconds": i, "mode": "UNKNOWN", "identity": {"status": "UNATTRIBUTED"}}],
                "busy": [],
            }
            for i in range(4)
        ]
        sessions = [
            {"caller_id": f"caller_{i}", "cwd": "C:/" + (f"session{i}-" * 90), "workspace": f"w{i}", "busy_titles": []}
            for i in range(3)
        ]
        sources = [
            {
                "instance": f"clone-{i}", "status": "LIVE", "http_status": 200,
                "backend_generation": "g" * 180, "runtime_identity": {"source_commit": "c" * 40, "dist_sha256": "d" * 64},
            }
            for i in range(4)
        ]
        glance = {
            "bootstrap": {"status": "OK"},
            "synthetic_fixed_payload": "z" * 16_500,
            "live_swarm": {
                "summary": {"recent_callers": 4, "lanes": 4},
                "evidence": {"activity_window_complete": True},
                "recurring_actors": [
                    {"slot_id": "S1/1", "actor": "S1/Hazel", "evidence_state": "RECENT_ATTRIBUTED_MCP_ACTIVITY", "mcp": {"branch": "x" * 300}},
                    {"slot_id": "S2/3", "actor": "S2/Willow", "evidence_state": "RECENT_ATTRIBUTED_MCP_ACTIVITY", "mcp": {"branch": "y" * 300}},
                ],
                "lanes": lanes,
                "lane_details": {"policy": "most_recent", "limit": 4, "returned": 4, "total": 4, "bounded": False, "semantics": "bootstrap_detail_bound_not_evidence_truncation"},
            },
            "mcp": {
                "active_session_count": 4, "active_session_count_status": "COMPLETE",
                "active_sessions": sessions,
                "active_session_details": {"policy": "most_recent", "limit": 3, "returned": 3, "total": 4, "bounded": True, "semantics": "bootstrap_detail_bound_not_evidence_truncation"},
                "service_health": {"source_count": 4, "live_source_count": 4, "sources": sources},
            },
        }
        raw_size = len(json.dumps(glance, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        stability_ceiling = BOOTSTRAP_GLANCE_MAX_BYTES - BOOTSTRAP_GLANCE_HEADROOM_RESERVE_BYTES
        self.assertGreater(raw_size, stability_ceiling)
        fitted = _fit_bootstrap_glance_budget(glance)
        fitted_size = len(json.dumps(fitted, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        self.assertLessEqual(fitted_size, stability_ceiling)
        self.assertEqual(fitted["bootstrap"]["payload_budget"]["headroom_reserve_bytes"], BOOTSTRAP_GLANCE_HEADROOM_RESERVE_BYTES)
        self.assertEqual(fitted["bootstrap"]["payload_budget"]["stability_ceiling_bytes"], stability_ceiling)
        self.assertTrue(fitted["bootstrap"]["payload_budget"]["headroom_compacted"])
        self.assertTrue(fitted["bootstrap"]["payload_budget"]["headroom_target_met"])
        self.assertEqual(fitted["mcp"]["active_session_count"], 4)
        self.assertEqual(fitted["live_swarm"]["summary"]["recent_callers"], 4)
        self.assertGreaterEqual(len(fitted["live_swarm"]["lanes"]), 1)
        self.assertTrue(
            fitted["mcp"]["active_session_details"].get("budget_limited")
            or fitted["live_swarm"]["lane_details"].get("budget_limited")
            or fitted["mcp"]["service_health"].get("budget_limited")
        )
        self.assertEqual(len(glance["mcp"]["active_sessions"]), 3)
        self.assertEqual(len(glance["live_swarm"]["lanes"]), 4)

    def test_bootstrap_reports_unmet_headroom_target_without_faking_failure(self):
        glance = {
            "bootstrap": {"status": "OK"},
            "synthetic_fixed_payload": "x" * 22_000,
        }
        fitted = _fit_bootstrap_glance_budget(glance)
        size = len(json.dumps(fitted, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        self.assertGreater(size, BOOTSTRAP_GLANCE_MAX_BYTES - BOOTSTRAP_GLANCE_HEADROOM_RESERVE_BYTES)
        self.assertLessEqual(size, BOOTSTRAP_GLANCE_MAX_BYTES)
        self.assertFalse(fitted["bootstrap"]["payload_budget"]["headroom_target_met"])
        self.assertFalse(fitted["bootstrap"]["payload_budget"]["headroom_compacted"])
        self.assertEqual(fitted["bootstrap_end"]["status"], "COMPLETE")

    def test_bootstrap_hard_cap_does_not_relax_existing_compaction_target(self):
        glance = {
            "bootstrap": {"status": "OK"},
            "mcp_recovery_state": {
                "conditions": [
                    {
                        "type": f"Condition{i}", "status": "Unknown", "reason": "BoundedReason",
                        "message": "detail " * 400, "observed_generation": "g" * 500,
                    }
                    for i in range(5)
                ],
            },
        }
        raw_size = len(json.dumps(glance, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        self.assertGreater(raw_size, BOOTSTRAP_GLANCE_COMPACTION_TARGET_BYTES)
        self.assertLess(raw_size, BOOTSTRAP_GLANCE_MAX_BYTES)
        fitted = _fit_bootstrap_glance_budget(glance)
        fitted_size = len(json.dumps(fitted, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
        self.assertLessEqual(fitted_size, BOOTSTRAP_GLANCE_COMPACTION_TARGET_BYTES)
        self.assertTrue(fitted["bootstrap"]["payload_budget"]["compacted"])
        self.assertEqual(fitted["bootstrap"]["payload_budget"]["max_bytes"], 25_000)
        self.assertEqual(fitted["bootstrap"]["payload_budget"]["compaction_target_bytes"], 15_000)
        self.assertEqual(fitted["mcp_recovery_state"]["conditions"][0], {"type": "Condition0", "status": "Unknown", "reason": "BoundedReason"})

    def test_bootstrap_compaction_keeps_stack_commands_directly_executable(self):
        glance = {
            "bootstrap": {"status": "OK"},
            "commands": {
                "bootstrap": r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py bootstrap-glance",
                "live_swarm": r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py live-swarm",
                "fleet_watch": r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py fleet-watch --worker-id <own-automation-id>",
                "stack_owner": r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py lookup <id-or-alias>",
                "stack_find": r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py find <query>",
                "production_change_gate": r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py production-change-gate <component> --actor <actor> --busy-scope <exact-scope>",
                "memory_overview": r"python C:\Users\Lauri\Desktop\vault\tools\memory_bank.py overview",
                "tiny3d_asset_library": "lookup tiny3d_library",
            },
            "paths": {
                "rules": r"C:\Users\Lauri\.agents\RULES.md",
                "agents": r"C:\Users\Lauri\.agents\AGENTS.md",
                "vault": r"C:\Users\Lauri\Desktop\vault",
                "synthetic_bloat": "x" * 20_000,
            },
        }
        fitted = _fit_bootstrap_glance_budget(glance)
        commands = fitted["commands"]
        self.assertTrue(fitted["bootstrap"]["payload_budget"]["compacted"])
        self.assertEqual(commands["live_swarm"], r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py live-swarm")
        self.assertEqual(commands["stack_find"], r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py find <query>")
        self.assertEqual(commands["memory_overview"], r"python C:\Users\Lauri\Desktop\vault\tools\memory_bank.py overview")
        self.assertLessEqual(
            len(json.dumps(fitted, separators=(",", ":"), ensure_ascii=False).encode("utf-8")),
            BOOTSTRAP_GLANCE_COMPACTION_TARGET_BYTES,
        )

    def test_bootstrap_mcp_service_health_source_detail_is_bounded(self):
        glance = {
            "bootstrap": {"status": "OK"},
            "mcp": {"active_session_count": 2, "service_health": {
                "available": True, "status": "LIVE", "source_count": 10, "live_source_count": 10,
                "sources": [{"instance": f"source-{i}", "status": "LIVE", "backend_generation": "g" * 80} for i in range(10)],
            }},
        }
        fitted = _fit_bootstrap_glance_budget(glance)
        health = fitted["mcp"]["service_health"]
        self.assertEqual(health["source_count"], 10)
        self.assertEqual(health["live_source_count"], 10)
        self.assertEqual(health["source_detail_limit"], BOOTSTRAP_MCP_SERVICE_HEALTH_SOURCE_LIMIT)
        self.assertTrue(health["sources_truncated"])
        self.assertEqual(len(health["sources"]), BOOTSTRAP_MCP_SERVICE_HEALTH_SOURCE_LIMIT)
        self.assertEqual([item["instance"] for item in health["sources"]], [f"source-{i}" for i in range(BOOTSTRAP_MCP_SERVICE_HEALTH_SOURCE_LIMIT)])
        self.assertTrue(fitted["bootstrap"]["payload_budget"]["compacted"])

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

    def test_production_change_gate_covers_bootstrap_control_plane_components(self):
        busy = {"available": True, "claim": {"actor": "ChatGPT:test"}, "job": None}
        for target, scope in (
            ("bootstrap_snapshot", "vault:bootstrap-snapshot:runtime-bundle"),
            ("vault_checkout_sync", "vault:checkout-sync:scheduled-task"),
            ("worktree_hygiene", "vault:worktree-hygiene:scheduled-task"),
        ):
            gate = production_change_gate(
                target, actor="ChatGPT:test", busy_scope=scope,
                explicit_user_authorization=True, independent_rollback_verified=True,
                offpath_proof_verified=True, busy_status=busy,
            )
            self.assertEqual(gate["verdict"], "PASS", gate)
            self.assertTrue(gate["target"]["shared_production"])
            self.assertEqual(gate["reasons"], [])
            self.assertEqual(gate["live_dependencies"], {})

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
            _write_test_slot_registry(root)
            current = root / "worker-reports" / "current"
            supervision = root / "worker-reports" / ".supervision"
            current.mkdir(parents=True)
            supervision.mkdir(parents=True, exist_ok=True)
            now = datetime.now(timezone.utc)

            missing_id, _ = TEST_RECURRING_WORKERS[0]
            stale_id, _ = TEST_RECURRING_WORKERS[1]
            for index, (worker_id, label) in enumerate(TEST_RECURRING_WORKERS[1:], start=1):
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

        self.assertEqual(watch["scheduler_probe"], "required_before_scheduler_mutation")
        self.assertFalse(watch["local_evidence_scheduler_mutation_authorized"])
        self.assertTrue(watch["same_partition_peer_reenable_after_live_scheduler_confirmation"])
        self.assertNotIn("scheduler_mutation_authorized", watch)
        self.assertTrue(watch["recovery_candidates_require_live_scheduler_probe"])
        self.assertEqual(watch["observed_worker_reports"], len(TEST_RECURRING_WORKERS) - 1)
        self.assertEqual(watch["status"], "LOCAL_RECOVERY_EVIDENCE")
        self.assertEqual(watch["health_verdict"], "NOT_PROVIDED")
        self.assertEqual(watch["liveness_authority"], "live_swarm_runtime_evidence")
        self.assertIn("not_worker_liveness_or_swarm_health", watch["evidence_semantics"])
        self.assertNotIn("suspect_workers", watch)
        self.assertNotIn("suspect_count", watch)
        suspect_ids = {item["automation_id"] for item in watch["lifecycle_gaps"]}
        self.assertIn(missing_id, suspect_ids)
        self.assertIn(stale_id, suspect_ids)
        self.assertEqual(watch["recovery_candidate_count"], 2)
        self.assertEqual(watch["scheduler_probe_candidate_count"], 2)
        self.assertEqual(watch["scheduler_probe_candidates"], watch["recovery_candidates"])

    def test_fleet_watch_running_worker_uses_last_activity_for_freshness(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_test_slot_registry(root)
            current = root / "worker-reports" / "current"
            supervision = root / "worker-reports" / ".supervision"
            current.mkdir(parents=True)
            supervision.mkdir(parents=True, exist_ok=True)
            now = datetime.now(timezone.utc)
            target_id, _ = TEST_RECURRING_WORKERS[0]
            for worker_id, label in TEST_RECURRING_WORKERS:
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
        self.assertEqual(watch["running_report_with_start_receipt"], 1)
        self.assertNotIn(target_id, {item["automation_id"] for item in watch["lifecycle_gaps"]})

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

    def test_bootstrap_swarm_topology_uses_two_independent_five_worker_partitions(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract = root / "04 Operating Contracts" / "chatgpt-swarm-topology.json"
            contract.parent.mkdir(parents=True)
            contract.write_text(json.dumps({
                "authority": "CURRENT_USER_DIRECTION_AND_VERIFIED_PARTITION_LOCAL_SCHEDULER_STATE",
                "subscriptions": {
                    "S1": {"recurring_worker_slots": 5, "operator_control": "PARTITION_LOCAL"},
                    "S2": {"recurring_worker_slots": 5, "operator_control": "PARTITION_LOCAL"},
                },
                "recurring_worker_global_max": 10,
                "recurring_worker_partition_max": 5,
                "recurring_worker_partition_rule": "At most five recurring scheduler workers per partition; canonical partitions S1 and S2.",
                "manual_workers": {
                    "population": "SEPARATE_ON_DEMAND",
                    "counts_against_recurring_slots": False,
                    "total_swarm_semantics": "up to 5 recurring workers in S1 plus up to 5 in S2 plus manual/on-demand workers",
                },
                "handoff": {"primary_operator_subscription": "PARTITION_LOCAL"},
            }), encoding="utf-8")
            manual_root = root / "worker-reports" / "manual" / "current"
            manual_root.mkdir(parents=True)
            now = datetime(2026, 9, 10, 4, 30, tzinfo=timezone.utc)
            with patch("tools.stack_atlas.ATLAS_LIVE_ROOT", root):
                topology = _bootstrap_swarm_topology(now)

        self.assertEqual(topology["chatgpt_subscription_count"], 2)
        self.assertEqual(topology["recurring_worker_partitions"], {"S1": 5, "S2": 5})
        self.assertEqual(topology["recurring_workers_total"], 10)
        self.assertEqual(topology["operator_handoff"]["primary_operator_subscription"], "PARTITION_LOCAL")
        self.assertEqual(topology["routine_recurring_recovery"]["scheduler_role"], "RECURRENCE_ONLY")
        self.assertEqual(topology["routine_recurring_recovery"]["authority"], "SUPERVISING_CHAT_OR_OPERATOR_HANDOFF")
        self.assertFalse(topology["manual_workers"]["counts_against_recurring_slots"])
        self.assertIn("S1", topology["manual_workers"]["total_swarm_semantics"])
        self.assertIn("S2", topology["manual_workers"]["total_swarm_semantics"])
    def test_recurring_worker_recovery_allows_only_bounded_same_partition_reenable(self):
        topology = component_details("swarm_topology")
        workers = component_details("execution_workers")
        scheduler = component_details("chatgpt_automations")

        self.assertIn("bounded same-partition sibling re-enable", topology["supervisor"])
        self.assertIn("chatgpt_automations", topology["dependents"])
        self.assertNotIn("scheduler", topology["dependents"])
        self.assertEqual(topology["self_heal"], "bounded_same_partition_peer_reenable_with_supervising_fallback")
        self.assertIn("BusyCoordinator is exact mutation collision control only", workers["supervisor"])
        self.assertIn("exact same-partition sibling", workers["supervisor"])
        self.assertFalse(any("worker_recovery_guard" in route for route in workers["independent_recovery"]))
        self.assertTrue(any("idempotent is_enabled=true" in route for route in workers["independent_recovery"]))
        self.assertIn("does not supervise worker health", scheduler["supervisor"])
        self.assertEqual(scheduler["self_heal"], "not_swarm_supervision")
        self.assertTrue(any("worker_recovery_guard.py" in route for route in topology["independent_recovery"]))
        self.assertTrue(any("same-partition targeted is_enabled=true" in route for route in topology["independent_recovery"]))
        self.assertTrue(any("worker_recovery_guard" in route for route in scheduler["independent_recovery"]))
        self.assertTrue(any("same-partition is_enabled=true" in route for route in scheduler["independent_recovery"]))

        timed = find_features("timed runs", limit=5)
        match = next(item for item in timed if item["id"] == "worker.swarm_topology")
        self.assertIn("scheduler provides recurrence only", match["boundary"])
        self.assertIn("targeted idempotent is_enabled=true", match["boundary"])
        self.assertIn("same-partition sibling", match["boundary"])

    def test_fleet_watch_unbound_slot_is_capacity_not_recovery_candidate(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_test_slot_registry(root)
            registry = root / "worker-reports" / ".supervision" / "recurring-slot-bindings.json"
            payload = json.loads(registry.read_text(encoding="utf-8"))
            payload["bindings"].pop("S1/5")
            registry.write_text(json.dumps(payload), encoding="utf-8")
            current = root / "worker-reports" / "current"
            current.mkdir(parents=True)
            now = datetime.now(timezone.utc)
            for worker_id, label in TEST_RECURRING_WORKER_PARTITIONS["S1"][:4]:
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
                watch = _bootstrap_fleet_watch(now, partition="S1")

        self.assertEqual(watch["status"], "LOCAL_RECOVERY_EVIDENCE")
        self.assertEqual(watch["expected_recurring_workers"], 5)
        self.assertEqual(watch["bound_recurring_workers"], 4)
        self.assertEqual(watch["worker_partitions"]["S1"]["unbound_slots"], ["S1/5"])
        self.assertEqual(watch["recovery_candidate_count"], 0)
        self.assertEqual(watch["lifecycle_gap_count"], 0)

    def test_fleet_watch_replacement_binding_accepts_new_id_and_rejects_old_id(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_test_slot_registry(root)
            old_id = TEST_RECURRING_WORKER_PARTITIONS["S1"][0][0]
            new_id = "f" * 32
            registry = root / "worker-reports" / ".supervision" / "recurring-slot-bindings.json"
            payload = json.loads(registry.read_text(encoding="utf-8"))
            payload["bindings"]["S1/1"]["automation_id"] = new_id
            payload["bindings"]["S1/1"]["label"] = "Renamed replacement"
            registry.write_text(json.dumps(payload), encoding="utf-8")
            with patch("tools.stack_atlas.ATLAS_LIVE_ROOT", root):
                current = _bootstrap_fleet_watch(datetime.now(timezone.utc), worker_id=new_id)
                retired = _bootstrap_fleet_watch(datetime.now(timezone.utc), worker_id=old_id)

        self.assertEqual(current["subscription_scope"], "S1")
        self.assertEqual(current["bound_recurring_workers"], 5)
        self.assertEqual(retired["status"], "UNBOUND_WORKER_ID")
        self.assertEqual(retired["scheduler_probe"], "not_performed")

    def test_fleet_watch_models_two_independent_five_worker_partitions(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_test_slot_registry(root)
            current = root / "worker-reports" / "current"
            current.mkdir(parents=True)
            now = datetime(2026, 9, 10, 4, 30, tzinfo=timezone.utc)
            s1_workers = TEST_RECURRING_WORKER_PARTITIONS["S1"]
            missing_id = s1_workers[0][0]
            acting_id = s1_workers[1][0]
            for worker_id, label in TEST_RECURRING_WORKERS:
                if worker_id == missing_id:
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
                s1_watch = _bootstrap_fleet_watch(now, worker_id=acting_id)
                s2_watch = _bootstrap_fleet_watch(now, partition="S2")

        self.assertEqual(len(TEST_RECURRING_WORKER_PARTITIONS), 2)
        self.assertEqual({name: len(workers) for name, workers in TEST_RECURRING_WORKER_PARTITIONS.items()}, {"S1": 5, "S2": 5})
        self.assertEqual(global_watch["subscription_count"], 2)
        self.assertEqual(global_watch["expected_recurring_workers"], 10)
        self.assertEqual(global_watch["expected_recurring_workers_total"], 10)
        self.assertEqual(global_watch["worker_partitions"]["S1"]["expected_recurring_workers"], 5)
        self.assertEqual(global_watch["worker_partitions"]["S2"]["expected_recurring_workers"], 5)
        self.assertEqual(s1_watch["subscription_scope"], "S1")
        self.assertEqual(s1_watch["expected_recurring_workers"], 5)
        self.assertEqual(s1_watch["expected_recurring_workers_total"], 10)
        self.assertEqual(s1_watch["recovery_candidate_count"], 1)
        self.assertEqual(s1_watch["recovery_candidates"][0]["automation_id"], missing_id)
        self.assertEqual(s1_watch["recovery_candidates"][0]["subscription_partition"], "S1")
        self.assertEqual(s2_watch["subscription_scope"], "S2")
        self.assertEqual(s2_watch["expected_recurring_workers"], 5)
        self.assertEqual(s2_watch["expected_recurring_workers_total"], 10)
    def test_fleet_watch_does_not_recover_new_worker_before_first_expected_start_plus_grace(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_test_slot_registry(root)
            current = root / "worker-reports" / "current"
            current.mkdir(parents=True)
            now = datetime(2026, 9, 7, 16, 35, tzinfo=timezone.utc)
            target_id, target_label = TEST_RECURRING_WORKER_PARTITIONS["S1"][0]
            actor_id, _ = TEST_RECURRING_WORKER_PARTITIONS["S1"][1]
            first_expected = now + timedelta(minutes=1)
            registry = root / "worker-reports" / ".supervision" / "recurring-slot-bindings.json"
            registry_payload = json.loads(registry.read_text(encoding="utf-8"))
            registry_payload["bindings"]["S1/1"]["first_expected_start_at"] = first_expected.isoformat()
            registry.write_text(json.dumps(registry_payload), encoding="utf-8")
            for worker_id, label in TEST_RECURRING_WORKER_PARTITIONS["S1"]:
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

        pending_target = next(item for item in pending.get("lifecycle_gaps", []) if item.get("automation_id") == target_id) if any(item.get("automation_id") == target_id for item in pending.get("lifecycle_gaps", [])) else None
        self.assertIsNone(pending_target)
        self.assertEqual(pending["first_start_pending"], 1)
        self.assertEqual(pending["recovery_candidate_count"], 0)
        degraded_target = next(item for item in degraded["lifecycle_gaps"] if item["automation_id"] == target_id)
        self.assertEqual(degraded_target["reason"], "NO_LOCAL_START_EVIDENCE")
        self.assertTrue(degraded_target["probe_actionable"])

    def test_fleet_watch_running_without_start_receipt_uses_short_race_grace_then_flags_recovery(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_test_slot_registry(root)
            current = root / "worker-reports" / "current"
            current.mkdir(parents=True)
            now = datetime(2026, 9, 7, 3, 30, tzinfo=timezone.utc)
            target_id, _ = TEST_RECURRING_WORKERS[0]
            for worker_id, label in TEST_RECURRING_WORKERS:
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

        self.assertEqual(pending["status"], "LOCAL_RECOVERY_EVIDENCE")
        self.assertEqual(pending["start_receipt_pending"], 1)
        self.assertEqual(pending["running_report_without_start_receipt"], 0)
        self.assertEqual(pending["recovery_candidate_count"], 0)
        suspect = next(item for item in degraded["lifecycle_gaps"] if item["automation_id"] == target_id)
        self.assertEqual(suspect["reason"], "RUNNING_REPORT_WITHOUT_START_RECEIPT")
        self.assertEqual(suspect["scheduler_probe_status"], "SCHEDULER_PROBE_NEEDED")
        self.assertTrue(suspect["probe_actionable"])
        self.assertEqual(degraded["running_report_without_start_receipt"], 1)
        self.assertEqual(degraded["recovery_candidate_count"], 1)
        self.assertEqual(degraded["scheduler_probe"], "required_before_scheduler_mutation")
        self.assertFalse(degraded["local_evidence_scheduler_mutation_authorized"])
        self.assertTrue(degraded["same_partition_peer_reenable_after_live_scheduler_confirmation"])
        self.assertNotIn("scheduler_mutation_authorized", degraded)
        self.assertTrue(degraded["recovery_candidates"][0]["requires_live_scheduler_probe"])

    def test_fleet_watch_suppresses_duplicate_reenable_after_recent_worker_success(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_test_slot_registry(root)
            current = root / "worker-reports" / "current"
            current.mkdir(parents=True)
            now = datetime.now(timezone.utc)
            stale_id, stale_label = TEST_RECURRING_WORKERS[0]
            actor_id, actor_label = TEST_RECURRING_WORKERS[1]

            for worker_id, label in TEST_RECURRING_WORKERS:
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

        suspect = next(item for item in watch["lifecycle_gaps"] if item["automation_id"] == stale_id)
        self.assertEqual(suspect["scheduler_probe_status"], "SCHEDULER_PROBE_PENDING")
        self.assertFalse(suspect["probe_actionable"])
        self.assertEqual(suspect["last_recovery"]["actor_id"], actor_id)
        self.assertEqual(watch["recovery_candidate_count"], 0)
        self.assertEqual(watch["recovery_candidates"], [])
        self.assertEqual(watch["scheduler_probe"], "not_performed")

    def test_fleet_watch_accepts_pre_token_success_finding_for_cooldown(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_test_slot_registry(root)
            current = root / "worker-reports" / "current"
            current.mkdir(parents=True)
            now = datetime.now(timezone.utc)
            stale_id, stale_label = TEST_RECURRING_WORKERS[0]
            actor_id, actor_label = TEST_RECURRING_WORKERS[1]

            for worker_id, label in TEST_RECURRING_WORKERS:
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

        suspect = next(item for item in watch["lifecycle_gaps"] if item["automation_id"] == stale_id)
        self.assertEqual(suspect["scheduler_probe_status"], "SCHEDULER_PROBE_PENDING")
        self.assertEqual(suspect["last_recovery"]["actor_id"], actor_id)
        self.assertEqual(suspect["last_recovery"]["recovered_at"], (now - timedelta(minutes=20)).isoformat())
        self.assertEqual(watch["recovery_candidate_count"], 0)

    def test_fleet_watch_retries_after_recovered_worker_misses_next_observed_hourly_phase(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_test_slot_registry(root)
            current = root / "worker-reports" / "current"
            current.mkdir(parents=True)
            now = datetime(2026, 9, 7, 3, 26, tzinfo=timezone.utc)
            stale_id, stale_label = TEST_RECURRING_WORKERS[0]
            actor_id, actor_label = TEST_RECURRING_WORKERS[1]
            stale_started = datetime(2026, 9, 7, 1, 15, tzinfo=timezone.utc)
            recovered_at = datetime(2026, 9, 7, 3, 10, tzinfo=timezone.utc)
            for worker_id, label in TEST_RECURRING_WORKERS:
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

        suspect = next(item for item in watch["lifecycle_gaps"] if item["automation_id"] == stale_id)
        self.assertEqual(suspect["scheduler_probe_status"], "SCHEDULER_PROBE_RETRY_NEEDED")
        self.assertTrue(suspect["probe_actionable"])
        self.assertEqual(
            suspect["scheduler_probe_pending_until"],
            datetime(2026, 9, 7, 3, 25, tzinfo=timezone.utc).isoformat(),
        )
        self.assertEqual(watch["recovery_candidate_count"], 1)

    def test_fleet_watch_old_recovery_does_not_suppress_newer_start_then_later_miss(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_test_slot_registry(root)
            current = root / "worker-reports" / "current"
            current.mkdir(parents=True)
            now = datetime(2026, 9, 7, 5, 30, tzinfo=timezone.utc)
            stale_id, stale_label = TEST_RECURRING_WORKERS[0]
            actor_id, actor_label = TEST_RECURRING_WORKERS[1]
            recovered_at = datetime(2026, 9, 7, 3, 10, tzinfo=timezone.utc)
            newer_start = datetime(2026, 9, 7, 4, 15, tzinfo=timezone.utc)
            for worker_id, label in TEST_RECURRING_WORKERS:
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

        suspect = next(item for item in watch["lifecycle_gaps"] if item["automation_id"] == stale_id)
        self.assertEqual(suspect["scheduler_probe_status"], "SCHEDULER_PROBE_NEEDED")
        self.assertTrue(suspect["probe_actionable"])
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
                    "automation_id": TEST_RECURRING_WORKERS[index][0], "display_label": TEST_RECURRING_WORKERS[index][1],
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

    def test_worker_status_does_not_promote_fleet_watch_into_bootstrap_liveness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_test_slot_registry(root)
            metrics = root / "worker-reports" / "metrics.json"
            metrics.parent.mkdir(parents=True, exist_ok=True)
            metrics.write_text(json.dumps({
                "schema": "worker-report-metrics.v1", "population": "timed",
                "generated_at": "2026-09-13T03:00:00+00:00", "window_hours": 24.0, "latest_reports": [],
            }), encoding="utf-8")
            with patch("tools.stack_atlas.ATLAS_LIVE_ROOT", root), \
                 patch("tools.stack_atlas._bootstrap_manual_sanity", return_value={"available": False}), \
                 patch("tools.stack_atlas._bootstrap_fleet_watch", side_effect=AssertionError("worker status must not infer liveness from fleet-watch")) as fleet_watch:
                workers = _bootstrap_worker_status()
            fleet_watch.assert_not_called()
        self.assertTrue(workers["available"])
        self.assertNotIn("fleet_watch", workers)
        self.assertNotIn("recurring_scheduler_recovery", workers)

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
                    {"automation_id": TEST_RECURRING_WORKERS[0][0], "display_label": "Recent", "finished_at": (now - timedelta(minutes=30)).isoformat(), "duration_minutes": 12.0, "target_utilization_pct": 50.0},
                    {"automation_id": TEST_RECURRING_WORKERS[1][0], "display_label": "Stale", "finished_at": (now - timedelta(minutes=120)).isoformat(), "duration_minutes": 4.0, "target_utilization_pct": 16.7},
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

    def test_manual_current_diagnostic_surfaces_exact_binding_without_promoting_report_to_liveness(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manual_root = root / "worker-reports" / "manual"
            current = manual_root / "current"
            bindings = manual_root / "bindings"
            current.mkdir(parents=True)
            bindings.mkdir(parents=True)
            now = datetime.now(timezone.utc)
            run_id = "manual-bound"
            report = current / f"{run_id}.md"
            report.write_text(
                "\n".join([
                    f"run_id: {run_id}",
                    f"started_at: {(now - timedelta(minutes=2)).isoformat()}",
                    f"last_activity_at: {(now - timedelta(minutes=1)).isoformat()}",
                    r"repo: C:\repo",
                    "scope: exact binding bootstrap test",
                    "state: RUNNING",
                    "",
                ]),
                encoding="utf-8",
            )
            bindings.joinpath(f"{run_id}.json").write_text(json.dumps({
                "schema": "manual-run-binding.v1",
                "run_id": run_id,
                "authority": "EXACT_MCP_IDENTITY_EVIDENCE_NOT_WORK_LIVENESS",
                "caller_id": "caller-bound",
                "create_process_id": "process-create",
                "create_started_at": (now - timedelta(minutes=2)).isoformat(),
            }), encoding="utf-8")
            with patch("tools.stack_atlas.ATLAS_LIVE_ROOT", root):
                manual = _bootstrap_manual_current_status(now)

        item = manual["recent_running_reports"][0]
        self.assertEqual(item["identity"]["caller_id"], "caller-bound")
        self.assertEqual(item["identity"]["create_process_id"], "process-create")
        self.assertIn("not_process_liveness", manual["evidence_semantics"])

    def test_exact_manual_identity_requires_live_caller_and_newest_bound_run_wins(self):
        from tools.stack_atlas import _bootstrap_active_manual_run_identities
        manual = {
            "recent_running_reports": [
                {"run_id": "manual-old", "identity": {"caller_id": "caller-live", "create_process_id": "proc-old", "create_started_at": "2026-09-09T06:00:00+00:00"}},
                {"run_id": "manual-new", "identity": {"caller_id": "caller-live", "create_process_id": "proc-new", "create_started_at": "2026-09-09T06:05:00+00:00"}},
                {"run_id": "manual-report-only", "identity": {"caller_id": "caller-not-live", "create_process_id": "proc-stale", "create_started_at": "2026-09-09T06:06:00+00:00"}},
            ]
        }
        live = {
            "lanes": [{
                "callers": [{
                    "caller_id": "caller-live",
                    "last_activity_age_seconds": 2.0,
                    "latest_process": {"end_observed": False, "elapsed_seconds": 12.0, "semantics": "since_start_no_end_observed"},
                }]
            }]
        }
        result = _bootstrap_active_manual_run_identities(manual, live)
        self.assertEqual(len(result["runs"]), 1)
        self.assertEqual(result["runs"][0]["run_id"], "manual-new")
        self.assertEqual(result["runs"][0]["create_process_id"], "proc-new")
        self.assertNotIn("manual-report-only", json.dumps(result))
        self.assertNotIn("manual-old", json.dumps(result))

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
                    {"automation_id": TEST_RECURRING_WORKERS[index][0], "display_label": TEST_RECURRING_WORKERS[index][1], "finished_at": now.isoformat(), "duration_minutes": 20.0, "target_utilization_pct": 83.3}
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
        health_probe.assert_called_once_with(snapshot)
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
             patch("tools.stack_atlas._run_process", return_value=completed) as run:
            first = _bootstrap_github_status()
            with patch("tools.stack_atlas._run_process", side_effect=AssertionError("warm cache must not spawn gh")):
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
             patch("tools.stack_atlas._run_process", side_effect=[api_failure, auth_ok]) as run:
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
        with patch("tools.stack_atlas._run_process", return_value=completed) as run:
            __import__("tools.stack_atlas", fromlist=["_powershell_json"])._powershell_json("Get-Process")
        self.assertEqual(run.call_args.kwargs["timeout"], 5)

    def test_live_powershell_probe_timeout_is_explicit(self):
        timeout = __import__("subprocess").TimeoutExpired(["powershell"], 5)
        with patch("tools.stack_atlas._run_process", side_effect=timeout):
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

    def test_runtime_root_override_keeps_deployed_atlas_bound_to_canonical_repo(self):
        import runpy
        script = Path(__file__).resolve().parents[1] / 'tools' / 'stack_atlas.py'
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'STACK_ATLAS_ROOT_OVERRIDE': tmp}):
            namespace = runpy.run_path(str(script))
        self.assertEqual(namespace['ROOT'], Path(tmp).resolve())

    def test_bootstrap_git_timeout_covers_loaded_windows_process_startup(self):
        from tools.stack_atlas import BOOTSTRAP_GIT_COMMAND_TIMEOUT_SECONDS
        self.assertEqual(BOOTSTRAP_GIT_COMMAND_TIMEOUT_SECONDS, 3.0)

    def test_bootstrap_source_freshness_git_probes_share_one_deadline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agents = root / "agents"
            vault = root / "vault"
            agents.mkdir()
            contract = vault / "04 Operating Contracts" / "fresh-worker-generation-launch.md"
            contract.parent.mkdir(parents=True)
            (agents / "AGENTS.md").write_text("agents\n", encoding="utf-8")
            (agents / "RULES.md").write_text("rules\n", encoding="utf-8")
            contract.write_text("worker\n", encoding="utf-8")
            remote_metadata = {
                "canonical_agents_checkout": {"remote_main": "a" * 40},
                "AGENTS.md": {"remote_blob": "b" * 40, "last_updated_at": "2026-09-11T00:00:00Z", "last_update_commit": "c" * 40},
                "RULES.md": {"remote_blob": "d" * 40, "last_updated_at": "2026-09-11T00:00:00Z", "last_update_commit": "e" * 40},
                "worker_report_contract": {"remote_blob": "f" * 40, "last_updated_at": "2026-09-11T00:00:00Z", "last_update_commit": "1" * 40},
            }
            calls = []

            def slow_timeout(*args, **kwargs):
                timeout = float(kwargs["timeout"])
                calls.append(timeout)
                time.sleep(timeout + 0.02)
                raise subprocess.TimeoutExpired(args[0], timeout)

            with patch("tools.stack_atlas.AGENT_RULES_ROOT", str(agents)), \
                 patch("tools.stack_atlas.ROOT", vault), \
                 patch("tools.stack_atlas.BOOTSTRAP_GIT_COMMAND_TIMEOUT_SECONDS", 0.05), \
                 patch("tools.stack_atlas.BOOTSTRAP_SOURCE_FRESHNESS_LOCAL_GIT_BUDGET_SECONDS", 0.05), \
                 patch("tools.stack_atlas._bootstrap_cache_read_any", return_value=(remote_metadata, 0.1)), \
                 patch("tools.stack_atlas._bootstrap_cache_refresh_view", return_value=(remote_metadata, False)), \
                 patch("tools.stack_atlas._run_process", side_effect=slow_timeout):
                started = time.monotonic()
                result = _bootstrap_source_freshness()
                elapsed = time.monotonic() - started

            self.assertEqual(len(calls), 1)
            self.assertLess(elapsed, 0.25)
            self.assertEqual(result["canonical_checkout"]["coherence_basis"], "git_probe_timeout")
            self.assertTrue(result["attention_required"])

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
        self.assertTrue(timeline["entrypoints"][0].startswith("python tools\\stack_atlas.py find"))
        self.assertTrue(any("drill-down only:" in entry and "memory_bank.py timeline" in entry for entry in timeline["entrypoints"]))
        self.assertIn("Unified discovery starts with Stack Atlas find", timeline["boundary"])
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
        self.assertIn("not live progress telemetry", reports["boundary"])
        self.assertIn("may be updated at material natural checkpoints", reports["boundary"])
        self.assertIn("reviewed.json", " ".join(component_details("worker_reports")["live_status"]))
        self.assertIn(r"C:\P3Proofs", " ".join(component_details("worker_reports")["live_status"]))
        self.assertIn("not live progress telemetry", " ".join(component_details("worker_reports")["live_status"]))
        self.assertIn("may be updated at material natural checkpoints", " ".join(component_details("worker_reports")["live_status"]))
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

    def test_unified_find_composes_atlas_live_history_and_runtime_graph_without_changing_find_features(self):
        atlas_before = find_features("commander fallback", limit=2)
        live = [{"kind": "live_workspace", "workspace": "ponytail-upstream-read-20260911"}]
        history = [{"kind": "github_issue", "reference": "organicoverlords/regression-research#861"}]
        runtime_graph = [{"surface_id": "vault.bootstrap_snapshot", "status": "OK"}]
        with patch("tools.stack_atlas._live_discovery_hits", return_value=(live, {"status": "OK"})), \
                patch("tools.stack_atlas._timeline_discovery_hits", return_value=(history, {"status": "OK"})), \
                patch("tools.stack_atlas._search_gh_buffer_cache", return_value=([], {"status": "OK"})), \
                patch("tools.stack_atlas._runtime_graph_search_safe", return_value=(runtime_graph, {"status": "OK", "broad_task_enumeration": False})):
            result = unified_find("commander fallback", limit=2)
        self.assertEqual(result["schema"], "stack-atlas.discovery.v1")
        self.assertEqual(result["atlas_hits"], atlas_before)
        self.assertEqual(result["live_hits"], live)
        self.assertEqual(result["history_hits"], history)
        self.assertEqual(result["runtime_graph_hits"], runtime_graph)
        self.assertFalse(result["coverage"]["runtime_graph"]["broad_task_enumeration"])
        self.assertEqual(find_features("commander fallback", limit=2), atlas_before)
        self.assertIn("Discovery only", result["boundary"])

    def test_runtime_deployment_graph_is_discoverable_inside_unified_find_model(self):
        feature = find_features("runtime deployment graph", limit=3)[0]
        self.assertEqual(feature["id"], "runtime.deployment_graph")
        self.assertIn("one unified find surface", feature["boundary"])
        self.assertIn("No recursive scan", feature["boundary"])

    def test_bootstrap_snapshot_lookup_attaches_same_runtime_graph_surface(self):
        graph = {
            "schema": "stack-atlas.runtime-deployment-graph.v1",
            "surfaces": [{"surface_id": "vault.bootstrap_snapshot", "status": "OK"}],
            "coverage": {"status": "OK"},
        }
        with patch("tools.stack_atlas._runtime_graph_for_components_safe", return_value=graph) as runtime_graph:
            result = atlas_lookup("bootstrap snapshot")
        self.assertEqual(result["id"], "bootstrap_snapshot")
        self.assertEqual(result["runtime_graph"], graph)
        runtime_graph.assert_called_once_with(["bootstrap_snapshot"])

    def test_worktree_hygiene_lookup_attaches_runtime_graph_surface(self):
        graph = {
            "schema": "stack-atlas.runtime-deployment-graph.v1",
            "surfaces": [{"surface_id": "vault.worktree_hygiene", "status": "OK"}],
            "coverage": {"status": "OK"},
        }
        with patch("tools.stack_atlas._runtime_graph_for_components_safe", return_value=graph) as runtime_graph:
            result = atlas_lookup("worktree hygiene")
        self.assertEqual(result["id"], "worktree_hygiene")
        self.assertIn("VaultWorktreeHygiene", " ".join(result["live_status"]))
        self.assertEqual(result["runtime_graph"], graph)
        runtime_graph.assert_called_once_with(["worktree_hygiene"])

    def test_live_discovery_distinguishes_busy_handoff_from_runtime_caller_activity(self):
        snapshot = {
            "available": True,
            "evidence": {"source_age_seconds": 1.0, "busy_source_age_seconds": 2.0, "activity_window_seconds": 300, "observation_window_complete": True},
            "lanes": [
                {
                    "lane_id": "busy:issue301",
                    "workspace": None,
                    "worktree": None,
                    "busy": [{
                        "owner": "ChatGPT:issue301-image-library-work-20260912",
                        "checkpoint": "Issue #301 image/video/zip Library + Work fix",
                        "scopes": ["repo:ChatGPTMcpClean:file:src/lib/file-transfer.ts"],
                        "last_update_age_seconds": 3.0,
                    }],
                    "callers": [],
                },
                {
                    "lane_id": "wt:mcp",
                    "workspace": "MCP",
                    "worktree": {"branch": "fix/242-stall-watchdog", "path": "C:/work/ChatGPTMcpClean"},
                    "busy": [],
                    "callers": [{"caller_id": "caller_watchdog", "command": "output schema probe", "last_activity_age_seconds": 4.0}],
                },
            ],
        }
        busy_hits, coverage = _live_discovery_hits("issue 301 library", snapshot=snapshot)
        self.assertEqual(busy_hits[0]["kind"], "busy_handoff")
        self.assertEqual(busy_hits[0]["authority"], "BUSY_COORDINATION_EVIDENCE")
        self.assertEqual(busy_hits[0]["liveness_semantics"], "not_worker_liveness_or_progress")
        self.assertEqual(coverage["busy_semantics"], "coordination_handoff_only_not_worker_liveness_or_progress")
        caller_hits, _ = _live_discovery_hits("stall watchdog output schema", snapshot=snapshot)
        self.assertEqual(caller_hits[0]["kind"], "caller_activity")
        self.assertEqual(caller_hits[0]["authority"], "LIVE_MCP_RUNTIME_EVIDENCE")
        semantic_hits, _ = _live_discovery_hits("MCP kuvahommeli", snapshot=snapshot)
        self.assertEqual(semantic_hits[0]["kind"], "busy_handoff")
        self.assertIn("image", semantic_hits[0]["matched_terms"])
        self.assertIn("mcp", semantic_hits[0]["matched_terms"])

    def test_timeline_discovery_index_dedupes_issue_snapshots_and_artifact_lineage(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            state = root / ".state" / "timeline"
            state.mkdir(parents=True)
            generated = "2026-09-11T22:26:16+03:00"
            (state / "status.json").write_text(json.dumps({
                "generated_at": generated,
                "events": 6,
                "truncated": False,
                "saturated_sources": [],
            }), encoding="utf-8")
            ids = [
                "github-issue:organicoverlords/regression-research#861:2026-09-09T10:46:29Z",
                "github-issue:organicoverlords/regression-research#861:2026-09-09T09:48:50Z",
                "artifact:aaa:01 Reports/2026-09-09_issue-861_busy-dual-runtime-yagni-audit.md",
                "artifact:bbb:01 Reports/2026-09-09_issue-861_busy-dual-runtime-yagni-audit.md",
            ]
            import pickle
            with (state / "timeline-query-index.pkl").open("wb") as handle:
                pickle.dump({
                    "schema": "vault.timeline.query-index.v1",
                    "generated_at": generated,
                    "ids": ids,
                    "postings": {"yagni": [0, 1, 2, 3]},
                    "weight_codes": {"yagni": bytes([5, 5, 5, 5])},
                    "anchors": [
                        ["github:organicoverlords/regression-research#861"],
                        ["github:organicoverlords/regression-research#861"],
                        ["artifact:01 reports/2026-09-09_issue-861_busy-dual-runtime-yagni-audit.md"],
                        ["artifact:01 reports/2026-09-09_issue-861_busy-dual-runtime-yagni-audit.md"],
                    ],
                }, handle)
            hits, coverage = _timeline_discovery_hits("yagni", limit=5, root=root)
        self.assertEqual(coverage["status"], "OK")
        self.assertEqual(coverage["candidate_count"], 4)
        self.assertEqual([hit["kind"] for hit in hits], ["github_issue", "tracked_artifact"])
        self.assertEqual(hits[0]["reference"], "organicoverlords/regression-research#861")
        self.assertEqual(hits[1]["reference"], "01 Reports/2026-09-09_issue-861_busy-dual-runtime-yagni-audit.md")

    def test_timeline_discovery_surfaces_opaque_labels_from_query_index_only(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            state = root / ".state" / "timeline"
            state.mkdir(parents=True)
            generated = "2026-09-12T02:11:56+03:00"
            (state / "status.json").write_text(json.dumps({"generated_at": generated, "events": 2, "truncated": False, "saturated_sources": []}), encoding="utf-8")
            ids = ["mem-20260912-abc", "worker:deadbeef"]
            import pickle
            with (state / "timeline-query-index.pkl").open("wb") as handle:
                pickle.dump({
                    "schema": "vault.timeline.query-index.v1",
                    "generated_at": generated,
                    "ids": ids,
                    "postings": {"asshole": [0, 1]},
                    "weight_codes": {"asshole": bytes([5, 5])},
                    "anchors": [[], []],
                    "opaque_labels": {ids[0]: "Lightweight asshole correction marker", ids[1]: "Repo Worker Alder #S2"},
                }, handle)
            hits, coverage = _timeline_discovery_hits("asshole", limit=5, root=root)
        self.assertEqual(coverage["status"], "OK")
        self.assertEqual({hit["label"] for hit in hits}, {"Lightweight asshole correction marker", "Repo Worker Alder #S2"})
        self.assertEqual({hit["kind"] for hit in hits}, {"vault_memory", "worker_report"})

    def test_timeline_discovery_exact_missing_memory_is_reference_only_not_fabricated_object(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            state = root / ".state" / "timeline"
            state.mkdir(parents=True)
            generated = "2026-09-12T03:20:00+03:00"
            memory_id = "mem-20260912-dce895b5"
            commit_id = "git:vault:" + "a" * 40
            (state / "status.json").write_text(json.dumps({"generated_at": generated, "events": 1, "truncated": False, "saturated_sources": []}), encoding="utf-8")
            import pickle
            with (state / "timeline-query-index.pkl").open("wb") as handle:
                pickle.dump({
                    "schema": "vault.timeline.query-index.v1",
                    "generated_at": generated,
                    "ids": [commit_id],
                    "postings": {"mem": [0], "20260912": [0], "dce895b5": [0]},
                    "weight_codes": {"mem": bytes([5]), "20260912": bytes([5]), "dce895b5": bytes([5])},
                    "anchors": [[]],
                    "branch_refs": [["main"]],
                    "event_meta": [{
                        "source_type": "GIT_COMMIT", "project": "vault", "event_at": "2026-09-12T00:00:00Z",
                        "title": f"Reference {memory_id}", "summary": "memory correction reference", "authority": "LOCAL_GIT_HISTORY",
                        "terms": ["mem", "20260912", "dce895b5"], "details": {},
                    }],
                }, handle)
            hits, coverage = _timeline_discovery_hits(memory_id, limit=5, root=root)
        self.assertEqual(coverage["status"], "OK")
        self.assertEqual(hits[0]["kind"], "referenced_identity")
        self.assertEqual(hits[0]["reference"], memory_id)
        self.assertFalse(hits[0]["materialized_object_present"])
        self.assertEqual(hits[0]["authority"], "SEARCH_REFERENCE_ONLY_NOT_OBJECT_TRUTH")
        self.assertTrue(any(row.get("kind") == "git_commit" for row in hits[0]["referenced_by"]))

    def test_timeline_discovery_evidence_cluster_mixes_runtime_git_github_and_worker_without_merging_truth(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            state = root / ".state" / "timeline"
            state.mkdir(parents=True)
            generated = "2026-09-12T03:20:00+03:00"
            worker_id = "worker:" + "b" * 64
            ids = [
                "mcp-transport:stable:req1",
                "git:chatgptmcpclean:" + "a" * 40,
                "github-issue:organicoverlords/chatgpt-mcp-clean#999:2026-09-12T00:01:00Z",
                worker_id,
            ]
            times = ["2026-09-12T00:00:00Z", "2026-09-12T00:00:30Z", "2026-09-12T00:01:00Z", "2026-09-12T00:01:30Z"]
            source_types = ["MCP_EVENT", "GIT_COMMIT", "GITHUB_ISSUE", "WORKER_REPORT"]
            titles = ["MCP marker upload status 200", "marker upload implementation", "marker upload acceptance", "marker upload acceptance report"]
            (state / "status.json").write_text(json.dumps({"generated_at": generated, "events": 4, "truncated": False, "saturated_sources": []}), encoding="utf-8")
            import pickle
            with (state / "timeline-query-index.pkl").open("wb") as handle:
                pickle.dump({
                    "schema": "vault.timeline.query-index.v1",
                    "generated_at": generated,
                    "ids": ids,
                    "postings": {"marker": [0, 1, 2, 3], "upload": [0, 1, 2, 3]},
                    "weight_codes": {"marker": bytes([5, 5, 5, 5]), "upload": bytes([5, 5, 5, 5])},
                    "anchors": [["process:p1"], ["gitsha:" + "a" * 40], ["github:organicoverlords/chatgpt-mcp-clean#999"], []],
                    "branch_refs": [[], ["fix/marker-upload"], [], []],
                    "opaque_labels": {worker_id: "manual marker upload acceptance"},
                    "event_meta": [
                        {"source_type": source_types[i], "project": "chatgptmcpclean", "event_at": times[i], "title": titles[i], "summary": titles[i], "authority": f"AUTH_{source_types[i]}", "terms": ["marker", "upload"], "details": {"tool": "upload_local_file", "status": 200} if i == 0 else {}}
                        for i in range(4)
                    ],
                }, handle)
            hits, coverage = _timeline_discovery_hits("marker upload", limit=5, root=root)
        self.assertEqual(coverage["status"], "OK")
        clusters = coverage["evidence_clusters"]
        self.assertTrue(clusters)
        cluster = clusters[0]
        self.assertEqual(cluster["authority"], "SEARCH_CORRELATION_ONLY_NOT_SHARED_TRUTH")
        kinds = {member["kind"] for member in cluster["members"]}
        self.assertTrue({"mcp_event", "git_commit", "github_issue", "worker_report"}.issubset(kinds))
        git_member = next(member for member in cluster["members"] if member["kind"] == "git_commit")
        self.assertIn("fix/marker-upload", git_member["branches"])
        runtime_member = next(member for member in cluster["members"] if member["kind"] == "mcp_event")
        self.assertEqual(runtime_member["details"]["tool"], "upload_local_file")
        self.assertEqual(runtime_member["details"]["status"], 200)
        self.assertTrue(all(member["relationship"] in {"seed", "same_project_time_window", "shared_anchor"} for member in cluster["members"]))

    def test_timeline_discovery_resolves_exact_manual_worker_report_hash_or_path(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            state = root / ".state" / "timeline"
            state.mkdir(parents=True)
            generated = "2026-09-12T03:20:00+03:00"
            worker_hash = "229f46e6d59fdafe226c05834a8d022cb6e0bea4fa02029efb11357a56e6ecf2"
            worker_id = f"worker:{worker_hash}"
            (state / "status.json").write_text(json.dumps({"generated_at": generated, "events": 1, "truncated": False, "saturated_sources": []}), encoding="utf-8")
            import pickle
            with (state / "timeline-query-index.pkl").open("wb") as handle:
                pickle.dump({
                    "schema": "vault.timeline.query-index.v1",
                    "generated_at": generated,
                    "ids": [worker_id],
                    "postings": {},
                    "weight_codes": {},
                    "anchors": [[]],
                    "opaque_labels": {worker_id: "manual marker handoff report repair"},
                }, handle)
            hits, coverage = _timeline_discovery_hits(
                f"worker-reports/manual/history/_reports/{worker_hash}.md", limit=5, root=root
            )
        self.assertEqual(coverage["status"], "OK")
        self.assertEqual(hits[0]["kind"], "worker_report")
        self.assertEqual(hits[0]["reference"], worker_id)
        self.assertEqual(hits[0]["label"], "manual marker handoff report repair")
        self.assertGreaterEqual(hits[0]["score"], 100.0)

    def test_timeline_discovery_boosts_explicit_issue_number_over_textual_neighbor(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            state = root / ".state" / "timeline"
            state.mkdir(parents=True)
            generated = "2026-09-12T02:22:00+03:00"
            (state / "status.json").write_text(json.dumps({"generated_at": generated, "events": 2, "truncated": False, "saturated_sources": []}), encoding="utf-8")
            ids = [
                "github-issue:organicoverlords/chatgpt-mcp-clean#301:2026-09-12T00:00:00Z",
                "github-issue:organicoverlords/chatgpt-mcp-clean#248:2026-09-11T00:00:00Z",
            ]
            import pickle
            with (state / "timeline-query-index.pkl").open("wb") as handle:
                pickle.dump({
                    "schema": "vault.timeline.query-index.v1",
                    "generated_at": generated,
                    "ids": ids,
                    "postings": {"issue": [0, 1], "301": [0], "library": [0, 1], "file": [1], "transfer": [1]},
                    "weight_codes": {"issue": bytes([2, 2]), "301": bytes([2]), "library": bytes([3, 5]), "file": bytes([5]), "transfer": bytes([5])},
                    "anchors": [["github:organicoverlords/chatgpt-mcp-clean#301"], ["github:organicoverlords/chatgpt-mcp-clean#248"]],
                }, handle)
            hits, _ = _timeline_discovery_hits("issue 301 library file transfer", limit=5, root=root)
        self.assertEqual(hits[0]["reference"], "organicoverlords/chatgpt-mcp-clean#301")

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

    def test_github_runner_exposes_explicit_control_and_intent(self):
        details = component_details("github_runner")
        self.assertIn(r"C:\Users\Lauri\.agents\Manage-GitHubRunner.ps1", details["canonical_sources"])
        self.assertIn(r"C:\Users\Lauri\.agents\Start-GitHubRunnerHidden.ps1", details["canonical_sources"])
        self.assertIn("runtime_control", details["capabilities"])
        self.assertIn("Status", details["control"]["actions"])
        self.assertIn("AutostartOn", details["control"]["actions"])
        self.assertEqual(details["control"]["intent_semantics"]["off"], "task disabled intentionally")
        self.assertIn("-Action Status", " ".join(details["live_status"]))
        remote = details["remote_linux_provisioning"]
        self.assertEqual(remote["node"], "omen-linux-laptop")
        self.assertIn("Install-GitHubRunnerOmen.sh", remote["installer"])
        self.assertIn("authenticated Windows gh", remote["credential_route"])
        self.assertIn("directly over authenticated SSH", remote["credential_route"])
        self.assertIn("never expose", remote["credential_route"])
        self.assertIn("read-only acceleration only", remote["gh_buffer_boundary"])
        self.assertIn("does not block runner provisioning", remote["gh_buffer_boundary"])
        self.assertIn("restart-on-failure loops are not a recovery mechanism", details["self_heal"])

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

    def test_mcp_minimal_clone_pins_five_tools_plus_exact_original_image_resource(self):
        details = component_details("mcp_minimal_clone")
        surface = details["chatgpt_plugin_surface"]
        self.assertEqual(surface["profile"], "process")
        self.assertEqual(surface["tool_count"], 5)
        self.assertEqual(surface["tools"], ["start_process", "read_output", "kill_process", "upload_local_file", "download_chatgpt_file"])
        self.assertTrue(surface["image_delivery"]["adds_tool"])
        self.assertEqual(surface["image_delivery"]["upload_tool"], "upload_local_file")
        self.assertEqual(surface["image_delivery"]["widget_resource"], "ui://process/file-transfer-v1.html")
        self.assertTrue(surface["image_delivery"]["default_visual_retrieval"])
        self.assertIn("all workers/projects", surface["image_delivery"]["default_scope"])
        self.assertTrue(any("upload_local_file" in step for step in surface["image_delivery"]["sequence"]))
        self.assertTrue(any("native vision" in step for step in surface["image_delivery"]["sequence"]))
        for excluded in ("busy_list", "view_image", "open_visual_proof"):
            self.assertIn(excluded, surface["excluded_actions"])
        self.assertNotIn("conditional_ui", surface)
        self.assertIn("exactly five process-profile tools", surface["boundary"])
        status = " ".join(details["live_status"])
        self.assertEqual(details["current_topology"]["connector_url"], "https://91-159-12-133.sslip.io/mcp")
        self.assertIn("mcp-current-topology.v1", status)
        self.assertEqual(details["current_topology"]["status"], "OK")
        contract = json.loads((ROOT / "04 Operating Contracts" / "mcp-current-topology.json").read_text(encoding="utf-8"))
        self.assertIn(contract["serving"]["backend"]["listen"], details["current_topology"]["serving_path"])
        self.assertIn("5-61-91-127.sslip.io", details["current_topology"]["excluded_from_gpt1_path"])

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

    def test_nexus_and_devboard_resolve_through_first_class_navigation(self):
        for alias in ("nexus", "devboard", "dev progress board"):
            with self.subTest(alias=alias):
                details = atlas_lookup(alias)
                self.assertEqual(details["id"], "project.nexus_navigation")
                self.assertEqual(details["kind"], "feature_navigation")
                self.assertEqual(details["owner_components"], ["north_star", "local_git", "github"])
                joined = " ".join(details["entrypoints"])
                self.assertIn(os.path.expandvars(r"%LOCALAPPDATA%\nexus"), joined)
                self.assertIn("docs/repos/dev-progress-board/NORTH_STAR.md", joined)
                self.assertIn("organicoverlords/nexus", joined)
                self.assertIn("Navigation only", details["boundary"])
                self.assertIn("remain implementation/runtime authority", details["boundary"])
                self.assertIn("must not infer Nexus liveness", details["boundary"])

        self.assertEqual(find_features("nexus", limit=1)[0]["id"], "project.nexus_navigation")
        self.assertEqual(find_features("devboard", limit=1)[0]["id"], "project.nexus_navigation")

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
        for alias in ("shared_visual_library", "chatgpt_visual_library", "shared_chat_proof", "12-view", "12 view", "turnaround sheet", "multiview sheet", "standardized 12-view", "standardized 12 views", "canonical 12-view set", "review contact sheet"):
            with self.subTest(alias=alias):
                details = atlas_lookup(alias)
                self.assertEqual(details["id"], "project.shared_visual_library_integration")
                self.assertEqual(details["kind"], "feature_navigation")
                self.assertEqual(details["related_features"]["task_history"], "vault.history")
                self.assertEqual(details["related_features"]["tiny3d_library"], "project.tiny3d_asset_library")
                self.assertEqual(details["related_features"]["p3_visual_evidence"], "project.p3_visual_evidence")
                self.assertEqual(details["related_features"]["chatgpt_visual_transport"], "mcp.chatgpt_plugin_surface")
                self.assertEqual(details["shared_chat_display_state"], "MCP_EXACT_ORIGINAL_UPLOAD_THEN_NATIVE_INSPECTION")
                self.assertTrue(any("memory_bank.py context" in item for item in details["entrypoints"]))
                self.assertTrue(any("lookup tiny3d_library" in item for item in details["entrypoints"]))
                self.assertTrue(any("upload_local_file" in item for item in details["entrypoints"]))
                self.assertTrue(any("historical/non-canonical review lineage only" in item for item in details["entrypoints"]))
                self.assertIn("every worker/project", details["boundary"])
                self.assertIn("upload_local_file", details["boundary"])
                self.assertIn("native vision", details["boundary"])
                self.assertIn("thumbnail is UI-only", details["boundary"])
                self.assertIn("original/highest-resolution producer 12-view sheet is one transfer/review unit", details["boundary"])
                self.assertIn("inspect all twelve panels thoroughly", details["boundary"])
                self.assertIn("12 separate crop/transfer operations", details["boundary"])
                self.assertIn("complete standardized 12-view set already exists as canonical individual images", details["boundary"])
                self.assertIn("transient ZIP+manifest payload", details["boundary"])
                self.assertIn("Never create a reviewer-authored contact sheet", details["boundary"])
                self.assertIn("background, exposure, lighting, crop, scale/resolution, tone/color, or panel layout", details["boundary"])
                self.assertIn("owning renderer/grid builder's canonical standardized output", details["boundary"])
                self.assertIn("per-view crop/transfer is exception-only", details["boundary"])
                self.assertIn("Do not prefer Drive/Library", details["boundary"])
                self.assertNotIn("first-party connected Google Drive", details["boundary"])

        result = find_features(
            "make the library integrated so I can inspect a stored proof picture and show the same picture here",
            limit=1,
        )
        self.assertEqual(result[0]["id"], "project.shared_visual_library_integration")
        for query in ("review this 12-view render", "inspect the 12 view asset", "transfer the turnaround sheet", "review the multiview sheet", "use the standardized 12-view instead of making a contact sheet", "inspect the canonical 12-view set"):
            with self.subTest(query=query):
                self.assertEqual(find_features(query, limit=1)[0]["id"], "project.shared_visual_library_integration")

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
        expected = render_manual().replace(str(ROOT), r"C:\Users\Lauri\Desktop\vault") + "\n"
        self.assertEqual(manual.read_text(encoding="utf-8"), expected)
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
        self.assertIn("mcp_current_topology", glance)
        current = glance["mcp_current_topology"]
        self.assertTrue(current["available"])
        self.assertEqual(current["authority"], "current_serving_topology")
        self.assertEqual(current["connector_url"], "https://91-159-12-133.sslip.io/mcp")
        self.assertEqual(current["tool_count"], 5)
        self.assertEqual(current["tools"], ["start_process", "read_output", "kill_process", "upload_local_file", "download_chatgpt_file"])
        self.assertTrue(current["image_delivery_adds_tool"])
        self.assertIn("mcp_recovery_state", glance)
        if glance["mcp_recovery_state"]["available"]:
            recovery = glance["mcp_recovery_state"]
            self.assertEqual(recovery["read_state"], "OK")
            self.assertEqual(recovery["authority"], "recovery_target_not_live_serving_identity")
            self.assertEqual(recovery["scope"], "recovery_only_not_live_topology")
            self.assertTrue(recovery["details_path"].endswith("mcp-recovery-state.json"))
            self.assertNotIn("automatic_routing", recovery)
            self.assertNotIn("recovery_invariants", recovery)
            self.assertNotIn("latest_topology_restore", recovery)
            self.assertNotIn("conditions", recovery)
            payload = json.dumps(glance, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            self.assertLessEqual(len(payload), BOOTSTRAP_GLANCE_MAX_BYTES)
        self.assertTrue(glance["paths"]["mcp_current_topology"].endswith("mcp-current-topology.json"))
        self.assertTrue(glance["paths"]["mcp_recovery_state"].endswith("mcp-recovery-state.json"))
        self.assertTrue(glance["paths"]["mcp_security_routing_log"].endswith("mcp-security-routing-events.jsonl"))
        self.assertTrue(glance["paths"]["mcp"].endswith("ChatGPTMcpCandidate1100969"))

    def test_freeze_contract_exposes_restore_first_policy(self):
        import tools.stack_atlas as atlas
        freeze_path = ROOT / "04 Operating Contracts" / "mcp-recovery-state.json"
        raw_contract = json.loads(freeze_path.read_text(encoding="utf-8"))
        self.assertEqual(raw_contract["scope"], "recovery_only_not_live_topology")
        self.assertTrue(raw_contract["current_serving_topology_reference"].endswith("mcp-current-topology.json"))
        self.assertIn("Recovery target only", raw_contract["warning"])
        with patch.object(atlas, "MCP_RECOVERY_STATE_PATH", freeze_path):
            state = atlas._bootstrap_mcp_recovery_state()
        self.assertTrue(state["restore_first_on_regression"])
        self.assertFalse(state["post_restore_no_mcp_request_in_flight"])
        self.assertIn("3036", state["automatic_routing"])
        self.assertIn("3037", state["automatic_routing"])
        self.assertEqual(state["recovery_target_generation"], "b7b1e24-template-compat")
        self.assertIn("historical explicit recovery only", state["ssh_role"])
        self.assertTrue(any("keep the selected recovery target fixed" in item for item in state["recovery_invariants"]))
        self.assertTrue(any("OAuth stores" in item for item in state["recovery_invariants"]))
        self.assertIn("preserve unique work", state["preservation_rule"])
        self.assertIn("authorized by go/continue", state["authorization_rule"])
        self.assertIn("do not ask for redundant per-cutover approval", state["authorization_rule"])
        self.assertIn("scope-widening", state["authorization_rule"])
        self.assertEqual(state["replacement_safety_rules"], [])
        latest = state["latest_topology_restore"]
        self.assertIsNone(latest)
        # historical topology restore is no longer the selected recovery target
        # preserved in Git history, not current recovery projection
        # no current latest_topology_restore block
        # no current failed replacement state
        # immediate local acceptance is recorded under evidence.acceptance
        # current live health/tool contract is authoritative
        summary = {item["type"]: item["status"] for item in state["conditions"]}
        self.assertEqual(summary["ToolContractHealthy"], "True")
        self.assertEqual(summary["OAuthBoundaryHealthy"], "True")
        raw = json.loads(freeze_path.read_text(encoding="utf-8"))
        first_step = raw["recovery_target"]["policy"]["required_order"][0]
        self.assertIn("Preserve the current runtime", first_step)
        self.assertIn("OAuth stores", first_step)

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
    def test_chatgpt_plugin_surface_search_routes_to_exact_five_tool_contract(self):
        for query in ("ChatGPT plugin tool contract process profile", "image metadata library upload", "busy_list plugin command", "view_image plugin", "open_visual_proof"):
            with self.subTest(query=query):
                result = find_features(query)[0]
                self.assertEqual(result["id"], "mcp.chatgpt_plugin_surface")
                self.assertEqual(result["owner_components"], ["mcp_minimal_clone"])
                self.assertIn("exactly five process-profile tools", result["boundary"])
                self.assertIn("same-turn exact-original image resource", result["boundary"])
                self.assertIn("excluded", result["boundary"])
        sources = component_details("mcp_minimal_clone")["canonical_sources"]
        self.assertTrue(any(item.endswith(r"\config\process-tool-contract.json") for item in sources))
        self.assertTrue(any(item.endswith(r"\src\lib\file-transfer.ts") for item in sources))
        self.assertFalse(any("visual-proof-app.ts" in item for item in sources))

    def test_current_topology_contract_matches_atlas_and_excludes_old_gpt1_route(self):
        contract = json.loads((ROOT / "04 Operating Contracts" / "mcp-current-topology.json").read_text(encoding="utf-8"))
        details = component_details("mcp_minimal_clone")
        self.assertEqual(contract["schema"], "mcp-current-topology.v1")
        self.assertEqual(contract["serving"]["connector_url"], details["current_topology"]["connector_url"])
        self.assertEqual(details["current_topology"]["status"], "OK")
        self.assertIn(contract["serving"]["backend"]["listen"], details["current_topology"]["serving_path"])
        self.assertTrue(contract["serving"]["backend"]["listen"].startswith("127.0.0.1:"))
        self.assertTrue(contract["serving"]["peer_route"]["listen"].startswith("127.0.0.1:"))
        self.assertTrue(contract["serving"]["backend"]["persistence_task"])
        self.assertTrue(contract["serving"]["peer_route"]["persistence_task"])
        self.assertEqual(contract["chatgpt_surface"]["tool_count"], 5)
        self.assertEqual(contract["chatgpt_surface"]["tools"], details["chatgpt_plugin_surface"]["tools"])
        self.assertTrue(contract["chatgpt_surface"]["image_delivery"]["adds_tool"])
        self.assertIn("5-61-91-127.sslip.io", contract["not_in_gpt1_path"])
        current = find_features("gpt1 mcp topology 91-159-12-133")[0]
        self.assertEqual(current["id"], "mcp.current_topology")
        self.assertIn("mcp-current-topology.v1", current["boundary"])
        self.assertNotIn(contract["serving"]["backend"]["listen"], current["boundary"])
        self.assertNotIn(contract["serving"]["peer_route"]["listen"], current["boundary"])

    def test_mcp_lookup_reads_valid_current_topology_contract_at_call_time(self):
        import tools.stack_atlas as atlas
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "mcp-current-topology.json"
            path.write_text(json.dumps({
                "schema": "mcp-current-topology.v1",
                "authority": "current_serving_topology",
                "serving": {
                    "connector_url": "https://example.invalid/mcp",
                    "public_origin": "https://example.invalid",
                    "authorization_endpoint": "https://example.invalid/authorize",
                    "path": ["ChatGPT/GPT1 connector", "test Caddy", "127.0.0.1:3999"],
                    "backend": {"listen": "127.0.0.1:3999"},
                },
                "chatgpt_surface": {"tool_count": 5, "tools": ["a", "b", "c", "d", "e"]},
                "recovery": {"independent_local_control": "test rollback"},
                "not_in_gpt1_path": ["legacy.invalid"],
            }), encoding="utf-8")
            with patch.object(atlas, "MCP_CURRENT_TOPOLOGY_PATH", path):
                current = atlas.atlas_lookup("mcp_minimal_clone")["current_topology"]
        self.assertEqual(current["status"], "OK")
        self.assertEqual(current["connector_url"], "https://example.invalid/mcp")
        self.assertIn("127.0.0.1:3999", current["serving_path"])
        self.assertNotIn("3036", json.dumps(current))

    def test_mcp_lookup_fails_closed_when_current_topology_is_missing_or_invalid(self):
        import tools.stack_atlas as atlas
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            missing = root / "missing.json"
            with patch.object(atlas, "MCP_CURRENT_TOPOLOGY_PATH", missing):
                missing_current = atlas.component_details("mcp_minimal_clone")["current_topology"]
            invalid = root / "invalid.json"
            invalid.write_text(json.dumps({"schema": "wrong.v1"}), encoding="utf-8")
            with patch.object(atlas, "MCP_CURRENT_TOPOLOGY_PATH", invalid):
                invalid_current = atlas.component_details("mcp_minimal_clone")["current_topology"]
            split_brain = root / "split-brain.json"
            split_brain.write_text(json.dumps({
                "schema": "mcp-current-topology.v1",
                "authority": "current_serving_topology",
                "serving": {
                    "path": ["ChatGPT/GPT1 connector", "test Caddy", "127.0.0.1:3998"],
                    "backend": {"listen": "127.0.0.1:3999"},
                },
            }), encoding="utf-8")
            with patch.object(atlas, "MCP_CURRENT_TOPOLOGY_PATH", split_brain):
                split_brain_current = atlas.component_details("mcp_minimal_clone")["current_topology"]
        for current in (missing_current, invalid_current, split_brain_current):
            self.assertEqual(current["status"], "UNKNOWN_SOURCE_UNAVAILABLE")
            self.assertNotIn("serving_path", current)
            self.assertNotIn("3036", json.dumps(current))
            self.assertIn("must not masquerade", current["boundary"])


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
    def test_recovery_candidates_stay_in_canonical_s1_fleet(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "worker-reports" / "current"
            current.mkdir(parents=True)
            now = datetime(2026, 9, 7, 16, 30, tzinfo=timezone.utc)
            s1 = TEST_RECURRING_WORKER_PARTITIONS["S1"]
            missing_id = s1[0][0]
            actor_id = s1[1][0]
            for worker_id, label in TEST_RECURRING_WORKERS:
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
        self.assertEqual(watch["subscription_scope"], "S1")
        self.assertEqual(watch["expected_recurring_workers"], 5)
        self.assertEqual(watch["expected_recurring_workers_total"], 10)
        self.assertEqual(watch["recovery_candidate_count"], 1)
        self.assertEqual(watch["recovery_candidates"][0]["automation_id"], missing_id)
        self.assertTrue(all(item["subscription_partition"] == "S1" for item in watch["recovery_candidates"]))

    def test_new_worker_is_not_recoverable_before_first_expected_start_plus_grace(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "worker-reports" / "current"
            current.mkdir(parents=True)
            contract = root / "04 Operating Contracts" / "chatgpt-swarm-topology.json"
            contract.parent.mkdir(parents=True)
            now = datetime(2026, 9, 7, 16, 35, tzinfo=timezone.utc)
            target_id, target_label = TEST_RECURRING_WORKER_PARTITIONS["S1"][0]
            actor_id = TEST_RECURRING_WORKER_PARTITIONS["S1"][1][0]
            first_expected = now + timedelta(minutes=1)
            contract.write_text(json.dumps({"subscriptions": {"S1": {"workers": [{
                "automation_id": target_id,
                "label": target_label,
                "first_expected_start_at": first_expected.isoformat(),
            }]}}}), encoding="utf-8")
            for worker_id, label in TEST_RECURRING_WORKER_PARTITIONS["S1"]:
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
        self.assertEqual(pending["status"], "LOCAL_RECOVERY_EVIDENCE")
        self.assertEqual(pending["first_start_pending"], 1)
        self.assertEqual(pending["recovery_candidates"], [])
        target = next(item for item in overdue["lifecycle_gaps"] if item["automation_id"] == target_id)
        self.assertEqual(target["reason"], "NO_LOCAL_START_EVIDENCE")
        self.assertTrue(target["probe_actionable"])


class TestWindowsBoundedProcessCapture(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows inherited-handle regression")
    def test_capture_does_not_wait_for_descendant_inherited_stdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "spawn_descendant.py"
            script.write_text(
                "import subprocess, sys\n"
                "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(5)'])\n"
                "print('parent-done', flush=True)\n",
                encoding="utf-8",
            )
            started = time.monotonic()
            result = _run_process(
                [sys.executable, str(script)], capture_output=True, text=True, timeout=1.0
            )
            elapsed = time.monotonic() - started
        self.assertEqual(result.returncode, 0)
        self.assertIn("parent-done", result.stdout)
        self.assertLess(elapsed, 2.5)

    @unittest.skipUnless(os.name == "nt", "Windows inherited-handle regression")
    def test_timeout_terminates_descendant_tree_without_pipe_eof_wait(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "hang_tree.py"
            script.write_text(
                "import subprocess, sys, time\n"
                "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
                "time.sleep(30)\n",
                encoding="utf-8",
            )
            started = time.monotonic()
            with self.assertRaises(subprocess.TimeoutExpired):
                _run_process(
                    [sys.executable, str(script)], capture_output=True, text=True, timeout=0.2
                )
            elapsed = time.monotonic() - started
        self.assertLess(elapsed, 4.0)


class TestVaultServingCheckoutConvergence(unittest.TestCase):
    def _git(self, cwd: Path, *args: str) -> str:
        proc = subprocess.run(
            ["git", "-C", str(cwd), *args],
            check=True,
            text=True,
            capture_output=True,
        )
        return proc.stdout.strip()

    def _init_remote_pair(self, root: Path) -> tuple[Path, Path, Path]:
        remote = root / "remote.git"
        seed = root / "seed"
        live = root / "live"
        subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(seed)], check=True)
        self._git(seed, "config", "user.email", "test@example.com")
        self._git(seed, "config", "user.name", "Vault Sync Test")
        (seed / "tracked.txt").write_text("base\n", encoding="utf-8")
        self._git(seed, "add", "tracked.txt")
        self._git(seed, "commit", "-q", "-m", "base")
        self._git(seed, "remote", "add", "origin", str(remote))
        self._git(seed, "push", "-q", "-u", "origin", "main")
        self._git(remote, "symbolic-ref", "HEAD", "refs/heads/main")
        subprocess.run(["git", "clone", "-q", str(remote), str(live)], check=True)
        self._git(live, "config", "user.email", "test@example.com")
        self._git(live, "config", "user.name", "Vault Sync Test")
        return remote, seed, live

    def _advance_remote(self, seed: Path, filename: str, content: str) -> str:
        (seed / filename).write_text(content, encoding="utf-8")
        self._git(seed, "add", filename)
        self._git(seed, "commit", "-q", "-m", f"advance {filename}")
        self._git(seed, "push", "-q", "origin", "main")
        return self._git(seed, "rev-parse", "HEAD")

    def _run_sync(self, live: Path, *extra: str) -> tuple[int, dict]:
        script = ROOT / "tools" / "Sync-VaultCheckout.ps1"
        proc = subprocess.run(
            [
                "powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "Bypass", "-File", str(script),
                "-RepoRoot", str(live), *extra,
            ],
            text=True,
            capture_output=True,
        )
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        self.assertTrue(lines, msg=f"sync emitted no JSON: stderr={proc.stderr}")
        return proc.returncode, json.loads(lines[-1])

    @unittest.skipUnless(os.name == "nt", "Vault serving checkout sync is a Windows scheduled-task contract")
    def test_sync_fast_forwards_blocks_dirty_and_preserves_before_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, seed, live = self._init_remote_pair(Path(tmp))
            remote_head = self._advance_remote(seed, "remote-a.txt", "remote a\n")
            code, data = self._run_sync(live)
            self.assertEqual(code, 0)
            self.assertEqual(data["status"], "FAST_FORWARDED")
            self.assertEqual(self._git(live, "rev-parse", "HEAD"), remote_head)

            (live / "tracked.txt").write_text("foreign working tree\n", encoding="utf-8")
            (live / "foreign-untracked.txt").write_text("foreign untracked\n", encoding="utf-8")
            remote_head = self._advance_remote(seed, "remote-b.txt", "remote b\n")
            code, blocked = self._run_sync(live)
            self.assertNotEqual(code, 0)
            self.assertEqual(blocked["status"], "DIRTY_BLOCKED")
            self.assertEqual((live / "tracked.txt").read_text(encoding="utf-8"), "foreign working tree\n")
            self.assertEqual((live / "foreign-untracked.txt").read_text(encoding="utf-8"), "foreign untracked\n")

            code, repaired = self._run_sync(live, "-Repair")
            self.assertEqual(code, 0)
            self.assertEqual(repaired["status"], "REPAIRED")
            self.assertTrue(repaired["preservation_branch"].startswith("preserve/vault-live-"))
            self.assertEqual(self._git(live, "rev-parse", "HEAD"), remote_head)
            self.assertEqual(self._git(live, "status", "--porcelain"), "")
            preserved = self._git(live, "show", f'{repaired["preservation_branch"]}:tracked.txt')
            self.assertEqual(preserved, "foreign working tree")
            preserved_untracked = self._git(live, "show", f'{repaired["preservation_branch"]}:foreign-untracked.txt')
            self.assertEqual(preserved_untracked, "foreign untracked")
            self.assertFalse((live / "foreign-untracked.txt").exists())

    @unittest.skipUnless(os.name == "nt", "Vault serving checkout sync is a Windows scheduled-task contract")
    def test_sync_fails_closed_on_ahead_diverged_and_wrong_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, seed, live = self._init_remote_pair(Path(tmp))
            (live / "local.txt").write_text("local\n", encoding="utf-8")
            self._git(live, "add", "local.txt")
            self._git(live, "commit", "-q", "-m", "local ahead")
            code, ahead = self._run_sync(live)
            self.assertNotEqual(code, 0)
            self.assertEqual(ahead["status"], "AHEAD_BLOCKED")

            self._advance_remote(seed, "remote.txt", "remote\n")
            code, diverged = self._run_sync(live)
            self.assertNotEqual(code, 0)
            self.assertEqual(diverged["status"], "DIVERGED_BLOCKED")

            self._git(live, "reset", "--hard", "origin/main")
            self._git(live, "switch", "-q", "-c", "scratch")
            code, wrong = self._run_sync(live, "-SkipFetch")
            self.assertNotEqual(code, 0)
            self.assertEqual(wrong["status"], "WRONG_BRANCH")

    @unittest.skipUnless(os.name == "nt", "Vault serving checkout sync is a Windows scheduled-task contract")
    def test_sync_wrong_branch_still_refreshes_cached_remote_without_touching_worktree(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, seed, live = self._init_remote_pair(Path(tmp))
            self._git(live, "switch", "-q", "-c", "scratch")
            scratch_head = self._git(live, "rev-parse", "HEAD")
            remote_head = self._advance_remote(seed, "remote-refresh.txt", "remote refresh\n")

            code, wrong = self._run_sync(live)

            self.assertNotEqual(code, 0)
            self.assertEqual(wrong["status"], "WRONG_BRANCH")
            self.assertEqual(self._git(live, "rev-parse", "--abbrev-ref", "HEAD"), "scratch")
            self.assertEqual(self._git(live, "rev-parse", "HEAD"), scratch_head)
            self.assertEqual(self._git(live, "rev-parse", "origin/main"), remote_head)
            self.assertEqual(self._git(live, "status", "--porcelain"), "")

    def test_installer_is_hidden_one_minute_fail_closed_default(self):
        text = (ROOT / "tools" / "Install-VaultCheckoutSyncTask.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("'VaultCheckoutSync'", text)
        self.assertIn("[int]$IntervalMinutes = 1", text)
        self.assertIn("Get-Command pythonw.exe", text)
        self.assertIn("subprocess.STARTF_USESHOWWINDOW", text)
        self.assertIn("subprocess.SW_HIDE", text)
        self.assertIn("subprocess.CREATE_NEW_CONSOLE", text)
        self.assertIn("-MultipleInstances IgnoreNew", text)
        self.assertIn("-RunLevel Limited", text)
        self.assertIn("tools\\Sync-VaultCheckout.ps1", text)
        self.assertNotIn(" -Repair", text)

    def test_bootstrap_vault_status_marks_checkout_incoherence_degraded(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "vault"
            subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
            self._git(repo, "config", "user.email", "test@example.com")
            self._git(repo, "config", "user.name", "Vault Status Test")
            (repo / "tools").mkdir()
            (repo / "tools" / "stack_atlas.py").write_text("# probe\n", encoding="utf-8")
            (repo / "memory").mkdir()
            (repo / "memory" / "memory-bank.jsonl").write_text('{"id":"x"}\n', encoding="utf-8")
            (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
            self._git(repo, "add", ".")
            self._git(repo, "commit", "-q", "-m", "base")
            base = self._git(repo, "rev-parse", "HEAD")
            self._git(repo, "update-ref", "refs/remotes/origin/main", base)
            with patch("tools.stack_atlas.ROOT", repo):
                current = _bootstrap_vault_status()
            self.assertEqual(current["status"], "OK")
            self.assertTrue(current["checkout"]["coherent"])
            self.assertFalse(current["attention_required"])

            (repo / "tracked.txt").write_text("dirty\n", encoding="utf-8")
            with patch("tools.stack_atlas.ROOT", repo):
                dirty = _bootstrap_vault_status()
            self.assertEqual(dirty["status"], "DEGRADED")
            self.assertTrue(dirty["checkout"]["dirty"])
            self.assertTrue(dirty["attention_required"])

            self._git(repo, "reset", "--hard", base)
            (repo / "remote.txt").write_text("remote\n", encoding="utf-8")
            self._git(repo, "add", "remote.txt")
            self._git(repo, "commit", "-q", "-m", "remote simulated")
            remote = self._git(repo, "rev-parse", "HEAD")
            self._git(repo, "reset", "--hard", base)
            self._git(repo, "update-ref", "refs/remotes/origin/main", remote)
            with patch("tools.stack_atlas.ROOT", repo):
                behind = _bootstrap_vault_status()
            self.assertEqual(behind["status"], "DEGRADED")
            self.assertFalse(behind["checkout"]["coherent"])
            self.assertEqual(behind["checkout"]["remote_main"], remote)
            self.assertTrue(behind["attention_required"])
