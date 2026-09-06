from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

PRODUCT_ROOTS = {
    "lowvram": r"C:\Users\Lauri\Desktop\lowvram3d-repo",
    "tiny3d": r"C:\Users\Lauri\Desktop\tiny3d",
    "p3": r"C:\Users\Lauri\Documents\Unreal Projects\p3",
}

ISSUE_REF_RE = re.compile(r"#(?P<number>\d+)\b")
GITHUB_REMOTE_RE = re.compile(r"github\.com[:/](?P<repo>[^/\s]+/[^/\s]+?)(?:\.git)?$")
INCIDENT_ID_RE = re.compile(r"\b(?:INC|RR)-[A-Za-z0-9][A-Za-z0-9._-]*\b", re.I)
ARTIFACT_ROOTS = (
    "01 Reports",
    "02 Evidence",
    "03 Fixtures and Experiments",
    "04 Operating Contracts",
    "90 Raw Transcripts",
)
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


@dataclass(frozen=True)
class RepoSpec:
    project: str
    path: Path


def _run_git(path: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check,
    )


def _git_value(path: Path, *args: str) -> str | None:
    proc = _run_git(path, *args, check=False)
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip()
    return value or None


def discover_repo_specs(*, vault_root: Path | None = None) -> list[RepoSpec]:
    """Discover the known product repos used by this historical Git index."""
    specs: list[RepoSpec] = []
    seen: set[str] = set()
    for project, raw in PRODUCT_ROOTS.items():
        path = Path(os.path.expandvars(raw))
        if not (path / ".git").exists():
            continue
        key = str(path.resolve()).casefold()
        if key in seen:
            continue
        seen.add(key)
        specs.append(RepoSpec(project=project, path=path))
    if vault_root is not None and (vault_root / ".git").exists():
        key = str(vault_root.resolve()).casefold()
        if key not in seen:
            specs.append(RepoSpec(project="vault", path=vault_root))
    return specs

def parse_repo_arg(value: str) -> RepoSpec:
    project, sep, path = value.partition("=")
    if not sep or not project.strip() or not path.strip():
        raise ValueError("repo must use PROJECT=PATH")
    return RepoSpec(project=project.strip().casefold(), path=Path(path.strip()))



def _refs_from_title(title: str) -> list[str]:
    return [f"#{match.group('number')}" for match in ISSUE_REF_RE.finditer(title)]


def _git_log_rows(path: Path, revisions: list[str], *, limit: int, since: datetime | None = None) -> list[tuple[str, str, str, str]]:
    args = ["log", *revisions, "--date-order", f"--max-count={min(200, max(1, int(limit)))}"]
    if since is not None:
        args.append(f"--since={since.isoformat()}")
    args.append("--format=%H%x1f%cI%x1f%s%x1f%D")
    proc = _run_git(path, *args, check=False)
    if proc.returncode != 0:
        return []
    rows: list[tuple[str, str, str, str]] = []
    for line in proc.stdout.splitlines():
        parts = line.split("\x1f")
        if len(parts) != 4:
            continue
        sha, event_at, title, decorations = parts
        try:
            datetime.fromisoformat(event_at.replace("Z", "+00:00"))
        except ValueError:
            continue
        rows.append((sha, event_at, title, decorations))
    return rows


def _event_from_row(spec: RepoSpec, row: tuple[str, str, str, str], *, origin: str | None) -> dict[str, Any]:
    sha, event_at, title, decorations = row
    return {
        "id": f"git:{spec.project}:{sha}",
        "source_type": "GIT_COMMIT",
        "authority": "REPO_HISTORY",
        "event_at": event_at,
        "project": spec.project,
        "projects": [spec.project],
        "title": title,
        "summary": title,
        "sha": sha,
        "short_sha": sha[:10],
        "refs": _refs_from_title(title),
        "anchors": _github_anchors(origin, _refs_from_title(title)),
        "decorations": decorations,
        "repo_path": str(spec.path),
        "origin": origin,
        "repo_state": "ALL_BRANCHES",
        "thread_id": f"repo:{spec.project}",
        "thread_source": "PROJECT_REPO_STREAM",
    }


def _github_repo_slug(origin: str | None) -> str | None:
    if not origin:
        return None
    match = GITHUB_REMOTE_RE.search(str(origin).strip())
    if not match:
        return None
    return match.group("repo").removesuffix(".git").casefold()


def _github_anchors(origin: str | None, refs: Iterable[str]) -> list[str]:
    slug = _github_repo_slug(origin)
    if not slug:
        return []
    anchors: list[str] = []
    for ref in refs:
        match = re.fullmatch(r"#(\d+)", str(ref).strip())
        if match:
            anchors.append(f"github:{slug}#{match.group(1)}")
    return sorted(set(anchors))


