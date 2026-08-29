from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

try:
    from .conversation_search import DEFAULT_DB
except ImportError:
    from conversation_search import DEFAULT_DB

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO / ".state" / "user-message-catalog" / "user-messages.jsonl"
WALL_CLOCK_FLOOR = "2000-01-01T00:00:00Z"

SIGNALS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("persistent_scope", re.compile(r"\b(for all future(?: responses)?|from now on|going forward|global (?:instruction|rule)|custom instructions?|all future responses)\b", re.I)),
    ("memory_request", re.compile(r"\b(remember|save|store|add|put|write|update|overwrite)\b.{0,60}\b(memory|memories|instruction|rule|preference)\b|\b(memory|memories)\b.{0,60}\b(remember|save|store|add|put|write|update|overwrite)\b", re.I | re.S)),
    ("directive", re.compile(r"\b(do not|don't|dont|never|always|must|should|i want you to|i need you to|you need to|you must|please)\b", re.I)),
    ("behavior_target", re.compile(r"\b(answer|response|reply|think|reason|research|verify|check|tool|tools|work|task|stop|continue|report|ask|supervis|context|memory|guess|claim|proof|evidence|implement|finish|complete)\w*\b", re.I)),
    ("correction", re.compile(r"^\s*(no\b|wrong\b|stop\b)|\b(that(?:'s| is) wrong|you(?:'re| are) wrong|you keep|why are you|stop doing|do not do that|don't do that)\b", re.I)),
    ("evidence", re.compile(r"\b(proof|prove|verify|verified|evidence|claim|guess|assumption|hypothesis|source of truth|current state|live)\b", re.I)),
    ("completion", re.compile(r"\b(finish|complete|completion|done|keep working|continue|do not stop|don't stop|dont stop|actual outcome|real path)\b", re.I)),
    ("autonomy", re.compile(r"\b(own(?:ership)?|autonom\w*|supervis\w*|babysit|micromanag\w*|do it yourself|do the work|hand work back)\b", re.I)),
    ("anti_canned", re.compile(r"\b(canned|generic|shallow|template|templated|first plausible|simple answer|easy path|toy solution|placeholder)\b", re.I)),
    ("continuity", re.compile(r"\b(context|continue from|do not restart|don't restart|dont restart|prior decision|earlier decision|whole task|active task)\b", re.I)),
)


def _wall_clock(value: Any) -> bool:
    text = str(value or "")
    return bool(text and text >= WALL_CLOCK_FLOOR)


def classify_user_text(text: str) -> dict[str, Any]:
    normalized = " ".join(str(text or "").split())
    signals = [name for name, pattern in SIGNALS if pattern.search(normalized)]
    present = set(signals)
    if "persistent_scope" in present or "memory_request" in present:
        if "behavior_target" in present or "directive" in present:
            tier = "PERSISTENT_RULE_CANDIDATE"
        else:
            tier = "PERSISTENT_CONTEXT_CANDIDATE"
    elif "directive" in present and "behavior_target" in present:
        tier = "BEHAVIOR_RULE_CANDIDATE"
    elif "correction" in present and "behavior_target" in present:
        tier = "BEHAVIOR_CORRECTION_CANDIDATE"
    else:
        tier = "OTHER"
    return {"signals": signals, "candidate_tier": tier}


def iter_user_messages(db: Path) -> Iterable[dict[str, Any]]:
    if not db.is_file():
        raise FileNotFoundError(f"conversation search DB not found: {db}")
    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(
            """
            SELECT m.message_uid,m.conversation_id,m.message_id,m.created_at,m.order_index,m.text,
                   COALESCE(c.title,''),COALESCE(GROUP_CONCAT(DISTINCT s.locator),'')
            FROM messages m
            LEFT JOIN conversations c ON c.conversation_id=m.conversation_id
            LEFT JOIN source_messages sm ON sm.message_uid=m.message_uid
            LEFT JOIN sources s ON s.source_id=sm.source_id
            WHERE m.role='user'
            GROUP BY m.message_uid,m.conversation_id,m.message_id,m.created_at,m.order_index,m.text,c.title
            ORDER BY CASE WHEN m.created_at IS NULL OR m.created_at < ? THEN 1 ELSE 0 END,
                     COALESCE(m.created_at,''),m.conversation_id,m.order_index,m.message_uid
            """,
            (WALL_CLOCK_FLOOR,),
        )
        for uid, conv_id, message_id, created_at, order_index, text, title, locator_blob in rows:
            text = str(text or "")
            classification = classify_user_text(text)
            locators = sorted({item for item in str(locator_blob or "").split(",") if item})
            yield {
                "schema_version": 1,
                "message_uid": uid,
                "conversation_id": conv_id,
                "message_id": message_id,
                "created_at": created_at,
                "wall_clock": _wall_clock(created_at),
                "order_index": int(order_index),
                "conversation_title": title,
                "text": text,
                "text_sha256": hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest(),
                "text_chars": len(text),
                "source_locators": locators,
                **classification,
            }
    finally:
        conn.close()


