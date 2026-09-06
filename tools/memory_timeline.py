from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

try:
    from .memory_classification import classify_entry, projects_from_text, token_words
except ImportError:
    from memory_classification import classify_entry, projects_from_text, token_words

DEFAULT_LIMIT = 20
MAX_LIMIT = 50
MAX_SUMMARY_CHARS = 280
ERROR_MARKERS = {
    "error", "incident", "slopwall", "red-alert", "redalert", "red-critical", "panic-alert",
    "recurrence", "regression", "failure", "security-incident",
}
RECURRENCE_WORDS = {"again", "same", "recurrence", "recurred", "returned", "back"}
ERROR_WORDS = {"error", "bug", "broken", "failure", "failed", "failing", "incident", "problem", "issue", "wrong"}
_GITHUB_EVIDENCE_RE = re.compile(r"^github:([^/\s]+/[^#\s]+)#(\d+)$", re.I)
_GITHUB_URL_RE = re.compile(r"^https?://github\.com/([^/\s]+/[^/\s]+)/(?:issues|pull)/(\d+)(?:[/?#].*)?$", re.I)
_INCIDENT_EVIDENCE_RE = re.compile(r"\bINC-\d{8}(?:-\d{6})?(?:-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)?\b", re.I)

VAGUE_WORDS = {
    "a", "an", "and", "are", "back", "did", "error", "again", "happened", "is", "it", "my", "omg",
    "same", "the", "this", "that", "what", "why", "with", "wrong", "problem", "issue", "broken", "failed",
}


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _clip(value: Any, limit: int = MAX_SUMMARY_CHARS) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _safe_dt(value: Any) -> datetime | None:
    try:
        return _dt(str(value))
    except (TypeError, ValueError):
        return None


def _evidence_anchors(values: Iterable[Any]) -> list[str]:
    anchors: set[str] = set()
    for raw in values:
        value = str(raw or "").strip()
        if not value:
            continue
        match = _GITHUB_EVIDENCE_RE.match(value)
        if match:
            anchors.add(f"github:{match.group(1).casefold()}#{match.group(2)}")
            continue
        match = _GITHUB_URL_RE.match(value)
        if match:
            anchors.add(f"github:{match.group(1).casefold()}#{match.group(2)}")
            continue
        if value.casefold().startswith("incident:"):
            anchors.add(value.casefold())
            continue
        for incident in _INCIDENT_EVIDENCE_RE.findall(value):
            anchors.add(f"incident:{incident.casefold()}")
    return sorted(anchors)


def _event_source_family(event: dict[str, Any]) -> str:
    return {
        "VAULT_MEMORY": "memory",
        "GIT_COMMIT": "repo",
        "WORKER_REPORT": "worker",
        "TRACKED_ARTIFACT": "artifact",
    }.get(str(event.get("source_type") or ""), "other")


def _highlight_bucket(event: dict[str, Any]) -> str:
    family = _event_source_family(event)
    if family == "artifact":
        return "artifact:" + str(event.get("artifact_type") or "artifact")
    return family


def _event_anchors(event: dict[str, Any]) -> list[str]:
    anchors = {str(item).casefold() for item in event.get("anchors", []) if str(item).strip()}
    anchors.update(_evidence_anchors(event.get("evidence", [])))
    anchors.update(_evidence_anchors(event.get("refs", [])))
    proof = str(event.get("proof_artifact") or "").replace("\\", "/").strip()
    if proof:
        anchors.add("artifact:" + proof.casefold())
    return sorted(anchors)


def _compact_snapshot_event(event: dict[str, Any]) -> dict[str, Any]:
    out = {
        "id": event.get("id"),
        "event_at": event.get("event_at"),
        "source_type": event.get("source_type"),
        "title": _clip(event.get("title"), 120),
    }
    for key in ("project", "artifact_type", "disposition", "short_sha", "population"):
        if event.get(key) not in (None, "", []):
            out[key] = event.get(key)
    return out


