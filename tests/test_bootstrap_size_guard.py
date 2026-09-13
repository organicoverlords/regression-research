import json
from unittest.mock import patch

import tools.stack_atlas as stack_atlas


# User-approved static bootstrap baseline. Lowering is allowed; raising requires
# explicit user authorization. Runtime variability is separately bounded by the
# existing schema-level sample limits and the 28k overall budget.
USER_APPROVED_BOOTSTRAP_STATIC_BASELINE_BYTES = 7_633


def _deterministic_bootstrap() -> dict:
    execution_nodes = {
        "authority": "CANONICAL",
        "status": "OK",
        "routing_policy": {
            "default_execution_node": "omen-linux-laptop",
            "substantive_execution": "OMEN_REQUIRED",
            "kone_execution": "MANDATORY_WINDOWS_CI_LIGHT_ONLY",
            "kone_capacity_fallback": False,
        },
        "local_node_id": "kone-gpu-desktop",
        "nodes": {
            "kone-gpu-desktop": {"roles": ["mandatory_windows_ci_light"]},
            "omen-linux-laptop": {"roles": ["default_execution", "portable", "heavy"]},
        },
    }
    pc = {"disk": {"status": "OK", "free_gb": 100.0, "trend": {}}, "memory": {"status": "OK"}}
    workers = {
        "available": True,
        "manual_sanity": {"available": True, "status": "PROVEN", "score_delta": 0.0, "direction": "STABLE", "post_run_count": 20},
    }
    live_swarm = {
        "available": True,
        "summary": {"recent_callers": 4, "lanes": 4, "busy_owners": 0, "identity": "test"},
        "evidence": {"activity_window_seconds": 300, "observation_window_complete": True, "source_age_seconds": 0.0},
        "lanes": [
            {"basis": "worktree", "workspace": f"w{i}", "callers": [{"caller_id": f"c{i}"}], "busy": []}
            for i in range(4)
        ],
    }
    memory = {
        "contract": "history only", "eligible_entries": 0, "timeline_snapshots": {}, "incident_rollups": [],
        "recent": [], "projects": [], "recurring_tags": [],
        "timeline_materialized": {"status": "FRESH", "backfill_incomplete_sources": [], "retry_sources": []},
    }
    swarm = {
        "authority": "CURRENT", "read_state": "OK", "chatgpt_subscription_count": 2,
        "recurring_worker_partition_count": 2, "recurring_worker_partitions": {"S1": 5, "S2": 5},
        "recurring_workers_total": 10, "recurring_workers_total_semantics": "stable_slot_capacity_not_bound_worker_count",
        "slot_bindings": {"status": "OK", "bound_count": 10, "slot_capacity_total": 10, "partitions": {"S1": {"bound_count": 5, "unbound_count": 0}, "S2": {"bound_count": 5, "unbound_count": 0}}},
        "scheduler_boundary": "five stable recurring slots per partition; bindings may change",
        "scheduler_enabled_state_authority": "owning ChatGPT scheduler; registry/reports are not liveness",
        "routine_recurring_recovery": {"authority": "SUPERVISING_CHAT_OR_OPERATOR_HANDOFF", "scheduler_role": "RECURRENCE_ONLY", "operator_handoff_role": "ADMINISTRATIVE_FALLBACK_WHEN_SUPERVISING_CHAT_CANNOT_RECOVER", "user_role": "SETS_TOPOLOGY_AND_OBJECTIVES_NOT_ROUTINE_WORKER_SUPERVISION"},
        "operator_handoff": {"primary_operator_subscription": "PARTITION_LOCAL"},
        "manual_workers": {"population": "SEPARATE_ON_DEMAND", "counts_against_recurring_slots": False, "active_count_authority": "live MCP/runtime evidence", "total_swarm_semantics": "5+5 plus manual"},
    }
    mcp = {
        "available": True, "status": "LIVE", "active_session_count": 3, "active_session_count_status": "COMPLETE",
        "workspace_counts": {"Vault": 3},
        "active_sessions": [{"caller_id": f"c{i}", "cwd": f"C:/w{i}", "workspace": "Vault", "busy_titles": []} for i in range(3)],
        "active_session_details": {"limit": 3, "returned": 3, "total": 3, "bounded": False},
    }
    guidance = {
        "mode": "HINT_ONLY", "behavior_incident_version": "V2", "eli5": "fixed", "asshole": "fixed",
        "stack_find": "fixed", "shared_correction": "fixed", "security_evidence": {"mode": "CLASSIFY_BEFORE_CAUSALITY"},
        "slopwall": "fixed", "incident_report": "fixed",
    }
    patches = (
        patch("tools.stack_atlas._bootstrap_execution_node_topology", return_value=execution_nodes),
        patch("tools.stack_atlas._bootstrap_pc_status", return_value=pc),
        patch("tools.stack_atlas._bootstrap_worker_status", return_value=workers),
        patch("tools.stack_atlas.build_live_swarm_snapshot", return_value=live_swarm),
        patch("tools.stack_atlas._bootstrap_memory_overview", return_value=memory),
        patch("tools.stack_atlas._bootstrap_vault_status", return_value={"status": "OK"}),
        patch("tools.stack_atlas._bootstrap_github_status", return_value={"status": "OK"}),
        patch("tools.stack_atlas._bootstrap_source_freshness", return_value={"available": True, "attention_required": False, "updates_pending": False, "sources": {}}),
        patch("tools.stack_atlas._yard_inbox_check", return_value=[]),
        patch("tools.stack_atlas._bind_pc_node_identity", side_effect=lambda value, _: value),
        patch("tools.stack_atlas._bootstrap_manual_current_status", return_value={"available": True}),
        patch("tools.stack_atlas._bootstrap_swarm_topology", return_value=swarm),
        patch("tools.stack_atlas._bootstrap_mcp_status_from_live_swarm", return_value=mcp),
        patch("tools.stack_atlas._bootstrap_mcp_current_topology", return_value={"status": "OK"}),
        patch("tools.stack_atlas._bootstrap_mcp_recovery_state", return_value={"status": "OK"}),
        patch("tools.stack_atlas._bootstrap_mcp_recovery_orientation", side_effect=lambda value: value),
        patch("tools.stack_atlas._bootstrap_agent_contract_version", return_value={"status": "COHERENT", "version": 92, "rules_version": 92, "agents_version": 92}),
        patch("tools.stack_atlas._bootstrap_slopwall_contract", return_value={"status": "ENFORCED", "version": "V2", "triggers": ["slopwall", "incident_report"], "capture": "VISIBLE_CONTEXT_ONLY", "process": "failed_boundary > repair_inherited_objective"}),
        patch("tools.stack_atlas._bootstrap_critical_guidance", return_value=guidance),
        patch("tools.stack_atlas._bootstrap_active_manual_run_identities", return_value={"runs": []}),
    )
    entered = []
    try:
        for item in patches:
            entered.append(item)
            item.start()
        glance = stack_atlas.build_live_bootstrap_glance()
    finally:
        for item in reversed(entered):
            item.stop()

    # Normalize only volatile values; all schema/content bytes remain measured.
    glance["generated_at"] = "2026-09-13T08:00:00+00:00"
    glance["bootstrap"]["elapsed_ms"] = 123.4
    glance["paths"] = {key: f"<{key}>" for key in glance["paths"]}
    return glance


def test_bootstrap_static_shape_does_not_grow_without_user_authorization():
    glance = _deterministic_bootstrap()
    payload = json.dumps(glance, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert len(payload) <= USER_APPROVED_BOOTSTRAP_STATIC_BASELINE_BYTES
    assert glance["bootstrap_warning"].startswith("BOOTSTRAP INTEGRITY:")
    assert glance["bootstrap_end"] == {"status": "COMPLETE", "schema": "bootstrap.v1"}
    assert glance["bootstrap"]["payload_budget"]["runtime_action"] == "OBSERVE_ONLY_NO_FAIL"

