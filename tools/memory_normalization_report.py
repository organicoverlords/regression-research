from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from .memory_bank import DEFAULT_BANK, derive_display_title, load_bank
    from .durable_memory_adapter import _is_sensitive
except ImportError:
    from memory_bank import DEFAULT_BANK, derive_display_title, load_bank
    from durable_memory_adapter import _is_sensitive

DISPOSITIONS = (
    "CURRENT_DURABLE",
    "HISTORICAL_DURABLE",
    "SUPERSEDED",
    "REJECTED",
    "PROVISIONAL/NEEDS_EVIDENCE",
    "DUPLICATE_MERGED",
    "EPHEMERAL/DO_NOT_RECALL",
    "SENSITIVE_EXCLUDED",
)

_DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


def _source_classes(evidence: list[str]) -> list[str]:
    out: set[str] = set()
    for item in evidence:
        value = str(item)
        prefix = value.split(":", 1)[0].strip().casefold() if ":" in value else "path"
        out.add(prefix or "path")
    return sorted(out)


def _disposition(entry: dict[str, Any], superseded: set[str]) -> str:
    if entry["state"] == "REJECTED":
        return "REJECTED"
    if entry["id"] in superseded:
        return "SUPERSEDED"
    if entry["state"] == "PROVISIONAL":
        return "PROVISIONAL/NEEDS_EVIDENCE"
    return "CURRENT_DURABLE"


def _normalized_text_bytes(path: Path) -> bytes:
    text = path.read_text(encoding="utf-8-sig")
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def _sha256_text(path: Path) -> str:
    return hashlib.sha256(_normalized_text_bytes(path)).hexdigest()


