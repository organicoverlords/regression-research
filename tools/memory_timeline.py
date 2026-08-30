from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from .memory_classification import classify_entry, projects_from_text, token_words
    from .memory_authority import behavioral_context
except ImportError:
    from memory_classification import classify_entry, projects_from_text, token_words
    from memory_authority import behavioral_context

DEFAULT_LIMIT = 20
MAX_LIMIT = 50
MAX_SUMMARY_CHARS = 280
ERROR_MARKERS = {
    "error", "incident", "slopwall", "red-alert", "redalert", "red-critical", "panic-alert",
    "recurrence", "regression", "failure", "security-incident",
}
RECURRENCE_WORDS = {"again", "same", "recurrence", "recurred", "returned", "back"}
ERROR_WORDS = {"error", "bug", "broken", "failure", "failed", "failing", "incident", "problem", "issue", "wrong"}
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


def _thread_identity(entry: dict[str, Any], classification: dict[str, Any]) -> tuple[str, str]:
    explicit = str(entry.get("thread") or "").strip()
    if explicit:
        return "thread:" + explicit.casefold(), "EXPLICIT_THREAD"
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
        str(event.get("title") or ""), str(event.get("project") or ""),
        *[str(ref) for ref in event.get("refs", [])],
    ])
    return bool(query_tokens & token_words(text))


