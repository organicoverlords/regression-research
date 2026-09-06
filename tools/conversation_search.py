from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

REPO = Path(__file__).resolve().parents[1]
DEFAULT_VAULT = Path(r"C:\Users\Lauri\Desktop\vault") if __import__("os").name == "nt" else REPO
DEFAULT_VAULT = Path(__import__("os").environ.get("MEMORY_VAULT_ROOT", str(DEFAULT_VAULT)))
DEFAULT_DB = DEFAULT_VAULT / ".state" / "conversation-search" / "conversations.sqlite3"
DEFAULT_CORPUS_ROOT = DEFAULT_VAULT / "memory" / "conversations"
KNOWN_ROOT_NAMES = ("ChatPortEvidence", "ChatGPTLocalExporter")
DISCOVERY_RE = re.compile(r"(chatgpt|chatport|openai|conversation|export)", re.I)
MAX_LIMIT = 20


@dataclass(frozen=True)
class SourceItem:
    locator: str
    path: Path
    member: str | None
    size: int
    mtime_ns: int


def _source_id(locator: str) -> str:
    return "src-" + hashlib.sha256(locator.encode("utf-8", "surrogatepass")).hexdigest()[:20]


def _message_uid(conversation_id: str, message_id: str, role: str, text: str) -> str:
    raw = "\x1f".join((conversation_id, message_id, role, text)).encode("utf-8", "surrogatepass")
    return "msg-" + hashlib.sha256(raw).hexdigest()[:24]


