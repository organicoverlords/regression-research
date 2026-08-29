from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PREFIXES = ("01 Reports/", "02 Evidence/", "03 Fixtures and Experiments/", "04 Operating Contracts/")
PRIVATE_TEMP_PREFIXES = ("tmp-cloudflare-ab",)
PRIVATE_TEMP_NAMES = {"tmp-main-brave-history.sqlite", "tmp-chatport-history-copy.sqlite", "tmp-current-chat-cdp.mjs"}
LOCAL_TEMP_PREFIXES = ("tmp_",)
LOCAL_CHECKPOINT_NAMES = {"CONTEXT_PRUNE_SAFEPOINT.txt"}


def normalize(path: str) -> str:
    return path.strip().replace("\\", "/")


def classify_path(path: str) -> str:
    path = normalize(path)
    if path.startswith(EVIDENCE_PREFIXES):
        return "research_wip"
    name = Path(path).name
    if name in PRIVATE_TEMP_NAMES or path.startswith(PRIVATE_TEMP_PREFIXES):
        return "private_temp"
    if path.startswith((".state/", "memory/conversations/")):
        return "private_generated"
    if path.startswith(("quarantine/",)):
        return "quarantine"
    if path.startswith(("tests/", "tools/", "memory/")):
        return "code_or_memory_wip"
    if name in LOCAL_CHECKPOINT_NAMES:
        return "continuity_checkpoint_review"
    if name.startswith(LOCAL_TEMP_PREFIXES):
        return "local_temp_review"
    return "unclassified"


def _git_paths(*args: str, root: Path = ROOT) -> list[str]:
    proc = subprocess.run(["git", *args, "-z"], cwd=root, capture_output=True, check=True)
    return [normalize(item.decode("utf-8")) for item in proc.stdout.split(b"\0") if item]


def inventory(root: Path = ROOT) -> dict:
    untracked = _git_paths("ls-files", "--others", "--exclude-standard", root=root)
    ignored = _git_paths("ls-files", "--others", "--ignored", "--exclude-standard", root=root)
    ignored_private = [path for path in ignored if classify_path(path) in {"private_temp", "private_generated"}]
    counts = Counter(classify_path(path) for path in untracked)
    bytes_by_bucket: Counter[str] = Counter()
    for rel in untracked:
        try:
            path = root / rel
            if path.is_file():
                bytes_by_bucket[classify_path(rel)] += path.stat().st_size
        except OSError:
            pass
    return {
        "status": "REVIEW" if untracked else "CLEAN",
        "untracked_total": len(untracked),
        "counts": dict(sorted(counts.items())),
        "bytes": dict(sorted(bytes_by_bucket.items())),
        "ignored_private_local": sorted(ignored_private),
        "unclassified": sorted(path for path in untracked if classify_path(path) == "unclassified"),
        "contract": "research WIP, local checkpoints, and local temp review stay visible but non-canonical until deliberately integrated; private temp is ignored, not deleted",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Report non-canonical Vault WIP/private-state hygiene without deleting evidence.")
    parser.add_argument("--json", action="store_true", help="emit JSON (default is compact JSON too; retained for script compatibility)")
    args = parser.parse_args()
    print(json.dumps(inventory(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