def build_snapshot_receipt(root: Path, bank_path: Path) -> dict[str, Any]:
    bank_resolved = bank_path.resolve()
    try:
        bank_label = bank_resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        bank_label = str(bank_resolved)
    sources = [{"path": bank_label, "sha256": _sha256_text(bank_resolved)}]
    migrations = root / "memory" / "migrations"
    for path in sorted(migrations.glob("*candidates.jsonl")):
        sources.append({"path": path.relative_to(root).as_posix(), "sha256": _sha256_text(path)})
    canonical = json.dumps(sources, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return {
        "semantics": "POINT_IN_TIME_SOURCE_RECEIPT",
        "hash_semantics": "UTF8_TEXT_NORMALIZED_LF_NO_BOM",
        "source_fingerprint": fingerprint,
        "sources": sources,
        "note": "Counts/dispositions describe these logical UTF-8 text sources after BOM removal and LF normalization. Regenerate the tool for the current bank; normal later appends do not invalidate this historical audit snapshot.",
    }


def _read_candidate_files(root: Path, bank_ids: set[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in sorted((root / "memory" / "migrations").glob("*candidates.jsonl")):
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            cid = raw.get("id")
            if not isinstance(cid, str) or not cid or cid in bank_ids or cid in seen:
                continue
            seen.add(cid)
            raw = dict(raw)
            raw["_candidate_path"] = path.relative_to(root).as_posix()
            out.append(raw)
    return out


def build_report(entries: list[dict[str, Any]], candidate_entries: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    superseded_by: dict[str, list[str]] = {}
    for entry in entries:
        for old_id in entry.get("supersedes", []):
            superseded_by.setdefault(old_id, []).append(entry["id"])
    superseded = set(superseded_by)

    records: list[dict[str, Any]] = []
    sensitivity_counts: Counter[str] = Counter()
    for entry in entries:
        match = _DATE_RE.search(entry.get("text", ""))
        sensitive = _is_sensitive(entry.get("text", ""), {"tags": entry.get("tags", [])})
        sensitivity = "REVIEW" if sensitive else "CLEAR"
        sensitivity_counts[sensitivity] += 1
        disposition = _disposition(entry, superseded)
        records.append(
            {
                "id": entry["id"],
                "source_layer": "BANK",
                "title": entry.get("title") or derive_display_title(entry),
                "kind": entry["kind"],
                "scope": entry["scope"],
                "tags": entry.get("tags", []),
                "state": entry["state"],
                "disposition": disposition,
                "ordinary_recall": disposition in {"CURRENT_DURABLE", "PROVISIONAL/NEEDS_EVIDENCE"},
                "write_timestamp": entry["timestamp"],
                "event_date_hint": match.group(1) if match else None,
                "evidence": entry.get("evidence", []),
                "source_classes": _source_classes(entry.get("evidence", [])),
                "supersedes": entry.get("supersedes", []),
                "superseded_by": sorted(superseded_by.get(entry["id"], [])),
                "sensitivity": sensitivity,
                "retrieval_value": (
                    "CURRENT" if disposition == "CURRENT_DURABLE"
                    else "REVIEW" if disposition == "PROVISIONAL/NEEDS_EVIDENCE"
                    else "HISTORICAL"
                ),
            }
        )

    for entry in candidate_entries or []:
        text = str(entry.get("text", ""))
        sensitive = _is_sensitive(text, {"tags": entry.get("tags", [])})
        sensitivity = "REVIEW" if sensitive else "CLEAR"
        sensitivity_counts[sensitivity] += 1
        state = str(entry.get("state") or "PROVISIONAL")
        disposition = "REJECTED" if state == "REJECTED" else "PROVISIONAL/NEEDS_EVIDENCE"
        source_class = str(entry.get("source_class") or "candidate").casefold()
        evidence = [str(item) for item in entry.get("evidence", [])]
        event_source = entry.get("source_timestamp") or entry.get("timestamp")
        event_match = _DATE_RE.search(str(event_source or ""))
        records.append(
            {
                "id": entry["id"],
                "source_layer": "CANDIDATE",
                "candidate_path": entry.get("_candidate_path"),
                "title": entry.get("title") or f"Candidate {entry['id']}",
                "kind": entry.get("kind", "lesson"),
                "scope": entry.get("scope", "global"),
                "tags": entry.get("tags", []),
                "state": state,
                "disposition": disposition,
                "ordinary_recall": False,
                "write_timestamp": entry.get("timestamp"),
                "event_date_hint": event_match.group(1) if event_match else None,
                "evidence": evidence,
                "source_classes": sorted(set(_source_classes(evidence) + [source_class])),
                "supersedes": entry.get("supersedes", []),
                "superseded_by": [],
                "sensitivity": sensitivity,
                "retrieval_value": "REVIEW",
            }
        )

    disposition_counts = Counter(record["disposition"] for record in records)
    for name in DISPOSITIONS:
        disposition_counts.setdefault(name, 0)
    return {
        "schema_version": 1,
        "authority": "DERIVED_AUDIT_ONLY",
        "notes": [
            "This report is mechanically derived from the append-only memory bank and is not a second recall authority.",
            "A committed JSON report is a point-in-time evidence snapshot, not a perpetually current mirror; run this tool again for current state.",
            "PROVISIONAL records remain explicit review items; rejected/superseded records remain historically searchable.",
            "event_date_hint is only the first YYYY-MM-DD found in the memory text, not an independently proven timestamp.",
            "sensitivity=REVIEW is conservative triage only and does not rewrite or delete the source memory.",
        ],
        "total_records": len(records),
        "bank_records": len(entries),
        "candidate_only_records": len(candidate_entries or []),
        "counts": {
            "dispositions": dict(sorted(disposition_counts.items())),
            "states": dict(sorted(Counter(entry["state"] for entry in entries).items())),
            "kinds": dict(sorted(Counter(entry["kind"] for entry in entries).items())),
            "scopes": dict(sorted(Counter(entry["scope"] for entry in entries).items())),
            "sensitivity": dict(sorted(sensitivity_counts.items())),
        },
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Derived full-bank normalization/accounting report; does not mutate recall state.")
    parser.add_argument("--bank", type=Path, default=DEFAULT_BANK)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    entries = load_bank(args.bank)
    root = Path(__file__).resolve().parents[1]
    candidates = _read_candidate_files(root, {entry["id"] for entry in entries})
    report = build_report(entries, candidates)
    report["snapshot"] = build_snapshot_receipt(root, args.bank)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8", newline="\n")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
