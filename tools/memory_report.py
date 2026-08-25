#!/usr/bin/env python3
"""Produce bounded WebGPT reports from the local regression corpus.

This module is deliberately a read-only workflow, not a new MCP server.  The
existing shell-mcp owns the transport and its frozen seven-tool contract can
invoke this CLI with ``start_process``; ``read_output`` then reads the bounded
result.  The command never downloads, imports, writes, executes, or opens raw
transcripts.  It reads only the canonical bank, source registry, and
provenance index in this repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

try:  # Support both ``python -m tools.memory_report`` and direct execution.
    from .memory_bank import (
        BankError,
        DEFAULT_BANK,
        DEFAULT_SOURCES,
        MAX_HISTORY_LIMIT,
        MAX_RECALL_LIMIT,
        load_bank,
        search_entries,
    )
except ImportError:  # pragma: no cover - exercised by the CLI smoke test.
    from memory_bank import (  # type: ignore
        BankError,
        DEFAULT_BANK,
        DEFAULT_SOURCES,
        MAX_HISTORY_LIMIT,
        MAX_RECALL_LIMIT,
        load_bank,
        search_entries,
    )


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROVENANCE = ROOT / "provenance.json"
DEFAULT_LIMIT = 5
MAX_QUERY_CHARS = 200
MAX_SCOPE_CHARS = 80
MAX_TAG_CHARS = 40
MAX_OUTPUT_CHARS = 6000
MAX_FIELD_CHARS = 800
MAX_PROVENANCE_ITEMS = 8
MAX_PROVENANCE_PATH_CHARS = 240
EXPOSURE_STATUS = "NOT_PROVEN"
EXPOSURE_NOTE = (
    "ChatGPT-web exposure is NOT_PROVEN: this local workflow has not observed a "
    "live ChatGPT tool call."
)


class ReportError(ValueError):
    """A safe, user-actionable input or corpus error."""


def _clip(value: Any, limit: int = MAX_FIELD_CHARS) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[\w-]+", value.casefold(), flags=re.UNICODE))


def _validate_text(value: str, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReportError(f"{field} must be a non-empty string")
    if len(value) > maximum:
        raise ReportError(f"{field} exceeds {maximum} characters")
    if any(ord(char) < 32 and char not in "\t\n\r" for char in value):
        raise ReportError(f"{field} contains a control character")
    return value.strip()


def _load_json(path: Path, label: str) -> Any:
    if not path.is_file():
        raise ReportError(f"{label} is unavailable")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReportError(f"{label} is invalid") from exc


def _safe_relative(path: str) -> str | None:
    """Return a normalized repo-relative path, rejecting traversal/absolute paths."""

    if not isinstance(path, str) or not path.strip():
        return None
    candidate = Path(path.replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    normalized = candidate.as_posix()
    resolved = (ROOT / candidate).resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        return None
    return normalized


def _bounded_paths(values: Iterable[Any]) -> list[str]:
    paths: list[str] = []
    for value in list(values)[:MAX_PROVENANCE_ITEMS]:
        safe = _safe_relative(value)
        if safe is not None:
            paths.append(_clip(safe, MAX_PROVENANCE_PATH_CHARS))
    return paths


def _source_registry() -> dict[str, Any]:
    data = _load_json(DEFAULT_SOURCES, "memory source registry")
    if not isinstance(data, dict) or not isinstance(data.get("classes"), dict):
        raise ReportError("memory source registry is invalid")
    if not isinstance(data.get("sources", []), list):
        raise ReportError("memory source registry is invalid")
    return data


def _provenance_index() -> dict[str, Any]:
    data = _load_json(DEFAULT_PROVENANCE, "provenance index")
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        raise ReportError("provenance index is invalid")
    return data


def _file_receipt(path: Path, relative: str) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise ReportError(f"canonical source is unavailable: {relative}") from exc
    return {
        "path": relative,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def corpus_receipt() -> dict[str, Any]:
    """Return deterministic hashes for the three read-only canonical inputs."""

    files = [
        _file_receipt(DEFAULT_BANK, "memory/memory-bank.jsonl"),
        _file_receipt(DEFAULT_SOURCES, "memory/sources.json"),
        _file_receipt(DEFAULT_PROVENANCE, "provenance.json"),
    ]
    digest = hashlib.sha256()
    for item in files:
        digest.update(item["path"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(item["sha256"].encode("ascii"))
        digest.update(b"\n")
    return {"corpus_sha256": digest.hexdigest(), "files": files}


def _request_id(command: str, values: dict[str, Any], receipt: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"command": command, "request": values, "corpus_sha256": receipt["corpus_sha256"]},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "rr-" + hashlib.sha256(canonical).hexdigest()[:16]


def _entry_view(entry: dict[str, Any]) -> dict[str, Any]:
    """Expose only compact bank fields; never embed source content."""

    return {
        "id": entry["id"],
        "timestamp": entry["timestamp"],
        "kind": entry["kind"],
        "scope": entry["scope"],
        "tags": list(entry["tags"][:12]),
        "text": _clip(entry["text"]),
        "state": entry["state"],
        "evidence": _bounded_paths(entry["evidence"]),
        "supersedes": list(entry["supersedes"][:16]),
    }


def _provenance_view(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "incident_id": entry.get("incident_id"),
        "report_path": _safe_relative(entry.get("report_path", "")),
        "title": _clip(entry.get("title", ""), 300),
        "date": entry.get("date"),
        "evidence_type": entry.get("evidence_type"),
        "duplicate_status": entry.get("duplicate_status"),
        "superseded_by": entry.get("superseded_by"),
        "raw_transcripts": _bounded_paths(entry.get("raw_transcripts", [])),
        "evidence_files": _bounded_paths(entry.get("evidence_files", [])),
        "contract_snapshots": _bounded_paths(entry.get("contract_snapshots", [])),
        "missing": [
            _clip(item, MAX_PROVENANCE_PATH_CHARS)
            for item in list(entry.get("missing", []))[:MAX_PROVENANCE_ITEMS]
        ],
    }


def _provenance_matches(entries: list[dict[str, Any]], query: str, limit: int) -> list[dict[str, Any]]:
    query_tokens = _tokens(query)
    ranked: list[tuple[int, str, dict[str, Any]]] = []
    for entry in entries:
        searchable = " ".join(
            str(entry.get(field, ""))
            for field in ("incident_id", "report_path", "title", "evidence_type", "duplicate_status")
        )
        searchable += " " + " ".join(
            str(item)
            for field in ("raw_transcripts", "evidence_files", "contract_snapshots")
            for item in entry.get(field, [])
        )
        tokens = _tokens(searchable)
        score = sum(token in tokens for token in query_tokens)
        if score:
            ranked.append((score, str(entry.get("date", "")), entry))
    ranked.sort(
        key=lambda item: (item[0], item[1], str(item[2].get("report_path", ""))),
        reverse=True,
    )
    return [_provenance_view(item[2]) for item in ranked[:limit]]


def _status_summary(entries: list[dict[str, Any]], sources: dict[str, Any], provenance: dict[str, Any]) -> dict[str, Any]:
    classes = sources.get("classes", {})
    source_records = sources.get("sources", [])
    availability = Counter(
        str(item.get("availability", "unknown"))
        for item in sources.get("candidate_source_inventory", [])
        if isinstance(item, dict)
    )
    class_counts = Counter(
        str(item.get("class", "unknown"))
        for item in source_records
        if isinstance(item, dict)
    )
    report_paths = []
    broken_paths = []
    for item in provenance.get("entries", []):
        if not isinstance(item, dict):
            broken_paths.append("invalid provenance entry")
            continue
        report_path = _safe_relative(item.get("report_path", ""))
        if report_path:
            report_paths.append(report_path)
            if not (ROOT / report_path).is_file():
                broken_paths.append(report_path)
        else:
            broken_paths.append("invalid report path")
        for field in ("raw_transcripts", "evidence_files", "contract_snapshots"):
            for raw_path in item.get(field, []):
                safe = _safe_relative(raw_path)
                if safe and not (ROOT / safe).exists():
                    broken_paths.append(safe)
                elif safe is None:
                    broken_paths.append("unsafe provenance path")
    duplicate_reports = len(report_paths) - len(set(report_paths))
    valid = not broken_paths and duplicate_reports == 0 and all(isinstance(item, dict) for item in provenance.get("entries", []))
    return {
        "status": "PROVEN" if valid else "NOT_PROVEN",
        "entries": len(entries),
        "states": dict(sorted(Counter(str(item["state"]) for item in entries).items())),
        "kinds": dict(sorted(Counter(str(item["kind"]) for item in entries).items())),
        "scopes": dict(sorted(Counter(str(item["scope"]) for item in entries).items())),
        "source_classes": dict(sorted(class_counts.items())),
        "source_class_ranks": dict(sorted((str(key), int(value)) for key, value in classes.items())),
        "source_availability": dict(sorted(availability.items())),
        "provenance": {
            "entries": len(provenance.get("entries", [])),
            "reports_indexed": len(set(report_paths)),
            "broken_paths": sorted(set(broken_paths))[:MAX_PROVENANCE_ITEMS],
            "duplicate_report_paths": duplicate_reports,
        },
    }


def _base_payload(command: str, values: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        "service_status": "PROVEN",
        "integration_status": EXPOSURE_STATUS,
        "integration_note": EXPOSURE_NOTE,
        "command": command,
        "request": values,
        "receipt": {
            "report_id": _request_id(command, values, receipt),
            "corpus_sha256": receipt["corpus_sha256"],
            "source_files": receipt["files"],
        },
    }


def _load_context() -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    try:
        entries = load_bank(DEFAULT_BANK)
    except BankError as exc:
        raise ReportError("memory bank validation failed") from exc
    return entries, _source_registry(), _provenance_index()


def build_report(query: str, *, scope: str | None = None, tags: list[str] | None = None,
                 limit: int = DEFAULT_LIMIT, history: bool = False) -> dict[str, Any]:
    query = _validate_text(query, "query", MAX_QUERY_CHARS)
    if scope is not None:
        scope = _validate_text(scope, "scope", MAX_SCOPE_CHARS)
    tags = tags or []
    if len(tags) > 12:
        raise ReportError("tags exceeds 12 items")
    tags = [_validate_text(tag, "tag", MAX_TAG_CHARS) for tag in tags]
    hard_cap = MAX_HISTORY_LIMIT if history else MAX_RECALL_LIMIT
    if not isinstance(limit, int) or limit < 1:
        raise ReportError("limit must be at least 1")
    limit = min(limit, hard_cap)
    entries, sources, provenance = _load_context()
    receipt = corpus_receipt()
    matches = search_entries(
        entries,
        query,
        scope=scope,
        tags=tags,
        limit=limit,
        history=history,
        source_registry=sources,
    )
    prov = _provenance_matches(provenance["entries"], query, min(MAX_PROVENANCE_ITEMS, limit))
    payload = _base_payload(
        "report",
        {"query": query, "scope": scope, "tags": tags, "limit": limit, "history": history},
        receipt,
    )
    payload.update(
        {
            "summary": {
                "memory_matches": len(matches),
                "provenance_matches": len(prov),
                "history_mode": history,
                "claim_states": sorted({entry["state"] for entry in matches}),
            },
            "findings": [_entry_view(entry) for entry in matches],
            "provenance": prov,
            "limitations": [
                "Results are compact memory claims and provenance pointers; raw transcripts are not opened or returned.",
                "Current user instruction and live evidence outrank recalled memory.",
                "Source authority reorders relevant matches; it does not create relevance.",
            ],
        }
    )
    return payload


def build_status() -> dict[str, Any]:
    entries, sources, provenance = _load_context()
    receipt = corpus_receipt()
    payload = _base_payload("status", {}, receipt)
    payload["corpus"] = _status_summary(entries, sources, provenance)
    payload["bounds"] = {
        "default_recall": DEFAULT_LIMIT,
        "max_recall": MAX_RECALL_LIMIT,
        "max_history": MAX_HISTORY_LIMIT,
        "max_output_chars": MAX_OUTPUT_CHARS,
        "entry_text_chars": MAX_FIELD_CHARS,
    }
    return payload


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _text_report(payload: dict[str, Any]) -> str:
    request = payload["request"]
    summary = payload.get("summary", {})
    lines = [
        "Regression Research bounded report",
        f"Query: {request.get('query', '')}",
        f"Service status: {payload['service_status']}",
        f"Integration status: {payload['integration_status']}",
        f"Matches: memory={summary.get('memory_matches', 0)} provenance={summary.get('provenance_matches', 0)}",
        "",
        "Findings:",
    ]
    findings = payload.get("findings", [])
    if not findings:
        lines.append("- No matching non-superseded memory entries.")
    for index, entry in enumerate(findings, start=1):
        lines.append(f"{index}. [{entry['state']}] {entry['id']} ({entry['scope']}/{entry['kind']})")
        lines.append(f"   {entry['text']}")
        if entry.get("evidence"):
            lines.append(f"   Evidence: {', '.join(entry['evidence'])}")
    lines.extend(["", "Provenance:"])
    provenance = payload.get("provenance", [])
    if not provenance:
        lines.append("- No matching indexed report.")
    for item in provenance:
        lines.append(f"- {item.get('title') or item.get('report_path')} [{item.get('evidence_type')}]" )
        if item.get("report_path"):
            lines.append(f"  Report: {item['report_path']}")
        pointers = item.get("raw_transcripts", []) + item.get("evidence_files", []) + item.get("contract_snapshots", [])
        if pointers:
            lines.append(f"  Pointers: {', '.join(pointers)}")
    lines.extend(
        [
            "",
            "Limitations:",
            *[f"- {item}" for item in payload.get("limitations", [EXPOSURE_NOTE])],
            "",
            f"Receipt: {payload['receipt']['report_id']} corpus={payload['receipt']['corpus_sha256'][:16]}",
            f"Exposure: {EXPOSURE_NOTE}",
        ]
    )
    return "\n".join(lines)


def _fit_output(payload: dict[str, Any], formatter: str) -> str:
    """Keep the worker-facing result <=6,000 chars without losing the receipt."""

    while True:
        output = _json_text(payload) if formatter == "json" else _text_report(payload)
        if len(output) + 1 <= MAX_OUTPUT_CHARS:
            return output + "\n"
        findings = payload.get("findings", [])
        provenance = payload.get("provenance", [])
        if len(findings) > 1:
            payload["findings"] = findings[:-1]
            payload.setdefault("summary", {})["truncated"] = True
            continue
        if len(provenance) > 1:
            payload["provenance"] = provenance[:-1]
            payload.setdefault("summary", {})["truncated"] = True
            continue
        # The fixed fields are already bounded; this is only a final guard
        # against unexpectedly large future schema additions. Keep JSON valid
        # when the guard is needed instead of slicing a serialized document.
        compact_payload = {
            "service_status": payload.get("service_status"),
            "integration_status": payload.get("integration_status"),
            "receipt": {
                "report_id": payload.get("receipt", {}).get("report_id"),
                "corpus_sha256": payload.get("receipt", {}).get("corpus_sha256"),
            },
            "summary": payload.get("summary"),
            "truncated": True,
        }
        compact = _json_text(compact_payload)
        if formatter == "text":
            return compact + "\n"
        return compact + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bounded read-only report over the local regression corpus")
    sub = parser.add_subparsers(dest="command", required=True)
    report = sub.add_parser("report", help="retrieve bounded memory and provenance findings")
    report.add_argument("--query", required=True, help="relevance query; blank searches are not allowed")
    report.add_argument("--scope")
    report.add_argument("--tag", action="append", default=[])
    report.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    report.add_argument("--history", action="store_true", help="include rejected/superseded history, capped at 20")
    report.add_argument("--format", choices=("text", "json"), default="text")
    status = sub.add_parser("status", help="report local corpus validation and counts")
    status.add_argument("--format", choices=("text", "json"), default="json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "report":
            payload = build_report(
                args.query,
                scope=args.scope,
                tags=args.tag,
                limit=args.limit,
                history=args.history,
            )
            output = _fit_output(payload, args.format)
        else:
            payload = build_status()
            output = _fit_output(payload, args.format)
    except ReportError as exc:
        error = {"status": "REJECTED", "error": str(exc), "integration_status": EXPOSURE_STATUS}
        print(_json_text(error))
        return 2
    print(output, end="")
    return 0


if __name__ == "__main__":  # pragma: no cover - covered by subprocess smoke tests.
    raise SystemExit(main())
