from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from tools.cleanup_converger import converge, hygiene_snapshot
except ModuleNotFoundError:
    from cleanup_converger import converge, hygiene_snapshot

ISSUE_URL = "https://github.com/organicoverlords/regression-research/issues/900"
STATE_DIR = Path(os.path.expandvars(r"%LOCALAPPDATA%")) / "VaultWorktreeHygiene"
STATE_PATH = STATE_DIR / "latest.json"
MAX_AUXILIARY = 12
MAX_DIRTY = 6
TARGET_REPOS = {"Vault", "Agents"}


def classify_health(snapshot: dict) -> str:
    if snapshot["auxiliary_count"] > MAX_AUXILIARY or snapshot["dirty_count"] > MAX_DIRTY:
        return "degraded"
    return "healthy"


def write_state(payload: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, STATE_PATH)

def main() -> int:
    now = datetime.now(timezone.utc).isoformat()
    try:
        cleanup = converge(
            apply=False,
            safe_auto=True,
            repo_names=TARGET_REPOS,
            max_rounds=4,
            stable_rounds=1,
            settle_seconds=1.0,
            window_seconds=600,
            actor="ChatGPT:scheduled-worktree-hygiene",
        )
        snapshot = hygiene_snapshot(600, repo_names=TARGET_REPOS)
        status = classify_health(snapshot)
        payload = {
            "schema": "worktree-hygiene.v1",
            "at": now,
            "status": status,
            "issue": ISSUE_URL,
            "thresholds": {"max_auxiliary": MAX_AUXILIARY, "max_dirty": MAX_DIRTY},
            "cleanup": cleanup,
            "snapshot": snapshot,
        }
        write_state(payload)
        return 0 if status == "healthy" else 3
    except Exception as exc:
        write_state({"schema": "worktree-hygiene.v1", "at": now, "status": "error", "issue": ISSUE_URL, "error": f"{type(exc).__name__}: {exc}"})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
