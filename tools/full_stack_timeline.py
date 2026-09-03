from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from .repo_timeline import RepoSpec, collect_repo_history, default_operator_live, discover_repo_specs, parse_repo_arg
    from .stack_atlas import COMPONENTS, PRODUCT_COMPONENTS, PRODUCT_ROOTS, MCP_ROOT
    from .worker_report_history import summarize_history, worker_history_events
except ImportError:
    from repo_timeline import RepoSpec, collect_repo_history, default_operator_live, discover_repo_specs, parse_repo_arg
    from stack_atlas import COMPONENTS, PRODUCT_COMPONENTS, PRODUCT_ROOTS, MCP_ROOT
    from worker_report_history import summarize_history, worker_history_events

ROOT = Path(__file__).resolve().parents[1]
DATE_RE = re.compile(r"(?P<date>20\d{2}[-_]?[01]\d[-_]?[0-3]\d)(?:[_-]?(?P<time>[0-2]\d[0-5]\d))?")
TEXT_EXTENSIONS = {".md", ".txt", ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ps1", ".py"}
SKIP_DIRS = {".git", ".pytest_cache", "node_modules", "__pycache__", ".tmp"}
EPISTEMIC_CLASSES = ("OBSERVED_FACT", "REPRODUCED_FACT", "INFERENCE", "HISTORICAL_CLAIM")
EXPLICIT_EVIDENCE_SCHEMA = "full-stack-timeline-events.v1"
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
            item = dict(raw)
            item["source_type"] = "STRUCTURED_EVIDENCE_EVENT"
            item["authority"] = "EXPLICIT_EVIDENCE_MANIFEST"
            item["manifest_path"] = path.relative_to(root).as_posix()
            item["evidence"] = list(evidence)
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
    reflog_text = _git(path, "reflog", "show", "--all", f"--max-count={max(1, reflog_limit)}", "--date=iso-strict", "--format=%H%x1f%gD%x1f%gI%x1f%gs")
    state["reflog"] = _parse_rows(reflog_text, ("sha", "selector", "event_at", "subject"))
    refs_text = _git(path, "for-each-ref", "--format=%(refname)%x1f%(objectname)%x1f%(committerdate:iso-strict)%x1f%(subject)")
    state["refs"] = _parse_rows(refs_text, ("ref", "sha", "event_at", "subject"))
    status = _git(path, "status", "--porcelain=v1")
    state["dirty_entries"] = len([line for line in status.splitlines() if line.strip()])
    state["mutation_admission"] = checkout_mutation_admission(state)
    return state


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
    ps = "$p=Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -match 'ChatGPTMcpClean|DesktopCommander|tailscale'} | Select-Object ProcessId,Name,CommandLine; $ids=@($p.ProcessId); $l=Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object {$ids -contains $_.OwningProcess} | Select-Object LocalAddress,LocalPort,OwningProcess; [pscustomobject]@{processes=$p;listeners=$l}|ConvertTo-Json -Depth 5 -Compress"
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
    memory = collect_memory_events(vault_root / "memory" / "memory-bank.jsonl")
    worker_root = vault_root / "worker-reports" / "history"
    workers = []
    for raw in worker_history_events(worker_root):
        item = dict(raw)
        item["epistemic_class"] = "HISTORICAL_CLAIM"
        item["epistemic_basis"] = "finalized worker self-report; useful lagging evidence but not current-state or liveness proof"
        workers.append(item)
    commits = [event for spec in specs for event in collect_all_commit_events(spec, limit=commit_limit)]
    events, relationships = _project_explicit_relationships([*documents, *explicit_evidence, *memory, *workers, *commits])
    if query:
        events = [item for item in events if _matches(item, query)]
        visible_ids = {str(item.get("id")) for item in events if item.get("id")}
        relationships = [rel for rel in relationships if rel["from_id"] in visible_ids or rel["to_id"] in visible_ids]
    events.sort(key=_sort_time, reverse=True)
    git_states = [collect_git_state(spec.project, spec.path, reflog_limit=reflog_limit) for spec in specs]
    history = collect_repo_history(specs, limit_per_repo=20)
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "authority": "DERIVED_FULL_STACK_TIMELINE_NOT_CURRENT_TRUTH",
        "contract": {
            "history": "documents, memory, worker reports and Git chronology are evidence with provenance, not current truth by themselves",
            "git": "branches, refs, tags, stashes, worktrees and reflogs come directly from each local Git object database",
            "runtime": "live probes are current observations only for the instant collected",
            "epistemics": "OBSERVED_FACT is directly observed metadata/runtime state; REPRODUCED_FACT and INFERENCE require explicit structured evidence with basis + evidence refs; documents, memory and worker reports remain HISTORICAL_CLAIM by default",
            "relationships": "only explicit supersedes/contradicts links are projected; chronology, matching text and proximity never create a contradiction or causal edge",
            "storage": "read-only projection; no new database, queue, coordinator or authority is created",
        },
        "query": query,
        "repositories": git_states,
        "repo_snapshots": history["repo_snapshots"],
        "events": events,
        "relationships": relationships,
        "structured_evidence_errors": explicit_evidence_errors,
        "epistemic_counts": _epistemic_counts(events),
        "counts": {
            "repositories": len(specs),
            "documents": len(documents),
            "explicit_evidence_events": len(explicit_evidence),
            "explicit_evidence_errors": len(explicit_evidence_errors),
            "memory_events": len(memory),
            "worker_events": len(workers),
            "git_commits": len(commits),
            "matching_events": len(events),
            "explicit_relationships": len(relationships),
        },
        "worker_metrics": summarize_history(worker_root, hours=24.0) if worker_root.exists() else {},
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