def _artifact_type(path: str, *, evidence_type: str | None = None) -> str:
    normalized = path.replace("\\", "/")
    lower = normalized.casefold()
    suffix = Path(normalized).suffix.casefold()
    if "proof" in lower:
        return "proof"
    if suffix in IMAGE_SUFFIXES or "screenshot" in lower:
        return "screenshot"
    if lower.startswith("01 reports/"):
        return "report"
    if lower.startswith("02 evidence/"):
        if suffix in {".jsonl", ".log"} or "log" in lower or "telemetry" in lower or "chronology" in lower:
            return "evidence_log"
        return "evidence"
    if lower.startswith("03 fixtures and experiments/"):
        return "fixture"
    if lower.startswith("04 operating contracts/"):
        return "contract"
    if lower.startswith("90 raw transcripts/"):
        return "transcript"
    return "artifact"


def _normalise_artifact_path(value: str) -> str:
    return str(value or "").replace("\\", "/").strip().strip('"')


def _provenance_path_map(vault_root: Path, provenance_path: Path | None = None) -> dict[str, dict[str, Any]]:
    path = provenance_path or (vault_root / "provenance.json")
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for entry in payload.get("entries", []) if isinstance(payload, dict) else []:
        if not isinstance(entry, dict):
            continue
        incident_id = str(entry.get("incident_id") or "").strip()
        meta = {
            "incident_id": incident_id or None,
            "report_title": entry.get("title"),
            "evidence_type": entry.get("evidence_type"),
            "report_path": entry.get("report_path"),
        }
        related = [entry.get("report_path")]
        for field in ("raw_transcripts", "evidence_files", "contract_snapshots"):
            values = entry.get(field)
            if isinstance(values, list):
                related.extend(values)
        for raw in related:
            normalized = _normalise_artifact_path(str(raw or ""))
            if normalized:
                out.setdefault(normalized.casefold(), meta)
    return out


