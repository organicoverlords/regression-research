from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FORMS = ("slopwall", "slop wall")
CONTEXT_TURNS = 4
MAX_CONTEXT_CHARS = 800


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _message_text(message: dict[str, Any]) -> str:
    parts = (message.get("content") or {}).get("parts") or []
    return "\n".join(part for part in parts if isinstance(part, str)).strip()


def _clip(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_CONTEXT_CHARS:
        return text, False
    return text[:MAX_CONTEXT_CHARS], True


def _iso_utc(epoch: float | int | None) -> str | None:
    if not epoch:
        return None
    return datetime.fromtimestamp(float(epoch), timezone.utc).isoformat().replace("+00:00", "Z")


def _context_row(row: tuple[float, str, str, str]) -> dict[str, Any]:
    epoch, message_id, role, text = row
    clipped, truncated = _clip(text)
    return {
        "message_id": message_id,
        "role": role,
        "timestamp": _iso_utc(epoch),
        "text": clipped,
        "text_truncated": truncated,
    }


def discover(root: Path, *, source_root_label: str = "ChatPortEvidence/raw") -> dict[str, Any]:
    root = root.resolve()
    files_scanned = 0
    bad_json = 0
    unique_message_ids: set[str] = set()
    hits: dict[str, dict[str, Any]] = {}

    for path in sorted(root.glob("*/*.json")):
        files_scanned += 1
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            bad_json += 1
            continue

        rel = path.relative_to(root).as_posix()
        source = {
            "path": f"{source_root_label.rstrip('/')}/{rel}",
            "sha256": _sha256(path),
        }
        conversation_id = data.get("conversation_id")
        title = data.get("title")
        rows: list[tuple[float, str, str, str]] = []
        seen_in_file: set[str] = set()
        for node in (data.get("mapping") or {}).values():
            message = (node or {}).get("message")
            if not isinstance(message, dict):
                continue
            message_id = message.get("id") or (node or {}).get("id")
            if not isinstance(message_id, str) or not message_id or message_id in seen_in_file:
                continue
            seen_in_file.add(message_id)
            unique_message_ids.add(message_id)
            role = str((message.get("author") or {}).get("role") or "")
            if role == "system":
                continue
            text = _message_text(message)
            epoch = float(message.get("create_time") or 0)
            if text or role == "tool":
                rows.append((epoch, message_id, role, text))
        rows.sort(key=lambda item: (item[0], item[1]))
        position = {row[1]: i for i, row in enumerate(rows)}

        for epoch, message_id, role, text in rows:
            if role != "user":
                continue
            lowered = text.casefold()
            counts = {form: lowered.count(form) for form in FORMS}
            if not any(counts.values()):
                continue
            idx = position[message_id]
            before = rows[max(0, idx - CONTEXT_TURNS):idx]
            after = rows[idx + 1:idx + 1 + CONTEXT_TURNS]
            candidate = hits.setdefault(
                message_id,
                {
                    "message_id": message_id,
                    "conversation_id": conversation_id,
                    "conversation_title": title,
                    "timestamp": _iso_utc(epoch),
                    "raw_user_text": text,
                    "matched_forms": counts,
                    "sources": [],
                    "context_before": [],
                    "context_after": [],
                    "_context_size": -1,
                    "_text_variants": set(),
                },
            )
            candidate["_text_variants"].add(text)
            if source not in candidate["sources"]:
                candidate["sources"].append(source)
            context_size = len(before) + len(after)
            if context_size > candidate["_context_size"]:
                candidate["_context_size"] = context_size
                candidate["conversation_id"] = conversation_id
                candidate["conversation_title"] = title
                candidate["timestamp"] = _iso_utc(epoch)
                candidate["raw_user_text"] = text
                candidate["matched_forms"] = counts
                candidate["context_before"] = [_context_row(row) for row in before]
                candidate["context_after"] = [_context_row(row) for row in after]

    records: list[dict[str, Any]] = []
    form_totals: Counter[str] = Counter()
    for message_id, candidate in hits.items():
        for form, count in candidate["matched_forms"].items():
            form_totals[form] += count
        candidate["sources"].sort(key=lambda item: item["path"])
        candidate["source_alias_count"] = len(candidate["sources"])
        candidate["text_variant_count"] = len(candidate.pop("_text_variants"))
        candidate.pop("_context_size", None)
        candidate["occurrence_id"] = "raw-" + hashlib.sha256(message_id.encode("utf-8")).hexdigest()[:20]
        candidate["review_state"] = "PENDING_CANONICAL_DEDUPE_AND_SCORING"
        records.append(candidate)
    records.sort(key=lambda row: ((row.get("timestamp") or ""), row["message_id"]))

    return {
        "schema_version": 1,
        "study_issue": 89,
        "authority": "RAW_DISCOVERY_ONLY",
        "notes": [
            "This layer binds literal raw-export hits and provenance aliases; it does not replace the canonical scored event index.",
            "Distinct raw messages are deduplicated by ChatGPT message_id across repeated exports.",
            "Four bounded non-system messages before and after are retained when available; long context text is clipped to 800 characters.",
            "PENDING_CANONICAL_DEDUPE_AND_SCORING means role, phenotype, confidence, and severity still require evidence review before canonical promotion.",
        ],
        "literal_forms": list(FORMS),
        "summary": {
            "files_scanned": files_scanned,
            "bad_json_files": bad_json,
            "unique_message_ids_scanned": len(unique_message_ids),
            "unique_hit_messages": len(records),
            "literal_occurrences": {form: form_totals.get(form, 0) for form in FORMS},
            "source_aliases": sum(row["source_alias_count"] for row in records),
        },
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover literal slopwall/slop wall messages in raw ChatPort conversation exports.")
    parser.add_argument("--root", type=Path, required=True, help="ChatPortEvidence/raw directory")
    parser.add_argument("--source-root-label", default="ChatPortEvidence/raw")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = json.dumps(discover(args.root, source_root_label=args.source_root_label), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8", newline="\n")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
