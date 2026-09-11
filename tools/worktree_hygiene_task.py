from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

try:
    from tools.worktree_hygiene_guard import ensure_canonical_main, quarantine_pressure
except ModuleNotFoundError:
    from worktree_hygiene_guard import ensure_canonical_main, quarantine_pressure

try:
    from tools.cleanup_converger import converge, hygiene_snapshot
except ModuleNotFoundError:
    from cleanup_converger import converge, hygiene_snapshot

ISSUE_URL = "https://github.com/organicoverlords/regression-research/issues/1005"
STATE_DIR = Path(os.path.expandvars(r"%LOCALAPPDATA%")) / "VaultWorktreeHygiene"
STATE_PATH = STATE_DIR / "latest.json"
MAX_AUXILIARY = 12
MAX_DIRTY = 6
SOFT_FREE_GIB = 60.0
TARGET_FREE_GIB = 75.0
HARD_RESERVE_GIB = 25.0
TARGET_REPOS = {"Vault", "Agents"}
PRESSURE_REPOS = {"P3", "Vault", "Agents"}
VAULT_ROOT = Path(r"C:\Users\Lauri\Desktop\vault")
AGENTS_ROOT = Path(r"C:\Users\Lauri\.agents")


def classify_health(snapshot: dict, canonical_roots: dict[str, dict] | None = None) -> str:
    if canonical_roots and any(row.get("status") not in {"current", "restored"} for row in canonical_roots.values()):
        return "degraded"
    if snapshot["auxiliary_count"] > MAX_AUXILIARY or snapshot["dirty_count"] > MAX_DIRTY:
        return "degraded"
    return "healthy"


def pressure_active(free_gib: float, was_active: bool) -> bool:
    threshold = TARGET_FREE_GIB if was_active else SOFT_FREE_GIB
    return free_gib < threshold


def disk_free_gib(path: Path = VAULT_ROOT) -> float:
    return shutil.disk_usage(path).free / (1024**3)


def read_previous_pressure() -> bool:
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return bool(payload.get("capacity", {}).get("pressure_active"))
    except (OSError, json.JSONDecodeError, TypeError):
        return False


def capacity_tick(
    *,
    previous_pressure: bool,
    probe: Callable[[], float] = disk_free_gib,
    reclaimer: Callable[[], dict] | None = None,
) -> tuple[dict, dict | None]:
    before = float(probe())
    active_before = pressure_active(before, previous_pressure)
    cleanup = None
    attempted = False
    if active_before:
        attempted = True
        if reclaimer is None:
            reclaimer = lambda: converge(
                apply=False,
                safe_auto=False,
                pressure_auto=True,
                repo_names=PRESSURE_REPOS,
                max_rounds=1,
                stable_rounds=1,
                settle_seconds=0.0,
                window_seconds=600,
                actor="ChatGPT:scheduled-capacity-hygiene",
            )
        cleanup = reclaimer()
    after = float(probe()) if attempted else before
    active_after = pressure_active(after, active_before)
    return {
        "free_before_gib": round(before, 1),
        "free_after_gib": round(after, 1),
        "soft_free_gib": SOFT_FREE_GIB,
        "target_free_gib": TARGET_FREE_GIB,
        "hard_reserve_gib": HARD_RESERVE_GIB,
        "pressure_before": active_before,
        "pressure_active": active_after,
        "reclaim_attempted": attempted,
        "reclaim_passes": 1 if attempted else 0,
    }, cleanup


def write_state(payload: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, STATE_PATH)


def main() -> int:
    now = datetime.now(timezone.utc).isoformat()
    try:
        canonical_roots = {
            "Vault": ensure_canonical_main(VAULT_ROOT, 600),
            "Agents": ensure_canonical_main(AGENTS_ROOT, 600),
        }
        capacity, pressure_cleanup = capacity_tick(previous_pressure=read_previous_pressure())
        if pressure_cleanup is None:
            cleanup = converge(
                apply=False,
                safe_auto=True,
                pressure_auto=False,
                repo_names=TARGET_REPOS,
                max_rounds=4,
                stable_rounds=1,
                settle_seconds=1.0,
                window_seconds=600,
                actor="ChatGPT:scheduled-worktree-hygiene",
            )
        else:
            cleanup = pressure_cleanup
        quarantine = [
            quarantine_pressure("Vault", VAULT_ROOT, "organicoverlords/regression-research:git-worktree-metadata", max_dirty=MAX_DIRTY),
            quarantine_pressure("Agents", AGENTS_ROOT, "organicoverlords/agents:git-worktree-metadata", max_dirty=MAX_DIRTY),
        ]
        snapshot = hygiene_snapshot(600, repo_names=TARGET_REPOS)
        status = classify_health(snapshot, canonical_roots)
        payload = {
            "schema": "worktree-hygiene.v2",
            "at": now,
            "status": status,
            "issue": ISSUE_URL,
            "thresholds": {"max_auxiliary": MAX_AUXILIARY, "max_dirty": MAX_DIRTY},
            "canonical_roots": canonical_roots,
            "capacity": capacity,
            "cleanup": cleanup,
            "quarantine": quarantine,
            "snapshot": snapshot,
        }
        write_state(payload)
        # Degraded hygiene is reported in state, not converted into a scheduler
        # failure/restart signal. Only an execution error is nonzero.
        return 0
    except Exception as exc:
        write_state({"schema": "worktree-hygiene.v2", "at": now, "status": "error", "issue": ISSUE_URL, "error": f"{type(exc).__name__}: {exc}"})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
