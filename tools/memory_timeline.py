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
RECALL_VISIBLE_DISPOSITIONS = frozenset({"CURRENT_DURABLE", "PROVISIONAL/NEEDS_EVIDENCE"})
ERROR_WORDS = {"error", "bug", "broken", "failure", "failed", "failing", "incident", "problem", "issue", "wrong"}
_GITHUB_EVIDENCE_RE = re.compile(r"^github:([^/\s]+/[^#\s]+)#(\d+)$", re.I)
_GITHUB_URL_RE = re.compile(r"^https?://github\.com/([^/\s]+/[^/\s]+)/(?:issues|pull)/(\d+)(?:[/?#].*)?$", re.I)
_INCIDENT_EVIDENCE_RE = re.compile(r"\bINC-\d{8}(?:-\d{6})?(?:-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)?\b", re.I)
_RED_SIGNAL_RE = re.compile(r"\bred[ _-]?(?:alert|critical)\b", re.I)
_LEGACY_INCIDENT_SIGNAL_RE = re.compile(r"\b(?:incident\s+report|critical\s+incident|security[-_\s]+incident)\b", re.I)
_REGRESSION_SIGNAL_RE = re.compile(r"\b(?:recurrence|failure|failed|broken|premature)\b|\bregression\b(?![-_\s]+research\b)", re.I)
_SIGNAL_ORDER = ("red_alert", "slopwall", "security_incident", "incident", "regression")

TIMELINE_NARRATIVE_CONTRACT = {
    "primary_unit": "CONTINUITY_CASE",
    "answer_order": ["CONTINUITY_CASES", "WORK_GRAPH", "EVIDENCE_DENSITY", "CONTEXT_ONLY_CORROBORATION"],
    "observation_counts": "EVIDENCE_DENSITY_NOT_CASE_COUNT",
    "broad_github_anchors": "CONTEXT_ONLY_NEVER_CASE_IDENTITY",
    "context_wording": "DO_NOT_CALL_CONTEXT_ONLY_ANCHOR_THE_CASE_OR_THREAD",
    "causality": "SEQUENCE_OR_CORROBORATION_DOES_NOT_PROVE_CAUSE",
}

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
        normalized = value.replace(chr(92), "/").strip()
        if normalized.casefold().startswith("incident:"):
            anchors.add(normalized.casefold())
            continue
        if normalized.casefold().startswith(("01 reports/", "02 evidence/", "03 fixtures and experiments/", "04 operating contracts/", "90 raw transcripts/")):
            anchors.add("artifact:" + normalized.casefold())
        for incident in _INCIDENT_EVIDENCE_RE.findall(value):
            anchors.add(f"incident:{incident.casefold()}")
    return sorted(anchors)


def _normalized_labels(values: Iterable[Any]) -> set[str]:
    return {
        str(value).strip().casefold().replace("-", "_")
        for value in values
        if str(value or "").strip()
    }


def _legacy_fallback_eligible(
    event: dict[str, Any],
    *,
    tags: set[str] | None = None,
    finding_tags: set[str] | None = None,
) -> bool:
    """Allow title/scope compatibility only when canonical signal metadata is absent."""
    source = str(event.get("source_type") or "UNKNOWN")
    tags = tags if tags is not None else _normalized_labels(event.get("tags", []))
    finding_tags = finding_tags if finding_tags is not None else _normalized_labels(event.get("finding_tags", []))
    if source == "VAULT_MEMORY":
        # Canonical assistant-recorded memories already have structured category/tags.
        # Their prose may discuss incidents/regressions without becoming one themselves.
        return not bool({"assistant_recorded", "verbatim_source"} & tags)
    if source == "WORKER_REPORT":
        # finding_tags are the canonical worker signal lane; display prose is descriptive.
        return not bool(finding_tags)
    if source == "TRACKED_ARTIFACT":
        evidence_type = str(event.get("evidence_type") or "").strip().casefold()
        artifact_type = str(event.get("artifact_type") or "").strip().casefold()
        if evidence_type:
            # A structured research/audit/proof type must not be relabeled by its title.
            # Incident provenance may still use legacy title text to recover missing severity.
            return "incident" in evidence_type
        # Old report history may predate provenance taxonomy. Generic evidence/fixture names
        # such as regression-coverage-matrix.csv are not signal labels by themselves.
        return artifact_type == "report"
    return False


