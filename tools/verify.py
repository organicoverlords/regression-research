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
    "tools/capability_routing.py",
    "tests/fixtures/capability-routing-policy.json",
    "tests/test_capability_routing.py",
    "tools/instruction_provenance.py",
    "tests/fixtures/instruction-provenance-policy.json",
    "tests/fixtures/instruction-delivery-canary.json",
    "tests/fixtures/source-grounding-cases.json",
    "tests/test_instruction_provenance.py",
    "tools/busy_authority.py",
    "tests/fixtures/busy-ownership-policy.json",
    "tests/test_busy_authority.py",
    "tools/stack_acceptance.py",
    "tests/fixtures/stack-acceptance-scenarios.json",
    "tests/test_stack_acceptance.py",
    "tools/replay_scoring.py",
    "tools/evidence_bundle.py",
    "tests/test_evidence_bundle.py",
    "tools/connector_reliability.py",
    "tests/test_connector_reliability.py",
    "tests/test_north_star_entry.py",
    "03 Fixtures and Experiments/issue122-acceptance-boundary-classification.json",
    "tests/test_issue122_acceptance_boundary_replay.py",
    "03 Fixtures and Experiments/issue123-startup-memory-orchestration.json",
    "tests/test_issue123_startup_memory_acceptance.py",
}


MEMORY_PATHS = {
    "memory/behavior-authority-registry.json",
    "memory/README.md",
    "docs/assistant-stack-architecture.md",
    "04 Operating Contracts/chatgpt-personal-instructions-bootstrap.txt",
    "04 Operating Contracts/chatgpt-bootstrap-distribution.md",
    "tools/chatgpt_bootstrap_artifact.py",
    "tools/memory_authority.py",
    "tools/memory_bank.py",
    "tools/memory_classification.py",
    "tools/memory_git_sync.py",
    "tools/memory_hybrid.py",
    "tools/memory_timeline.py",
    "tools/benchmark_memory_behavior_retrieval.py",
    "tools/benchmark_memory_retrieval.py",
    "tools/provenance.py",
    "tools/wip_hygiene.py",
    "tests/fixtures/memory-behavior-retrieval-v1.json",
    "tests/test_memory_authority.py",
    "tests/test_memory_authority_pipeline.py",
    "tests/test_memory_bank.py",
    "tests/test_memory_bootstrap.py",
    "tests/test_memory_classification.py",
    "tests/test_memory_context_retrieval.py",
    "tests/test_memory_git_sync.py",
    "tests/test_memory_retrieval_quality.py",
    "tests/test_memory_timeline.py",
    "tests/test_provenance_index.py",
    "tests/test_taxonomy_matrix.py",
    "tests/test_wip_hygiene.py",
}

CONVERSATION_PATHS = {
    "tools/conversation_search.py",
    "tools/conversation_search_refresh.py",
    "tools/validate_conversation_search_corpus.py",
    "tests/test_conversation_search.py",
    "tests/test_conversation_search_refresh.py",
    "tests/fixtures/conversation-corpus/ChatPortEvidence/old.json",
    "tests/fixtures/conversation-corpus/ChatGPTLocalExporter/new.json",
}

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
        return ["stack", "memory", "conversation"]
    selected = []
    if changed & STACK_PATHS:
        selected.append("stack")
    if changed & MEMORY_PATHS:
        selected.append("memory")
    if changed & CONVERSATION_PATHS:
        selected.append("conversation")
    return selected


def run(command: list[str]) -> None:
    print(f"VERIFY_RUN: {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def verify_changelog(base_ref: str | None) -> None:
    command = [sys.executable, ".github/scripts/check_changelog_landing.py"]
    if base_ref:
        command.extend(["--base-ref", base_ref])
    run(command)


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
            "tools/capability_routing.py",
            "tools/instruction_provenance.py",
            "tools/busy_authority.py",
            "tools/stack_acceptance.py",
            "tools/replay_scoring.py",
            "tools/evidence_bundle.py",
            "tools/connector_reliability.py",
        ]
    )
    run(
        [
            sys.executable,
            "-m",
            "unittest",
            "tests.test_capability_routing",
            "tests.test_instruction_provenance",
            "tests.test_busy_authority",
            "tests.test_stack_acceptance",
            "tests.test_evidence_bundle",
            "tests.test_issue122_acceptance_boundary_replay",
            "tests.test_issue123_startup_memory_acceptance",
            "tests.test_connector_reliability",
            "tests.test_north_star_entry",
            "-v",
        ]
    )
    print("ASSISTANT_STACK_POLICY_PROVEN")


def verify_memory() -> None:
    run(
        [
            sys.executable,
            "-m",
            "py_compile",
            "tools/chatgpt_bootstrap_artifact.py",
            "tools/memory_authority.py",
            "tools/memory_bank.py",
            "tools/memory_classification.py",
            "tools/memory_git_sync.py",
            "tools/memory_hybrid.py",
            "tools/memory_timeline.py",
            "tools/benchmark_memory_behavior_retrieval.py",
            "tools/benchmark_memory_retrieval.py",
            "tools/provenance.py",
            "tools/wip_hygiene.py",
        ]
    )
    run([sys.executable, "tools/memory_bank.py", "validate"])
    run([sys.executable, "tools/memory_bank.py", "authority-validate"])
    run([sys.executable, "tools/provenance.py", "validate"])
    run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_memory_authority.py",
            "tests/test_memory_authority_pipeline.py",
            "tests/test_memory_bank.py",
            "tests/test_memory_bootstrap.py",
            "tests/test_memory_classification.py",
            "tests/test_memory_context_retrieval.py",
            "tests/test_memory_git_sync.py",
            "tests/test_memory_retrieval_quality.py",
            "tests/test_memory_timeline.py",
            "tests/test_provenance_index.py",
            "tests/test_taxonomy_matrix.py",
            "tests/test_wip_hygiene.py",
        ]
    )
    print("MEMORY_AUTHORITY_RETRIEVAL_PROVEN")


def verify_conversation() -> None:
    run(
        [
            sys.executable,
            "-m",
            "py_compile",
            "tools/conversation_search.py",
            "tools/conversation_search_refresh.py",
            "tools/validate_conversation_search_corpus.py",
        ]
    )
    run(
        [
            sys.executable,
            "-m",
            "unittest",
            "tests.test_conversation_search",
            "tests.test_conversation_search_refresh",
            "-v",
        ]
    )
    with tempfile.TemporaryDirectory(prefix="regression-research-verify-") as temp_dir:
        database = str(Path(temp_dir) / "conversation-search.sqlite3")
        corpus = "tests/fixtures/conversation-corpus"
        run(
            [
                sys.executable,
                "tools/conversation_search_refresh.py",
                "--db",
                database,
                "--corpus-root",
                corpus,
            ]
        )
        run([sys.executable, "tools/validate_conversation_search_corpus.py", "--db", database])
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

    verify_changelog(args.base_ref)
    verify_entrypoint()
    for area in areas:
        if area == "stack":
            verify_stack()
        elif area == "memory":
            verify_memory()
        elif area == "conversation":
            verify_conversation()

    if not areas:
        print("CHANGED_AREA_CHECKS_SKIPPED")
    print("REPOSITORY_VERIFY_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
