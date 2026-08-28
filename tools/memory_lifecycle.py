from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def parse_expiry(entry: dict[str, Any]) -> datetime | None:
    raw = entry.get("expires_at")
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("expires_at must include a timezone offset")
    return parsed


def is_expired(entry: dict[str, Any], *, now: datetime | None = None) -> bool:
    expiry = parse_expiry(entry)
    if expiry is None:
        return False
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return expiry <= current
