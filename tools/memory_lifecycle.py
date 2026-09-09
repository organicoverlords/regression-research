from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any


_EXCESS_FRACTION_RE = re.compile(r"(\.\d{6})\d+(?=(?:[+-]\d{2}:\d{2})?$)")


def parse_iso_datetime(value: Any) -> datetime:
    normalized = str(value).strip().replace("Z", "+00:00")
    normalized = _EXCESS_FRACTION_RE.sub(r"\1", normalized)
    return datetime.fromisoformat(normalized)


def parse_expiry(entry: dict[str, Any]) -> datetime | None:
    raw = entry.get("expires_at")
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    parsed = parse_iso_datetime(value)
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
