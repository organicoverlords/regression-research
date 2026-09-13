#!/usr/bin/env python3
"""Run the deterministic repository checks used by CI."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

STACK_PATHS = {
    "AGENTS.md",
    "NORTH_STAR.md",
    "tests/fixtures/instruction-delivery-canary.json",
    "tests/fixtures/source-grounding-cases.json",
    "tools/stack_atlas.py",
    "tools/tiny3d_atlas_projection.py",
    "tests/test_tiny3d_atlas_projection.py",
    "docs/assistant-stack-operational-atlas.md",
    "tests/fixtures/stack-atlas-pid-29864.json",
    "tests/test_stack_atlas.py",
    "tests/test_slopwall_v2_bootstrap.py",
    "tests/test_issue693_fresh_worker_entry.py",
    "tests/fixtures/issue693_fresh_worker_entry.json",
    "04 Operating Contracts/fresh-worker-generation-launch.md",
    "tools/replay_scoring.py",
    "tools/slopwall_v2.py",
    "tests/test_replay_scoring.py",
    "tests/test_behavior_regression_contract.py",
    "tests/test_manual_go_replay.py",
    "01 Reports/2026-09-13_manual_worker_optional_github_tool_selection_regression.md",
    "03 Fixtures and Experiments/2026-09-13_manual_worker_optional_github_tool_selection.json",
    "tests/test_optional_remote_tool_selection.py",
    "01 Reports/2026-09-13_headless_tool_commentary_rule_gap.md",
    "03 Fixtures and Experiments/2026-09-13_headless_tool_commentary_boundary.json",
    "tests/test_headless_tool_commentary_replay.py",
    "01 Reports/SW-V2-20260913-003_incident.md",
    "02 Evidence/SW-V2-20260913-003_visible-context.json",
    "03 Fixtures and Experiments/SW-V2-20260913-003_replay.json",
    "memory/reports/SW-V2-20260913-003_pending-memory.md",
    "tests/test_sw_v2_003_preservation.py",
    "tests/fixtures/tool-result-answer-boundary.json",
    "tests/test_tool_result_answer_boundary.py",
    "03 Fixtures and Experiments/2026-09-07_0221_EEST_go-issue-completion-stop_next_action.json",
    "tests/test_slopwall_v2.py",
    "04 Operating Contracts/assistant-behavior-regression.md",
    "04 Operating Contracts/slopwall-v2-capture-contract.md",
    "03 Fixtures and Experiments/2026-09-13_slopwall-v2_wrong-slopwall-semantics_replay.json",
    "tests/test_north_star_entry.py",
    "03 Fixtures and Experiments/issue122-acceptance-boundary-classification.json",
    "tests/test_issue122_acceptance_boundary_replay.py",
    "03 Fixtures and Experiments/issue122-false-boundary-provenance.json",
    "tests/test_issue122_false_boundary_replay.py",
    "tests/test_issue122_forensic_integrity.py",
    "02 Evidence/issue122/2026-08-25_122229_EEST_pre-repair-memory-block.txt",
    "02 Evidence/issue122/2026-08-27_canonical-claim-evidence-ledger.md",
    ".gitattributes",
    "03 Fixtures and Experiments/issue123-current-vault-history-boundary.json",
    "01 Reports/2026-09-03_issue123-current-vault-history-boundary.md",
    "02 Evidence/issue123/2026-08-27_current-user-preference-coverage.md",
    "tests/test_issue123_current_vault_history_boundary.py",
    "tests/fixtures/issue123-small-response-shape.json",
    "tests/test_issue123_response_shape.py",
}


MEMORY_PATHS = {
    "memory/README.md",
    "02 Evidence/mcp-security-routing-events.jsonl",
    "tools/stack_atlas.py",
    "tools/memory_bank.py",
    "tools/memory_classification.py",
    "tools/memory_context.py",
    "tools/memory_git_sync.py",
    "tools/memory_hybrid.py",
    "tools/memory_timeline.py",
    "tools/mcp_reroute_evidence.py",
    "tools/repo_timeline.py",
    "tools/timeline_materializer.py",
    "tools/provenance.py",
    "tests/test_memory_bank.py",
    "tests/test_memory_bootstrap.py",
    "tests/test_memory_classification.py",
    "tests/test_memory_cli.py",
    "tests/test_memory_context.py",
    "tests/test_memory_context_retrieval.py",
    "tests/test_memory_git_sync.py",
    "tests/test_memory_retrieval_quality.py",
    "tests/test_memory_timeline.py",
    "tests/test_mcp_reroute_evidence.py",
    "tests/test_repo_timeline.py",
    "tests/test_timeline_materializer.py",
    "tests/test_timeline_recovery_issue649.py",
    "tests/test_timeline_query_filters.py",
    "tests/test_issue675_query_cache_generation.py",
    "tests/test_memory_standalone.py",
    "tests/test_provenance_index.py",
    "tests/test_taxonomy_matrix.py",
    "tests/test_issue675_lesson_lineage_safety.py",
    "tests/test_issue675_lesson_validation_safety.py",
    "tests/test_issue675_static_proof_safety.py",
}

CONVERSATION_PATHS = {
    "tools/conversation_search.py",
    "tests/test_conversation_search.py",
    "tests/fixtures/conversation-corpus/ChatPortEvidence/old.json",
    "tests/fixtures/conversation-corpus/ChatGPTLocalExporter/new.json",
}

WORKER_REPORT_PATHS = {
    "tools/worker_report_history.py",
    "tools/manual_work_disposition.py",
    "tests/test_worker_report_history.py",
    "tests/test_manual_work_disposition.py",
}

BUSY_ROOT = "03 Fixtures and Experiments/issue125-busy-coordinator"
BUSY_PATH_PREFIX = BUSY_ROOT + "/"

VERIFIER_PATHS = {
    "tools/verify.py",
    "tests/test_verify.py",
    ".github/workflows/changelog-landing.yml",
}

ROUTING_PATHS = {
    "tools/swarm_route.py",
    "tests/test_swarm_route.py",
    "tests/test_swarm_route_node_identity.py",
}

WINDOW_UI_PATHS = {
    "tools/stack_atlas.py",
    "tools/bootstrap_read_loop.py",
    "tools/cleanup_converger.py",
    "tools/memory_git_sync.py",
    "tools/repo_timeline.py",
    "tools/runtime_dependency_graph.py",
    "tools/timeline_materializer.py",
    "tools/worker_report_history.py",
    "tools/worktree_hygiene_guard.py",
    "tools/Sync-VaultCheckout.ps1",
    "tools/Install-TimelineMaterializerTask.ps1",
    "tools/Install-VaultCheckoutSyncTask.ps1",
    "tools/Install-WorktreeHygieneTask.ps1",
    "tools/install_bootstrap_snapshot_task.ps1",
    "tools/windows_ui_probe.py",
    "tests/test_hidden_subprocess_windows.py",
    "tests/test_windows_ui_probe.py",
}


ALL_AREAS = ("stack", "memory", "conversation", "busy", "worker_reports", "routing", "windows_ui")
WINDOWS_ONLY_AREAS = frozenset({"stack", "busy", "windows_ui"})


def changed_files(base_ref: str) -> set[str]:
    commands = [
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
        ["git", "diff", "--name-only", "HEAD"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]
    changed = set()
    for command in commands:
        output = subprocess.check_output(command, cwd=ROOT, text=True, encoding="utf-8")
        changed.update(
            line.strip().replace("\\", "/")
            for line in output.splitlines()
            if line.strip()
        )
    return changed


def select_areas(changed: set[str], run_all: bool = False) -> list[str]:
    if run_all or changed & VERIFIER_PATHS:
        return list(ALL_AREAS)
    selected = []
    if changed & STACK_PATHS or any(
        Path(path).parent.as_posix() == "03 Fixtures and Experiments" and path.endswith(".json")
        for path in changed
    ):
        selected.append("stack")
    if changed & MEMORY_PATHS:
        selected.append("memory")
    if changed & CONVERSATION_PATHS:
        selected.append("conversation")
    if changed & WORKER_REPORT_PATHS:
        selected.append("worker_reports")
    if any(path.startswith(BUSY_PATH_PREFIX) for path in changed):
        selected.append("busy")
    if changed & ROUTING_PATHS:
        selected.append("routing")
    if changed & WINDOW_UI_PATHS:
        selected.append("windows_ui")
    return selected


def split_areas(areas: list[str]) -> dict[str, object]:
    invalid = [area for area in areas if area not in ALL_AREAS]
    if invalid:
        raise ValueError(f"unknown verification area(s): {', '.join(invalid)}")
    windows_areas = [area for area in areas if area in WINDOWS_ONLY_AREAS]
    portable_areas = [area for area in areas if area not in WINDOWS_ONLY_AREAS]
    return {
        "areas": list(areas),
        "portable_areas": portable_areas,
        "windows_areas": windows_areas,
        "needs_windows": bool(windows_areas),
    }


def run_areas(areas: list[str]) -> None:
    for area in areas:
        if area == "stack":
            verify_stack()
        elif area == "memory":
            verify_memory()
        elif area == "conversation":
            verify_conversation()
        elif area == "busy":
            verify_busy()
        elif area == "worker_reports":
            verify_worker_reports()
        elif area == "routing":
            verify_routing()
        elif area == "windows_ui":
            verify_windows_ui()
        else:
            raise ValueError(f"unknown verification area: {area}")


def run(command: list[str]) -> None:
    print(f"VERIFY_RUN: {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def run_pytest(test_paths: list[str]) -> None:
    with tempfile.TemporaryDirectory(prefix="regression-research-pytest-") as temp_dir:
        run([sys.executable, "-m", "pytest", "-q", "--basetemp", temp_dir, *test_paths])


def verify_entrypoint() -> None:
    run([sys.executable, "-m", "py_compile", "tools/verify.py"])
    run([sys.executable, "-m", "unittest", "tests.test_verify", "-v"])
    print("VERIFICATION_ENTRYPOINT_PROVEN")


def verify_stack() -> None:
    run(
        [
            sys.executable,
            "-m",
            "py_compile",
                    "tools/stack_atlas.py",
            "tools/tiny3d_atlas_projection.py",
            "tools/replay_scoring.py",
            "tools/slopwall_v2.py",
            "tools/behavior_incident_capture.py",
            "tools/behavior_incident_close.py",
        ]
    )
    run(
        [
            sys.executable,
            "-m",
            "unittest",
            "tests.test_stack_atlas",
            "tests.test_slopwall_v2_bootstrap",
            "tests.test_replay_scoring",
            "tests.test_tiny3d_atlas_projection",
            "tests.test_issue693_fresh_worker_entry",
            "tests.test_issue122_acceptance_boundary_replay",
            "tests.test_issue122_false_boundary_replay",
            "tests.test_issue122_forensic_integrity",
            "tests.test_issue123_current_vault_history_boundary",
            "tests.test_issue123_response_shape",
            "tests.test_tool_result_answer_boundary",
            "tests.test_north_star_entry",
            "-v",
        ]
    )
    run_pytest(
        [
            "tests/test_behavior_regression_contract.py",
            "tests/test_manual_go_replay.py",
            "tests/test_optional_remote_tool_selection.py",
            "tests/test_headless_tool_commentary_replay.py",
            "tests/test_sw_v2_003_preservation.py",
            "tests/test_slopwall_v2.py",
            "tests/test_behavior_incident_capture.py",
            "tests/test_behavior_incident_close.py",
        ]
    )
    print("ASSISTANT_STACK_POLICY_PROVEN")


def verify_busy() -> None:
    python_core = f"{BUSY_ROOT}/python/busy.py"
    compatibility = f"{BUSY_ROOT}/tests/install_compatibility.py"
    manifest = f"{BUSY_ROOT}/rust/Cargo.toml"
    run([sys.executable, "-m", "py_compile", python_core, compatibility])
    run(["cargo", "test", "--release", "--manifest-path", manifest])
    run([sys.executable, compatibility])
    print("BUSY_COORDINATOR_COMPATIBILITY_PROVEN")


def verify_memory() -> None:
    run(
        [
            sys.executable,
            "-m",
            "py_compile",
                    "tools/stack_atlas.py",
                    "tools/memory_bank.py",
            "tools/memory_classification.py",
            "tools/memory_context.py",
            "tools/memory_git_sync.py",
            "tools/memory_hybrid.py",
            "tools/memory_timeline.py",
            "tools/mcp_reroute_evidence.py",
            "tools/repo_timeline.py",
            "tools/timeline_materializer.py",
            "tools/provenance.py",
        ]
    )
    run([sys.executable, "tools/memory_bank.py", "validate"])
    run([sys.executable, "tools/provenance.py", "validate"])
    run([sys.executable, "tools/mcp_reroute_evidence.py", "verify"])
    run_pytest(
        [
            "tests/test_memory_bank.py",
            "tests/test_memory_bootstrap.py",
            "tests/test_memory_classification.py",
            "tests/test_memory_cli.py",
            "tests/test_memory_context.py",
            "tests/test_memory_context_retrieval.py",
            "tests/test_memory_git_sync.py",
            "tests/test_memory_retrieval_quality.py",
            "tests/test_memory_timeline.py",
            "tests/test_mcp_reroute_evidence.py",
            "tests/test_repo_timeline.py",
            "tests/test_timeline_materializer.py",
            "tests/test_timeline_recovery_issue649.py",
            "tests/test_timeline_query_filters.py",
            "tests/test_issue675_query_cache_generation.py",
            "tests/test_memory_standalone.py",
            "tests/test_provenance_index.py",
            "tests/test_taxonomy_matrix.py",
            "tests/test_issue675_lesson_lineage_safety.py",
            "tests/test_issue675_lesson_validation_safety.py",
            "tests/test_issue675_static_proof_safety.py",
        ]
    )
    print("MEMORY_HISTORY_RETRIEVAL_PROVEN")


def verify_worker_reports() -> None:
    run([sys.executable, "-m", "py_compile", "tools/worker_report_history.py", "tools/manual_work_disposition.py"])
    run_pytest(["tests/test_worker_report_history.py", "tests/test_manual_work_disposition.py"])
    print("MANUAL_WORK_DISPOSITION_PROVEN")


def verify_routing() -> None:
    run([sys.executable, "-m", "py_compile", "tools/swarm_route.py"])
    run([sys.executable, "-m", "unittest", "tests.test_swarm_route", "tests.test_swarm_route_node_identity", "-v"])
    print("SWARM_ROUTING_POLICY_PROVEN")


def verify_windows_ui() -> None:
    run(
        [
            sys.executable,
            "-m",
            "py_compile",
            "tools/windows_ui_probe.py",
            "tests/test_hidden_subprocess_windows.py",
            "tests/test_windows_ui_probe.py",
        ]
    )
    run(
        [
            sys.executable,
            "-m",
            "unittest",
            "tests.test_hidden_subprocess_windows",
            "tests.test_windows_ui_probe",
            "-v",
        ]
    )
    print("WINDOWS_BACKGROUND_UI_CONTRACT_PROVEN")


def verify_conversation() -> None:
    run(
        [
            sys.executable,
            "-m",
            "py_compile",
            "tools/conversation_search.py",
                ]
    )
    run(
        [
            sys.executable,
            "-m",
            "unittest",
            "tests.test_conversation_search",
            "-v",
        ]
    )
    with tempfile.TemporaryDirectory(prefix="regression-research-verify-") as temp_dir:
        database = str(Path(temp_dir) / "conversation-search.sqlite3")
        corpus = "tests/fixtures/conversation-corpus"
        run(
            [
                sys.executable,
                "tools/conversation_search.py",
                "--db",
                database,
                "index",
                "--root",
                corpus,
            ]
        )
    print("CONVERSATION_SEARCH_FIXTURE_PROVEN")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic regression-research checks without reading the live corpus."
    )
    parser.add_argument(
        "--base-ref",
        help="Run only checks selected by changes since this Git ref (CI mode).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run every deterministic check (the default when no base ref is supplied).",
    )
    parser.add_argument(
        "--areas",
        help="Run an explicit comma-separated area list. An empty value runs only the verifier entrypoint.",
    )
    parser.add_argument(
        "--plan-json",
        action="store_true",
        help="Print the selected portable/Windows area split as JSON without executing checks.",
    )
    args = parser.parse_args()

    if args.areas is not None:
        areas = [item.strip() for item in args.areas.split(",") if item.strip()]
        try:
            split_areas(areas)
        except ValueError as exc:
            parser.error(str(exc))
    else:
        run_all = args.all or not args.base_ref
        changed = set() if run_all else changed_files(args.base_ref)
        areas = select_areas(changed, run_all=run_all)

    if args.plan_json:
        print(json.dumps(split_areas(areas), sort_keys=True))
        return 0

    verify_entrypoint()
    run_areas(areas)

    if not areas:
        print("CHANGED_AREA_CHECKS_SKIPPED")
    print("REPOSITORY_VERIFY_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
