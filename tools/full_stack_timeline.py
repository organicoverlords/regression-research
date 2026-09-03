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
            "category": _category(path, root),
            "path": str(path),
            "relative_path": path.relative_to(root).as_posix(),
            "size": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "event_at_hint": _event_time_from_name(path),
        })
    items.sort(key=lambda item: (item.get("event_at_hint") or item["modified_at"], item["relative_path"]), reverse=True)
    return items
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
            "id": item.get("id"),
            "event_at": event_at,
            "title": item.get("title") or item.get("summary") or item.get("kind") or item.get("id"),
            "scope": item.get("scope"),
            "kind": item.get("kind"),
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
            "id": f"git:{spec.project}:{sha}",
            "event_at": row["event_at"],
            "title": row["title"],
            "project": spec.project,
            "sha": sha,
            "decorations": row["decorations"],
            "repo_path": str(spec.path),
        })
    return events


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
    memory = collect_memory_events(vault_root / "memory" / "memory-bank.jsonl")
    worker_root = vault_root / "worker-reports" / "history"
    workers = worker_history_events(worker_root)
    commits = [event for spec in specs for event in collect_all_commit_events(spec, limit=commit_limit)]
    events = [*documents, *memory, *workers, *commits]
    if query:
        events = [item for item in events if _matches(item, query)]
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
            "storage": "read-only projection; no new database, queue, coordinator or authority is created",
        },
        "query": query,
        "repositories": git_states,
        "repo_snapshots": history["repo_snapshots"],
        "events": events,
        "counts": {
            "repositories": len(specs),
            "documents": len(documents),
            "memory_events": len(memory),
            "worker_events": len(workers),
            "git_commits": len(commits),
            "matching_events": len(events),
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
