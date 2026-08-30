#!/usr/bin/env python3
"""Require stack maps to move with architecture-bearing changes."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HUMAN_MAP = "docs/assistant-stack-human-map.md"
MACHINE_MAP = "docs/assistant-stack-capability-map.json"
REQUIRED_MAP_FILES = {HUMAN_MAP, MACHINE_MAP}

WATCHED_EXACT = {
    "AGENTS.md",
    "NORTH_STAR.md",
    "04 Operating Contracts/chatgpt-personal-instructions-bootstrap.txt",
    "04 Operating Contracts/fresh-chat-startup-orientation.md",
    "04 Operating Contracts/fresh-worker-generation-launch.md",
    "04 Operating Contracts/chatgpt-bootstrap-distribution.md",
    "tools/memory_timeline.py",
    "tools/memory_bank.py",
    "tools/chatgpt_bootstrap_artifact.py",
    "tools/capability_routing.py",
    "tools/busy_authority.py",
    "tools/stack_acceptance.py",
    "tools/live_worker_status.py",
}
WATCHED_PREFIXES = (
    "03 Fixtures and Experiments/issue125-busy-coordinator/",
)


def changed_files(base_ref: str) -> set[str]:
    commands = [
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
        ["git", "diff", "--name-only", "HEAD"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]
    changed: set[str] = set()
    for command in commands:
        output = subprocess.check_output(command, cwd=ROOT, text=True, encoding="utf-8")
        changed.update(
            line.strip().replace("\\", "/")
            for line in output.splitlines()
            if line.strip()
        )
    return changed


def architecture_changes(changed: set[str]) -> set[str]:
    return {
        path for path in changed
        if path in WATCHED_EXACT or any(path.startswith(prefix) for prefix in WATCHED_PREFIXES)
    }


def validate(changed: set[str]) -> None:
    impact = architecture_changes(changed)
    if not impact:
        return
    missing = REQUIRED_MAP_FILES - changed
    if missing:
        raise SystemExit(
            "STACK_MAP_FRESHNESS_FAIL: stack-defining changes require refreshed human + machine maps; "
            f"impact={sorted(impact)} missing={sorted(missing)}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Enforce assistant-stack map freshness.")
    parser.add_argument("--base-ref", required=True)
    args = parser.parse_args()
    changed = changed_files(args.base_ref)
    validate(changed)
    print("STACK_MAP_FRESHNESS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