def _legacy_signal_fallback(event: dict[str, Any]) -> tuple[set[str], str | None, list[str]]:
    """Best-effort compatibility for genuinely unstructured historical signal records."""
    text = " ".join(
        str(event.get(key) or "")
        for key in ("title", "scope")
    )
    lowered = text.casefold()
    traits: set[str] = set()
    severity: str | None = None
    basis: list[str] = []
    if _RED_SIGNAL_RE.search(text):
        severity = "RED"
        basis.append("legacy_text:red_alert")
    if "slopwall" in lowered:
        traits.add("slopwall")
        basis.append("legacy_text:slopwall")
    if "security incident" in lowered or "security_incident" in lowered or "security-incident" in lowered:
        traits.add("security_incident")
        basis.append("legacy_text:security_incident")
    if _REGRESSION_SIGNAL_RE.search(text):
        traits.add("regression")
        basis.append("legacy_text:regression")
    if _LEGACY_INCIDENT_SIGNAL_RE.search(text) or _INCIDENT_EVIDENCE_RE.search(text):
        traits.add("incident")
        basis.append("legacy_text:incident")
    return traits, severity, basis


def _continuity_semantics(event: dict[str, Any]) -> dict[str, Any]:
    """Normalize event semantics independently from evidence form.

    Structured source metadata wins. Text matching exists only to retain old records that
    predate structured tags/provenance and is surfaced explicitly in classification_basis.
    """
    source = str(event.get("source_type") or "UNKNOWN")
    tags = _normalized_labels(event.get("tags", []))
    finding_tags = _normalized_labels(event.get("finding_tags", []))
    traits: set[str] = set()
    basis: list[str] = []
    severity = "NORMAL"
    event_class = "OBSERVATION"

    if source == "GIT_COMMIT":
        event_class = "CHANGE"
        basis.append("structured:source_type=GIT_COMMIT")
    elif source == "WORKER_REPORT":
        event_class = "WORK_RUN"
        basis.append("structured:source_type=WORKER_REPORT")
    elif source == "TRACKED_ARTIFACT":
        event_class = "EVIDENCE"
        basis.append("structured:source_type=TRACKED_ARTIFACT")
        if event.get("incident_id"):
            event_class = "INCIDENT"
            traits.add("incident")
            basis.append("structured:provenance.incident_id")
        elif "incident" in str(event.get("evidence_type") or "").casefold():
            event_class = "INCIDENT"
            traits.add("incident")
            basis.append("structured:provenance.evidence_type")
    elif source == "VAULT_MEMORY":
        # Memory semantic_category is retrieval/content taxonomy, not continuity authority.
        # Explicit signal tags below (or the bounded legacy compatibility path) decide whether
        # a memory observation belongs to an incident/regression/slopwall continuity case.
        semantic = str(event.get("semantic_category") or "").upper()
        event_class = "MEMORY"
        if semantic:
            basis.append("context:memory.semantic_category=" + semantic)

    if {"red_alert", "red_critical", "red_level"} & tags:
        severity = "RED"
        basis.append("structured:memory.tags:red")
    if "critical_incident" in tags:
        severity = "RED"
        traits.add("incident")
        basis.append("structured:memory.tags:critical_incident")
    if "slopwall" in tags:
        traits.add("slopwall")
        basis.append("structured:memory.tags:slopwall")
    if {"incident", "security_incident"} & tags:
        traits.update({value for value in ("incident", "security_incident") if value in tags})
        basis.append("structured:memory.tags:incident")
    if {"regression", "recurrence", "bug", "error", "failure"} & tags:
        traits.add("regression")
        basis.append("structured:memory.tags:regression")

    if {"regression", "bug", "error"} & finding_tags:
        traits.add("regression")
        basis.append("structured:worker.finding_tags:regression")
    if "incident" in finding_tags:
        traits.add("incident")
        basis.append("structured:worker.finding_tags:incident")
    if "slopwall" in finding_tags:
        traits.add("slopwall")
        basis.append("structured:worker.finding_tags:slopwall")
    if {"red_alert", "red_critical"} & finding_tags:
        severity = "RED"
        basis.append("structured:worker.finding_tags:red")

    # Structured signal markers from source adapters are accepted, but adapters should
    # use them only when they came from schema/provenance, not title-word guessing.
    explicit_signals = _normalized_labels(event.get("signals", []))
    for signal in explicit_signals:
        if signal in {"red_alert", "red_critical"}:
            severity = "RED"
        elif signal in {"incident", "regression", "slopwall", "security_incident"}:
            traits.add(signal)
    if explicit_signals:
        basis.append("structured:source.signals")

    # Legacy-only fallback is deliberately narrow and visible. It only supplies a
    # missing field; it never re-labels already-structured semantics as legacy-derived.
    legacy_severity_inferred = False
    legacy_traits_inferred: set[str] = set()
    if (
        (severity == "NORMAL" or not traits)
        and _legacy_fallback_eligible(event, tags=tags, finding_tags=finding_tags)
    ):
        fallback_traits, fallback_severity, fallback_basis = _legacy_signal_fallback(event)
        used_fallback: list[str] = []
        if severity == "NORMAL" and fallback_severity:
            severity = fallback_severity
            legacy_severity_inferred = True
            used_fallback.extend(item for item in fallback_basis if item == "legacy_text:red_alert")
        if not traits and fallback_traits:
            traits.update(fallback_traits)
            legacy_traits_inferred.update(fallback_traits)
            used_fallback.extend(item for item in fallback_basis if item != "legacy_text:red_alert")
        basis.extend(used_fallback)

    if severity == "RED" or traits & {"incident", "regression", "slopwall", "security_incident"}:
        event_class = "INCIDENT"

    result = {
        "event_class": event_class,
        "severity": severity,
        "traits": sorted(traits),
        "classification_basis": sorted(set(basis)),
        "legacy_inferred": any(item.startswith("legacy_text:") for item in basis),
    }
    if legacy_severity_inferred:
        result["legacy_severity_inferred"] = True
    if legacy_traits_inferred:
        result["legacy_traits_inferred"] = sorted(legacy_traits_inferred)
    return result


