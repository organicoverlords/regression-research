from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import argparse
import json
import os
import tempfile
import time
import uuid

DEFAULT_STORE = Path(os.environ.get(
    "YARD_INBOX_STORE",
    r"C:\Users\Lauri\Desktop\yard_recon\viewer\comments.json",
))
CLAIM_TTL_SECONDS = 20 * 60
LIVE_SCRIPT = Path(r"C:\Users\Lauri\Desktop\vault\tools\yard_inbox_bridge.py")


@contextmanager
def _file_lock(store: Path):
    """Cross-process lock compatible with yard-reconstruction viewer/comment_store.py."""
    lock_path = store.with_suffix(store.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _read_unlocked(store: Path) -> list[dict[str, Any]]:
    if not store.exists():
        return []
    raw = json.loads(store.read_text(encoding="utf-8") or "[]")
    if not isinstance(raw, list):
        raise ValueError("yard comments store must contain a JSON array")
    items: list[dict[str, Any]] = []
    for raw_item in raw:
        if not isinstance(raw_item, dict):
            continue
        item = dict(raw_item)
        item.setdefault("role", "human")
        item.setdefault("status", "unread" if item.get("role") == "human" else "posted")
        items.append(item)
    return items


def _write_unlocked(store: Path, items: list[dict[str, Any]]) -> None:
    store.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=store.name + ".", suffix=".tmp", dir=store.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(items, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, store)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _stamp(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _stale(item: dict[str, Any], now: datetime, ttl_seconds: int) -> bool:
    if item.get("status") != "processing":
        return False
    raw = str(item.get("claimed_at") or "").strip()
    if not raw:
        return True
    try:
        claimed_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return True
    if claimed_at.tzinfo is None:
        claimed_at = claimed_at.replace(tzinfo=timezone.utc)
    return (now.astimezone(timezone.utc) - claimed_at.astimezone(timezone.utc)).total_seconds() >= ttl_seconds


def peek_next(store_path: str | Path | None = None, *, now: datetime | None = None, ttl_seconds: int = CLAIM_TTL_SECONDS) -> dict[str, Any]:
    """Read the next eligible yard comment without taking ownership of it."""
    store = Path(store_path) if store_path is not None else DEFAULT_STORE
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    base = {
        "authority": "live_yard_comment_store",
        "store": str(store),
        "claim_semantics": "first_receiving_chat_atomic_claim",
        "claim_ttl_seconds": int(ttl_seconds),
    }
    if not store.exists():
        return {**base, "available": False, "status": "STORE_MISSING"}
    try:
        with _file_lock(store):
            items = _read_unlocked(store)
            eligible = [
                item for item in items
                if item.get("role") == "human"
                and (item.get("status") == "unread" or _stale(item, current, ttl_seconds))
            ]
            if not eligible:
                return {**base, "available": True, "status": "EMPTY", "pending_count": 0}
            item = eligible[0]
            preview = {
                "id": item.get("id"),
                "name": item.get("name"),
                "text_preview": str(item.get("text") or "")[:800],
                "ts": item.get("ts"),
            }
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {**base, "available": False, "status": "ERROR", "error": str(exc)[:240]}
    return {
        **base,
        "available": True,
        "status": "PENDING",
        "pending_count": len(eligible),
        "message_preview": preview,
        "instruction": "Before normal work, run claim_command. Only the chat that receives CLAIMED owns and handles the yard comment; EMPTY means another chat won.",
        "claim_command": f'python "{LIVE_SCRIPT}" --store "{store}" claim',
    }

def claim_next(
    store_path: str | Path | None = None,
    *,
    actor: str | None = None,
    now: datetime | None = None,
    ttl_seconds: int = CLAIM_TTL_SECONDS,
) -> dict[str, Any]:
    store = Path(store_path) if store_path is not None else DEFAULT_STORE
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    claim_actor = (str(actor).strip()[:120] if actor else "") or f"bootstrap:{os.getpid()}:{uuid.uuid4().hex[:12]}"
    base = {
        "authority": "live_yard_comment_store",
        "store": str(store),
        "claim_semantics": "first_bootstrap_atomic_claim",
        "claim_ttl_seconds": int(ttl_seconds),
    }
    if not store.exists():
        return {**base, "available": False, "status": "STORE_MISSING"}
    try:
        with _file_lock(store):
            items = _read_unlocked(store)
            chosen = next((
                item for item in items
                if item.get("role") == "human"
                and (item.get("status") == "unread" or _stale(item, current, ttl_seconds))
            ), None)
            if chosen is None:
                return {**base, "available": True, "status": "EMPTY"}
            chosen["role"] = "human"
            chosen["status"] = "processing"
            chosen["claimed_by"] = claim_actor
            chosen["claimed_at"] = _stamp(current)
            _write_unlocked(store, items)
            message = dict(chosen)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {**base, "available": False, "status": "ERROR", "error": str(exc)[:240]}
    message_id = str(message.get("id"))
    return {
        **base,
        "available": True,
        "status": "CLAIMED",
        "actor": claim_actor,
        "message": message,
        "instruction": "Handle this claimed yard comment before normal project work, then answer or release it through the yard inbox bridge.",
        "answer_command": f'python "{LIVE_SCRIPT}" --store "{store}" answer "{message_id}" --actor "{claim_actor}" --text <reply>',
        "release_command": f'python "{LIVE_SCRIPT}" --store "{store}" release "{message_id}" --actor "{claim_actor}"',
    }


def pending(store_path: str | Path | None = None) -> dict[str, Any]:
    store = Path(store_path) if store_path is not None else DEFAULT_STORE
    if not store.exists():
        return {"available": False, "status": "STORE_MISSING", "store": str(store), "messages": []}
    with _file_lock(store):
        items = _read_unlocked(store)
    messages = [item for item in items if item.get("role") == "human" and item.get("status") == "unread"]
    return {"available": True, "status": "OK", "store": str(store), "messages": messages[:20]}


def answer(message_id: str, actor: str, text: str, *, name: str = "Assistant", store_path: str | Path | None = None) -> dict[str, Any]:
    store = Path(store_path) if store_path is not None else DEFAULT_STORE
    reply_text = str(text).strip()[:4000]
    if not reply_text:
        raise ValueError("answer text is required")
    with _file_lock(store):
        items = _read_unlocked(store)
        source = next((item for item in items if str(item.get("id")) == str(message_id)), None)
        if source is None:
            raise KeyError(f"unknown message id: {message_id}")
        if source.get("status") != "processing" or source.get("claimed_by") != actor:
            raise ValueError("message is not claimed by this actor")
        ts = _stamp()
        reply = {
            "id": f"msg_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}",
            "role": "assistant",
            "name": str(name).strip()[:60] or "Assistant",
            "text": reply_text,
            "reply_to": source.get("id"),
            "view": source.get("view"),
            "status": "posted",
            "ts": ts,
        }
        source["status"] = "answered"
        source["answered_at"] = ts
        source.pop("claimed_by", None)
        source.pop("claimed_at", None)
        items.append(reply)
        _write_unlocked(store, items)
    return {"ok": True, "reply": reply, "store": str(store)}


def release(message_id: str, actor: str, *, store_path: str | Path | None = None) -> dict[str, Any]:
    store = Path(store_path) if store_path is not None else DEFAULT_STORE
    with _file_lock(store):
        items = _read_unlocked(store)
        source = next((item for item in items if str(item.get("id")) == str(message_id)), None)
        if source is None:
            raise KeyError(f"unknown message id: {message_id}")
        if source.get("status") != "processing" or source.get("claimed_by") != actor:
            raise ValueError("message is not claimed by this actor")
        source["status"] = "unread"
        source.pop("claimed_by", None)
        source.pop("claimed_at", None)
        _write_unlocked(store, items)
    return {"ok": True, "message": source, "store": str(store)}


def main() -> int:
    parser = argparse.ArgumentParser(description="MCP/bootstrap-facing yard comment inbox bridge")
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    sub = parser.add_subparsers(dest="action", required=True)
    claim = sub.add_parser("claim")
    claim.add_argument("--actor")
    sub.add_parser("pending")
    ans = sub.add_parser("answer")
    ans.add_argument("message_id")
    ans.add_argument("--actor", required=True)
    ans.add_argument("--text", required=True)
    ans.add_argument("--name", default="Assistant")
    rel = sub.add_parser("release")
    rel.add_argument("message_id")
    rel.add_argument("--actor", required=True)
    args = parser.parse_args()
    try:
        if args.action == "claim":
            value = claim_next(args.store, actor=args.actor)
        elif args.action == "pending":
            value = pending(args.store)
        elif args.action == "answer":
            value = answer(args.message_id, args.actor, args.text, name=args.name, store_path=args.store)
        else:
            value = release(args.message_id, args.actor, store_path=args.store)
        print(json.dumps(value, ensure_ascii=True, separators=(",", ":")))
        return 0 if value.get("status") != "ERROR" else 2
    except (KeyError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "status": "ERROR", "error": str(exc)}, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