def catalog_manifest(records: Iterable[dict[str, Any]], *, catalog_sha256: str | None = None) -> dict[str, Any]:
    items = list(records)
    tiers = Counter(item["candidate_tier"] for item in items)
    signals = Counter(signal for item in items for signal in item["signals"])
    wall = [str(item["created_at"]) for item in items if item["wall_clock"]]
    return {
        "schema_version": 1,
        "source": "preserved conversation-search DB; user-role messages only",
        "authority": "FORENSIC_CATALOG_ONLY",
        "user_messages": len(items),
        "wall_clock_messages": len(wall),
        "non_wall_clock_messages": len(items) - len(wall),
        "wall_clock_first": min(wall) if wall else None,
        "wall_clock_last": max(wall) if wall else None,
        "candidate_tiers": dict(sorted(tiers.items())),
        "signals": dict(sorted(signals.items())),
        "catalog_sha256": catalog_sha256,
    }


def build_catalog(db: Path, output: Path) -> dict[str, Any]:
    records = list(iter_user_messages(db))
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    digest = hashlib.sha256()
    with tmp.open("wb") as handle:
        for record in records:
            line = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
            handle.write(line)
            digest.update(line)
    tmp.replace(output)
    manifest = catalog_manifest(records, catalog_sha256=digest.hexdigest())
    manifest_path = output.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {**manifest, "catalog": str(output), "manifest": str(manifest_path)}


def candidate_records(db: Path, *, tier: str | None = None, signal: str | None = None, query: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    needle = str(query or "").casefold().strip()
    selected: list[dict[str, Any]] = []
    for record in iter_user_messages(db):
        if tier and record["candidate_tier"] != tier:
            continue
        if signal and signal not in record["signals"]:
            continue
        if needle and needle not in record["text"].casefold():
            continue
        selected.append(record)
    selected.sort(key=lambda item: (str(item.get("created_at") or ""), item["conversation_id"], item["order_index"], item["message_uid"]), reverse=True)
    return selected[: max(0, int(limit))]


def _bounded(record: dict[str, Any], chars: int = 700) -> dict[str, Any]:
    out = dict(record)
    text = " ".join(str(out.get("text") or "").split())
    if len(text) > chars:
        text = text[: max(0, chars - 3)].rstrip() + "..."
    out["text"] = text
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic catalog of preserved user-authored conversation messages.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="Rebuild the private local JSONL catalog from the preserved search DB.")
    build.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    sub.add_parser("summary", help="Report deterministic user-message and rule-candidate coverage without writing files.")
    candidates = sub.add_parser("candidates", help="Show bounded deterministic candidate records.")
    candidates.add_argument("--tier", choices=("PERSISTENT_RULE_CANDIDATE", "PERSISTENT_CONTEXT_CANDIDATE", "BEHAVIOR_RULE_CANDIDATE", "BEHAVIOR_CORRECTION_CANDIDATE", "OTHER"))
    candidates.add_argument("--signal", choices=tuple(name for name, _ in SIGNALS))
    candidates.add_argument("--query")
    candidates.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    if args.command == "build":
        result = build_catalog(args.db, args.output)
    elif args.command == "summary":
        result = catalog_manifest(iter_user_messages(args.db))
    else:
        result = {"records": [_bounded(item) for item in candidate_records(args.db, tier=args.tier, signal=args.signal, query=args.query, limit=args.limit)]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
