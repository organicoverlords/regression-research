from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from conversation_search import coverage_report, search_db

OLD_MARKER = "\\chatportevidence\\"


def _is_old(locator: str) -> bool:
    return OLD_MARKER in locator.casefold().replace("/", "\\")


def _phrase_candidates(text: str):
    clean = re.sub(r"\s+", " ", text).strip()
    for match in re.finditer(r"[\w][\w .,:;!?()'\"/\\-]{23,79}", clean, flags=re.UNICODE):
        phrase = match.group(0).strip(" .,:;!?()'\"")
        if 24 <= len(phrase) <= 80:
            yield phrase


def _cohort_counts(conn: sqlite3.Connection) -> tuple[int, int, int, int]:
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
    return len(old_ids), len(new_ids), old_messages, new_messages


def _probe(conn: sqlite3.Connection, db: Path, want_old: bool) -> dict[str, Any]:
    rows = conn.execute(
        """SELECT m.message_uid,m.text FROM messages m
        JOIN source_messages sm ON sm.message_uid=m.message_uid
        JOIN sources s ON s.source_id=sm.source_id AND s.status='ok'
        GROUP BY m.message_uid,m.text ORDER BY LENGTH(m.text) DESC LIMIT 5000"""
    )
    for uid, text in rows:
        locators = [
            r[0]
            for r in conn.execute(
                "SELECT s.locator FROM sources s JOIN source_messages sm ON sm.source_id=s.source_id WHERE sm.message_uid=?",
                (uid,),
            )
        ]
        cohort_old = bool(locators) and all(_is_old(locator) for locator in locators)
        cohort_new = bool(locators) and all(not _is_old(locator) for locator in locators)
        if want_old and not cohort_old:
            continue
        if not want_old and not cohort_new:
            continue
        for phrase in _phrase_candidates(text):
            opposite = False
            matching = conn.execute(
                "SELECT message_uid FROM messages WHERE instr(lower(text),lower(?))>0", (phrase,)
            )
            for (other_uid,) in matching:
                other_locators = [
                    r[0]
                    for r in conn.execute(
                        "SELECT s.locator FROM sources s JOIN source_messages sm ON sm.source_id=s.source_id WHERE sm.message_uid=?",
                        (other_uid,),
                    )
                ]
                if want_old and any(not _is_old(locator) for locator in other_locators):
                    opposite = True
                    break
                if not want_old and any(_is_old(locator) for locator in other_locators):
                    opposite = True
                    break
            if opposite:
                continue
            hits = search_db(db, phrase, literal=True, limit=20, context_chars=120)
            for hit in hits:
                hit_sources = hit.get("sources") or []
                if want_old and hit_sources and all(_is_old(locator) for locator in hit_sources):
                    return {"status": "PROVEN", "length": len(phrase), "hit_count": len(hits)}
                if not want_old and hit_sources and all(not _is_old(locator) for locator in hit_sources):
                    return {"status": "PROVEN", "length": len(phrase), "hit_count": len(hits)}
    return {"status": "NOT_PROVEN", "reason": "no cohort-unique searchable phrase found"}


def validate(db: Path) -> dict[str, Any]:
    conn = sqlite3.connect(db)
    try:
        coverage = coverage_report(conn)
        old_sources, new_sources, old_messages, new_messages = _cohort_counts(conn)
        result = {
            "coverage": coverage,
            "old_sources": old_sources,
            "new_sources": new_sources,
            "old_messages": old_messages,
            "new_messages": new_messages,
        }
        if not old_sources or not old_messages:
            return {"status": "NOT_PROVEN", "reason": "old ChatPort corpus not indexed", **result}
        if not new_sources or not new_messages:
            return {"status": "NOT_PROVEN", "reason": "newer non-ChatPort downloads not indexed", **result}
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
