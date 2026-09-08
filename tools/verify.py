#!/usr/bin/env python3
"""Run the deterministic repository checks used by CI."""

from __future__ import annotations

import argparse
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
    "tests/test_issue693_fresh_worker_entry.py",
    "tests/fixtures/issue693_fresh_worker_entry.json",
    "04 Operating Contracts/fresh-worker-generation-launch.md",
    "tools/replay_scoring.py",
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
    "04 Operating Contracts/chatgpt-personal-instructions-bootstrap.txt",
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

BUSY_ROOT = "03 Fixtures and Experiments/issue125-busy-coordinator"
BUSY_PATH_PREFIX = BUSY_ROOT + "/"

VERIFIER_PATHS = {
    "tools/verify.py",
    "tests/test_verify.py",
    ".github/workflows/changelog-landing.yml",
}


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
        return ["stack", "memory", "conversation", "busy"]
    selected = []
    if changed & STACK_PATHS:
        selected.append("stack")
    if changed & MEMORY_PATHS:
        selected.append("memory")
    if changed & CONVERSATION_PATHS:
        selected.append("conversation")
    if any(path.startswith(BUSY_PATH_PREFIX) for path in changed):
        selected.append("busy")
    return selected


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
        ]
    )
    run(
        [
            sys.executable,
            "-m",
            "unittest",
            "tests.test_stack_atlas",
            "tests.test_tiny3d_atlas_projection",
            "tests.test_issue693_fresh_worker_entry",
            "tests.test_issue122_acceptance_boundary_replay",
            "tests.test_issue122_false_boundary_replay",
            "tests.test_issue122_forensic_integrity",
            "tests.test_issue123_current_vault_history_boundary",
            "tests.test_issue123_response_shape",
            "tests.test_north_star_entry",
            "-v",
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
    args = parser.parse_args()

    run_all = args.all or not args.base_ref
    changed = set() if run_all else changed_files(args.base_ref)
    areas = select_areas(changed, run_all=run_all)

    verify_entrypoint()
    for area in areas:
        if area == "stack":
            verify_stack()
        elif area == "memory":
            verify_memory()
        elif area == "conversation":
            verify_conversation()
        elif area == "busy":
            verify_busy()

    if not areas:
        print("CHANGED_AREA_CHECKS_SKIPPED")
    print("REPOSITORY_VERIFY_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