def _utc_text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        text = str(value).strip()
        return text or None
    try:
        return datetime.fromtimestamp(number, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except (OverflowError, OSError, ValueError):
        return str(value)


def _text_part(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "\n".join(x for x in (_text_part(item) for item in value) if x)
    if isinstance(value, dict):
        for key in ("text", "value", "caption", "content"):
            if key in value:
                text = _text_part(value[key])
                if text:
                    return text
    return ""


def message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, dict):
        if "parts" in content:
            text = _text_part(content.get("parts"))
            if text:
                return text
        for key in ("text", "result", "content"):
            if key in content:
                text = _text_part(content.get(key))
                if text:
                    return text
    for key in ("text", "content"):
        if key in message and not isinstance(message.get(key), dict):
            text = _text_part(message.get(key))
            if text:
                return text
    return ""


def _role(message: dict[str, Any]) -> str:
    author = message.get("author")
    if isinstance(author, dict) and author.get("role"):
        return str(author["role"])
    return str(message.get("role") or message.get("sender") or "unknown")


def iter_conversations(obj: Any) -> Iterator[dict[str, Any]]:
    if isinstance(obj, list):
        for item in obj:
            yield from iter_conversations(item)
        return
    if not isinstance(obj, dict):
        return
    if isinstance(obj.get("mapping"), dict) or isinstance(obj.get("messages"), list):
        yield obj
        return
    if isinstance(obj.get("conversation"), dict):
        yield from iter_conversations(obj["conversation"])
    if isinstance(obj.get("conversations"), list):
        yield from iter_conversations(obj["conversations"])
    if not any(key in obj for key in ("conversation", "conversations")):
        for value in obj.values():
            if isinstance(value, dict) and (isinstance(value.get("mapping"), dict) or isinstance(value.get("messages"), list)):
                yield value


def _active_mapping_path(conv: dict[str, Any], mapping: dict[str, Any]) -> list[tuple[str, dict[str, Any]]] | None:
    """Return the active ``current_node`` ancestry when the export exposes it.

    ChatGPT mappings may retain retried/branched nodes that are mutually exclusive.
    Chronology must therefore follow the selected branch instead of timestamp-sorting
    every mapping node together. Older/partial exports without a usable
    ``current_node`` keep the legacy all-node fallback for discoverability.
    """
    current = conv.get("current_node")
    if not isinstance(current, str) or current not in mapping:
        return None

    path: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    node_key: str | None = current
    while node_key:
        if node_key in seen:
            raise ValueError(f"conversation mapping contains a parent cycle at {node_key}")
        seen.add(node_key)
        node = mapping.get(node_key)
        if not isinstance(node, dict):
            raise ValueError(f"conversation current_node ancestry references missing node {node_key}")
        path.append((node_key, node))
        parent = node.get("parent")
        node_key = parent if isinstance(parent, str) and parent else None
    path.reverse()
    return path


def iter_messages(conv: dict[str, Any], locator: str) -> Iterator[dict[str, Any]]:
    mapping = conv.get("mapping")
    if isinstance(mapping, dict):
        active_path = _active_mapping_path(conv, mapping)
        if active_path is not None:
            message_rows = [
                (node_key, node["message"])
                for node_key, node in active_path
                if isinstance(node.get("message"), dict)
            ]
        else:
            rows: list[tuple[float, str, dict[str, Any]]] = []
            for node_key, node in mapping.items():
                if not isinstance(node, dict) or not isinstance(node.get("message"), dict):
                    continue
                message = node["message"]
                try:
                    when = float(message.get("create_time")) if message.get("create_time") is not None else float("inf")
                except (TypeError, ValueError):
                    when = float("inf")
                rows.append((when, str(node_key), message))
            rows.sort(key=lambda item: (item[0], item[1]))
            message_rows = [(node_key, message) for _, node_key, message in rows]

        order_index = 0
        for node_key, message in message_rows:
            text = message_text(message).strip()
            if text:
                yield {
                    "message_id": str(message.get("id") or node_key),
                    "role": _role(message),
                    "created_at": _utc_text(message.get("create_time")),
                    "order_index": order_index,
                    "text": text,
                }
                order_index += 1
        return
    messages = conv.get("messages")
    if isinstance(messages, list):
        for order_index, message in enumerate(messages):
            if not isinstance(message, dict):
                continue
            text = message_text(message).strip()
            if text:
                yield {
                    "message_id": str(message.get("id") or f"{locator}:{order_index}"),
                    "role": _role(message),
                    "created_at": _utc_text(message.get("create_time") or message.get("timestamp")),
                    "order_index": order_index,
                    "text": text,
                }


def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS sources(
          source_id TEXT PRIMARY KEY, locator TEXT NOT NULL UNIQUE, size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
          content_sha256 TEXT, status TEXT NOT NULL, conversations INTEGER NOT NULL DEFAULT 0,
          messages INTEGER NOT NULL DEFAULT 0, indexed_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS conversations(
          conversation_id TEXT PRIMARY KEY, title TEXT, create_time TEXT, update_time TEXT);
        CREATE TABLE IF NOT EXISTS source_conversations(
          source_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE, conversation_id TEXT NOT NULL,
          PRIMARY KEY(source_id, conversation_id));
        CREATE TABLE IF NOT EXISTS messages(
          rowid INTEGER PRIMARY KEY, message_uid TEXT NOT NULL UNIQUE, conversation_id TEXT NOT NULL,
          message_id TEXT NOT NULL, role TEXT NOT NULL, created_at TEXT, order_index INTEGER NOT NULL, text TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS source_messages(
          source_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE, message_uid TEXT NOT NULL,
          PRIMARY KEY(source_id, message_uid));
        CREATE VIRTUAL TABLE IF NOT EXISTS message_fts USING fts5(
          message_uid UNINDEXED, conversation_id UNINDEXED, role UNINDEXED, text, tokenize='unicode61');
        CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
          INSERT INTO message_fts(rowid,message_uid,conversation_id,role,text)
          VALUES(new.rowid,new.message_uid,new.conversation_id,new.role,new.text);
        END;
        CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
          DELETE FROM message_fts WHERE rowid=old.rowid;
        END;
        CREATE INDEX IF NOT EXISTS messages_conv_order ON messages(conversation_id,order_index,created_at);
        CREATE INDEX IF NOT EXISTS source_messages_uid ON source_messages(message_uid);
        """
    )


def _zip_relevant(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as zf:
            names = [name.casefold() for name in zf.namelist()]
    except (OSError, zipfile.BadZipFile):
        return False
    return any(
        name.endswith(("conversations.json", "conversation.json", ".jsonl"))
        or ("conversation" in name and name.endswith(".json"))
        for name in names
    )


def discover_roots(downloads: Path | None = None) -> list[Path]:
    downloads = downloads or Path.home() / "Downloads"
    roots: list[Path] = []
    for name in KNOWN_ROOT_NAMES:
        candidate = downloads / name
        if candidate.exists():
            roots.append(candidate)
    if downloads.is_dir():
        try:
            children = list(downloads.iterdir())
        except OSError:
            children = []
        for child in children:
            if child in roots:
                continue
            if child.is_dir() and DISCOVERY_RE.search(child.name):
                roots.append(child)
            elif child.is_file() and child.suffix.casefold() == ".zip" and (DISCOVERY_RE.search(child.name) or _zip_relevant(child)):
                roots.append(child)
    seen: set[str] = set()
    out: list[Path] = []
    for root in roots:
        key = str(root.resolve(strict=False)).casefold()
        if key not in seen:
            seen.add(key)
            out.append(root)
    return out


def iter_source_items(root: Path) -> Iterator[SourceItem]:
    if root.is_file():
        paths: Iterable[Path] = [root]
    elif root.is_dir():
        paths = (p for p in root.rglob("*") if p.is_file())
    else:
        return
    for path in paths:
        suffix = path.suffix.casefold()
        if suffix not in {".json", ".jsonl", ".zip"}:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        if suffix == ".zip":
            try:
                with zipfile.ZipFile(path) as zf:
                    for info in zf.infolist():
                        if info.is_dir() or Path(info.filename).suffix.casefold() not in {".json", ".jsonl"}:
                            continue
                        yield SourceItem(
                            f"{path.resolve(strict=False)}!{info.filename}", path, info.filename,
                            int(info.file_size), int(stat.st_mtime_ns)
                        )
            except (OSError, zipfile.BadZipFile):
                continue
        else:
            yield SourceItem(str(path.resolve(strict=False)), path, None, int(stat.st_size), int(stat.st_mtime_ns))


def _read_source(item: SourceItem) -> bytes:
    if item.member is None:
        return item.path.read_bytes()
    with zipfile.ZipFile(item.path) as zf:
        return zf.read(item.member)


def _objects(data: bytes, suffix: str) -> Iterator[Any]:
    text = data.decode("utf-8-sig")
    if suffix == ".jsonl":
        for line in text.splitlines():
            if line.strip():
                yield json.loads(line)
    else:
        yield json.loads(text)


def _conv_id(conv: dict[str, Any], fallback: str) -> str:
    value = conv.get("id") or conv.get("conversation_id") or conv.get("conversationId")
    return str(value) if value else "conv-" + hashlib.sha256(fallback.encode()).hexdigest()[:20]


def _upsert_conversation(conn: sqlite3.Connection, conv: dict[str, Any], conv_id: str) -> None:
    title = str(conv["title"]) if conv.get("title") is not None else None
    create_time = _utc_text(conv.get("create_time"))
    update_time = _utc_text(conv.get("update_time"))
    conn.execute(
        """INSERT INTO conversations(conversation_id,title,create_time,update_time) VALUES(?,?,?,?)
        ON CONFLICT(conversation_id) DO UPDATE SET
        title=COALESCE(excluded.title,conversations.title),
        create_time=COALESCE(conversations.create_time,excluded.create_time),
        update_time=CASE WHEN conversations.update_time IS NULL THEN excluded.update_time
                         WHEN excluded.update_time IS NULL THEN conversations.update_time
                         WHEN excluded.update_time>conversations.update_time THEN excluded.update_time
                         ELSE conversations.update_time END""",
        (conv_id, title, create_time, update_time),
    )


def ingest_source(conn: sqlite3.Connection, item: SourceItem, force: bool = False) -> dict[str, Any]:
    source_id = _source_id(item.locator)
    current = conn.execute("SELECT size,mtime_ns,status FROM sources WHERE source_id=?", (source_id,)).fetchone()
    if current and not force and int(current[0]) == item.size and int(current[1]) == item.mtime_ns and current[2] in {"ok", "no-conversations"}:
        return {"status": "skipped", "source_id": source_id, "locator": item.locator}
    now = datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")
    conn.execute(
        """INSERT INTO sources(source_id,locator,size,mtime_ns,status,indexed_at)
        VALUES(?,?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET locator=excluded.locator,size=excluded.size,
        mtime_ns=excluded.mtime_ns,status=excluded.status,indexed_at=excluded.indexed_at""",
        (source_id, item.locator, item.size, item.mtime_ns, "reading", now),
    )
    conn.execute("DELETE FROM source_messages WHERE source_id=?", (source_id,))
    conn.execute("DELETE FROM source_conversations WHERE source_id=?", (source_id,))
    try:
        data = _read_source(item)
        digest = hashlib.sha256(data).hexdigest()
        suffix = Path(item.member or item.path.name).suffix.casefold()
        conv_count = msg_count = 0
        for obj in _objects(data, suffix):
            for index, conv in enumerate(iter_conversations(obj)):
                conv_id = _conv_id(conv, f"{item.locator}:{index}")
                _upsert_conversation(conn, conv, conv_id)
                conn.execute("INSERT OR IGNORE INTO source_conversations VALUES(?,?)", (source_id, conv_id))
                conv_count += 1
                for msg in iter_messages(conv, item.locator):
                    uid = _message_uid(conv_id, msg["message_id"], msg["role"], msg["text"])
                    conn.execute(
                        """INSERT OR IGNORE INTO messages(message_uid,conversation_id,message_id,role,created_at,order_index,text)
                        VALUES(?,?,?,?,?,?,?)""",
                        (uid, conv_id, msg["message_id"], msg["role"], msg["created_at"], msg["order_index"], msg["text"]),
                    )
                    conn.execute("INSERT OR IGNORE INTO source_messages VALUES(?,?)", (source_id, uid))
                    msg_count += 1
        status = "ok" if conv_count else "no-conversations"
        conn.execute(
            "UPDATE sources SET content_sha256=?,status=?,conversations=?,messages=?,indexed_at=? WHERE source_id=?",
            (digest, status, conv_count, msg_count, now, source_id),
        )
        conn.execute("DELETE FROM messages WHERE message_uid NOT IN (SELECT message_uid FROM source_messages)")
        conn.execute("DELETE FROM conversations WHERE conversation_id NOT IN (SELECT conversation_id FROM source_conversations)")
        return {"status": status, "source_id": source_id, "locator": item.locator, "conversations": conv_count, "messages": msg_count}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        conn.execute("UPDATE sources SET status=?,indexed_at=? WHERE source_id=?", (f"error:{type(exc).__name__}", now, source_id))
        return {"status": "error", "source_id": source_id, "locator": item.locator, "error": str(exc)[:300]}


def coverage_report(conn: sqlite3.Connection) -> dict[str, Any]:
    roles = {role: count for role, count in conn.execute("SELECT role,COUNT(*) FROM messages GROUP BY role ORDER BY role")}
    message_first, message_last, non_wall_clock_messages = conn.execute(
        """
        SELECT
          MIN(CASE WHEN created_at>='2000-01-01T00:00:00Z' THEN created_at END),
          MAX(CASE WHEN created_at>='2000-01-01T00:00:00Z' THEN created_at END),
          SUM(CASE WHEN created_at IS NULL OR created_at<'2000-01-01T00:00:00Z' THEN 1 ELSE 0 END)
        FROM messages
        """
    ).fetchone()
    return {
        "sources": conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
        "sources_with_conversations": conn.execute("SELECT COUNT(*) FROM sources WHERE status='ok'").fetchone()[0],
        "sources_ignored": conn.execute("SELECT COUNT(*) FROM sources WHERE status='no-conversations'").fetchone()[0],
        "sources_unresolved": conn.execute("SELECT COUNT(*) FROM sources WHERE status NOT IN ('ok','no-conversations')").fetchone()[0],
        "conversations": conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0],
        "messages": conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
        "roles": roles,
        "message_first": message_first,
        "message_last": message_last,
        "non_wall_clock_messages": int(non_wall_clock_messages or 0),
    }


def index_roots(db: Path, roots: Iterable[Path], force: bool = False) -> dict[str, Any]:
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    counts: Counter[str] = Counter()
    errors = []
    seen = 0
    try:
        _init_db(conn)
        for root in roots:
            for item in iter_source_items(root):
                seen += 1
                result = ingest_source(conn, item, force=force)
                counts[result["status"]] += 1
                if result["status"] == "error":
                    errors.append(result)
                conn.commit()
        return {
            "status": "PROVEN" if not errors else "NOT_PROVEN",
            "roots": [str(r) for r in roots],
            "source_items_seen": seen,
            "source_results": dict(counts),
            "errors": errors[:20],
            "coverage": coverage_report(conn),
            "db": str(db),
        }
    finally:
        conn.close()


def rebuild_index(db: Path, roots: Iterable[Path]) -> dict[str, Any]:
    """Atomically replace the disposable search index from the selected preserved roots."""
    roots = list(roots)
    db.parent.mkdir(parents=True, exist_ok=True)
    temp = db.with_name(db.name + f".rebuild-{os.getpid()}")
    for path in (temp, Path(str(temp) + "-wal"), Path(str(temp) + "-shm")):
        path.unlink(missing_ok=True)
    result = index_roots(temp, roots, force=True)
    if result["status"] != "PROVEN":
        return result
    for sidecar in (Path(str(temp) + "-wal"), Path(str(temp) + "-shm")):
        if sidecar.exists() and sidecar.stat().st_size:
            raise RuntimeError(f"temporary SQLite sidecar did not checkpoint: {sidecar}")
        sidecar.unlink(missing_ok=True)
    for sidecar in (Path(str(db) + "-wal"), Path(str(db) + "-shm")):
        sidecar.unlink(missing_ok=True)
    os.replace(temp, db)
    result["db"] = str(db)
    result["rebuild"] = "atomic-fresh"
    return result


def _fts_query(query: str) -> str:
    tokens = re.findall(r"[\w-]+", query, flags=re.UNICODE)
    if not tokens:
        raise ValueError("query has no searchable tokens")
    return " AND ".join('"' + token.replace('"', '""') + '"' for token in tokens)


def _clip(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _neighbor(conn: sqlite3.Connection, conv_id: str, order_index: int, before: bool) -> str | None:
    op, ordering = ("<", "DESC") if before else (">", "ASC")
    row = conn.execute(
        f"SELECT role,text FROM messages WHERE conversation_id=? AND order_index{op}? ORDER BY order_index {ordering} LIMIT 1",
        (conv_id, order_index),
    ).fetchone()
    return f"{row[0]}: {row[1]}" if row else None


def search_db(db: Path, query: str, literal: bool = False, limit: int = 8, context_chars: int = 420) -> list[dict[str, Any]]:
    if not db.is_file():
        raise FileNotFoundError(f"conversation index not found: {db}")
    limit = max(1, min(MAX_LIMIT, int(limit)))
    context_chars = max(80, min(2000, int(context_chars)))
    conn = sqlite3.connect(db)
    try:
        _init_db(conn)
        select = """SELECT m.message_uid,m.conversation_id,m.message_id,m.role,m.created_at,m.order_index,m.text,
        c.title,c.create_time,c.update_time FROM {table} {alias} {join} LEFT JOIN conversations c ON c.conversation_id=m.conversation_id
        WHERE {where} ORDER BY {order} LIMIT ?"""
        if literal:
            sql = select.format(table="messages", alias="m", join="", where="instr(lower(m.text),lower(?))>0", order="COALESCE(m.created_at,'') DESC,m.rowid DESC")
            rows = conn.execute(sql, (query, limit)).fetchall()
        else:
            sql = select.format(table="message_fts", alias="f", join="JOIN messages m ON m.rowid=f.rowid", where="message_fts MATCH ?", order="bm25(message_fts),COALESCE(m.created_at,'') DESC")
            rows = conn.execute(sql, (_fts_query(query), limit)).fetchall()
        out = []
        for uid, conv_id, message_id, role, created_at, order_index, text, title, conv_create, conv_update in rows:
            sources = [
                r[0]
                for r in conn.execute(
                    "SELECT s.locator FROM sources s JOIN source_messages sm ON sm.source_id=s.source_id WHERE sm.message_uid=? ORDER BY s.locator",
                    (uid,),
                )
            ]
            out.append(
                {
                    "conversation_id": conv_id,
                    "title": title,
                    "conversation_create_time": conv_create,
                    "conversation_update_time": conv_update,
                    "message_id": message_id,
                    "role": role,
                    "created_at": created_at,
                    "match": _clip(text, context_chars),
                    "context_before": _clip(_neighbor(conn, conv_id, int(order_index), True), context_chars),
                    "context_after": _clip(_neighbor(conn, conv_id, int(order_index), False), context_chars),
                    "sources": sources,
                }
            )
        return out
    finally:
        conn.close()


def _match_sql(query: str, literal: bool) -> tuple[str, str, str, str, str]:
    if literal:
        return "messages", "m", "", "instr(lower(m.text),lower(?))>0", query
    return "message_fts", "f", "JOIN messages m ON m.rowid=f.rowid", "message_fts MATCH ?", _fts_query(query)


def _populate_query_matches(conn: sqlite3.Connection, query: str, literal: bool) -> None:
    conn.execute("DROP TABLE IF EXISTS temp.query_matches")
    conn.execute("CREATE TEMP TABLE query_matches(message_rowid INTEGER PRIMARY KEY)")
    table, alias, join, where, param = _match_sql(query, literal)
    conn.execute(
        f"INSERT INTO query_matches(message_rowid) SELECT m.rowid FROM {table} {alias} {join} WHERE {where}",
        (param,),
    )


def _representative_rows(conn: sqlite3.Connection) -> list[tuple[Any, ...]]:
    sql = """
        WITH chosen AS (
          SELECT m.conversation_id,MAX(q.message_rowid) AS message_rowid
          FROM query_matches q
          JOIN messages m ON m.rowid=q.message_rowid
          GROUP BY m.conversation_id
        )
        SELECT m.message_uid,m.conversation_id,m.message_id,m.role,m.created_at,m.order_index,m.text,
               c.title,c.create_time,c.update_time
        FROM chosen x
        JOIN messages m ON m.rowid=x.message_rowid
        LEFT JOIN conversations c ON c.conversation_id=m.conversation_id
        ORDER BY COALESCE(m.created_at,'') ASC,m.conversation_id ASC
    """
    return conn.execute(sql).fetchall()


def _evenly_spaced(rows: list[tuple[Any, ...]], limit: int) -> list[tuple[Any, ...]]:
    if len(rows) <= limit:
        return list(reversed(rows))
    if limit == 1:
        return [rows[-1]]
    positions = [round(index * (len(rows) - 1) / (limit - 1)) for index in range(limit)]
    sampled = [rows[index] for index in positions]
    sampled.reverse()
    return sampled


def _hit_from_row(conn: sqlite3.Connection, row: tuple[Any, ...], context_chars: int) -> dict[str, Any]:
    uid, conv_id, message_id, role, created_at, order_index, text, title, conv_create, conv_update = row
    sources = [
        source[0]
        for source in conn.execute(
            "SELECT s.locator FROM sources s JOIN source_messages sm ON sm.source_id=s.source_id WHERE sm.message_uid=? ORDER BY s.locator",
            (uid,),
        )
    ]
    return {
        "conversation_id": conv_id,
        "title": title,
        "conversation_create_time": conv_create,
        "conversation_update_time": conv_update,
        "message_id": message_id,
        "role": role,
        "created_at": created_at,
        "match": _clip(text, context_chars),
        "context_before": _clip(_neighbor(conn, conv_id, int(order_index), True), context_chars),
        "context_after": _clip(_neighbor(conn, conv_id, int(order_index), False), context_chars),
        "sources": sources,
    }


def search_report(db: Path, query: str, literal: bool = False, limit: int = 8, context_chars: int = 420) -> dict[str, Any]:
    """Return full-corpus match aggregates plus a bounded, conversation-diverse sample."""
    if not db.is_file():
        raise FileNotFoundError(f"conversation index not found: {db}")
    limit = max(1, min(MAX_LIMIT, int(limit)))
    context_chars = max(80, min(2000, int(context_chars)))
    conn = sqlite3.connect(db)
    try:
        _init_db(conn)
        _populate_query_matches(conn, query, literal)
        base = "FROM query_matches q JOIN messages m ON m.rowid=q.message_rowid"
        matching_messages, matching_conversations, first_match, last_match, non_wall_clock_messages = conn.execute(
            f"""
            SELECT COUNT(*),COUNT(DISTINCT m.conversation_id),
                   MIN(CASE WHEN m.created_at>='2000-01-01T00:00:00Z' THEN m.created_at END),
                   MAX(CASE WHEN m.created_at>='2000-01-01T00:00:00Z' THEN m.created_at END),
                   SUM(CASE WHEN m.created_at IS NULL OR m.created_at<'2000-01-01T00:00:00Z' THEN 1 ELSE 0 END)
            {base}
            """
        ).fetchone()
        roles = {
            role: count
            for role, count in conn.execute(
                f"SELECT m.role,COUNT(*) {base} GROUP BY m.role ORDER BY m.role"
            )
        }
        top_conversations = [
            {
                "conversation_id": conv_id,
                "title": title,
                "matches": count,
                "first_match": first_seen,
                "last_match": last_seen,
            }
            for conv_id, title, count, first_seen, last_seen in conn.execute(
                f"""
                SELECT m.conversation_id,c.title,COUNT(*) AS match_count,
                       MIN(CASE WHEN m.created_at>='2000-01-01T00:00:00Z' THEN m.created_at END),
                       MAX(CASE WHEN m.created_at>='2000-01-01T00:00:00Z' THEN m.created_at END)
                FROM query_matches q
                JOIN messages m ON m.rowid=q.message_rowid
                LEFT JOIN conversations c ON c.conversation_id=m.conversation_id
                GROUP BY m.conversation_id,c.title
                ORDER BY match_count DESC,
                         COALESCE(MAX(CASE WHEN m.created_at>='2000-01-01T00:00:00Z' THEN m.created_at END),'') DESC,
                         m.conversation_id ASC
                LIMIT 5
                """
            )
        ]
        rows = _representative_rows(conn)
        sampled_rows = _evenly_spaced(rows, limit)
        hits = [_hit_from_row(conn, row, context_chars) for row in sampled_rows]
        return {
            "summary": {
                "matching_messages": int(matching_messages),
                "matching_conversations": int(matching_conversations),
                "first_match": first_match,
                "last_match": last_match,
                "non_wall_clock_messages": int(non_wall_clock_messages or 0),
                "roles": roles,
                "top_conversations": top_conversations,
                "sample_strategy": "one-match-per-conversation, evenly spaced across matched-conversation time range",
                "sampled_conversations": len(hits),
            },
            "hits": hits,
        }
    finally:
        conn.close()


def _print(value: Any) -> None:
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    stream = getattr(sys.stdout, "buffer", None)
    if stream is None:
        print(json.dumps(value, ensure_ascii=True, indent=2))
        return
    stream.write(payload.encode("utf-8", "backslashreplace"))
    stream.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description="Full-text indexing and search for preserved ChatGPT conversations.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    sub = parser.add_subparsers(dest="command", required=True)
    discover = sub.add_parser("discover", help="List candidate exports under Downloads without indexing them.")
    discover.add_argument("--downloads", type=Path, default=Path.home() / "Downloads")
    index = sub.add_parser("index", help="Index explicit roots or the canonical Vault corpus.")
    index.add_argument(
        "--root",
        type=Path,
        action="append",
        default=[],
        help="Source root to index; repeatable. Defaults to the canonical Vault corpus.",
    )
    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--literal", action="store_true")
    search.add_argument("--limit", type=int, default=8)
    search.add_argument("--context-chars", type=int, default=420)
    sub.add_parser("coverage")
    args = parser.parse_args()
    try:
        if args.command == "discover":
            _print({"roots": [str(p) for p in discover_roots(args.downloads)]})
            return 0
        if args.command == "index":
            roots = args.root or [DEFAULT_CORPUS_ROOT]
            if not all(root.exists() for root in roots):
                _print({"status": "NOT_PROVEN", "error": "conversation corpus root is missing", "roots": [str(root) for root in roots]})
                return 2
            _print(rebuild_index(args.db, roots))
            return 0
        if args.command == "search":
            report = search_report(args.db, args.query, args.literal, args.limit, args.context_chars)
            _print({"query": args.query, "literal": args.literal, **report})
            return 0
        if args.command == "coverage":
            if not args.db.is_file():
                _print({"status": "NOT_PROVEN", "error": f"conversation index not found: {args.db}"})
                return 2
            conn = sqlite3.connect(args.db)
            try:
                _init_db(conn)
                _print({"status": "PROVEN", "db": str(args.db), **coverage_report(conn)})
            finally:
                conn.close()
            return 0
    except (OSError, sqlite3.Error, ValueError, FileNotFoundError) as exc:
        _print({"status": "REJECTED", "error": str(exc)})
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
