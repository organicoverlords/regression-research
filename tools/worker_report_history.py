from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _fields(raw: bytes) -> dict[str, str]:
    text = raw.decode("utf-8", errors="replace")
    result: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        if key and key.replace("_", "").isalnum():
            result[key] = value.strip()
    return result


def archive_finalized_report(report: Path, history_root: Path) -> dict[str, Any]:
    raw = report.read_bytes()
    fields = _fields(raw)
    state = fields.get("state", "").upper()
    if state not in {"DONE", "BLOCKED"}:
        raise ValueError(f"report is not finalized: state={state or 'MISSING'}")
    worker = fields.get("worker") or report.stem
    digest = hashlib.sha256(raw).hexdigest()
    target_dir = history_root / worker
    target = target_dir / f"{digest}.md"
    if target.exists():
        if target.read_bytes() != raw:
            raise RuntimeError(f"history hash collision at {target}")
        return {"ok": True, "archived": False, "deduplicated": True, "sha256": digest, "path": str(target)}
    target_dir.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    return {"ok": True, "archived": True, "deduplicated": False, "sha256": digest, "path": str(target)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preserve finalized worker-report snapshots before replacement.")
    parser.add_argument("archive", choices=["archive"])
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--history-root", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    history_root = args.history_root or args.report.parent / "history"
    try:
        result = archive_finalized_report(args.report, history_root)
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())