def _case_anchors(event: dict[str, Any]) -> list[str]:
    """Return strong identity anchors; broad GitHub issue refs are corroboration-only."""
    cached = event.get("case_anchors")
    if isinstance(cached, list):
        return sorted({str(value).casefold() for value in cached if str(value).strip()})
    anchors = {
        str(anchor).casefold()
        for anchor in _event_anchors(event)
        if str(anchor).casefold().startswith(("incident:", "artifact:"))
    }
    if str(event.get("thread_source") or "") == "EXPLICIT_THREAD" and event.get("thread_id"):
        anchors.add(str(event["thread_id"]).casefold())
    proof = str(event.get("proof_artifact") or "").replace(chr(92), "/").strip()
    if proof:
        anchors.add("artifact:" + proof.casefold())
    if not anchors and str(event.get("thread_source") or "") == "SPECIFIC_SCOPE" and event.get("thread_id"):
        anchors.add(str(event["thread_id"]).casefold())
    return sorted(anchors)


def _event_source_family(event: dict[str, Any]) -> str:
    return {
        "VAULT_MEMORY": "memory",
        "GIT_COMMIT": "repo",
        "WORKER_REPORT": "worker",
        "TRACKED_ARTIFACT": "artifact",
        "LOCAL_ARTIFACT": "artifact",
        "LIBRARY_ARTIFACT": "artifact",
        "MACHINE_OBSERVATION": "machine",
        "GITHUB_ISSUE": "github",
        "GITHUB_PR": "github",
        "GITHUB_ACTION": "github",
        "MCP_EVENT": "mcp",
        "RUNNER_LOG": "runner",
    }.get(str(event.get("source_type") or ""), "other")


