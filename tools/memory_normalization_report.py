from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from .memory_bank import DEFAULT_BANK, derive_display_title, load_bank
    from .memory_classification import (
        DOMAINS,
        DURABILITIES,
        SEMANTIC_CATEGORIES,
        SENSITIVITIES,
        classify_entry,
    )
except ImportError:
    from memory_bank import DEFAULT_BANK, derive_display_title, load_bank
    from memory_classification import (
        DOMAINS,
        DURABILITIES,
        SEMANTIC_CATEGORIES,
        SENSITIVITIES,
        classify_entry,
    )

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
_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def _source_classes(evidence: list[str]) -> list[str]:
    out: set[str] = set()
    for item in evidence:
        value = str(item)
        prefix = value.split(":", 1)[0].strip().casefold() if ":" in value else "path"
        out.add(prefix or "path")
    return sorted(out)


def _disposition(entry: dict[str, Any], superseded: set[str], classification: dict[str, Any]) -> str:
    if entry["state"] == "REJECTED":
        return "REJECTED"
    if entry["id"] in superseded:
        return "SUPERSEDED"
    if classification["sensitivity"] == "EXCLUDE":
        return "SENSITIVE_EXCLUDED"
    if classification["durability"] == "EPHEMERAL":
        return "EPHEMERAL/DO_NOT_RECALL"
    if classification["expired"] or (
        classification["durability"] == "HISTORICAL" and entry["state"] == "PROVEN"
    ):
        return "HISTORICAL_DURABLE"
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
    for path in sorted(migrations.glob("*candidate-dispositions.json")):
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


