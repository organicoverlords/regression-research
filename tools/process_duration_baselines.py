#!/usr/bin/env python3
"""Maintain derived duration baselines from completed MCP process receipts.

Evidence only. Normal refresh scans only the bounded hot receipt set and merges unseen
samples into a cache. Specific historical receipts may be imported explicitly.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median

DEFAULT_RECEIPT_ROOT = Path(os.environ.get("LOCALAPPDATA", "")) / "ChatGPTMcpClean" / "minimal-connectors" / "shared-process-receipts"
DEFAULT_STATE_ROOT = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".local" / "state")) / "VaultProcessDurationBaselines"
DEFAULT_OUTPUT = DEFAULT_STATE_ROOT / "process-duration-baselines.json"
MAX_SAMPLES_PER_JOB = 64


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def percentile(values: list[float], q: float) -> float:
    xs = sorted(values)
    if not xs:
        return 0.0
    idx = max(0, min(len(xs) - 1, math.ceil(q * len(xs)) - 1))
    return xs[idx]


def cwd_hint(cwd: str) -> str:
    name = Path(cwd).name if cwd else "unknown"
    return re.sub(r"-20\d{6,}.*$", "", name) or "unknown"


def normalize(command: str, cwd: str) -> tuple[str, str]:
    c = " ".join((command or "").split())
    low = c.lower()
    # Do not learn timing from diagnostic/editor commands that merely mention tool names.
    if len(c) > 2000 or "Set-Content" in c or re.match(r"^(rg|grep|findstr|Get-Content|Select-String|python\s+-c)\b", c, re.I):
        return "other", f"other --cwd {cwd_hint(cwd).lower()}"
    m = re.search(r"\bgh\s+run\s+watch\s+\d+.*?--repo\s+([^\s]+)", c, re.I)
    if m:
        return "ci_watch", f"gh run watch --repo {m.group(1).lower()}"
    if re.match(r"^gh\s+run\s+watch\s+\d+", c, re.I):
        return "ci_watch", f"gh run watch --cwd {cwd_hint(cwd).lower()}"
    if "blender.exe" in low or re.match(r"^\s*blender(?:\.exe)?\s", c, re.I):
        return "blender", f"blender --cwd {cwd_hint(cwd).lower()}"
    if re.search(r"(?:^|[;&|]\s*)[^;&]*(?:runuat(?:\.bat)?|unrealbuildtool(?:\.exe)?|build\.bat)\b", c, re.I):
        return "unreal_build", f"unreal build --cwd {cwd_hint(cwd).lower()}"
    if re.search(r"(?:^|[;&|]\s*)cmake\s+--build\b", c, re.I):
        return "cmake_build", f"cmake --build --cwd {cwd_hint(cwd).lower()}"
    if re.search(r"(?:^|[;&|]\s*)ctest\b", c, re.I):
        return "ctest", f"ctest --cwd {cwd_hint(cwd).lower()}"
    m = re.search(r"(?:^|[;&|]\s*)(?:uv\s+run\s+[^;&]*?\s+)?(?:python(?:\.exe)?\s+-m\s+)?pytest\b(?P<args>[^;&]*)", c, re.I)
    if m:
        args = re.sub(r"\s+", " ", m.group("args").strip().lower())[:180]
        return "pytest", f"pytest {args} --cwd {cwd_hint(cwd).lower()}".strip()
    m = re.search(r"python(?:\.exe)?\s+-m\s+unittest\b(?P<args>[^;&]*)", c, re.I)
    if m:
        args = re.sub(r"\s+", " ", m.group("args").strip().lower())[:180]
        return "unittest", f"unittest {args} --cwd {cwd_hint(cwd).lower()}".strip()
    if re.search(r"(?:^|[;&|]\s*)(npm|pnpm|yarn)\s+(run\s+)?(test|build)\b", c, re.I):
        return "js_build_test", f"js build/test --cwd {cwd_hint(cwd).lower()}"
    return "other", f"other --cwd {cwd_hint(cwd).lower()}"


def summarize(samples: list[dict]) -> dict:
    ordered = sorted(samples, key=lambda s: s["finished_at"])
    durations = [float(s["duration_seconds"]) for s in ordered]
    split = max(1, len(ordered) // 2)
    older = durations[:split]
    recent = durations[split:] or older
    older_med = median(older)
    recent_med = median(recent)
    delta = ((recent_med - older_med) / older_med * 100.0) if older_med > 0 else 0.0
    trend = "insufficient_samples" if len(samples) < 4 else ("rising" if delta >= 15 else "falling" if delta <= -15 else "stable")
    return {
        "samples": len(samples),
        "mean_seconds": round(mean(durations), 1),
        "median_seconds": round(median(durations), 1),
        "p90_seconds": round(percentile(durations, 0.90), 1),
        "min_seconds": round(min(durations), 1),
        "max_seconds": round(max(durations), 1),
        "latest_seconds": round(durations[-1], 1),
        "recent_vs_older_median_pct": round(delta, 1),
        "trend": trend,
        "latest_finished_at": ordered[-1]["finished_at"],
    }


def load_cached_samples(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return list(json.loads(path.read_text(encoding="utf-8")).get("sample_cache", []))
    except Exception:
        return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt-root", type=Path, default=DEFAULT_RECEIPT_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--lookback-hours", type=float, default=72.0)
    parser.add_argument("--min-seconds", type=float, default=5.0)
    parser.add_argument("--import-receipt", action="append", type=Path, default=[], help="Import one specific historical receipt; repeatable.")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=args.lookback_hours)
    by_id: dict[str, dict] = {}
    for sample in load_cached_samples(args.output):
        try:
            if parse_time(sample["finished_at"]) >= cutoff:
                by_id[sample["process_id"]] = sample
        except Exception:
            pass

    hot_seen = hot_added = imported_added = malformed = 0

    def ingest(path: Path, source: str) -> None:
        nonlocal hot_added, imported_added, malformed
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            pid, started, finished = data.get("process_id"), data.get("started_at"), data.get("finished_at")
            if not pid or not started or not finished:
                return
            finished_dt = parse_time(finished)
            if finished_dt < cutoff:
                return
            duration = (finished_dt - parse_time(started)).total_seconds()
            if duration < args.min_seconds:
                return
            family, key = normalize(str(data.get("command", "")), str(data.get("cwd", "")))
            if family == "other":
                return
            sample = {
                "process_id": pid,
                "family": family,
                "job_key": key,
                "duration_seconds": round(duration, 3),
                "exit_code": data.get("exit_code"),
                "started_at": started,
                "finished_at": finished,
            }
            is_new = pid not in by_id
            by_id[pid] = sample
            if is_new and source == "hot":
                hot_added += 1
            elif is_new and source == "import":
                imported_added += 1
        except Exception:
            malformed += 1

    if args.receipt_root.exists():
        for path in args.receipt_root.glob("*.json"):
            hot_seen += 1
            ingest(path, "hot")
    for path in args.import_receipt:
        ingest(path, "import")

    grouped: dict[str, list[dict]] = defaultdict(list)
    family_grouped: dict[str, list[dict]] = defaultdict(list)
    for sample in by_id.values():
        if sample["family"] != "other":
            grouped[sample["job_key"]].append(sample)
            family_grouped[sample["family"]].append(sample)

    cache: list[dict] = []
    for samples in grouped.values():
        cache.extend(sorted(samples, key=lambda s: s["finished_at"])[-MAX_SAMPLES_PER_JOB:])
    cache.sort(key=lambda s: s["finished_at"])

    jobs = {k: summarize(v) for k, v in sorted(grouped.items(), key=lambda kv: (-len(kv[1]), kv[0])) if len(v) >= 2}
    families = {k: summarize(v) for k, v in sorted(family_grouped.items(), key=lambda kv: (-len(kv[1]), kv[0])) if len(v) >= 2}
    payload = {
        "schema": "process-duration-baselines.v1",
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "authority": "DERIVED_EVIDENCE_NOT_PROCESS_OR_SCHEDULING_AUTHORITY",
        "source": str(args.receipt_root),
        "collection_mode": "incremental_hot_receipts_plus_explicit_imports",
        "lookback_hours": args.lookback_hours,
        "minimum_duration_seconds": args.min_seconds,
        "hot_receipts_seen": hot_seen,
        "new_hot_samples_added": hot_added,
        "new_imported_samples_added": imported_added,
        "malformed_receipts_skipped": malformed,
        "tracked_samples": len(cache),
        "families": families,
        "jobs": jobs,
        "polling_guidance": {
            "rule": "Use a matching baseline only after the process is observed still running. Prefer median/p90; sparse or missing samples do not justify a long blind wait.",
            "anomaly": "A materially longer-than-p90 run is a process/build anomaly candidate for one discriminating check, not a reason to poll faster.",
            "security_boundary": "Never infer or adapt to platform security reroutes from tool-call symptoms. Tool-policy rejection, MCP/transport failure, process failure, and user-confirmed platform reroute remain separate classifications."
        },
        "sample_cache": cache,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ["generated_at", "hot_receipts_seen", "new_hot_samples_added", "new_imported_samples_added", "tracked_samples", "families", "jobs"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