def _event_anchors(event: dict[str, Any]) -> list[str]:
    cached = event.get("_all_anchors_cache")
    if isinstance(cached, list):
        return cached
    anchors = {str(item).casefold() for item in event.get("anchors", []) if str(item).strip()}
    anchors.update(_evidence_anchors(event.get("evidence", [])))
    anchors.update(_evidence_anchors(event.get("refs", [])))
    proof = str(event.get("proof_artifact") or "").replace(chr(92), "/").strip()
    if proof:
        anchors.add("artifact:" + proof.casefold())
    return sorted(anchors)


def _evidence_form(event: dict[str, Any]) -> str:
    source = str(event.get("source_type") or "")
    if source == "VAULT_MEMORY":
        return "memory"
    if source == "GIT_COMMIT":
        return "commit"
    if source == "WORKER_REPORT":
        return "worker_report"
    if source in {"TRACKED_ARTIFACT", "LOCAL_ARTIFACT", "LIBRARY_ARTIFACT"}:
        return str(event.get("artifact_type") or "artifact")
    if source == "GITHUB_ISSUE":
        return "issue"
    if source == "GITHUB_PR":
        return "pull_request"
    if source == "GITHUB_ACTION":
        return "action_run"
    if source == "MCP_EVENT":
        return "mcp_event"
    if source == "RUNNER_LOG":
        return "runner_log"
    if source == "MACHINE_OBSERVATION":
        return "machine_snapshot"
    return "observation"


def _event_continuity(event: dict[str, Any]) -> dict[str, Any]:
    existing = event.get("continuity")
    return dict(existing) if isinstance(existing, dict) else _continuity_semantics(event)


def _highlight_bucket(event: dict[str, Any]) -> str:
    semantics = _event_continuity(event)
    if semantics.get("severity") == "RED":
        return "signal:red_alert"
    traits = set(semantics.get("traits") or [])
    for trait in ("slopwall", "security_incident", "incident", "regression"):
        if trait in traits:
            return "signal:" + trait
    family = _event_source_family(event)
    if family == "artifact":
        return "artifact:" + str(event.get("artifact_type") or "artifact")
    return family


def _compact_snapshot_event(event: dict[str, Any]) -> dict[str, Any]:
    semantics = _event_continuity(event)
    out = {
        "id": event.get("id"),
        "event_at": event.get("event_at"),
        "source_type": event.get("source_type"),
        "title": _clip(event.get("title"), 120),
    }
    if semantics.get("severity") == "RED":
        out["severity"] = "RED"
    if semantics.get("traits"):
        out["traits"] = list(semantics["traits"])
    if semantics.get("legacy_inferred"):
        out["legacy_inferred"] = True
    for key in ("project", "artifact_type", "disposition", "short_sha", "population"):
        if event.get(key) not in (None, "", []):
            out[key] = event.get(key)
    return out


def _case_anchor_sort_key(anchor: str) -> tuple[int, str]:
    low = str(anchor).casefold()
    if low.startswith("incident:"):
        rank = 0
    elif low.startswith("thread:"):
        rank = 1
    elif low.startswith("artifact:"):
        rank = 2
    elif low.startswith("scope:"):
        rank = 3
    else:
        rank = 4
    return rank, low


