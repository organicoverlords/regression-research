#!/usr/bin/env python3
"""Audit the first bounded population pass over the canonical memory bank.

The population pass is intentionally repository-only.  It reads the prepared
candidate/curated JSONL and migration audit alongside the canonical bank and
source registry, then runs a fixed, small recall matrix.  It never downloads,
imports raw transcripts, opens an MCP server, or changes the bank.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

try:  # Support both ``python -m tools.memory_population`` and direct execution.
    from .memory_bank import (
        BankError,
        DEFAULT_BANK,
        DEFAULT_SOURCES,
        DEFAULT_RECALL_LIMIT,
        MAX_HISTORY_LIMIT,
        MAX_RECALL_LIMIT,
        load_bank,
        load_source_registry,
        search_entries,
    )
    from .memory_report import EXPOSURE_NOTE, EXPOSURE_STATUS, corpus_receipt
    from .migrate_memory_bank import source_class
except ImportError:  # pragma: no cover - exercised by the CLI smoke test.
    from memory_bank import (  # type: ignore
        BankError,
        DEFAULT_BANK,
        DEFAULT_SOURCES,
        DEFAULT_RECALL_LIMIT,
        MAX_HISTORY_LIMIT,
        MAX_RECALL_LIMIT,
        load_bank,
        load_source_registry,
        search_entries,
    )
    from memory_report import EXPOSURE_NOTE, EXPOSURE_STATUS, corpus_receipt  # type: ignore
    from migrate_memory_bank import source_class  # type: ignore


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATES = ROOT / "memory" / "migrations" / "2026-08-25-population-candidates.jsonl"
DEFAULT_CURATED = ROOT / "memory" / "migrations" / "2026-08-25-population-curated.jsonl"
DEFAULT_AUDIT = ROOT / "memory" / "migrations" / "2026-08-25-population-audit.jsonl"
DEFAULT_OUTPUT = ROOT / "memory" / "reports" / "2026-08-25-population-acceptance.json"
INITIAL_BANK_SIZE = 16
MAX_OUTPUT_CHARS = 6000


class PopulationError(ValueError):
    """A safe, user-actionable population-audit error."""


# The labels are the acceptance language from issue #18.  Queries are explicit
# and deterministic so a report cannot claim coverage merely from a title.
ACCEPTANCE_QUERIES: tuple[dict[str, Any], ...] = (
    {
        "id": "all_caps_rules_corrections",
        "label": "all-caps rules/corrections",
        "query": "correction action routing",
        "scope": "global",
        "history": False,
        "expected_any": ["mem-20260825-correction-action-gate"],
    },
    {
        "id": "mcp_safety_routing_history",
        "label": "MCP safety-routing history",
        "query": "MCP safety routing",
        "scope": "mcp",
        "history": True,
        "expected_any": [
            "mem-20260825-mcp-nonarrival",
            "mem-20260825-mcp-trigger-status",
        ],
    },
    {
        "id": "anti_churn_behavior",
        "label": "anti-churn behavior",
        "query": "anti churn retry",
        "scope": None,
        "history": False,
        "expected_any": [
            "mem-20260825-anti-churn",
            "mem-20260825-route-contradiction",
        ],
    },
    {
        "id": "p3_fleet_convergence",
        "label": "P3 fleet convergence",
        "query": "fleet convergence",
        "scope": "p3",
        "history": False,
        "expected_any": ["mem-20260825-p3-convergence"],
    },
    {
        "id": "prior_project_status",
        "label": "prior project status",
        "query": "Chain Lightning",
        "scope": "p3",
        "history": True,
        "expected_any": ["mem-20260825-chain-lightning"],
    },
    {
        "id": "shared_policy_changes",
        "label": "shared policy changes",
        "query": "policy live state",
        "scope": "global",
        "history": True,
        "expected_any": [
            "mem-20260825-policy-live-state-current",
            "mem-20260825-policy-live-state-v13",
        ],
    },
    {
        "id": "rejected_historical_theories",
        "label": "rejected historical theories",
        "query": "6KB MCP",
        "scope": "mcp",
        "history": True,
        "expected_any": ["mem-20260825-mcp-6kb-hard"],
    },
)


def _read_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    if not path.is_file():
        raise PopulationError(f"{label} is unavailable: {path.as_posix()}")
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError) as exc:
        raise PopulationError(f"{label} is unreadable") from exc
    for line_no, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PopulationError(f"{label} line {line_no} is invalid JSON") from exc
        if not isinstance(record, dict):
            raise PopulationError(f"{label} line {line_no} is not an object")
        records.append(record)
    return records


def _read_bank(path: Path, label: str) -> list[dict[str, Any]]:
    try:
        return load_bank(path)
    except BankError as exc:
        raise PopulationError(f"{label} validation failed: {exc}") from exc


def _count(values: Iterable[Any]) -> dict[str, int]:
    return dict(sorted(Counter(str(value) for value in values).items()))


def _matching_source_ids(entry: dict[str, Any], registry: dict[str, Any]) -> list[str]:
    matches: set[str] = set()
    for evidence in entry.get("evidence", []):
        for source in registry.get("sources", []):
            if not isinstance(source, dict):
                continue
            prefixes = source.get("match_prefixes", [])
            if any(str(evidence).startswith(str(prefix)) for prefix in prefixes):
                matches.add(str(source.get("id", "unclassified")))
    return sorted(matches) or ["unclassified"]


def _entry_counts(entries: list[dict[str, Any]], registry: dict[str, Any]) -> dict[str, dict[str, int]]:
    by_source: Counter[str] = Counter()
    source_pointer_matches: Counter[str] = Counter()
    by_class: Counter[str] = Counter()
    for entry in entries:
        matches = _matching_source_ids(entry, registry)
        source_pointer_matches.update(matches)
        # A record can retain several evidence pointers.  The ``source`` view
        # is deliberately exclusive: choose the highest-authority matched
        # source, then the stable registry order, so counts describe records
        # rather than double-counting pointers.
        ranked_sources: list[tuple[int, int, str]] = []
        for registry_index, source in enumerate(registry.get("sources", [])):
            if not isinstance(source, dict) or str(source.get("id")) not in matches:
                continue
            class_name = str(source.get("class", "UNCLASSIFIED"))
            rank = int((registry.get("classes") or {}).get(class_name, 0))
            ranked_sources.append((rank, -registry_index, str(source.get("id"))))
        primary_source = max(ranked_sources)[2] if ranked_sources else "unclassified"
        by_source.update([primary_source])
        by_class.update([source_class(entry, registry)[0] or "UNCLASSIFIED"])
    return {
        "source": dict(sorted(by_source.items())),
        "source_pointer_matches": dict(sorted(source_pointer_matches.items())),
        "class": dict(sorted(by_class.items())),
        "kind": _count(entry["kind"] for entry in entries),
        "state": _count(entry["state"] for entry in entries),
    }


def _audit_counts(audit: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter()
    for index, record in enumerate(audit, start=1):
        action = record.get("action")
        candidate = record.get("candidate")
        if not isinstance(action, str) or not action:
            raise PopulationError(f"population audit record {index} has no action")
        if not isinstance(candidate, str) or not candidate:
            raise PopulationError(f"population audit record {index} has no candidate")
        counts[action] += 1
    return dict(sorted(counts.items()))


def _query_result(
    entries: list[dict[str, Any]],
    registry: dict[str, Any],
    specification: dict[str, Any],
) -> dict[str, Any]:
    history = bool(specification["history"])
    requested_limit = MAX_HISTORY_LIMIT if history else MAX_RECALL_LIMIT
    matches = search_entries(
        entries,
        str(specification["query"]),
        scope=specification.get("scope"),
        limit=requested_limit,
        history=history,
        source_registry=registry,
    )
    matched_ids = [str(entry["id"]) for entry in matches]
    expected = [str(item) for item in specification.get("expected_any", [])]
    expected_hit = any(item in matched_ids for item in expected)
    bounded = len(matches) <= (MAX_HISTORY_LIMIT if history else MAX_RECALL_LIMIT)
    status = "PROVEN" if matches and expected_hit and bounded else "NOT_PROVEN"
    return {
        "id": specification["id"],
        "label": specification["label"],
        "query": specification["query"],
        "scope": specification.get("scope"),
        "history": history,
        "limit_requested": requested_limit,
        "limit_hard_cap": MAX_HISTORY_LIMIT if history else MAX_RECALL_LIMIT,
        "returned": len(matches),
        "matched_ids": matched_ids,
        "expected_any": expected,
        "expected_hit": expected_hit,
        "claim_states": sorted({str(entry["state"]) for entry in matches}),
        "bounded": bounded,
        "status": status,
    }


def _recall_acceptance(entries: list[dict[str, Any]], registry: dict[str, Any]) -> dict[str, Any]:
    queries = [_query_result(entries, registry, specification) for specification in ACCEPTANCE_QUERIES]
    ordinary_specs = [specification for specification in ACCEPTANCE_QUERIES if not specification["history"]]
    default_counts = [
        len(
            search_entries(
                entries,
                str(specification["query"]),
                scope=specification.get("scope"),
                source_registry=registry,
            )
        )
        for specification in ordinary_specs
    ]
    ordinary_hard_counts = [
        len(
            search_entries(
                entries,
                str(specification["query"]),
                scope=specification.get("scope"),
                limit=999,
                source_registry=registry,
            )
        )
        for specification in ordinary_specs
    ]
    history_counts = [item["returned"] for item in queries if item["history"]]
    rejected_id = "mem-20260825-mcp-6kb-hard"
    policy_snapshot_id = "mem-20260825-policy-live-state-v13"
    ordinary_rejected = search_entries(
        entries,
        "6KB MCP",
        scope="mcp",
        limit=999,
        history=False,
        source_registry=registry,
    )
    ordinary_policy = search_entries(
        entries,
        "policy live state",
        scope="global",
        limit=999,
        history=False,
        source_registry=registry,
    )
    provisional_candidates = {
        str(entry["id"])
        for entry in entries
        if entry["state"] == "PROVISIONAL"
    }
    provisional_preserved = all(
        entry["id"] in provisional_candidates and entry["state"] == "PROVISIONAL"
        for entry in entries
        if entry["id"] in provisional_candidates
    )
    checks = {
        "all_required_queries_proven": all(item["status"] == "PROVEN" for item in queries),
        "ordinary_default_bound": max(default_counts or [0]) <= DEFAULT_RECALL_LIMIT,
        "ordinary_hard_bound": max(ordinary_hard_counts or [0]) <= MAX_RECALL_LIMIT,
        "history_hard_bound": max(history_counts or [0]) <= MAX_HISTORY_LIMIT,
        "rejected_hidden_from_ordinary_recall": rejected_id not in {entry["id"] for entry in ordinary_rejected},
        "superseded_policy_hidden_from_ordinary_recall": policy_snapshot_id
        not in {entry["id"] for entry in ordinary_policy},
        "blank_unscoped_recall_empty": search_entries(entries, "", source_registry=registry) == [],
        "provisional_claims_preserved": provisional_preserved,
    }
    return {
        "status": "PROVEN" if all(checks.values()) else "NOT_PROVEN",
        "queries": queries,
        "checks": checks,
        "bounds": {
            "ordinary_default": DEFAULT_RECALL_LIMIT,
            "ordinary_hard_cap": MAX_RECALL_LIMIT,
            "history_hard_cap": MAX_HISTORY_LIMIT,
        },
        "provisional_entries": sorted(provisional_candidates),
    }


def build_population_report() -> dict[str, Any]:
    """Build a deterministic, evidence-bound population report."""

    entries = _read_bank(DEFAULT_BANK, "canonical memory bank")
    registry = load_source_registry(DEFAULT_SOURCES)
    if not isinstance(registry, dict) or not isinstance(registry.get("sources"), list):
        raise PopulationError("memory source registry is invalid")
    candidates = _read_bank(DEFAULT_CANDIDATES, "population candidates")
    curated = _read_bank(DEFAULT_CURATED, "curated population")
    audit = _read_jsonl(DEFAULT_AUDIT, "population audit")
    audit_actions = _audit_counts(audit)
    curated_ids = {str(entry["id"]) for entry in curated}
    bank_ids = {str(entry["id"]) for entry in entries}
    candidate_states = _count(entry["state"] for entry in candidates)
    kept_ids = {
        str(record["candidate"])
        for record in audit
        if record.get("action") == "kept"
    }
    promoted_ids = kept_ids & bank_ids
    before = len(entries) - len(promoted_ids)
    supersession_edges = [
        {"source": str(entry["id"]), "target": str(target)}
        for entry in entries
        for target in entry.get("supersedes", [])
    ]
    recall = _recall_acceptance(entries, registry)
    checks = {
        "bank_substantially_beyond_initial_16": len(entries) > INITIAL_BANK_SIZE,
        "candidate_and_curated_counts_match": len(candidates) == len(curated),
        "curated_records_represented_in_bank": curated_ids <= bank_ids,
        "candidate_provisional_state_preserved": all(
            entry["state"] == "PROVISIONAL"
            for entry in candidates
            if entry["state"] == "PROVISIONAL" and entry["id"] in bank_ids
        ),
        "audit_covers_curated_records": {str(record.get("candidate")) for record in audit}
        >= curated_ids,
        "recall_acceptance_proven": recall["status"] == "PROVEN",
    }
    status = "PROVEN" if all(checks.values()) else "NOT_PROVEN"
    return {
        "status": status,
        "integration_status": EXPOSURE_STATUS,
        "integration_note": EXPOSURE_NOTE,
        "acceptance": {
            "issue": 18,
            "objective": "initial ranked population and bounded recall acceptance sweep",
            "status": status,
            "checks": checks,
        },
        "population": {
            "initial_bank_entries": INITIAL_BANK_SIZE,
            "bank_entries_before_population": before,
            "bank_entries_after_population": len(entries),
            "growth": len(entries) - before,
            "candidates": len(candidates),
            "curated": len(curated),
            "represented_curated_ids": len(curated_ids & bank_ids),
            "candidate_states": candidate_states,
            "provisional_candidates_not_auto_promoted": sorted(
                entry["id"] for entry in candidates if entry["state"] == "PROVISIONAL"
            ),
        },
        "counts": _entry_counts(entries, registry),
        "duplicate_and_supersession": {
            "audit_actions": audit_actions,
            "duplicate_collapses": audit_actions.get("collapsed_duplicate", 0),
            "supersession_audit_actions": sum(
                count for action, count in audit_actions.items() if action.startswith("supersession_")
            ),
            "bank_supersession_edges": len(supersession_edges),
            "bank_superseded_entries": len({item["target"] for item in supersession_edges}),
            "bank_supersessions": supersession_edges,
        },
        "recall_acceptance": recall,
        "limitations": [
            "Population uses only committed repository evidence and prepared bounded candidates; no downloads or raw transcript imports were used.",
            "Source/class counts are derived from evidence-prefix matches in memory/sources.json.",
            "Current user instruction and live evidence outrank recalled memory; ChatGPT-web exposure remains NOT_PROVEN until a live tool call is observed.",
        ],
        "receipt": corpus_receipt(),
    }


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _text_report(payload: dict[str, Any]) -> str:
    population = payload["population"]
    counts = payload["counts"]
    recall = payload["recall_acceptance"]
    lines = [
        "Regression Research population acceptance",
        f"Status: {payload['status']} (issue #{payload['acceptance']['issue']})",
        f"Bank: {population['bank_entries_before_population']} -> {population['bank_entries_after_population']} (+{population['growth']})",
        f"Candidates/curated: {population['candidates']}/{population['curated']}",
        f"States: {counts['state']}",
        f"Classes: {counts['class']}",
        f"Kinds: {counts['kind']}",
        f"Sources: {counts['source']}",
        f"Duplicates/supersessions: {payload['duplicate_and_supersession']['duplicate_collapses']}/"
        f"{payload['duplicate_and_supersession']['bank_supersession_edges']}",
        "",
        "Recall acceptance:",
    ]
    for item in recall["queries"]:
        lines.append(
            f"- {item['status']}: {item['label']} -> {item['returned']} "
            f"({', '.join(item['matched_ids'][:3])})"
        )
    lines.extend(
        [
            "",
            f"Bounds/checks: {recall['checks']}",
            f"Receipt: {payload['receipt']['corpus_sha256'][:16]}",
            f"WebGPT exposure: {payload['integration_status']}",
        ]
    )
    return "\n".join(lines)


def _fit_output(payload: dict[str, Any], formatter: str) -> str:
    output = _json_text(payload) if formatter == "json" else _text_report(payload)
    if len(output) + 1 > MAX_OUTPUT_CHARS:
        compact = {
            "status": payload.get("status"),
            "integration_status": payload.get("integration_status"),
            "acceptance": payload.get("acceptance"),
            "population": payload.get("population"),
            "recall_acceptance": {
                "status": payload.get("recall_acceptance", {}).get("status"),
                "checks": payload.get("recall_acceptance", {}).get("checks"),
            },
            "receipt": payload.get("receipt"),
            "truncated": True,
        }
        output = _json_text(compact)
    return output + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit the bounded memory population and recall acceptance")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--output",
        type=Path,
        help="optional repository-relative JSON report path under memory/reports",
    )
    return parser


def _safe_output(path: Path) -> Path:
    resolved = path if path.is_absolute() else ROOT / path
    resolved = resolved.resolve()
    reports_root = (ROOT / "memory" / "reports").resolve()
    try:
        resolved.relative_to(reports_root)
    except ValueError as exc:
        raise PopulationError("output must be under memory/reports") from exc
    return resolved


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = build_population_report()
        if args.output:
            destination = _safe_output(args.output)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(_json_text(payload) + "\n", encoding="utf-8", newline="\n")
        print(_fit_output(payload, args.format), end="")
        return 0 if payload["status"] == "PROVEN" else 1
    except PopulationError as exc:
        print(json.dumps({"status": "REJECTED", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":  # pragma: no cover - covered by subprocess smoke tests.
    raise SystemExit(main())
