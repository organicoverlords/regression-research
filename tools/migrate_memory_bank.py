from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from tools.memory_bank import append_entry, load_bank, load_source_registry, validate_entry
except ModuleNotFoundError:
    from memory_bank import append_entry, load_bank, load_source_registry, validate_entry


def _semantic_key(entry: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        entry["kind"].casefold(),
        entry["scope"].casefold(),
        " ".join(entry["text"].split()).casefold(),
        entry["state"],
    )


def source_class(entry: dict[str, Any], registry: dict[str, Any]) -> tuple[str | None, int]:
    """Best source class name and rank for an entry, from its evidence prefixes."""
    classes = registry.get("classes") or {}
    best_name: str | None = None
    best_rank = 0
    for evidence in entry.get("evidence", []):
        for source in registry.get("sources", []):
            if any(evidence.startswith(prefix) for prefix in source.get("match_prefixes", [])):
                rank = int(classes.get(source.get("class"), 0))
                if rank > best_rank:
                    best_name, best_rank = source.get("class"), rank
    return best_name, best_rank


def _audit(audit: list[dict[str, Any]] | None, **record: Any) -> None:
    if audit is not None:
        audit.append(record)


def _resolve_supersessions(entries: list[dict[str, Any]],
                           assertions: dict[str, list[tuple[str, str | None, int]]],
                           known: dict[str, dict[str, Any]],
                           registry: dict[str, Any], audit: list[dict[str, Any]] | None) -> None:
    """Strip supersessions asserted by a lower-authority source than their target.

    Recall hides any entry named in another entry's `supersedes`, so an unchecked
    supersession lets a RECOVERY_ONLY claim silently remove canonical policy from
    ordinary results. Authority is compared before the claim is honoured.

    Each assertion is judged at the authority of the candidate that actually made it,
    captured before duplicate collapse. Merging evidence across duplicates legitimately
    raises an entry's rank for recall, but must not retroactively license a supersession
    that a lower-authority candidate asserted.
    """
    for entry in entries:
        kept: list[str] = []
        for target_id, name, rank in assertions.get(entry["id"], []):
            if target_id in kept:
                continue
            target = known.get(target_id)
            if target is None:
                kept.append(target_id)
                _audit(audit, candidate=entry["id"], action="supersession_unverified",
                       target=target_id, source_class=name, target_class=None,
                       reason="supersession target is not in this batch or the existing bank")
                continue
            target_name, target_rank = source_class(target, registry)
            if rank >= target_rank:
                kept.append(target_id)
                _audit(audit, candidate=entry["id"], action="supersession_accepted",
                       target=target_id, source_class=name, target_class=target_name,
                       reason="claiming source ranks at or above the superseded entry")
                continue
            _audit(audit, candidate=entry["id"], action="supersession_rejected",
                   target=target_id, source_class=name, target_class=target_name,
                   reason="lower-authority source may not supersede a higher-authority entry")
        entry["supersedes"] = kept


def migrate_candidates(candidates: list[dict[str, Any]], *,
                       registry: dict[str, Any] | None = None,
                       existing: list[dict[str, Any]] | None = None,
                       audit: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    registry = registry if registry is not None else load_source_registry()
    merged: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str, str]] = []
    assertions: dict[str, list[tuple[str, str | None, int]]] = {}
    for candidate in candidates:
        validate_entry(candidate)
        key = _semantic_key(candidate)
        cls_name, cls_rank = source_class(candidate, registry)
        holder = merged[key]["id"] if key in merged else candidate["id"]
        for target_id in dict.fromkeys(candidate["supersedes"]):
            assertions.setdefault(holder, []).append((target_id, cls_name, cls_rank))
        if key not in merged:
            merged[key] = {k: v for k, v in candidate.items() if not k.startswith("source_")}
            merged[key]["tags"] = list(dict.fromkeys(candidate["tags"]))
            merged[key]["evidence"] = list(dict.fromkeys(candidate["evidence"]))
            merged[key]["supersedes"] = []
            order.append(key)
            _audit(audit, candidate=candidate["id"], action="kept", target=None,
                   source_class=source_class(candidate, registry)[0], target_class=None,
                   reason="first candidate with this kind/scope/text/state")
            continue
        current = merged[key]
        current["tags"] = list(dict.fromkeys(current["tags"] + candidate["tags"]))
        current["evidence"] = list(dict.fromkeys(current["evidence"] + candidate["evidence"]))
        _audit(audit, candidate=candidate["id"], action="collapsed_duplicate",
               target=current["id"], source_class=source_class(candidate, registry)[0],
               target_class=source_class(current, registry)[0],
               reason="identical kind/scope/text/state; evidence merged into the kept entry")
    entries = [merged[key] for key in order]
    known = {entry["id"]: entry for entry in (existing or [])}
    known.update({entry["id"]: entry for entry in entries})
    _resolve_supersessions(entries, assertions, known, registry, audit)
    return entries


def read_candidates(path: Path) -> list[dict[str, Any]]:
    return load_bank(path)


def write_bank(entries: list[dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("", encoding="utf-8")
    for entry in entries:
        append_entry(output, entry)


def write_audit(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Curate prepared memory-bank candidates")
    parser.add_argument("candidates", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--existing", type=Path, help="bank whose ids may be superseded")
    parser.add_argument("--audit", type=Path, help="write the promotion/rejection record here")
    args = parser.parse_args()
    audit: list[dict[str, Any]] = []
    existing = load_bank(args.existing) if args.existing else None
    entries = migrate_candidates(read_candidates(args.candidates), existing=existing, audit=audit)
    write_bank(entries, args.output)
    if args.audit:
        write_audit(audit, args.audit)
    counts: dict[str, int] = {}
    for record in audit:
        counts[record["action"]] = counts.get(record["action"], 0) + 1
    print(json.dumps({"status": "PROVEN", "entries": len(entries),
                      "output": str(args.output), "audit": counts}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