def _is_signal_semantics(semantics: dict[str, Any]) -> bool:
    return (
        semantics.get("severity") == "RED"
        or semantics.get("event_class") == "INCIDENT"
        or bool(set(semantics.get("traits") or []) & {"incident", "regression", "slopwall", "security_incident"})
    )


def _counts_as_active_signal(event: dict[str, Any]) -> bool:
    """Keep forensic memory history without letting revoked claims inflate active cases."""
    if event.get("source_type") != "VAULT_MEMORY":
        return True
    return str(event.get("disposition") or "") not in {"SUPERSEDED", "REJECTED"}


def _build_continuity_cases(
    events: Iterable[dict[str, Any]], *, include_members: bool = False,
) -> list[dict[str, Any]]:
    """Join source observations into cases using explicit strong anchors only."""
    nodes: list[dict[str, Any]] = []
    parent: list[int] = []
    anchor_owner: dict[str, int] = {}

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        lroot, rroot = find(left), find(right)
        if lroot != rroot:
            parent[rroot] = lroot

    for raw in events:
        event = dict(raw)
        if not _counts_as_active_signal(event):
            continue
        semantics = _event_continuity(event)
        anchors = _case_anchors(event)
        if (
            not anchors
            and _is_signal_semantics(semantics)
            and not semantics.get("legacy_inferred")
            and event.get("source_type") == "VAULT_MEMORY"
        ):
            anchors = ["event:" + str(event.get("id") or "unknown").casefold()]
        if not anchors:
            continue
        index = len(nodes)
        nodes.append({"event": event, "semantics": semantics, "anchors": anchors})
        parent.append(index)
        for anchor in anchors:
            prior = anchor_owner.get(anchor)
            if prior is None:
                anchor_owner[anchor] = index
            else:
                union(index, prior)

    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for index, node in enumerate(nodes):
        groups[find(index)].append(node)

    cases: list[dict[str, Any]] = []
    for group in groups.values():
        signal_nodes = [node for node in group if _is_signal_semantics(node["semantics"])]
        if not signal_nodes:
            continue
        anchors = sorted({anchor for node in group for anchor in node["anchors"]}, key=_case_anchor_sort_key)
        traits = sorted({trait for node in group for trait in node["semantics"].get("traits", [])})
        bases = sorted({basis for node in group for basis in node["semantics"].get("classification_basis", [])})
        families = sorted({_event_source_family(node["event"]) for node in group})
        forms = sorted({_evidence_form(node["event"]) for node in group})
        severity = "RED" if any(node["semantics"].get("severity") == "RED" for node in group) else "NORMAL"
        legacy_support_present = any(node["semantics"].get("legacy_inferred") for node in group)
        legacy_dependent_fields: list[str] = []
        if severity == "RED" and not any(
            node["semantics"].get("severity") == "RED"
            and not node["semantics"].get("legacy_severity_inferred")
            for node in signal_nodes
        ):
            legacy_dependent_fields.append("severity:red")
        for trait in traits:
            if not any(
                trait in (node["semantics"].get("traits") or [])
                and trait not in (node["semantics"].get("legacy_traits_inferred") or [])
                for node in signal_nodes
            ):
                legacy_dependent_fields.append("trait:" + trait)
        classification_quality = (
            "LEGACY_DEPENDENT" if legacy_dependent_fields
            else "MIXED" if legacy_support_present
            else "STRUCTURED"
        )
        latest_node = max(group, key=lambda node: (_dt(str(node["event"]["event_at"])), str(node["event"].get("id") or "")))
        latest_signal = max(signal_nodes, key=lambda node: (_dt(str(node["event"]["event_at"])), str(node["event"].get("id") or "")))
        case = {
            "case_id": anchors[0] if anchors else "event:" + str(latest_signal["event"].get("id") or "unknown"),
            "anchors": anchors,
            "severity": severity,
            "traits": traits,
            "observation_count": len(group),
            "signal_observation_count": len(signal_nodes),
            "source_families": families,
            "evidence_forms": forms,
            "classification_basis": bases,
            "classification_quality": classification_quality,
            "legacy_support_present": legacy_support_present,
            "legacy_dependent_fields": legacy_dependent_fields,
            "legacy_inferred": bool(legacy_dependent_fields),
            "latest_event_at": latest_node["event"].get("event_at"),
            "latest_signal_at": latest_signal["event"].get("event_at"),
            "latest_title": _clip(latest_signal["event"].get("title"), 140),
            "latest_source_type": latest_signal["event"].get("source_type"),
        }
        if include_members:
            case["event_ids"] = sorted(str(node["event"].get("id") or "") for node in group if node["event"].get("id"))
            case["signal_event_ids"] = sorted(str(node["event"].get("id") or "") for node in signal_nodes if node["event"].get("id"))
        cases.append(case)
    cases.sort(
        key=lambda case: (
            1 if case.get("severity") == "RED" else 0,
            _dt(str(case.get("latest_signal_at"))),
            str(case.get("case_id")),
        ),
        reverse=True,
    )
    return cases