def tracked_artifact_events(
    vault_root: Path,
    *,
    limit: int = 200,
    since: datetime | None = None,
    provenance_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Project Git-tracked reports/evidence/proofs into the canonical history timeline.

    Events are derived from local Git history only. Untracked files are intentionally not
    promoted into durable history merely because they exist in a worktree.
    """
    effective_limit = min(1000, max(0, int(limit)))
    if effective_limit == 0 or not vault_root.is_dir():
        return []
    if _run_git(vault_root, "rev-parse", "--git-dir", check=False).returncode != 0:
        return []
    args = [
        "-c", "core.quotepath=false", "log", "--all", "--date-order",
        f"--max-count={min(300, max(20, effective_limit))}",
    ]
    if since is not None:
        args.append(f"--since={since.isoformat()}")
    args.extend([
        "--format=%x1e%H%x1f%cI%x1f%s%x1f%D", "--name-status", "--", *ARTIFACT_ROOTS,
    ])
    proc = _run_git(vault_root, *args, check=False)
    if proc.returncode != 0:
        return []
    provenance = _provenance_path_map(vault_root, provenance_path)
    origin = _git_value(vault_root, "remote", "get-url", "origin")
    events: list[dict[str, Any]] = []
    for chunk in proc.stdout.split("\x1e"):
        chunk = chunk.strip("\r\n")
        if not chunk:
            continue
        lines = chunk.splitlines()
        header = lines[0].split("\x1f")
        if len(header) != 4:
            continue
        sha, event_at, commit_title, decorations = header
        try:
            datetime.fromisoformat(event_at.replace("Z", "+00:00"))
        except ValueError:
            continue
        for raw in lines[1:]:
            raw = raw.strip("\r\n")
            if not raw or "\t" not in raw:
                continue
            parts = raw.split("\t")
            change = parts[0]
            rel_path = _normalise_artifact_path(parts[-1])
            if not rel_path or not any(rel_path.casefold().startswith(root.casefold() + "/") for root in ARTIFACT_ROOTS):
                continue
            meta = provenance.get(rel_path.casefold(), {})
            incident_ids = {item.upper() for item in INCIDENT_ID_RE.findall(rel_path)}
            if meta.get("incident_id"):
                incident_ids.add(str(meta["incident_id"]).upper())
            refs = _refs_from_title(commit_title)
            anchors = [f"incident:{item.casefold()}" for item in sorted(incident_ids)]
            anchors.extend(_github_anchors(origin, refs))
            anchors.append("artifact:" + rel_path.casefold())
            artifact_type = _artifact_type(rel_path, evidence_type=meta.get("evidence_type"))
            report_title = str(meta.get("report_title") or "").strip()
            display = report_title if rel_path.casefold() == str(meta.get("report_path") or "").casefold() and report_title else Path(rel_path).name
            action = {"A": "added", "M": "updated", "D": "deleted"}.get(change[:1], "changed")
            events.append({
                "id": f"artifact:{sha}:{rel_path}",
                "source_type": "TRACKED_ARTIFACT",
                "authority": "PRESERVED_REPO_ARTIFACT_HISTORY",
                "event_at": event_at,
                "recorded_at": event_at,
                "project": "regression-research",
                "projects": ["regression-research"],
                "title": f"{artifact_type}: {display}",
                "summary": f"{action} in {sha[:10]}: {commit_title}",
                "artifact_type": artifact_type,
                "path": rel_path,
                "change": change,
                "sha": sha,
                "short_sha": sha[:10],
                "decorations": decorations,
                "refs": [rel_path, *refs],
                "anchors": sorted(set(anchors)),
                "incident_id": meta.get("incident_id"),
                "evidence_type": meta.get("evidence_type"),
                "report_path": meta.get("report_path"),
                "thread_id": "artifact:" + rel_path.casefold(),
                "thread_source": "PRESERVED_ARTIFACT_PATH",
            })
    events.sort(key=lambda event: (datetime.fromisoformat(event["event_at"].replace("Z", "+00:00")), event["id"]), reverse=True)
    if len(events) <= effective_limit:
        return events

    # Preserve high-signal evidence lanes before generic contract/fixture churn can
    # consume the bounded timeline source window.
    priority = (
        "report", "proof", "screenshot", "evidence_log",
        "evidence", "transcript", "contract", "fixture", "artifact",
    )
    chosen: list[dict[str, Any]] = []
    chosen_ids: set[str] = set()
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_type[str(event.get("artifact_type") or "artifact")].append(event)
    # Reserve every available high-signal report/proof/log/screenshot first.
    # event first; remaining capacity is filled in newest-first order.
    reserve_types = {"report", "proof", "screenshot", "evidence_log"}
    for artifact_type in priority:
        if artifact_type not in reserve_types:
            continue
        for event in by_type.get(artifact_type, []):
            ident = str(event["id"])
            if ident in chosen_ids:
                continue
            chosen.append(event)
            chosen_ids.add(ident)
            if len(chosen) >= effective_limit:
                break
        if len(chosen) >= effective_limit:
            break
    if len(chosen) < effective_limit:
        for event in events:
            ident = str(event["id"])
            if ident in chosen_ids:
                continue
            chosen.append(event)
            chosen_ids.add(ident)
            if len(chosen) >= effective_limit:
                break
    chosen.sort(key=lambda event: (datetime.fromisoformat(event["event_at"].replace("Z", "+00:00")), event["id"]), reverse=True)
    return chosen


def git_commit_events(spec: RepoSpec, *, limit: int = 20, since: datetime | None = None) -> list[dict[str, Any]]:
    """Return one bounded date-ordered chronology across every local/remote branch ref.

    No branch, including main/default, receives a privileged quota. Decorations preserve
    the refs that make each commit reachable so workers can orient from the actual live
    workstreams instead of treating one integration branch as the project timeline.
    """
    if limit <= 0 or not spec.path.is_dir():
        return []
    if _run_git(spec.path, "rev-parse", "--git-dir", check=False).returncode != 0:
        return []
    origin = _git_value(spec.path, "remote", "get-url", "origin")
    rows = _git_log_rows(spec.path, ["--all"], limit=limit, since=since)
    events = [_event_from_row(spec, row, origin=origin) for row in rows]
    events.sort(key=lambda event: (datetime.fromisoformat(event["event_at"].replace("Z", "+00:00")), event["id"]), reverse=True)
    return events

def collect_repo_history(specs: Iterable[RepoSpec], *, limit_per_repo: int = 20, since: datetime | None = None) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    coverage: dict[str, Any] = {}
    for spec in specs:
        project_events = git_commit_events(spec, limit=limit_per_repo, since=since)
        events.extend(project_events)
        coverage[spec.project] = {
            "events": len(project_events),
            "limit": max(0, int(limit_per_repo)),
            "saturated": bool(limit_per_repo > 0 and len(project_events) >= limit_per_repo),
        }
    events.sort(key=lambda event: (datetime.fromisoformat(event["event_at"].replace("Z", "+00:00")), event["id"]), reverse=True)
    return {
        "authority": "LOCAL_REPO_HISTORY",
        "contract": "local Git history only; no network fetch and no memory authority; saturated per-repo limits make event counts lower bounds",
        "coverage": coverage,
        "events": events,
    }
