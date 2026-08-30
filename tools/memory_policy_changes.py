from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TRACKED_PATHS = (
    "memory/memory-bank.jsonl",
    "memory/behavior-authority-registry.json",
    "04 Operating Contracts",
    "AGENTS.md",
    "NORTH_STAR.md",
)
MAX_CHANGE_LOG_LIMIT = 100


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["git", *args], cwd=root, text=True, encoding="utf-8", capture_output=True
    )
    if check and proc.returncode:
        detail = (proc.stderr or proc.stdout).strip()[-1600:]
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return proc


def _first_parent(root: Path, commit: str) -> str | None:
    row = _git(root, "rev-list", "--parents", "-n", "1", commit).stdout.strip().split()
    return row[1] if len(row) > 1 else None


def _entry_summary(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entry.get("id"),
        "title": entry.get("title"),
        "kind": entry.get("kind"),
        "scope": entry.get("scope"),
        "state": entry.get("state"),
        "supersedes": list(entry.get("supersedes") or []),
    }


def _memory_delta(diff_text: str) -> dict[str, list[dict[str, Any]]]:
    added: dict[str, dict[str, Any]] = {}
    removed: dict[str, dict[str, Any]] = {}
    for raw in diff_text.splitlines():
        if raw.startswith("+++") or raw.startswith("---") or not raw[:1] in {"+", "-"}:
            continue
        try:
            entry = json.loads(raw[1:])
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            continue
        target = added if raw.startswith("+") else removed
        target[entry["id"]] = entry
    modified_ids = sorted(set(added) & set(removed))
    return {
        "added": [_entry_summary(added[i]) for i in sorted(set(added) - set(removed))],
        "modified": [_entry_summary(added[i]) for i in modified_ids],
        "removed": [_entry_summary(removed[i]) for i in sorted(set(removed) - set(added))],
    }


def _registry_at(root: Path, revision: str | None) -> dict[str, set[str]]:
    if revision is None:
        return {"user_explicit_ids": set(), "canonical_policy_ids": set()}
    proc = _git(
        root,
        "show",
        f"{revision}:memory/behavior-authority-registry.json",
        check=False,
    )
    if proc.returncode:
        return {"user_explicit_ids": set(), "canonical_policy_ids": set()}
    payload = json.loads(proc.stdout)
    return {
        "user_explicit_ids": set(payload.get("user_explicit_ids") or []),
        "canonical_policy_ids": set(payload.get("canonical_policy_ids") or []),
    }


def _authority_delta(root: Path, parent: str | None, commit: str) -> dict[str, list[str]]:
    before = _registry_at(root, parent)
    after = _registry_at(root, commit)
    return {
        "user_explicit_added": sorted(after["user_explicit_ids"] - before["user_explicit_ids"]),
        "user_explicit_removed": sorted(before["user_explicit_ids"] - after["user_explicit_ids"]),
        "canonical_policy_added": sorted(after["canonical_policy_ids"] - before["canonical_policy_ids"]),
        "canonical_policy_removed": sorted(before["canonical_policy_ids"] - after["canonical_policy_ids"]),
    }


def recent_memory_policy_changes(
    *, root: Path = ROOT, ref: str = "HEAD", limit: int = 20
) -> list[dict[str, Any]]:
    effective_limit = min(MAX_CHANGE_LOG_LIMIT, max(1, int(limit)))
    log = _git(
        root,
        "log",
        ref,
        f"--max-count={effective_limit}",
        "--format=%H%x09%aI%x09%s",
        "--",
        *TRACKED_PATHS,
    ).stdout
    changes: list[dict[str, Any]] = []
    for raw in log.splitlines():
        if not raw.strip():
            continue
        commit, timestamp, subject = raw.split("\t", 2)
        parent = _first_parent(root, commit)
        diff_args = ["diff"]
        if parent is None:
            diff_args.extend([f"{commit}^!", "--root"])
        else:
            diff_args.extend([parent, commit])
        paths = {
            line.strip().replace("\\", "/")
            for line in _git(root, *diff_args, "--name-only", "--", *TRACKED_PATHS).stdout.splitlines()
            if line.strip()
        }
        if parent is None:
            memory_diff = _git(
                root, "show", "--format=", "--unified=0", commit, "--", "memory/memory-bank.jsonl"
            ).stdout
        else:
            memory_diff = _git(
                root, "diff", "--unified=0", parent, commit, "--", "memory/memory-bank.jsonl"
            ).stdout
        policy_files = sorted(
            path for path in paths
            if path in {"AGENTS.md", "NORTH_STAR.md"} or path.startswith("04 Operating Contracts/")
        )
        changes.append({
            "commit": commit,
            "timestamp": timestamp,
            "subject": subject,
            "memory": _memory_delta(memory_diff),
            "behavior_authority": _authority_delta(root, parent, commit),
            "policy_files": policy_files,
        })
    return changes