def _diverse_highlights(events: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    ordered = sorted(events, key=lambda event: (_dt(str(event["event_at"])), str(event.get("id") or "")), reverse=True)
    priority = [
        "repo", "worker", "memory",
        "artifact:incident_report", "artifact:proof", "artifact:screenshot", "artifact:evidence_log",
        "artifact:report", "artifact:evidence", "artifact:transcript", "artifact:contract", "artifact:fixture", "artifact:artifact",
        "other",
    ]
    latest_by_bucket: dict[str, dict[str, Any]] = {}
    for event in ordered:
        latest_by_bucket.setdefault(_highlight_bucket(event), event)
    chosen: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for bucket in priority:
        event = latest_by_bucket.get(bucket)
        if event is None:
            continue
        ident = str(event.get("id") or "")
        chosen.append(event)
        used_ids.add(ident)
        if len(chosen) >= limit:
            return [_compact_snapshot_event(item) for item in chosen]
    for event in ordered:
        ident = str(event.get("id") or "")
        if ident in used_ids:
            continue
        chosen.append(event)
        if len(chosen) >= limit:
            break
    return [_compact_snapshot_event(event) for event in chosen]


def build_timeline_snapshots(
    events: Iterable[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build cumulative 24h/3d/7d snapshots from the canonical multi-source timeline.

    24h gets the richest highlights. 3d and 7d counts are cumulative, while their
    highlights come only from the older incremental slice to avoid repeating the same
    newest events three times.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.astimezone()
    valid: list[tuple[dict[str, Any], datetime]] = []
    for raw in events:
        event = dict(raw)
        stamp = _safe_dt(event.get("event_at"))
        if stamp is None:
            continue
        valid.append((event, stamp.astimezone(now.tzinfo)))

    windows: list[dict[str, Any]] = []
    for label, upper_hours, lower_hours, highlight_limit in (
        ("24h", 24, 0, 8),
        ("3d", 72, 24, 5),
        ("7d", 168, 72, 5),
    ):
        cumulative: list[dict[str, Any]] = []
        incremental: list[dict[str, Any]] = []
        for event, stamp in valid:
            age_hours = (now - stamp).total_seconds() / 3600.0
            if age_hours < 0 or age_hours > upper_hours:
                continue
            cumulative.append(event)
            if age_hours >= lower_hours:
                incremental.append(event)

        source_counts = Counter(str(event.get("source_type") or "UNKNOWN") for event in cumulative)
        slice_source_counts = Counter(str(event.get("source_type") or "UNKNOWN") for event in incremental)
        artifact_counts = Counter(
            str(event.get("artifact_type") or "artifact")
            for event in cumulative if event.get("source_type") == "TRACKED_ARTIFACT"
        )
        anchor_groups: dict[str, dict[str, Any]] = {}
        for event in cumulative:
            family = _event_source_family(event)
            for anchor in _event_anchors(event):
                group = anchor_groups.setdefault(anchor, {"families": set(), "event_ids": set(), "latest_at": None})
                group["families"].add(family)
                group["event_ids"].add(str(event.get("id") or ""))
                stamp = str(event.get("event_at") or "")
                if group["latest_at"] is None or (_safe_dt(stamp) and _safe_dt(group["latest_at"]) and _dt(stamp) > _dt(group["latest_at"])):
                    group["latest_at"] = stamp
        corroborated = [
            {
                "anchor": anchor,
                "source_families": sorted(group["families"]),
                "event_count": len(group["event_ids"]),
            }
            for anchor, group in anchor_groups.items()
            if len(group["families"]) >= 2
        ]
        corroborated.sort(key=lambda item: (-len(item["source_families"]), -item["event_count"], item["anchor"]))
        windows.append({
            "window": label,
            "hours": upper_hours,
            "event_count": len(cumulative),
            "source_counts": dict(sorted(source_counts.items())),
            "artifact_counts": dict(sorted(artifact_counts.items())),
            "corroborated_anchors": corroborated[:6],
            "slice": "0-24h" if lower_hours == 0 else f"{lower_hours}h-{upper_hours}h",
            "slice_event_count": len(incremental),
            "slice_source_counts": dict(sorted(slice_source_counts.items())),
            "highlights": _diverse_highlights(incremental, highlight_limit),
        })
    return {
        "authority": "DERIVED_HISTORY_ONLY",
        "contract": "multi-source chronology snapshot; source diversity is corroboration evidence, not independent witness proof, current-state authority, or causal inference",
        "as_of": now.isoformat(),
        "windows": windows,
    }


def _title(entry: dict[str, Any]) -> str:
    title = str(entry.get("title") or "").strip()
    if title:
        return title
    text = " ".join(str(entry.get("text") or "").split())
    first = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0] if text else entry.get("id", "event")
    return _clip(first, 100)


def _superseded_by(entries: Iterable[dict[str, Any]]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for entry in entries:
        for target in entry.get("supersedes", []):
            out[str(target)].append(str(entry["id"]))
    return {key: sorted(values) for key, values in out.items()}


def _disposition(entry: dict[str, Any], superseded_by: dict[str, list[str]], classification: dict[str, Any]) -> str:
    if entry.get("state") == "REJECTED":
        return "REJECTED"
    if str(entry.get("id")) in superseded_by:
        return "SUPERSEDED"
    if classification.get("sensitivity") == "EXCLUDE":
        return "SENSITIVE_EXCLUDED"
    durability = classification.get("durability")
    if durability == "EPHEMERAL":
        return "EPHEMERAL/DO_NOT_RECALL"
    if durability == "HISTORICAL" or classification.get("expired"):
        return "HISTORICAL_DURABLE"
    if entry.get("state") == "PROVISIONAL":
        return "PROVISIONAL/NEEDS_EVIDENCE"
    return "CURRENT_DURABLE"


def _stable_evidence_thread(entry: dict[str, Any]) -> str | None:
    """Return one unambiguous durable evidence anchor, or abstain."""
    anchors: set[str] = set()
    for raw in entry.get("evidence", []):
        value = str(raw or "").strip()
        if not value:
            continue
        match = _GITHUB_EVIDENCE_RE.match(value)
        if match:
            anchors.add(f"github:{match.group(1).casefold()}#{match.group(2)}")
            continue
        match = _GITHUB_URL_RE.match(value)
        if match:
            anchors.add(f"github:{match.group(1).casefold()}#{match.group(2)}")
            continue
        incidents = {item.casefold() for item in _INCIDENT_EVIDENCE_RE.findall(value)}
        anchors.update(f"incident:{item}" for item in incidents)
    if len(anchors) == 1:
        return next(iter(anchors))
    return None


def _thread_identity(entry: dict[str, Any], classification: dict[str, Any]) -> tuple[str, str]:
    explicit = str(entry.get("thread") or "").strip()
    if explicit:
        return "thread:" + explicit.casefold(), "EXPLICIT_THREAD"
    evidence_anchor = _stable_evidence_thread(entry)
    if evidence_anchor:
        return "evidence:" + evidence_anchor, "EVIDENCE_ANCHOR"
    scope = str(entry.get("scope") or "global").strip().casefold()
    # Only structurally specific scopes are safe implicit thread identities. Broad
    # scopes such as `response-quality`, `mcp`, or `p3` contain unrelated events.
    if scope and scope != "global" and any(char in scope for char in "/:,#"):
        return "scope:" + scope, "SPECIFIC_SCOPE"
    return "event:" + str(entry.get("id")), "EVENT_ONLY"


def _project_linkage(classification: dict[str, Any], project: str | None) -> str | None:
    if not project:
        return None
    project = project.casefold()
    if project in set(classification.get("projects") or []):
        return "EXPLICIT_PROJECT"
    if project in set(classification.get("entities") or []):
        return "ENTITY_MENTION"
    return None


def _is_error_event(entry: dict[str, Any], classification: dict[str, Any]) -> bool:
    if classification.get("semantic_category") == "INCIDENT":
        return True
    descriptors = " ".join([
        str(entry.get("scope") or ""), str(entry.get("title") or ""),
        *[str(tag) for tag in entry.get("tags", [])],
    ]).casefold()
    words = token_words(descriptors)
    return bool(words & ERROR_MARKERS) or any(marker in descriptors for marker in ERROR_MARKERS)


def _query_tokens(query: str, *, error_view: bool = False) -> set[str]:
    words = token_words(query)
    if error_view and needs_timeline_fallback(query):
        return set()
    return {word for word in words if word not in VAGUE_WORDS}


def needs_timeline_fallback(query: str) -> bool:
    words = token_words(query)
    return bool(words & RECURRENCE_WORDS) and bool(words & ERROR_WORDS)


def build_event(entry: dict[str, Any], superseded_by: dict[str, list[str]]) -> dict[str, Any]:
    classification = classify_entry(entry)
    event_at = str(entry.get("event_at") or entry["timestamp"])
    explicit_event_at = "event_at" in entry
    thread_id, thread_source = _thread_identity(entry, classification)
    return {
        "id": entry["id"],
        "source_type": "VAULT_MEMORY",
        "authority": "DERIVED_MEMORY_HISTORY",
        "event_at": event_at,
        "event_time_source": "EXPLICIT_EVENT_AT" if explicit_event_at else "RECORDED_AT_FALLBACK",
        "recorded_at": entry["timestamp"],
        "title": _title(entry),
        "summary": _clip(entry.get("text")),
        "kind": entry["kind"],
        "scope": entry["scope"],
        "thread_id": thread_id,
        "thread_source": thread_source,
        "state": entry["state"],
        "disposition": _disposition(entry, superseded_by, classification),
        "semantic_category": classification.get("semantic_category"),
        "primary_domain": classification.get("primary_domain"),
        "projects": list(classification.get("projects") or []),
        "roles": list(classification.get("roles") or []),
        "entities": list(classification.get("entities") or []),
        "durability": classification.get("durability"),
        "evidence": list(entry.get("evidence") or [])[:4],
        "anchors": _evidence_anchors(entry.get("evidence") or []),
        "supersedes": list(entry.get("supersedes") or []),
        "superseded_by": list(superseded_by.get(str(entry["id"]), [])),
    }


def _matches_query(event: dict[str, Any], query_tokens: set[str]) -> bool:
    if not query_tokens:
        return True
    text = " ".join([
        event.get("title", ""), event.get("summary", ""), event.get("scope", ""),
        event.get("semantic_category", ""), event.get("primary_domain", ""),
        *event.get("projects", []), *event.get("entities", []),
    ])
    words = token_words(text)
    return bool(query_tokens & words)


def _matches_repo_query(event: dict[str, Any], query_tokens: set[str]) -> bool:
    if not query_tokens:
        return True
    text = " ".join([
        str(event.get("title") or ""), str(event.get("project") or ""), str(event.get("worker") or ""),
        str(event.get("artifact_type") or ""), str(event.get("path") or ""),
        *[str(ref) for ref in event.get("refs", [])], *[str(anchor) for anchor in event.get("anchors", [])],
    ])
    return bool(query_tokens & token_words(text))


def build_timeline(
    entries: Iterable[dict[str, Any]], *, view: str = "general", project: str | None = None,
    query: str = "", thread: str | None = None, limit: int = DEFAULT_LIMIT,
    since: datetime | None = None, repo_events: Iterable[dict[str, Any]] | None = None,
    worker_events: Iterable[dict[str, Any]] | None = None,
    artifact_events: Iterable[dict[str, Any]] | None = None,
    snapshot_now: datetime | None = None,
    source_coverage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    items = list(entries)
    superseded_by = _superseded_by(items)
    events = [build_event(entry, superseded_by) for entry in items]
    if view not in {"general", "project", "errors"}:
        raise ValueError(f"invalid timeline view: {view}")
    if view == "project" and not project:
        raise ValueError("project timeline requires project")
    project_key = project.casefold() if project else None
    qtokens = _query_tokens(query, error_view=view == "errors")

    selected: list[dict[str, Any]] = []
    by_id = {entry["id"]: entry for entry in items}
    for event in events:
        entry = by_id[event["id"]]
        classification = classify_entry(entry)
        if view == "errors" and not _is_error_event(entry, classification):
            continue
        linkage = _project_linkage(classification, project_key)
        if project_key and linkage is None:
            continue
        if view == "project" and linkage is None:
            continue
        if thread and event["thread_id"] != thread:
            continue
        if since is not None and _dt(event["event_at"]) < since:
            continue
        if not _matches_query(event, qtokens):
            continue
        event = dict(event)
        if project_key:
            event["project_linkage"] = linkage
        selected.append(event)

    selected.sort(key=lambda event: (_dt(event["event_at"]), _dt(event["recorded_at"]), event["id"]))
    previous_by_thread: dict[str, str] = {}
    for event in selected:
        previous = previous_by_thread.get(event["thread_id"])
        if previous:
            event["previous_in_thread"] = previous
        previous_by_thread[event["thread_id"]] = event["id"]

    thread_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in selected:
        thread_groups[event["thread_id"]].append(event)
    threads: list[dict[str, Any]] = []
    for thread_id, group in thread_groups.items():
        group.sort(key=lambda event: (_dt(event["event_at"]), event["id"]))
        projects = sorted({p for event in group for p in event.get("projects", [])})
        entities = sorted({p for event in group for p in event.get("entities", [])})
        threads.append({
            "thread_id": thread_id,
            "scope": group[-1]["scope"],
            "event_count": len(group),
            "first_event_at": group[0]["event_at"],
            "latest_event_at": group[-1]["event_at"],
            "latest_event_id": group[-1]["id"],
            "latest_title": group[-1]["title"],
            "latest_disposition": group[-1]["disposition"],
            "projects": projects,
            "entities": entities,
        })
    threads.sort(key=lambda item: (_dt(item["latest_event_at"]), item["thread_id"]), reverse=True)

    repo_selected: list[dict[str, Any]] = []
    worker_selected: list[dict[str, Any]] = []
    artifact_selected: list[dict[str, Any]] = []
    invalid_source_events: Counter[str] = Counter()

    def select_external(raw_events: Iterable[dict[str, Any]] | None, target: list[dict[str, Any]]) -> None:
        for raw in raw_events or []:
            event = dict(raw)
            source_type = str(event.get("source_type") or "UNKNOWN")
            stamp = _safe_dt(event.get("event_at"))
            if stamp is None:
                invalid_source_events[source_type] += 1
                continue
            if project_key and str(event.get("project") or "").casefold() != project_key:
                continue
            if since is not None and stamp < since:
                continue
            if not _matches_repo_query(event, qtokens):
                continue
            target.append(event)

    if view != "errors" and thread is None:
        select_external(repo_events, repo_selected)
        select_external(worker_events, worker_selected)
        select_external(artifact_events, artifact_selected)

    effective_limit = min(MAX_LIMIT, max(1, int(limit)))
    combined = [*selected, *repo_selected, *worker_selected, *artifact_selected]
    combined.sort(key=lambda event: (_dt(str(event["event_at"])), str(event["id"])), reverse=True)
    newest = combined[:effective_limit]
    snapshots = build_timeline_snapshots(combined, now=snapshot_now)
    snapshots["coverage"] = dict(source_coverage or {})
    return {
        "schema_version": 2,
        "authority": "DERIVED_HISTORY_ONLY",
        "contract": {
            "timeline": "chronology and grouping, never current truth by itself",
            "relationships": "only explicit supersedes plus explicit-thread/stable-evidence/specific-scope chronology; ambiguous evidence and broad scopes never imply one incident and no causal edge is inferred",
            "project_linkage": "explicit project metadata outranks secondary entity mentions",
            "repo_history": "local all-branch Git commits/refs are observed repository history, not memory or causal interpretation",
            "worker_history": "immutable finalized worker reports are lagging self-report evidence with automatically derived duration/utilization; they are not current-state authority or liveness proof",
            "artifact_history": "Git-tracked reports, incident reports, evidence, logs, screenshots, proofs, fixtures, contracts, and transcripts are preserved artifact history; untracked WIP is not promoted into durable history",
            "corroboration": "snapshot source diversity can strengthen orientation but never turns repetition into authority or proves causality",
        },
        "view": view,
        "project": project_key,
        "query": " ".join(str(query or "").split()),
        "thread": thread,
        "matching_events": len(combined),
        "memory_events": len(selected),
        "repo_events": len(repo_selected),
        "worker_events": len(worker_selected),
        "artifact_events": len(artifact_selected),
        "invalid_source_events": dict(sorted(invalid_source_events.items())),
        "source_coverage": dict(source_coverage or {}),
        "matching_threads": len(threads),
        "events": newest,
        "threads": threads[: min(20, effective_limit)],
        "snapshots": snapshots,
        "truncated": len(combined) > effective_limit,
    }




def build_incident_rollups(entries: Iterable[dict[str, Any]], *, limit: int = 5, member_id_limit: int = 20) -> list[dict[str, Any]]:
    """Compress recurring durable incident/topic lineages without discarding source events."""
    items = list(entries)
    effective_limit = min(20, max(0, int(limit)))
    effective_member_limit = min(20, max(1, int(member_id_limit)))
    if effective_limit == 0 or not items:
        return []

    # General chronology is required so explicit/evidence-backed learning lineages
    # can compact decisions/lessons as well as records classified as incidents.
    # Specific-scope grouping stays conservative: it is admitted only when the
    # same thread also appears in the error projection.
    report = build_timeline(items, view="general", limit=MAX_LIMIT)
    error_report = build_timeline(items, view="errors", limit=MAX_LIMIT)
    error_thread_ids = {str(thread["thread_id"]) for thread in error_report["threads"]}
    visible_dispositions = {"CURRENT_DURABLE", "PROVISIONAL/NEEDS_EVIDENCE"}
    events_by_thread: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in report["events"]:
        events_by_thread[str(event["thread_id"])].append(event)
    out: list[dict[str, Any]] = []
    for thread in report["threads"]:
        if int(thread.get("event_count") or 0) < 2:
            continue
        if thread.get("latest_disposition") not in visible_dispositions:
            continue
        events = sorted(
            events_by_thread.get(str(thread["thread_id"]), []),
            key=lambda event: (_dt(str(event["event_at"])), str(event["id"])),
            reverse=True,
        )
        if not events:
            continue
        latest = events[0]
        thread_id = str(thread["thread_id"])
        thread_source = str(latest.get("thread_source") or "")
        if thread_source not in {"EXPLICIT_THREAD", "EVIDENCE_ANCHOR"} and thread_id not in error_thread_ids:
            continue
        quoted_thread = thread_id.replace('"', '\"')
        out.append({
            "thread_id": thread_id,
            "thread_source": thread_source,
            "scope": thread.get("scope"),
            "observations": int(thread["event_count"]),
            "first_event_at": thread.get("first_event_at"),
            "latest_event_at": thread.get("latest_event_at"),
            "latest_event_id": thread.get("latest_event_id"),
            "latest_title": thread.get("latest_title"),
            "latest_disposition": thread.get("latest_disposition"),
            "summary": _clip(latest.get("summary"), 240),
            "projects": list(thread.get("projects") or []),
            "entities": list(thread.get("entities") or []),
            "member_ids": [str(event["id"]) for event in events[:effective_member_limit]],
            "drilldown": f'python tools\\memory_bank.py timeline --thread "{quoted_thread}" --limit 20 --no-workers',
        })
        if len(out) >= effective_limit:
            break
    return out

def build_recurrence_context(entries: Iterable[dict[str, Any]], query: str, *, max_threads: int = 4, events_per_thread: int = 6) -> list[dict[str, Any]]:
    if not needs_timeline_fallback(query):
        return []
    projects = sorted(projects_from_text(query))
    project = projects[0] if len(projects) == 1 else None
    report = build_timeline(entries, view="errors", project=project, limit=MAX_LIMIT)
    by_thread: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in report["events"]:
        by_thread[event["thread_id"]].append(event)
    out: list[dict[str, Any]] = []
    for thread in report["threads"][:max_threads]:
        events = sorted(by_thread.get(thread["thread_id"], []), key=lambda event: _dt(event["event_at"]))[-events_per_thread:]
        out.append({
            "thread_id": thread["thread_id"],
            "scope": thread["scope"],
            "event_count": thread["event_count"],
            "latest_event_at": thread["latest_event_at"],
            "latest_title": thread["latest_title"],
            "projects": thread["projects"],
            "entities": thread["entities"],
            "events": [{
                "id": event["id"], "event_at": event["event_at"], "title": event["title"],
                "state": event["state"], "disposition": event["disposition"],
                "semantic_category": event["semantic_category"],
            } for event in events],
        })
    return out
