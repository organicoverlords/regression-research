from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from .repo_timeline import RepoSpec, collect_repo_history, default_operator_live, discover_repo_specs, parse_repo_arg
    from .stack_atlas import COMPONENTS, PRODUCT_COMPONENTS, PRODUCT_ROOTS, MCP_ROOT
    from .worker_report_history import worker_history_events
except ImportError:
    from repo_timeline import RepoSpec, collect_repo_history, default_operator_live, discover_repo_specs, parse_repo_arg
    from stack_atlas import COMPONENTS, PRODUCT_COMPONENTS, PRODUCT_ROOTS, MCP_ROOT
    from worker_report_history import worker_history_events

ROOT = Path(__file__).resolve().parents[1]
DATE_RE = re.compile(r"(?P<date>20\d{2}[-_]?[01]\d[-_]?[0-3]\d)(?:[_-]?(?P<time>[0-2]\d[0-5]\d))?")
TEXT_EXTENSIONS = {".md", ".txt", ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ps1", ".py"}
SKIP_DIRS = {".git", ".pytest_cache", "node_modules", "__pycache__", ".tmp"}
EPISTEMIC_CLASSES = ("OBSERVED_FACT", "REPRODUCED_FACT", "INFERENCE", "HISTORICAL_CLAIM")
EXPLICIT_EVIDENCE_SCHEMA = "full-stack-timeline-events.v1"
STRONG_EPISTEMIC_CLASSES = {"OBSERVED_FACT", "REPRODUCED_FACT", "INFERENCE"}
EXTERNAL_EVIDENCE_PREFIXES = ("git:", "github:", "http://", "https://")
ASSISTANT_HISTORY_SOURCES = (
    ("chatgpt-history", "ChatGPT"),
    ("opencode-history", "OpenCode"),
    ("claude-history", "Claude"),
    ("codex-history", "Codex"),
    ("traycer-artifacts", "Traycer"),
    ("command-code-history", "Command-Code"),
)
def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(args), cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def _git(path: Path, *args: str) -> str:
    proc = _run("git", "-C", str(path), *args)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _event_time_from_name(path: Path) -> str | None:
    match = DATE_RE.search(path.name)
    if not match:
        return None
    raw = match.group("date").replace("_", "-")
    if "-" not in raw:
        raw = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    clock = match.group("time") or "0000"
    try:
        stamp = datetime.fromisoformat(f"{raw}T{clock[:2]}:{clock[2:]}:00")
    except ValueError:
        return None
    return stamp.isoformat()


def _category(path: Path, root: Path) -> str:
    rel = path.relative_to(root).as_posix().casefold()
    name = path.name.casefold()
    if rel.startswith("04 operating contracts/"):
        return "operating_contract"
    if rel.startswith("03 fixtures and experiments/"):
        return "fixture_or_experiment"
    if rel.startswith("02 evidence/"):
        return "evidence"
    if rel.startswith("worker-reports/"):
        return "worker_report"
    if rel.startswith("memory/"):
        return "memory_source"
    if rel.startswith("01 reports/") or any(term in name for term in ("audit", "incident", "red-alert", "red_alert", "bug", "error", "slopwall")):
        return "incident_or_audit"
    if name in {"readme.md", "changelog.md", "north_star.md", "agents.md"}:
        return "project_document"
    return "other_durable_source"


def _resolve_assistant_history_location(vault_root: Path, home: Path, location: str) -> Path | None:
    if location == "preserved ChatGPT conversation/export corpus":
        return vault_root / "memory" / "conversations"
    if location.startswith("local/"):
        return home / Path(location[len("local/"):])
    return None


def collect_assistant_surface_coverage(
    vault_root: Path, *, home: Path | None = None, observed_at: str | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    home = home or Path.home()
    observed_at = observed_at or datetime.now(timezone.utc).isoformat()
    registry_path = vault_root / "memory" / "sources.json"
    errors: list[dict[str, Any]] = []
    inventory: dict[str, dict[str, Any]] = {}
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8-sig"))
        rows = payload.get("candidate_source_inventory")
        if not isinstance(rows, list):
            raise ValueError("candidate_source_inventory must be an array")
        inventory = {str(item.get("id")): item for item in rows if isinstance(item, dict) and item.get("id")}
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        errors.append({"path": str(registry_path), "error": f"assistant source registry unavailable: {exc}"})

    events: list[dict[str, Any]] = []
    for source_id, surface in ASSISTANT_HISTORY_SOURCES:
        raw = inventory.get(source_id)
        location = str(raw.get("location") or "") if raw else ""
        resolved = _resolve_assistant_history_location(vault_root, home, location) if location else None
        if raw is None:
            status = "REGISTRY_MISSING"
            path_kind = None
            basis = "required assistant-history source is missing from the source registry; this is a coverage gap and does not prove that behavior did not occur"
        elif resolved is None:
            status = "UNRESOLVED_LOCATION"
            path_kind = None
            basis = "assistant-history registry location is not concrete enough for filesystem verification; this is a coverage gap and does not prove source absence or behavior"
        elif resolved.is_dir():
            status = "SOURCE_PRESENT"
            path_kind = "directory"
            basis = "configured assistant-history source directory presence observed at collection time; this does not prove content completeness, freshness, or any behavior claim"
        elif resolved.is_file():
            status = "SOURCE_PRESENT"
            path_kind = "file"
            basis = "configured assistant-history source file presence observed at collection time; this does not prove content completeness, freshness, or any behavior claim"
        else:
            status = "SOURCE_MISSING"
            path_kind = "missing"
            basis = "configured assistant-history source path absence observed at collection time; this is a coverage gap and does not prove that behavior did not occur"
        events.append({
            "source_type": "ASSISTANT_SURFACE_COVERAGE",
            "authority": "LOCAL_SOURCE_REGISTRY_AND_FILESYSTEM",
            "epistemic_class": "OBSERVED_FACT",
            "epistemic_basis": basis,
            "id": f"assistant-coverage:{source_id}:{observed_at}",
            "event_at": observed_at,
            "title": f"{surface} history coverage: {status}",
            "surface": surface,
            "source_id": source_id,
            "registry_class": raw.get("class") if raw else None,
            "declared_availability": raw.get("availability") if raw else None,
            "registry_location": location or None,
            "resolved_path": str(resolved) if resolved is not None else None,
            "path_kind": path_kind,
            "coverage_status": status,
            "coverage_gap": status != "SOURCE_PRESENT",
            "content_coverage": "UNASSESSED",
        })
    return events, errors


def collect_opencode_session_events(db_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Project metadata-only OpenCode session chronology from the local primary database."""
    if not db_path.is_file():
        return [], [{
            "path": str(db_path),
            "error": "OpenCode session metadata store is unavailable; this is a coverage gap and does not prove behavior absence",
        }]

    events: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=1.0)
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(session)")}
        required = {"id", "time_created"}
        if not required.issubset(columns):
            missing = ", ".join(sorted(required - columns))
            raise ValueError(f"session table missing required columns: {missing}")
        wanted = [
            "id", "project_id", "workspace_id", "parent_id", "directory", "version", "agent", "model",
            "time_created", "time_updated", "time_archived",
        ]
        selected = [name for name in wanted if name in columns]
        sql = f"SELECT {', '.join(selected)} FROM session ORDER BY time_created, id"
        for values in connection.execute(sql):
            row = dict(zip(selected, values))
            session_id = str(row["id"])
            try:
                event_at = datetime.fromtimestamp(float(row["time_created"]) / 1000.0, tz=timezone.utc).isoformat()
                updated_at = (
                    datetime.fromtimestamp(float(row["time_updated"]) / 1000.0, tz=timezone.utc).isoformat()
                    if row.get("time_updated") is not None
                    else None
                )
                archived_at = (
                    datetime.fromtimestamp(float(row["time_archived"]) / 1000.0, tz=timezone.utc).isoformat()
                    if row.get("time_archived") is not None
                    else None
                )
            except (TypeError, ValueError, OSError, OverflowError) as exc:
                errors.append({
                    "path": str(db_path),
                    "session_id": session_id,
                    "error": f"invalid OpenCode session timestamp: {exc}",
                })
                continue

            model_raw = row.get("model")
            model_id = None
            model_provider = None
            model_variant = None
            if isinstance(model_raw, str) and model_raw:
                try:
                    model_payload = json.loads(model_raw)
                except json.JSONDecodeError:
                    model_id = model_raw
                else:
                    if isinstance(model_payload, dict):
                        model_id = model_payload.get("id")
                        model_provider = model_payload.get("providerID") or model_payload.get("provider_id")
                        model_variant = model_payload.get("variant")
                    else:
                        model_id = model_raw

            events.append({
                "source_type": "OPENCODE_SESSION",
                "authority": "LOCAL_OPENCODE_SQLITE",
                "epistemic_class": "OBSERVED_FACT",
                "epistemic_basis": "primary local OpenCode session metadata observed directly from opencode.db; title/metadata/prompt/message/part content and credentials are intentionally not read, and metadata does not prove task outcome or behavior",
                "id": f"opencode-session:{session_id}",
                "event_at": event_at,
                "updated_at": updated_at,
                "archived_at": archived_at,
                "title": f"OpenCode session metadata {session_id[:8]}",
                "surface": "OpenCode",
                "source_id": "opencode-history",
                "source_path": str(db_path),
                "content_coverage": "METADATA_ONLY",
                "session_id": session_id,
                "project_id": row.get("project_id"),
                "workspace_id": row.get("workspace_id"),
                "parent_id": row.get("parent_id"),
                "directory": row.get("directory"),
                "version": row.get("version"),
                "agent": row.get("agent"),
                "model_id": model_id,
                "model_provider": model_provider,
                "model_variant": model_variant,
                "archived": archived_at is not None,
            })
    except (sqlite3.Error, ValueError) as exc:
        errors.append({
            "path": str(db_path),
            "error": f"OpenCode session metadata unreadable: {exc}; this is a coverage gap and does not prove behavior absence",
        })
    finally:
        if connection is not None:
            connection.close()
    return events, errors


def collect_claude_session_events(claude_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Project metadata-only Claude session chronology from the local history index."""
    history_path = claude_root / "history.jsonl"
    if not history_path.is_file():
        return [], [{
            "path": str(history_path),
            "error": "Claude history index is unavailable; this is a coverage gap and does not prove behavior absence",
        }]

    sessions: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    try:
        with history_path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    errors.append({
                        "path": str(history_path),
                        "line": line_number,
                        "error": f"invalid Claude history JSON: {exc.msg}",
                    })
                    continue
                session_id = str(row.get("sessionId") or "").strip()
                timestamp = row.get("timestamp")
                if not session_id or not isinstance(timestamp, (int, float)):
                    continue
                record = sessions.setdefault(session_id, {
                    "first_timestamp_ms": timestamp,
                    "last_timestamp_ms": timestamp,
                    "projects": set(),
                    "history_entries": 0,
                })
                record["first_timestamp_ms"] = min(record["first_timestamp_ms"], timestamp)
                record["last_timestamp_ms"] = max(record["last_timestamp_ms"], timestamp)
                record["history_entries"] += 1
                project = row.get("project")
                if isinstance(project, str) and project.strip():
                    record["projects"].add(project)
    except OSError as exc:
        return [], [{
            "path": str(history_path),
            "error": f"Claude history index unavailable: {exc}; this is a coverage gap and does not prove behavior absence",
        }]

    events: list[dict[str, Any]] = []
    for session_id, record in sessions.items():
        try:
            event_at = datetime.fromtimestamp(float(record["first_timestamp_ms"]) / 1000.0, tz=timezone.utc).isoformat()
            updated_at = datetime.fromtimestamp(float(record["last_timestamp_ms"]) / 1000.0, tz=timezone.utc).isoformat()
        except (TypeError, ValueError, OSError, OverflowError) as exc:
            errors.append({
                "path": str(history_path),
                "session_id": session_id,
                "error": f"invalid Claude session timestamp: {exc}",
            })
            continue
        projects = sorted(record["projects"])
        events.append({
            "source_type": "CLAUDE_SESSION",
            "authority": "LOCAL_CLAUDE_HISTORY_JSONL",
            "epistemic_class": "OBSERVED_FACT",
            "epistemic_basis": "primary local Claude session metadata observed from history.jsonl; text-bearing display/pasted content is discarded and never emitted, and metadata does not prove task outcome or behavior",
            "id": f"claude-session:{session_id}",
            "event_at": event_at,
            "updated_at": updated_at,
            "title": f"Claude session metadata {session_id[:8]}",
            "surface": "Claude",
            "source_id": "claude-history",
            "source_path": str(history_path),
            "content_coverage": "METADATA_ONLY",
            "session_id": session_id,
            "history_entries": record["history_entries"],
            "projects": projects,
            "project_scope": projects[0] if len(projects) == 1 else None,
            "project_scope_conflict": len(projects) > 1,
        })
    return events, errors


def collect_codex_thread_events(codex_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Project metadata-only Codex thread chronology from the local primary state store."""
    db_path = codex_root / "state_5.sqlite"
    if not db_path.is_file():
        return [], [{
            "path": str(db_path),
            "error": "Codex thread metadata store is unavailable; this is a coverage gap and does not prove behavior absence",
        }]

    events: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=1.0)
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(threads)")}
        required = {"id", "created_at"}
        if not required.issubset(columns):
            missing = ", ".join(sorted(required - columns))
            raise ValueError(f"threads table missing required columns: {missing}")
        wanted = [
            "id", "created_at", "updated_at", "source", "thread_source", "cwd", "git_sha",
            "git_branch", "git_origin_url", "model", "reasoning_effort", "archived",
        ]
        selected = [name for name in wanted if name in columns]
        sql = f"SELECT {', '.join(selected)} FROM threads ORDER BY created_at, id"
        for values in connection.execute(sql):
            row = dict(zip(selected, values))
            thread_id = str(row["id"])
            try:
                event_at = datetime.fromtimestamp(float(row["created_at"]), tz=timezone.utc).isoformat()
                updated_at = (
                    datetime.fromtimestamp(float(row["updated_at"]), tz=timezone.utc).isoformat()
                    if row.get("updated_at") is not None
                    else None
                )
            except (TypeError, ValueError, OSError, OverflowError) as exc:
                errors.append({
                    "path": str(db_path),
                    "thread_id": thread_id,
                    "error": f"invalid Codex thread timestamp: {exc}",
                })
                continue
            events.append({
                "source_type": "CODEX_THREAD",
                "authority": "LOCAL_CODEX_STATE_SQLITE",
                "epistemic_class": "OBSERVED_FACT",
                "epistemic_basis": "primary local Codex thread metadata observed directly from state_5.sqlite; transcript/user content is intentionally not read, and metadata does not prove task outcome or behavior",
                "id": f"codex-thread:{thread_id}",
                "event_at": event_at,
                "updated_at": updated_at,
                "title": f"Codex thread metadata {thread_id[:8]}",
                "surface": "Codex",
                "source_id": "codex-history",
                "source_path": str(db_path),
                "content_coverage": "METADATA_ONLY",
                "thread_id": thread_id,
                "thread_source": row.get("thread_source") or row.get("source"),
                "cwd": row.get("cwd"),
                "git_sha": row.get("git_sha"),
                "git_branch": row.get("git_branch"),
                "git_origin_url": row.get("git_origin_url"),
                "model": row.get("model"),
                "reasoning_effort": row.get("reasoning_effort"),
                "archived": bool(row.get("archived")) if row.get("archived") is not None else None,
            })
    except (sqlite3.Error, ValueError) as exc:
        errors.append({
            "path": str(db_path),
            "error": f"Codex thread metadata unavailable: {exc}; this is a coverage gap and does not prove behavior absence",
        })
    finally:
        if connection is not None:
            connection.close()
    return events, errors


def collect_document_sources(root: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not root.is_dir():
        return items
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.casefold() not in TEXT_EXTENSIONS:
            continue
        if any(part.casefold() in SKIP_DIRS for part in path.relative_to(root).parts[:-1]):
            continue
        stat = path.stat()
        items.append({
            "source_type": "DOCUMENT",
            "authority": "HISTORICAL_OR_DOCUMENTARY_EVIDENCE",
            "epistemic_class": "HISTORICAL_CLAIM",
            "epistemic_basis": "document presence is observed; document contents remain historical/documentary claims until separately reproduced or observed",
            "category": _category(path, root),
            "path": str(path),
            "relative_path": path.relative_to(root).as_posix(),
            "size": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "event_at_hint": _event_time_from_name(path),
        })
    items.sort(key=lambda item: (item.get("event_at_hint") or item["modified_at"], item["relative_path"]), reverse=True)
    return items


def _validate_explicit_evidence(root: Path, evidence: list[str], epistemic_class: str) -> tuple[dict[str, Any] | None, str | None]:
    root_resolved = root.resolve()
    verified_local: list[str] = []
    external_refs: list[str] = []
    for raw in evidence:
        value = raw.strip()
        if value.startswith(EXTERNAL_EVIDENCE_PREFIXES):
            external_refs.append(value)
            continue
        candidate = Path(value)
        if candidate.is_absolute():
            return None, f"local evidence must be Vault-relative: {value}"
        resolved = (root / candidate).resolve()
        try:
            resolved.relative_to(root_resolved)
        except ValueError:
            return None, f"local evidence escapes Vault root: {value}"
        if not resolved.is_file():
            return None, f"missing local evidence: {value}"
        verified_local.append(candidate.as_posix())
    if epistemic_class in STRONG_EPISTEMIC_CLASSES and not verified_local:
        return None, f"{epistemic_class} requires at least one existing Vault-relative evidence file"
    return {"verified_local": verified_local, "external_refs": external_refs}, None


def collect_explicit_evidence_events(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    manifest_root = root / "02 Evidence" / "timeline-events"
    events: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    if not manifest_root.is_dir():
        return events, errors
    required = ("id", "event_at", "title", "epistemic_class", "epistemic_basis", "evidence")
    for path in sorted(manifest_root.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append({"path": str(path), "error": f"invalid manifest JSON: {exc}"})
            continue
        if payload.get("schema") != EXPLICIT_EVIDENCE_SCHEMA or not isinstance(payload.get("events"), list):
            errors.append({"path": str(path), "error": f"expected schema {EXPLICIT_EVIDENCE_SCHEMA} with events array"})
            continue
        for index, raw in enumerate(payload["events"]):
            if not isinstance(raw, dict):
                errors.append({"path": str(path), "event_index": index, "error": "event must be an object"})
                continue
            missing = [field for field in required if field not in raw or raw.get(field) in (None, "", [])]
            if missing:
                errors.append({"path": str(path), "event_index": index, "error": f"missing required fields: {', '.join(missing)}"})
                continue
            epistemic_class = str(raw.get("epistemic_class"))
            if epistemic_class not in EPISTEMIC_CLASSES:
                errors.append({"path": str(path), "event_index": index, "error": f"invalid epistemic_class: {epistemic_class}"})
                continue
            evidence = raw.get("evidence")
            if not isinstance(evidence, list) or not evidence or any(not isinstance(item, str) or not item.strip() for item in evidence):
                errors.append({"path": str(path), "event_index": index, "error": "evidence must be a non-empty string array"})
                continue
            evidence_validation, evidence_error = _validate_explicit_evidence(root, evidence, epistemic_class)
            if evidence_error:
                errors.append({"path": str(path), "event_index": index, "error": evidence_error})
                continue
            item = dict(raw)
            item["source_type"] = "STRUCTURED_EVIDENCE_EVENT"
            item["authority"] = "EXPLICIT_EVIDENCE_MANIFEST"
            item["manifest_path"] = path.relative_to(root).as_posix()
            item["evidence"] = list(evidence)
            item["evidence_validation"] = evidence_validation
            item["supersedes"] = _relation_values(item.get("supersedes"))
            item["contradicts"] = _relation_values(item.get("contradicts"))
            events.append(item)
    events.sort(key=_sort_time, reverse=True)
    return events, errors


def checkout_mutation_admission(state: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    if not state.get("available", True):
        reasons.append("repo_unavailable")
    if int(state.get("dirty_entries") or 0) > 0:
        reasons.append("dirty_checkout")
    head = state.get("head")
    origin_main = state.get("origin_main")
    if head and origin_main and head != origin_main:
        reasons.append("head_differs_from_origin_main")
    if not origin_main:
        reasons.append("origin_main_unresolved")
    admitted = not reasons
    return {
        "direct_mutation_admitted": admitted,
        "decision": "DIRECT_MUTATION_ADMITTED" if admitted else "ISOLATED_WORKTREE_REQUIRED",
        "status": "DIRECT_OK" if admitted else "ISOLATE_REQUIRED",
        "reasons": reasons,
        "preserve_checkout": True,
        "action": "mutate this checkout" if admitted else "preserve checkout and use an isolated current-base worktree or an already-owned admitted lane",
    }


def _parse_worktrees(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for line in [*text.splitlines(), ""]:
        if not line:
            if current:
                out.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        if key in {"bare", "detached", "locked", "prunable"}:
            current[key] = True if not value else value
        else:
            current[key] = value
    return out


def _parse_rows(text: str, fields: tuple[str, ...]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        parts = line.split("\x1f")
        if len(parts) != len(fields):
            continue
        rows.append(dict(zip(fields, parts)))
    return rows


def _reflog_rows(text: str) -> list[dict[str, str]]:
    rows = _parse_rows(text, ("sha", "selector", "subject"))
    for row in rows:
        selector = row.get("selector", "")
        match = re.search(r"@\{(.+)\}$", selector)
        row["event_at"] = match.group(1) if match else ""
    return rows


def collect_git_state(project: str, path: Path, *, reflog_limit: int = 80) -> dict[str, Any]:
    available = path.is_dir() and bool(_git(path, "rev-parse", "--git-dir"))
    state: dict[str, Any] = {"project": project, "path": str(path), "available": available, "authority": "LOCAL_GIT_OBJECT_DATABASE"}
    if not available:
        return state
    state["head"] = _git(path, "rev-parse", "HEAD") or None
    state["branch"] = _git(path, "branch", "--show-current") or None
    state["origin"] = _git(path, "remote", "get-url", "origin") or None
    state["origin_main"] = _git(path, "rev-parse", "origin/main") or None
    state["branches"] = [line.strip() for line in _git(path, "for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines() if line.strip()]
    state["remote_branches"] = [line.strip() for line in _git(path, "for-each-ref", "--format=%(refname:short)", "refs/remotes").splitlines() if line.strip()]
    state["tags"] = [line.strip() for line in _git(path, "tag", "--list").splitlines() if line.strip()]
    stash_text = _git(path, "stash", "list", "--date=iso-strict", "--format=%H%x1f%gd%x1f%cI%x1f%s")
    state["stashes"] = _parse_rows(stash_text, ("sha", "ref", "event_at", "subject"))
    state["worktrees"] = _parse_worktrees(_git(path, "worktree", "list", "--porcelain"))
    reflog_text = _git(path, "reflog", "show", "--all", f"--max-count={max(1, reflog_limit)}", "--date=iso-strict", "--format=%H%x1f%gD%x1f%gs")
    state["reflog"] = _reflog_rows(reflog_text)
    refs_text = _git(path, "for-each-ref", "--format=%(refname)%x1f%(objectname)%x1f%(committerdate:iso-strict)%x1f%(subject)")
    state["refs"] = _parse_rows(refs_text, ("ref", "sha", "event_at", "subject"))
    status = _git(path, "status", "--porcelain=v1")
    state["dirty_entries"] = len([line for line in status.splitlines() if line.strip()])
    state["mutation_admission"] = checkout_mutation_admission(state)
    return state


def recoverable_git_events(states: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for state in states:
        if not state.get("available"):
            continue
        project = str(state.get("project") or "unknown")
        repo_path = str(state.get("path") or "")
        for row in state.get("stashes") or []:
            sha = str(row.get("sha") or "")
            ref = str(row.get("ref") or "")
            event_at = str(row.get("event_at") or "")
            title = str(row.get("subject") or ref or sha or "stash")
            key = ("GIT_STASH", project, sha, ref, event_at)
            if key in seen:
                continue
            seen.add(key)
            events.append({
                "source_type": "GIT_STASH",
                "authority": "LOCAL_GIT_OBJECT_DATABASE",
                "epistemic_class": "OBSERVED_FACT",
                "epistemic_basis": "stash metadata observed in local Git; the stash subject does not prove the intent, effect, or correctness of contained changes",
                "id": f"git-stash:{project}:{sha}:{ref}:{event_at}",
                "event_at": event_at,
                "title": title,
                "project": project,
                "sha": sha,
                "ref": ref,
                "repo_path": repo_path,
            })
        for row in state.get("reflog") or []:
            sha = str(row.get("sha") or "")
            selector = str(row.get("selector") or "")
            event_at = str(row.get("event_at") or "")
            title = str(row.get("subject") or selector or sha or "reflog")
            key = ("GIT_REFLOG", project, sha, selector, event_at)
            if key in seen:
                continue
            seen.add(key)
            events.append({
                "source_type": "GIT_REFLOG",
                "authority": "LOCAL_GIT_OBJECT_DATABASE",
                "epistemic_class": "OBSERVED_FACT",
                "epistemic_basis": "reflog metadata observed in local Git; the reflog subject does not prove the intent, effect, or correctness of the referenced operation",
                "id": f"git-reflog:{project}:{sha}:{selector}:{event_at}",
                "event_at": event_at,
                "title": title,
                "project": project,
                "sha": sha,
                "selector": selector,
                "repo_path": repo_path,
            })
    events.sort(key=_sort_time, reverse=True)
    return events


def _dedupe_specs(specs: Iterable[RepoSpec]) -> list[RepoSpec]:
    out: list[RepoSpec] = []
    seen: set[str] = set()
    for spec in specs:
        key = str(spec.path).casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(spec)
    return out


def discover_full_stack_repos(vault_root: Path, extras: Iterable[RepoSpec] = ()) -> list[RepoSpec]:
    operator = default_operator_live(vault_root)
    specs = list(discover_repo_specs(operator, vault_root=vault_root))
    for project, raw in PRODUCT_ROOTS.items():
        specs.append(RepoSpec(project, Path(os.path.expandvars(raw))))
    candidates = {
        "agents": Path.home() / ".agents",
        "mcp": Path(os.path.expandvars(MCP_ROOT)),
        "dev-progress-board": vault_root.parent / "DevProgressBoard",
    }
    specs.extend(RepoSpec(project, path) for project, path in candidates.items() if path.exists())
    specs.extend(extras)
    return _dedupe_specs(specs)
def _safe_json_command(*args: str) -> Any:
    proc = _run(*args)
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def collect_live_runtime() -> dict[str, Any]:
    runtime: dict[str, Any] = {
        "authority": "LIVE_RUNTIME_OBSERVATION",
        "epistemic_class": "OBSERVED_FACT",
        "epistemic_basis": "live probe result observed during this collection run",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "atlas_components": sorted({**COMPONENTS, **PRODUCT_COMPONENTS}),
    }
    if os.name != "nt":
        runtime["coverage_gap"] = "Windows-local runtime probes unavailable on this host"
        return runtime
    tailscale = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tailscale" / "tailscale.exe"
    if tailscale.is_file():
        runtime["tailscale_serve"] = _safe_json_command(str(tailscale), "serve", "status", "--json")
    try:
        with urllib.request.urlopen("https://5-61-91-127.sslip.io/edge-status", timeout=5) as response:
            runtime["vps_edge"] = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        runtime["vps_edge"] = {"status": "UNAVAILABLE", "error": f"{type(exc).__name__}: {exc}"}
    ps = "$p=Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -match 'ChatGPTMcpClean|tailscale'} | Select-Object ProcessId,Name,CommandLine; $ids=@($p.ProcessId); $l=Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object {$ids -contains $_.OwningProcess} | Select-Object LocalAddress,LocalPort,OwningProcess; [pscustomobject]@{processes=$p;listeners=$l}|ConvertTo-Json -Depth 5 -Compress"
    runtime["machine_routes"] = _safe_json_command("powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps)
    return runtime


def collect_memory_events(bank: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if not bank.is_file():
        return events
    for line in bank.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_at = item.get("event_at") or item.get("recorded_at") or item.get("timestamp")
        events.append({
            "source_type": "VAULT_MEMORY",
            "authority": "HISTORICAL_EVIDENCE_ONLY",
            "epistemic_class": "HISTORICAL_CLAIM",
            "epistemic_basis": "memory record is preserved history; its state label does not promote it to current truth",
            "id": item.get("id"),
            "event_at": event_at,
            "title": item.get("title") or item.get("summary") or item.get("kind") or item.get("id"),
            "scope": item.get("scope"),
            "kind": item.get("kind"),
            "state": item.get("state"),
            "project": item.get("project"),
            "thread": item.get("thread"),
            "supersedes": list(item.get("supersedes") or []),
            "contradicts": list(item.get("contradicts") or []),
        })
    return events
def collect_all_commit_events(spec: RepoSpec, *, limit: int = 0) -> list[dict[str, Any]]:
    if not spec.path.is_dir() or not _git(spec.path, "rev-parse", "--git-dir"):
        return []
    args = ["log", "--all", "--date-order"]
    if limit > 0:
        args.append(f"--max-count={limit}")
    args.append("--format=%H%x1f%cI%x1f%s%x1f%D")
    text = _git(spec.path, *args)
    events: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in _parse_rows(text, ("sha", "event_at", "title", "decorations")):
        sha = row["sha"]
        if sha in seen:
            continue
        seen.add(sha)
        events.append({
            "source_type": "GIT_COMMIT",
            "authority": "LOCAL_GIT_OBJECT_DATABASE",
            "epistemic_class": "OBSERVED_FACT",
            "epistemic_basis": "commit object metadata observed in local Git",
            "id": f"git:{spec.project}:{sha}",
            "event_at": row["event_at"],
            "title": row["title"],
            "project": spec.project,
            "sha": sha,
            "decorations": row["decorations"],
            "repo_path": str(spec.path),
        })
    return events


def _relation_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item]
    return []


def _project_explicit_relationships(events: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    projected = [dict(item) for item in events]
    by_id = {str(item["id"]): item for item in projected if item.get("id")}
    relationships: list[dict[str, Any]] = []
    for item in projected:
        source_id = str(item.get("id") or "")
        if not source_id:
            continue
        for field, relation, reverse_field in (
            ("supersedes", "SUPERSEDES", "superseded_by"),
            ("contradicts", "CONTRADICTS", "contradicted_by"),
        ):
            for target_id in _relation_values(item.get(field)):
                relationships.append({
                    "relation": relation,
                    "from_id": source_id,
                    "to_id": target_id,
                    "explicit": True,
                    "source_type": item.get("source_type"),
                })
                target = by_id.get(target_id)
                if target is not None:
                    target.setdefault(reverse_field, []).append(source_id)
    for item in projected:
        for field in ("superseded_by", "contradicted_by"):
            if field in item:
                item[field] = sorted(set(item[field]))
    relationships.sort(key=lambda rel: (rel["from_id"], rel["relation"], rel["to_id"]))
    return projected, relationships


def _epistemic_counts(events: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = {name: 0 for name in EPISTEMIC_CLASSES}
    for item in events:
        value = str(item.get("epistemic_class") or "")
        if value in counts:
            counts[value] += 1
    return counts


def _sort_time(item: dict[str, Any]) -> str:
    return str(item.get("event_at") or item.get("event_at_hint") or item.get("modified_at") or "")


def _matches(item: dict[str, Any], query: str) -> bool:
    if not query:
        return True
    needle = query.casefold()
    return needle in json.dumps(item, ensure_ascii=False, default=str).casefold()


def build_full_stack_timeline(vault_root: Path, *, extra_specs: Iterable[RepoSpec] = (), query: str = "", commit_limit: int = 0, reflog_limit: int = 120, live: bool = True) -> dict[str, Any]:
    specs = discover_full_stack_repos(vault_root, extra_specs)
    documents = collect_document_sources(vault_root)
    explicit_evidence, explicit_evidence_errors = collect_explicit_evidence_events(vault_root)
    assistant_coverage, assistant_coverage_errors = collect_assistant_surface_coverage(vault_root)
    opencode_coverage = next((item for item in assistant_coverage if item.get("source_id") == "opencode-history"), None)
    opencode_db = Path(str(opencode_coverage["resolved_path"])) if opencode_coverage and opencode_coverage.get("coverage_status") == "SOURCE_PRESENT" else None
    opencode_events, opencode_errors = collect_opencode_session_events(opencode_db) if opencode_db is not None else ([], [])
    claude_coverage = next((item for item in assistant_coverage if item.get("source_id") == "claude-history"), None)
    claude_root = Path(str(claude_coverage["resolved_path"])) if claude_coverage and claude_coverage.get("coverage_status") == "SOURCE_PRESENT" else None
    claude_events, claude_errors = collect_claude_session_events(claude_root) if claude_root is not None else ([], [])
    codex_coverage = next((item for item in assistant_coverage if item.get("source_id") == "codex-history"), None)
    codex_root = Path(str(codex_coverage["resolved_path"])) if codex_coverage and codex_coverage.get("coverage_status") == "SOURCE_PRESENT" else None
    codex_events, codex_errors = collect_codex_thread_events(codex_root) if codex_root is not None else ([], [])
    memory = collect_memory_events(vault_root / "memory" / "memory-bank.jsonl")
    worker_root = vault_root / "worker-reports" / "history"
    workers = []
    for raw in worker_history_events(worker_root):
        item = dict(raw)
        item["epistemic_class"] = "HISTORICAL_CLAIM"
        item["epistemic_basis"] = "finalized worker self-report; useful lagging evidence but not current-state or liveness proof"
        workers.append(item)
    commits = [event for spec in specs for event in collect_all_commit_events(spec, limit=commit_limit)]
    git_states = [collect_git_state(spec.project, spec.path, reflog_limit=reflog_limit) for spec in specs]
    recovery_events = recoverable_git_events(git_states)
    events, relationships = _project_explicit_relationships([*documents, *explicit_evidence, *assistant_coverage, *opencode_events, *claude_events, *codex_events, *memory, *workers, *commits, *recovery_events])
    if query:
        events = [item for item in events if _matches(item, query)]
        visible_ids = {str(item.get("id")) for item in events if item.get("id")}
        relationships = [rel for rel in relationships if rel["from_id"] in visible_ids or rel["to_id"] in visible_ids]
    events.sort(key=_sort_time, reverse=True)
    history = collect_repo_history(specs, limit_per_repo=20)
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "authority": "DERIVED_FULL_STACK_TIMELINE_NOT_CURRENT_TRUTH",
        "contract": {
            "history": "documents, memory, worker reports and Git chronology are evidence with provenance, not current truth by themselves",
            "git": "commits plus searchable stash/reflog metadata, branches, refs, tags and worktrees come directly from each local Git object database; Git messages never prove effect or intent",
            "runtime": "live probes are current observations only for the instant collected",
            "assistant_surfaces": "ChatGPT/OpenCode/Claude/Codex/Traycer/Command-Code source presence is checked from the existing memory/sources.json registry; OpenCode session metadata is projected from opencode.db, Claude session metadata from history.jsonl, and Codex thread metadata from state_5.sqlite while text/transcript content is excluded from emitted events; present paths do not prove content completeness and missing/unresolved paths remain explicit coverage gaps",
            "epistemics": "OBSERVED_FACT is directly observed metadata/runtime state; REPRODUCED_FACT and INFERENCE require explicit structured evidence with basis + evidence refs; documents, memory and worker reports remain HISTORICAL_CLAIM by default",
            "relationships": "only explicit supersedes/contradicts links are projected; chronology, matching text and proximity never create a contradiction or causal edge",
            "storage": "read-only projection; no new database, queue, coordinator or authority is created",
        },
        "query": query,
        "repositories": git_states,
        "repo_snapshots": history["repo_snapshots"],
        "events": events,
        "relationships": relationships,
        "assistant_surface_coverage": assistant_coverage,
        "assistant_surface_coverage_errors": assistant_coverage_errors,
        "opencode_session_errors": opencode_errors,
        "claude_session_errors": claude_errors,
        "codex_thread_errors": codex_errors,
        "structured_evidence_errors": explicit_evidence_errors,
        "epistemic_counts": _epistemic_counts(events),
        "counts": {
            "repositories": len(specs),
            "documents": len(documents),
            "explicit_evidence_events": len(explicit_evidence),
            "explicit_evidence_errors": len(explicit_evidence_errors),
            "assistant_surface_sources": len(assistant_coverage),
            "assistant_surface_gaps": sum(1 for item in assistant_coverage if item.get("coverage_gap")),
            "opencode_session_events": len(opencode_events),
            "opencode_session_errors": len(opencode_errors),
            "claude_session_events": len(claude_events),
            "claude_session_errors": len(claude_errors),
            "codex_thread_events": len(codex_events),
            "codex_thread_errors": len(codex_errors),
            "memory_events": len(memory),
            "worker_events": len(workers),
            "git_commits": len(commits),
            "git_recovery_events": len(recovery_events),
            "matching_events": len(events),
            "explicit_relationships": len(relationships),
        },
    }
    if live:
        result["runtime"] = collect_live_runtime()
    return result
def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only full-stack/project chronology and live-topology projection for workers.")
    parser.add_argument("query", nargs="?", default="", help="optional case-insensitive filter over timeline events")
    parser.add_argument("--vault-root", type=Path, default=ROOT)
    parser.add_argument("--repo", action="append", default=[], metavar="PROJECT=PATH")
    parser.add_argument("--commit-limit", type=int, default=0, help="0 means all reachable local commits")
    parser.add_argument("--reflog-limit", type=int, default=120)
    parser.add_argument("--no-live", action="store_true")
    parser.add_argument("--output", type=Path, help="write full JSON here; stdout is used when omitted")
    args = parser.parse_args()
    extras = [parse_repo_arg(value) for value in args.repo]
    report = build_full_stack_timeline(
        args.vault_root,
        extra_specs=extras,
        query=args.query,
        commit_limit=args.commit_limit,
        reflog_limit=args.reflog_limit,
        live=not args.no_live,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
        print(json.dumps({"ok": True, "output": str(args.output), "counts": report["counts"]}, ensure_ascii=False))
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
