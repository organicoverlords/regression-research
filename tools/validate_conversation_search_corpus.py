from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from conversation_search import coverage_report, search_db

OLD_TOKEN = "chatportevidence"
OLD_CAPTURE_END = "2026-08-22T23:12:19Z"


def _is_old(locator: str) -> bool:
    return OLD_TOKEN in locator.casefold()


def _phrase_candidates(text: str):
    clean = re.sub(r"\s+", " ", text).strip()
    for match in re.finditer(r"[\w][\w .,:;!?()'\"/\\-]{23,79}", clean, flags=re.UNICODE):
        phrase = match.group(0).strip(" .,:;!?()'\"")
        if 24 <= len(phrase) <= 80:
            yield phrase


def _cohort_counts(conn: sqlite3.Connection) -> tuple[int, int, int, int, str | None]:
    rows = list(conn.execute("SELECT source_id,locator FROM sources WHERE status='ok'"))
    old_ids = [sid for sid, locator in rows if _is_old(locator)]
    new_ids = [sid for sid, locator in rows if not _is_old(locator)]
    old_messages = (
        conn.execute(
            "SELECT COUNT(DISTINCT message_uid) FROM source_messages WHERE source_id IN (%s)"
            % ",".join("?" * len(old_ids)),
            old_ids,
        ).fetchone()[0]
        if old_ids
        else 0
    )
    new_messages = (
        conn.execute(
            "SELECT COUNT(DISTINCT message_uid) FROM source_messages WHERE source_id IN (%s)"
            % ",".join("?" * len(new_ids)),
            new_ids,
        ).fetchone()[0]
        if new_ids
        else 0
    )
    new_message_last = (
        conn.execute(
            """SELECT MAX(m.created_at) FROM messages m
            JOIN source_messages sm ON sm.message_uid=m.message_uid
            WHERE sm.source_id IN (%s) AND m.created_at IS NOT NULL"""
            % ",".join("?" * len(new_ids)),
            new_ids,
        ).fetchone()[0]
        if new_ids
        else None
    )
    return len(old_ids), len(new_ids), old_messages, new_messages, new_message_last


def _candidate_rows(conn: sqlite3.Connection, want_old: bool):
    having = (
        "MIN(CASE WHEN instr(lower(s.locator),?)>0 THEN 1 ELSE 0 END)=1"
        if want_old
        else "MAX(CASE WHEN instr(lower(s.locator),?)>0 THEN 1 ELSE 0 END)=0"
    )
    return conn.execute(
        f"""SELECT m.message_uid,m.text FROM messages m
        JOIN source_messages sm ON sm.message_uid=m.message_uid
        JOIN sources s ON s.source_id=sm.source_id AND s.status='ok'
        GROUP BY m.message_uid,m.text HAVING {having}
        ORDER BY LENGTH(m.text) DESC LIMIT 300""",
        (OLD_TOKEN,),
    )


def _exists_in_opposite_cohort(conn: sqlite3.Connection, phrase: str, want_old: bool) -> bool:
    having = (
        "MAX(CASE WHEN instr(lower(s.locator),?)=0 THEN 1 ELSE 0 END)=1"
        if want_old
        else "MAX(CASE WHEN instr(lower(s.locator),?)>0 THEN 1 ELSE 0 END)=1"
    )
    row = conn.execute(
        f"""SELECT 1 FROM messages m
        JOIN source_messages sm ON sm.message_uid=m.message_uid
        JOIN sources s ON s.source_id=sm.source_id AND s.status='ok'
        WHERE instr(lower(m.text),lower(?))>0
        GROUP BY m.message_uid HAVING {having} LIMIT 1""",
        (phrase, OLD_TOKEN),
    ).fetchone()
    return row is not None


def _probe(conn: sqlite3.Connection, db: Path, want_old: bool) -> dict[str, Any]:
    phrases_checked = 0
    for _uid, text in _candidate_rows(conn, want_old):
        for phrase in _phrase_candidates(text):
            phrases_checked += 1
            if phrases_checked > 200:
                break
            if _exists_in_opposite_cohort(conn, phrase, want_old):
                continue
            hits = search_db(db, phrase, literal=True, limit=20, context_chars=120)
            for hit in hits:
                hit_sources = hit.get("sources") or []
                if want_old and hit_sources and all(_is_old(locator) for locator in hit_sources):
                    return {"status": "PROVEN", "length": len(phrase), "hit_count": len(hits), "phrases_checked": phrases_checked}
                if not want_old and hit_sources and all(not _is_old(locator) for locator in hit_sources):
                    return {"status": "PROVEN", "length": len(phrase), "hit_count": len(hits), "phrases_checked": phrases_checked}
        if phrases_checked > 200:
            break
    return {"status": "NOT_PROVEN", "reason": "no cohort-unique searchable phrase found", "phrases_checked": phrases_checked}


def validate(db: Path) -> dict[str, Any]:
    conn = sqlite3.connect(db)
    try:
        coverage = coverage_report(conn)
        old_sources, new_sources, old_messages, new_messages, new_message_last = _cohort_counts(conn)
        result = {
            "coverage": coverage,
            "old_sources": old_sources,
            "new_sources": new_sources,
            "old_messages": old_messages,
            "new_messages": new_messages,
            "new_message_last": new_message_last,
            "old_capture_end": OLD_CAPTURE_END,
        }
        if not old_sources or not old_messages:
            return {"status": "NOT_PROVEN", "reason": "old ChatPort corpus not indexed", **result}
        if not new_sources or not new_messages:
            return {"status": "NOT_PROVEN", "reason": "newer non-ChatPort downloads not indexed", **result}
        if not new_message_last or new_message_last <= OLD_CAPTURE_END:
            return {"status": "NOT_PROVEN", "reason": "non-ChatPort corpus has no message newer than old ChatPort capture", **result}
        result["old_probe"] = _probe(conn, db, True)
        result["new_probe"] = _probe(conn, db, False)
        result["status"] = (
            "PROVEN"
            if result["old_probe"]["status"] == result["new_probe"]["status"] == "PROVEN"
            else "NOT_PROVEN"
        )
        return result
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate old/new downloaded conversation search without printing conversation text.")
    parser.add_argument("--db", type=Path, required=True)
    args = parser.parse_args()
    result = validate(args.db)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PROVEN" else 2


if __name__ == "__main__":
    raise SystemExit(main())