def _read_candidate_dispositions(root: Path, candidate_ids: set[str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in sorted((root / "memory" / "migrations").glob("*candidate-dispositions.json")):
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if data.get("schema_version") != 1 or not isinstance(data.get("reviews"), list):
            raise ValueError(f"invalid candidate-disposition receipt: {path}")
        for review in data["reviews"]:
            candidate_id = review.get("id")
            disposition = review.get("disposition")
            if candidate_id not in candidate_ids:
                raise ValueError(f"candidate-disposition receipt references unknown candidate: {candidate_id}")
            if candidate_id in out:
                raise ValueError(f"duplicate candidate disposition: {candidate_id}")
            if disposition not in DISPOSITIONS or disposition == "PROVISIONAL/NEEDS_EVIDENCE":
                raise ValueError(f"invalid final candidate disposition for {candidate_id}: {disposition}")
            if not isinstance(review.get("reason"), str) or not review["reason"].strip():
                raise ValueError(f"candidate disposition requires reason: {candidate_id}")
            normalized = dict(review)
            normalized["_review_path"] = path.relative_to(root).as_posix()
            out[candidate_id] = normalized
    return out


def _duplicate_groups(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for entry in entries:
        normalized = _NORMALIZE_RE.sub(" ", str(entry.get("text") or "").casefold()).strip()
        if not normalized:
            continue
        key = (str(entry.get("kind") or ""), str(entry.get("scope") or "").casefold(), normalized)
        buckets[key].append(entry["id"])
    return [
        {"ids": sorted(ids), "count": len(ids)}
        for ids in buckets.values()
        if len(ids) > 1
    ]


def _record_base(entry: dict[str, Any], classification: dict[str, Any]) -> dict[str, Any]:
    match = _DATE_RE.search(str(entry.get("text") or ""))
    return {
        "semantic_category": classification["semantic_category"],
        "primary_domain": classification["primary_domain"],
        "projects": classification["projects"],
        "roles": classification["roles"],
        "entities": classification["entities"],
        "durability": classification["durability"],
        "classification_confidence": classification["confidence"],
        "classification_review_reasons": classification["review_reasons"],
        "sensitivity": classification["sensitivity"],
        "expired": classification["expired"],
        "write_timestamp": entry.get("timestamp"),
        "event_date_hint": match.group(1) if match else None,
    }


def build_report(
    entries: list[dict[str, Any]],
    candidate_entries: list[dict[str, Any]] | None = None,
    candidate_dispositions: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    superseded_by: dict[str, list[str]] = {}
    for entry in entries:
        for old_id in entry.get("supersedes", []):
            superseded_by.setdefault(old_id, []).append(entry["id"])
    superseded = set(superseded_by)

    records: list[dict[str, Any]] = []
    candidate_dispositions = candidate_dispositions or {}

    for entry in entries:
        classification = classify_entry(entry)
        disposition = _disposition(entry, superseded, classification)
        record = {
            "id": entry["id"],
            "source_layer": "BANK",
            "title": entry.get("title") or derive_display_title(entry),
            "kind": entry["kind"],
            "scope": entry["scope"],
            "tags": entry.get("tags", []),
            "state": entry["state"],
            "disposition": disposition,
            "ordinary_recall": disposition in {"CURRENT_DURABLE", "PROVISIONAL/NEEDS_EVIDENCE"}
            and classification["durability"] not in {"EPHEMERAL", "HISTORICAL"}
            and classification["sensitivity"] != "EXCLUDE",
            "evidence": entry.get("evidence", []),
            "source_classes": _source_classes(entry.get("evidence", [])),
            "supersedes": entry.get("supersedes", []),
            "superseded_by": sorted(superseded_by.get(entry["id"], [])),
            "retrieval_value": (
                "CURRENT" if disposition == "CURRENT_DURABLE"
                else "REVIEW" if disposition == "PROVISIONAL/NEEDS_EVIDENCE"
                else "HISTORICAL"
            ),
            **_record_base(entry, classification),
        }
        records.append(record)

    for entry in candidate_entries or []:
        state = str(entry.get("state") or "PROVISIONAL")
        review = candidate_dispositions.get(entry["id"])
        classification = classify_entry(entry)
        disposition = (
            str(review["disposition"])
            if review is not None
            else "REJECTED" if state == "REJECTED"
            else "SENSITIVE_EXCLUDED" if classification["sensitivity"] == "EXCLUDE"
            else "PROVISIONAL/NEEDS_EVIDENCE"
        )
        source_class = str(entry.get("source_class") or "candidate").casefold()
        evidence = [str(item) for item in entry.get("evidence", [])]
        event_source = entry.get("source_timestamp") or entry.get("timestamp")
        event_match = _DATE_RE.search(str(event_source or ""))
        record = {
            "id": entry["id"],
            "source_layer": "CANDIDATE",
            "candidate_path": entry.get("_candidate_path"),
            "candidate_review_path": review.get("_review_path") if review else None,
            "candidate_review_reason": review.get("reason") if review else None,
            "candidate_review_evidence": list(review.get("evidence") or []) if review else [],
            "title": entry.get("title") or f"Candidate {entry['id']}",
            "kind": entry.get("kind", "lesson"),
            "scope": entry.get("scope", "global"),
            "tags": entry.get("tags", []),
            "state": state,
            "disposition": disposition,
            "ordinary_recall": False,
            "evidence": evidence,
            "source_classes": sorted(set(_source_classes(evidence) + [source_class])),
            "supersedes": entry.get("supersedes", []),
            "superseded_by": [],
            "retrieval_value": "REVIEW" if disposition == "PROVISIONAL/NEEDS_EVIDENCE" else "HISTORICAL",
            **_record_base(entry, classification),
        }
        record["event_date_hint"] = event_match.group(1) if event_match else None
        records.append(record)

    disposition_counts = Counter(record["disposition"] for record in records)
    for name in DISPOSITIONS:
        disposition_counts.setdefault(name, 0)

    review_queue: list[dict[str, Any]] = []
    ambiguous_records: list[dict[str, Any]] = []
    for record in records:
        # Historical/superseded/rejected records stay classified but are not active review work.
        if record["disposition"] not in {"CURRENT_DURABLE", "PROVISIONAL/NEEDS_EVIDENCE", "SENSITIVE_EXCLUDED"}:
            continue
        reasons = list(record.get("classification_review_reasons") or [])
        if record["disposition"] == "PROVISIONAL/NEEDS_EVIDENCE" and "claim_state_provisional" not in reasons:
            reasons.append("claim_state_provisional")
        if record["source_layer"] == "CANDIDATE" and not record.get("candidate_review_path"):
            reasons.append("candidate_missing_final_review")
        reasons = sorted(set(reasons))
        if reasons:
            item = {"id": record["id"], "source_layer": record["source_layer"], "reasons": reasons}
            review_queue.append(item)
            if any(reason in {"multiple_project_descriptors", "sensitivity_pattern_requires_review", "proven_record_classifies_as_hypothesis", "secret_like_value"} for reason in reasons):
                ambiguous_records.append(item)

    uncategorized = [
        record["id"] for record in records
        if record["semantic_category"] not in SEMANTIC_CATEGORIES
        or record["primary_domain"] not in DOMAINS
        or record["durability"] not in DURABILITIES
        or record["sensitivity"] not in SENSITIVITIES
    ]

    source_counter: Counter[str] = Counter()
    project_counter: Counter[str] = Counter()
    role_counter: Counter[str] = Counter()
    for record in records:
        source_counter.update(record["source_classes"] or ["none"])
        project_counter.update(record["projects"] or ["none"])
        role_counter.update(record["roles"] or ["none"])

    duplicate_groups = _duplicate_groups(entries)
    supersession_edges = [
        {"source": entry["id"], "target": old_id}
        for entry in entries for old_id in entry.get("supersedes", [])
    ]

    return {
        "schema_version": 2,
        "authority": "DERIVED_AUDIT_ONLY",
        "taxonomy": {
            "semantic_categories": list(SEMANTIC_CATEGORIES),
            "domains": list(DOMAINS),
            "durabilities": list(DURABILITIES),
            "sensitivities": list(SENSITIVITIES),
            "dispositions": list(DISPOSITIONS),
        },
        "notes": [
            "This report is mechanically derived from the append-only memory bank and is not a second recall authority.",
            "Classification is bounded and deterministic; ambiguous/sensitive/provisional records are surfaced in review_queue instead of silently promoted.",
            "A committed JSON report is a point-in-time evidence snapshot, not a perpetually current mirror; run this tool again for current state.",
            "event_date_hint is only the first YYYY-MM-DD found in the memory text, not an independently proven timestamp.",
            "Sensitive EXCLUDE records are excluded from current disposition; REVIEW is conservative triage and requires human/assistant review.",
        ],
        "total_records": len(records),
        "bank_records": len(entries),
        "candidate_only_records": len(candidate_entries or []),
        "counts": {
            "dispositions": dict(sorted(disposition_counts.items())),
            "states": dict(sorted(Counter(entry["state"] for entry in entries).items())),
            "kinds": dict(sorted(Counter(entry["kind"] for entry in entries).items())),
            "scopes": dict(sorted(Counter(entry["scope"] for entry in entries).items())),
            "semantic_categories": dict(sorted(Counter(record["semantic_category"] for record in records).items())),
            "domains": dict(sorted(Counter(record["primary_domain"] for record in records).items())),
            "projects": dict(sorted(project_counter.items())),
            "roles": dict(sorted(role_counter.items())),
            "durability": dict(sorted(Counter(record["durability"] for record in records).items())),
            "sensitivity": dict(sorted(Counter(record["sensitivity"] for record in records).items())),
            "source_classes": dict(sorted(source_counter.items())),
        },
        "duplicate_and_supersession": {
            "exact_duplicate_groups": duplicate_groups,
            "exact_duplicate_group_count": len(duplicate_groups),
            "supersession_edges": supersession_edges,
            "supersession_edge_count": len(supersession_edges),
        },
        "review_queue": review_queue,
        "ambiguous_records": ambiguous_records,
        "uncategorized": uncategorized,
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
    candidate_dispositions = _read_candidate_dispositions(root, {entry["id"] for entry in candidates})
    report = build_report(entries, candidates, candidate_dispositions)
    report["snapshot"] = build_snapshot_receipt(root, args.bank)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8", newline="\n")
    else:
        stream = getattr(__import__("sys").stdout, "buffer", None)
        if stream is None:
            print(json.dumps(report, ensure_ascii=True, indent=2))
        else:
            stream.write(payload.encode("utf-8", "backslashreplace"))
            stream.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
