from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA = "vault.memory.recent-titles.v1"
DEFAULT_FILENAME = "recent-titles.json"


def default_local_bank_path() -> Path:
    override = os.environ.get("VAULT_MEMORY_LOCAL_BANK")
    if override:
        return Path(override).expanduser()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "VaultMemory" / "memory-bank.local.jsonl"
    return Path.home() / ".local" / "state" / "vault-memory" / "memory-bank.local.jsonl"


def default_projection_path(local_bank_path: Path | None = None) -> Path:
    bank = Path(local_bank_path) if local_bank_path is not None else default_local_bank_path()
    return bank.with_name(DEFAULT_FILENAME)


def _fingerprint(path: Path) -> dict[str, Any]:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return {"exists": False}
    return {"exists": True, "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def source_fingerprints(seed_path: Path, overlay_path: Path) -> dict[str, dict[str, Any]]:
    return {"seed": _fingerprint(seed_path), "overlay": _fingerprint(overlay_path)}


def write_recent_projection(*, seed_path: Path, overlay_path: Path, recent: list[dict[str, Any]], projection_path: Path | None = None) -> Path:
    destination = projection_path or default_projection_path(overlay_path)
    payload = {
        "schema": SCHEMA,
        "generated_at": datetime.now().astimezone().isoformat(),
        "authority": "DERIVED_FROM_EFFECTIVE_LOCAL_MEMORY",
        "source_fingerprints": source_fingerprints(seed_path, overlay_path),
        "recent": recent,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=destination.name + ".", suffix=".tmp", dir=destination.parent)
    os.close(fd)
    temporary = Path(raw)
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def read_current_projection(*, seed_path: Path, overlay_path: Path, projection_path: Path | None = None) -> dict[str, Any] | None:
    source = projection_path or default_projection_path(overlay_path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        return None
    if payload.get("source_fingerprints") != source_fingerprints(seed_path, overlay_path):
        return None
    if not isinstance(payload.get("recent"), list):
        return None
    return payload