def build_timeline(
    entries: Iterable[dict[str, Any]], *, view: str = "general", project: str | None = None,
    query: str = "", thread: str | None = None, limit: int = DEFAULT_LIMIT,
    since: datetime | None = None, repo_events: Iterable[dict[str, Any]] | None = None,
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
    if view != "errors" and thread is None:
        for raw in repo_events or []:
            event = dict(raw)
            if project_key and str(event.get("project") or "").casefold() != project_key:
                continue
            if since is not None and _dt(str(event.get("event_at"))) < since:
                continue
            if not _matches_repo_query(event, qtokens):
                continue
            repo_selected.append(event)

    effective_limit = min(MAX_LIMIT, max(1, int(limit)))
    combined = [*selected, *repo_selected]
    combined.sort(key=lambda event: (_dt(str(event["event_at"])), str(event["id"])), reverse=True)
    newest = combined[:effective_limit]
    return {
        "schema_version": 1,
        "authority": "DERIVED_HISTORY_ONLY",
        "contract": {
            "timeline": "chronology and grouping, never current truth by itself",
            "relationships": "only explicit supersedes plus explicit-thread/specific-scope chronology; broad scopes never imply one incident and no causal edge is inferred",
            "project_linkage": "explicit project metadata outranks secondary entity mentions",
            "repo_history": "local Git commits are observed repository history, not memory or causal interpretation",
        },
        "view": view,
        "project": project_key,
        "query": " ".join(str(query or "").split()),
        "thread": thread,
        "matching_events": len(combined),
        "memory_events": len(selected),
        "repo_events": len(repo_selected),
        "matching_threads": len(threads),
        "events": newest,
        "threads": threads[: min(20, effective_limit)],
        "truncated": len(combined) > effective_limit,
    }


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



def build_fresh_session_startup_contract() -> dict[str, Any]:
    """Return the bootstrap-owned operating cycle for the first fresh chat."""
    return {
        "applies": "first successful bootstrap of a fresh normal conversation only",
        "rehydration": "post-compaction bootstrap restores behavior only; the continued presence of the same summary/compacted context is not a new fresh-session event and must not retrigger this sweep",
        "wake_up_semantics": "the first user message itself triggers startup even when it is only a greeting, short project name, go/continue, status question, or otherwise underspecified wake-up/context selector; resolve established shorthand and the active mission from Vault plus live state before asking the user to restate known context",
        "startup_sequence": ["behavior_bootstrap", "recent_memory_glance", "live_orientation", "response"],
        "recent_memory_glance": "after the complete behavior/policy load and before live orientation, consume up to 20 newest eligible non-superseded Vault memory titles and metadata as bounded historical orientation; it is not live authority, and current user direction plus verified live state outrank it",
        "response_gate": "do not send the first substantive response until the behavior bootstrap is complete, the bounded recent-memory glance has been consumed when available, and the bounded live orientation has been attempted through the available relevant routes; a greeting or short exchange does not bypass this gate",
        "live_orientation": "after the bounded recent-memory glance and before the first substantive response, always inspect enough relevant live truth to understand what is actually happening; for project work this normally includes repo HEAD/origin/dirty state, recent meaningful commits/PRs/checks, current ownership/claims, scheduled-worker state/recent runs, and material runtime/machine alerts; do not pre-judge the scan as unnecessary, and broaden to the wider fleet only when the task, active alerts, or observed symptoms require it",
        "orientation_reporting": "if the bounded scan is clean, stay quiet about the sweep; if it exposes a material abnormality, lead the first substantive response with that abnormality and any safe containment already performed",
        "anomaly_handling": "if the live scan shows an obvious operational failure or contradictory state, repair or contain it first when safely authorized; do not replace the inherited mission with scheduler churn or new architecture",
        "current_status_refresh": "after startup, re-check the relevant live sources before any later answer whose correctness depends on current repo/coordinator/worker/CI/runtime status; an earlier snapshot is timestamped evidence, not permanent authority",
        "worker_status_truth": "for any user-facing worker status, inspect the current execution surface immediately before answering; only a currently running automation/run/session/process or in-flight tool/command tied to the worker/scope can prove working now; claims, leases, heartbeats, checkpoints, schedules, enabled flags, last-run timestamps, branches, PRs, commits, reports, and prior snapshots have zero positive weight for liveness",
        "worker_progress_truth": "report how much actual work occurred during the relevant work window from concrete output events such as completed commands/tools/tests, created commits, written artifacts, or PR updates; claim timestamps may delimit the measurement window only, and claim existence itself adds zero progress evidence",
        "worker_status_reporting": "ordinary status reports only current execution plus measured actual work; never present coordinator active/claim/lease/heartbeat/checkpoint state as worker activity or as a reason no action is needed; if current execution is not observed, say not working now, or unverified when the execution surface itself cannot be inspected",
        "authority_cross_references": ["assistant-orchestration/user-burden", "assistant-orchestration/tool-availability"],
        "startup_report": "report only material abnormal proven state or repairs: stay silent when clean, and when abnormal lead with the fire; do not dump the orientation transcript or facts the user already knows",
        "continuation": "after any necessary abnormality report, continue the highest-value safe inherited/project work automatically; orientation, a context-loaded message, or a status dump is never task completion",
        "documentation": "04 Operating Contracts/fresh-chat-startup-orientation.md",
        "personal_instructions_bridge": "04 Operating Contracts/chatgpt-personal-instructions-bootstrap.txt",
    }


def build_behavior_bootstrap(entries: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Return the complete current behavioral constitution without history/project payload."""
    authorized = behavioral_context(list(entries))

    def item(entry: dict[str, Any]) -> dict[str, Any]:
        authority = dict(entry.get("behavioral_authority") or {})
        return {
            "id": entry.get("id"),
            "title": _title(entry),
            "scope": entry.get("scope"),
            "text": str(entry.get("text") or ""),
            "authority_role": authority.get("role"),
            "precedence": authority.get("precedence"),
        }

    user_rules = [item(entry) for entry in authorized if (entry.get("behavioral_authority") or {}).get("role") == "USER_EXPLICIT"]
    policies = [item(entry) for entry in authorized if (entry.get("behavioral_authority") or {}).get("role") == "CANONICAL_POLICY"]
    return {
        "schema_version": 1,
        "purpose": "mandatory behavior bootstrap / post-compaction rehydration",
        "contract": {
            "complete_behavior_semantics": True,
            "completion_boundary": "complete_behavior_semantics means the behavior/policy load only; fresh-chat startup then consumes the bounded recent-memory glance before live orientation",
            "history_included": False,
            "live_status_included": False,
            "live_status_gap_owner": "assistant must close the live-status gap with a bounded relevant scan before the first substantive response of a fresh chat",
            "follow_up": "for a fresh chat, consume the bounded recent-memory glance after behavior loading, then acquire the bounded live orientation before the first substantive response; thereafter re-check live sources before any answer whose correctness depends on current status; report only material abnormality",
        },
        "fresh_session_startup": build_fresh_session_startup_contract(),
        "behavior_profile": user_rules,
        "canonical_policy_profile": policies,
    }


def build_orientation(
    entries: Iterable[dict[str, Any]], *, projects: Iterable[str] = ("p3", "tiny3d", "lowvram"),
    recent_events: int = 8, error_threads: int = 4, project_events: int = 3, behavior_rules: int = 32,
    repo_events: Iterable[dict[str, Any]] | None = None, repo_snapshots: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build one compact fresh-chat continuity index from curated memory plus optional local Git history."""
    items = list(entries)
    repo_items = list(repo_events or [])
    general = build_timeline(items, view="general", limit=max(1, recent_events) * 2, repo_events=repo_items)
    errors = build_timeline(items, view="errors", limit=MAX_LIMIT)
    error_index = [{
        "thread_id": thread["thread_id"],
        "event_count": thread["event_count"],
        "latest_event_at": thread["latest_event_at"],
        "latest_title": thread["latest_title"],
        "latest_disposition": thread["latest_disposition"],
        "projects": thread["projects"],
        "entities": thread["entities"],
    } for thread in errors["threads"][:max(0, error_threads)]]

    project_index: dict[str, Any] = {}
    snapshots_by_project = {str(item.get("project") or "").casefold(): dict(item) for item in (repo_snapshots or []) if item.get("project")}
    for project in projects:
        key = str(project).strip().casefold()
        if not key:
            continue
        memory_report = build_timeline(items, view="project", project=key, limit=MAX_LIMIT)
        explicit = [event for event in memory_report["events"] if event.get("project_linkage") == "EXPLICIT_PROJECT"]
        linked = [event for event in memory_report["events"] if event.get("project_linkage") == "ENTITY_MENTION"]
        slots = max(1, project_events)
        explicit_current = [event for event in explicit if event.get("disposition") == "CURRENT_DURABLE"]
        explicit_historical = [event for event in explicit if event.get("disposition") != "CURRENT_DURABLE"]
        linked_current = [event for event in linked if event.get("disposition") == "CURRENT_DURABLE"]
        linked_historical = [event for event in linked if event.get("disposition") != "CURRENT_DURABLE"]
        chosen_memory = [*explicit_current, *linked_current, *explicit_historical, *linked_historical][:slots]
        project_commits = [event for event in repo_items if str(event.get("project") or "").casefold() == key]
        mainline_commits = [event for event in project_commits if event.get("repo_state") == "MAINLINE"]
        lane_commits = [event for event in project_commits if event.get("repo_state") == "LANE"]
        project_index[key] = {
            "memory_events": memory_report["matching_events"],
            "explicit_project_events": len(explicit),
            "entity_linked_events": len(linked),
            "latest_memory": [{
                "id": event["id"], "event_at": event["event_at"], "title": event["title"],
                "semantic_category": event["semantic_category"], "disposition": event["disposition"],
                "project_linkage": event.get("project_linkage"),
            } for event in chosen_memory],
            "latest_mainline_commits": [{
                "id": event["id"], "event_at": event["event_at"], "title": event["title"],
                "sha": event.get("sha"), "short_sha": event.get("short_sha"), "refs": list(event.get("refs") or []),
                "repo_state": event.get("repo_state"),
            } for event in mainline_commits[:slots]],
            "latest_lane_commits": [{
                "id": event["id"], "event_at": event["event_at"], "title": event["title"],
                "sha": event.get("sha"), "short_sha": event.get("short_sha"), "refs": list(event.get("refs") or []),
                "repo_state": event.get("repo_state"),
            } for event in lane_commits[:slots]],
        }
        if key in snapshots_by_project:
            project_index[key]["repo"] = snapshots_by_project[key]

    eligible_memory = [
        event for event in general["events"]
        if event.get("source_type") == "VAULT_MEMORY"
        and event.get("disposition") in {"CURRENT_DURABLE", "PROVISIONAL/NEEDS_EVIDENCE"}
    ][:max(1, recent_events)]
    eligible_repo = [event for event in general["events"] if event.get("source_type") == "GIT_COMMIT"][:max(1, recent_events)]
    recent = [*eligible_memory, *eligible_repo]
    recent.sort(key=lambda event: (_dt(str(event["event_at"])), str(event["id"])), reverse=True)

    def compact_behavior(entry: dict[str, Any]) -> dict[str, Any]:
        authority = dict(entry.get("behavioral_authority") or {})
        return {
            "id": entry.get("id"),
            "scope": entry.get("scope"),
            "kind": entry.get("kind"),
            "title": _title(entry),
            "text": _clip(entry.get("text"), 360),
            "behavior_rule_type": bool(authority.get("may_change_behavior")),
            "authority_role": authority.get("role"),
            "authority_basis": authority.get("basis"),
            "precedence": authority.get("precedence"),
        }

    authorized = behavioral_context(items)
    # Governing rules are never silently evicted by a presentation budget.
    # The behavior_rules argument remains accepted for CLI compatibility only.
    behavior = [
        compact_behavior(entry) for entry in authorized
        if (entry.get("behavioral_authority") or {}).get("role") == "USER_EXPLICIT"
    ]
    canonical_policy = [
        compact_behavior(entry) for entry in authorized
        if (entry.get("behavioral_authority") or {}).get("role") == "CANONICAL_POLICY"
    ]

    return {
        "schema_version": 1,
        "authority": "DERIVED_HISTORY_ONLY",
        "contract": {
            "purpose": "fresh-chat continuity index, not live status",
            "source": "curated memory plus optional local Git history; no full-conversation archive or download dependency",
            "repo_history": "read-only local Git projection; no network fetch and no automatic memory write",
            "follow_up": "use timeline/context/live sources before treating an incident or project event as current truth",
            "behavior_profile": "current explicitly typed user-authored behavior rules only; user provenance alone is not a behavior type; current user instruction still wins",
            "canonical_policy_profile": "current canonical repo policy kept separate from user-authored behavior",
        },
        "behavior_profile": behavior,
        "canonical_policy_profile": canonical_policy,
        "recent_events": recent[: max(2, recent_events * 2)],
        "recent_error_threads": error_index,
        "projects": project_index,
        "repo_snapshots": list(repo_snapshots or []),
    }

def main() -> int:
    parser = argparse.ArgumentParser(description="Derived chronological continuity views over the canonical memory bank.")
    parser.add_argument("--bank", type=Path, default=Path(__file__).resolve().parents[1] / "memory" / "memory-bank.jsonl")
    parser.add_argument("--view", choices=("general", "project", "errors"), default="general")
    parser.add_argument("--project")
    parser.add_argument("--query", default="")
    parser.add_argument("--thread")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--days", type=int)
    args = parser.parse_args()
    try:
        from .memory_bank import load_bank
    except ImportError:
        from memory_bank import load_bank
    since = None
    if args.days is not None:
        if args.days < 0:
            parser.error("--days must be non-negative")
        since = datetime.now(timezone.utc) - timedelta(days=args.days)
    report = build_timeline(load_bank(args.bank), view=args.view, project=args.project, query=args.query, thread=args.thread, limit=args.limit, since=since)
    payload = json.dumps(report, ensure_ascii=False, separators=(",", ":")) + "\n"
    stream = getattr(__import__("sys").stdout, "buffer", None)
    if stream is None:
        print(json.dumps(report, ensure_ascii=True))
    else:
        stream.write(payload.encode("utf-8", "backslashreplace"))
        stream.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