def build_continuity_graph(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Build the full materialized continuity-case graph with member event navigation."""
    cases = _build_continuity_cases(events, include_members=True)
    return {
        "semantics": "STRONG_ANCHOR_CASE_IDENTITY; BROAD_GITHUB_ANCHORS_CONTEXT_ONLY",
        "case_count": len(cases),
        "summary": _continuity_case_summary(cases),
        "cases": cases,
    }


def is_forensic_error_event(event: dict[str, Any]) -> bool:
    """Public shared selector for the canonical error-recall lane."""
    return _is_error_event(event)


def _signal_observation_summary(events: Iterable[dict[str, Any]]) -> dict[str, int]:
    summary = Counter()
    for event in events:
        if not _counts_as_active_signal(event):
            continue
        semantics = _event_continuity(event)
        if not _is_signal_semantics(semantics):
            continue
        summary["total"] += 1
        if semantics.get("severity") == "RED":
            summary["red"] += 1
        if semantics.get("legacy_inferred"):
            summary["legacy_inferred"] += 1
        if not _case_anchors(event):
            summary["unanchored"] += 1
        for trait in semantics.get("traits", []):
            if trait in {"incident", "regression", "slopwall", "security_incident"}:
                summary[trait] += 1
    return dict(summary)


def _continuity_case_summary(cases: Iterable[dict[str, Any]]) -> dict[str, int]:
    items = list(cases)
    summary = Counter()
    summary["total"] = len(items)
    for case in items:
        if case.get("severity") == "RED":
            summary["red"] += 1
        if case.get("legacy_inferred"):
            summary["legacy_inferred"] += 1
        for trait in case.get("traits", []):
            if trait in {"incident", "regression", "slopwall", "security_incident"}:
                summary[trait] += 1
    return dict(summary)


def _diverse_highlights(events: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    ordered = sorted(events, key=lambda event: (_dt(str(event["event_at"])), str(event.get("id") or "")), reverse=True)
    priority = [
        "signal:red_alert", "signal:slopwall", "signal:security_incident", "signal:incident", "signal:regression",
        "repo", "worker", "memory",
        "artifact:report", "artifact:proof", "artifact:screenshot", "artifact:evidence_log",
        "artifact:evidence", "artifact:transcript", "artifact:contract", "artifact:fixture", "artifact:artifact",
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
        artifact_objects: dict[str, set[str]] = defaultdict(set)
        for event in cumulative:
            if event.get("source_type") in {"TRACKED_ARTIFACT", "LIBRARY_ARTIFACT"}:
                artifact_objects[str(event.get("artifact_type") or "artifact")].add(
                    str(event.get("path") or event.get("id") or "").replace(chr(92), "/").casefold()
                )
        artifact_counts = {key: len(values) for key, values in sorted(artifact_objects.items())}
        continuity_cases = _build_continuity_cases(cumulative)
        case_summary = _continuity_case_summary(continuity_cases)
        signal_observation_summary = _signal_observation_summary(cumulative)
        anchor_groups: dict[str, dict[str, Any]] = {}
        for event in cumulative:
            family = _event_source_family(event)
            strong_case_anchors = set(_case_anchors(event))
            for anchor in _event_anchors(event):
                group = anchor_groups.setdefault(anchor, {
                    "families": set(), "event_ids": set(), "case_identity_events": set(), "latest_at": None,
                })
                group["families"].add(family)
                event_id = str(event.get("id") or "")
                group["event_ids"].add(event_id)
                if anchor in strong_case_anchors:
                    group["case_identity_events"].add(event_id)
                stamp = str(event.get("event_at") or "")
                if group["latest_at"] is None or (_safe_dt(stamp) and _safe_dt(group["latest_at"]) and _dt(stamp) > _dt(group["latest_at"])):
                    group["latest_at"] = stamp
        corroborated = [
            {
                "anchor": anchor,
                "source_families": sorted(group["families"]),
                "event_count": len(group["event_ids"]),
                "case_identity": bool(group["case_identity_events"]),
                "role": "CASE_LINK_SUPPORT" if group["case_identity_events"] else "CONTEXT_ONLY",
            }
            for anchor, group in anchor_groups.items()
            if len(group["families"]) >= 2
        ]
        corroborated.sort(key=lambda item: (-len(item["source_families"]), -item["event_count"], item["anchor"]))
        case_example_limit = 8 if label == "24h" else 4
        case_examples = continuity_cases[:case_example_limit]
        windows.append({
            "window": label,
            "hours": upper_hours,
            "event_count": len(cumulative),
            "source_counts": dict(sorted(source_counts.items())),
            "artifact_counts": artifact_counts,
            "signal_observation_summary": signal_observation_summary,
            "continuity_case_summary": case_summary,
            "continuity_case_examples": case_examples,
            "continuity_case_examples_returned": len(case_examples),
            "continuity_case_examples_total": len(continuity_cases),
            "continuity_case_examples_truncated": len(case_examples) < len(continuity_cases),
            "corroborated_anchors": corroborated[:6],
            "slice": "0-24h" if lower_hours == 0 else f"{lower_hours}h-{upper_hours}h",
            "slice_event_count": len(incremental),
            "slice_source_counts": dict(sorted(slice_source_counts.items())),
            "highlights": _diverse_highlights(incremental, highlight_limit),
        })
    return {
        "authority": "DERIVED_HISTORY_ONLY",
        "narrative_contract": dict(TIMELINE_NARRATIVE_CONTRACT),
        "contract": "multi-source chronology snapshot; continuity cases are the primary incident unit; observation volume is evidence density; source diversity is corroboration evidence, not independent witness proof, current-state authority, case identity, or causal inference",
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


def _is_error_event(event: dict[str, Any]) -> bool:
    """Select the forensic error-recall lane without promoting retrieval matches into cases."""
    semantics = _continuity_semantics(event)
    if _is_signal_semantics(semantics):
        return True
    tags = _normalized_labels(event.get("tags", []))
    # Old unstructured memory notes predate canonical signal tags. Keep them retrievable by
    # descriptive text, but this broader recall rule does not alter continuity semantics/cases.
    if event.get("source_type") == "VAULT_MEMORY" and _legacy_fallback_eligible(event, tags=tags, finding_tags=set()):
        descriptors = " ".join([
            str(event.get("scope") or ""), str(event.get("title") or ""), str(event.get("summary") or ""),
            *[str(tag) for tag in event.get("tags", [])],
        ]).casefold()
        words = token_words(descriptors)
        return bool(words & ERROR_MARKERS) or any(marker in descriptors for marker in ERROR_MARKERS)
    return False


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
        "tags": list(entry.get("tags") or []),
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
    supplemental_events: Iterable[dict[str, Any]] | None = None,
    max_limit: int = MAX_LIMIT,
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
        if view == "errors" and not _is_error_event(event):
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
    supplemental_selected: list[dict[str, Any]] = []
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
        select_external(supplemental_events, supplemental_selected)

    effective_limit = min(max(1, int(max_limit)), max(1, int(limit)))
    combined = [*selected, *repo_selected, *worker_selected, *artifact_selected, *supplemental_selected]
    for event in combined:
        event["continuity"] = _continuity_semantics(event)
        event["_all_anchors_cache"] = _event_anchors(event)
        event["case_anchors"] = _case_anchors(event)
        event["evidence_form"] = _evidence_form(event)
    combined.sort(key=lambda event: (_dt(str(event["event_at"])), str(event["id"])), reverse=True)
    newest = combined[:effective_limit]
    snapshots = build_timeline_snapshots(combined, now=snapshot_now)
    for event in combined:
        event.pop("_all_anchors_cache", None)
    snapshots["coverage"] = dict(source_coverage or {})
    memory_history_cases = _build_continuity_cases(events)
    memory_red_observations = sum(
        1 for event in events
        if _counts_as_active_signal(event) and _continuity_semantics(event).get("severity") == "RED"
    )
    memory_legacy_observations = sum(
        1 for event in events
        if _counts_as_active_signal(event) and _continuity_semantics(event).get("legacy_inferred")
    )
    snapshots["preserved_memory_history"] = {
        "observation_count": len(events),
        "red_observations": memory_red_observations,
        "legacy_inferred_observations": memory_legacy_observations,
        "signal_observation_summary": _signal_observation_summary(events),
        "continuity_case_summary": _continuity_case_summary(memory_history_cases),
    }
    return {
        "schema_version": 3,
        "authority": "DERIVED_HISTORY_ONLY",
        "contract": {
            "timeline": "chronology and grouping, never current truth by itself",
            "relationships": "only explicit supersedes plus explicit-thread/stable-evidence/specific-scope chronology; ambiguous evidence and broad scopes never imply one incident and no causal edge is inferred",
            "project_linkage": "explicit project metadata outranks secondary entity mentions",
            "repo_history": "local all-branch Git commits/refs are observed repository history, not memory or causal interpretation",
            "worker_history": "immutable finalized worker reports are lagging self-report evidence with automatically derived duration/utilization; they are not current-state authority or liveness proof",
            "artifact_history": "Git-tracked reports, evidence, logs, screenshots, proofs, fixtures, contracts, and transcripts are preserved artifact history; untracked WIP is not promoted into durable history",
            "continuity_cases": "report/log/screenshot/memory/commit describe evidence form; incident/regression/slopwall/security describe case traits; RED is severity; strong explicit anchors join observations into one case while broad GitHub issue refs remain corroboration-only",
            "snapshot_case_examples": "snapshot continuity_case_examples are explicitly bounded examples; complete materialized case navigation lives in continuity_graph",
            "classification": "structured memory tags/classification, worker finding tags, provenance incident IDs/evidence types, and explicit anchors outrank legacy text inference; legacy fallback is labeled",
            "corroboration": "snapshot source diversity can strengthen orientation but never turns repetition into authority or proves causality; broad GitHub anchors are context-only and must never be narrated as the case/thread itself",
            "narrative_order": "continuity cases first, work graph second, observation/evidence density third, context-only corroboration last",
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
        "supplemental_events": len(supplemental_selected),
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
    visible_dispositions = RECALL_VISIBLE_DISPOSITIONS
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
    for thread in report["threads"]:
        if thread.get("latest_disposition") not in RECALL_VISIBLE_DISPOSITIONS:
            continue
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
        if len(out) >= max_threads:
            break
    return out
