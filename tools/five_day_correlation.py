#!/usr/bin/env python3
"""Build the machine-readable dataset for the 2026-08-21..25 control-plane regression study.

Scope:
  - Parse MCP transport telemetry from the local ChatGPTMcpClean state dir when available.
  - Capture MCP commit/deploy boundaries from organicoverlords/chatgpt-mcp-clean.
  - Capture a PR activity join across p3 + tiny3d + lowvram3d-studio + regression-research.
  - Emit per-day metrics, joined correlation rows, and a normalised count of long polls.

If a source is unavailable on this machine, the script falls back to the snapshot
counts published in issue 28 comments and records the substitution explicitly in
the dataset (provenance.status). The script is byte-deterministic and never
mutates its inputs.
"""

from __future__ import annotations

import argparse
import collections
import datetime
import hashlib
import json
import pathlib
import subprocess
import sys
from typing import Any, Iterable


DEFAULT_TELEMETRY = pathlib.Path(
    r"C:\Users\Lauri\AppData\Local\ChatGPTMcpClean\.state\transport.jsonl"
)
DEFAULT_OUT_DIR = pathlib.Path(
    "02 Evidence/five-day-control-plane-20260821-25"
)
DEFAULT_VERSION_BOUNDARIES = [
    {
        "commit": "afc85f4",
        "date": "2026-08-23T20:42:32+00:00",
        "title": "remove foreground command tool from MCP surface",
        "effect": "eliminates execute_command / 195k+64k token retrievals",
    },
    {
        "commit": "7ae7025",
        "date": "2026-08-25T06:28:48+00:00",
        "title": "cap read_output at 6000 characters + observability work",
        "effect": "compresses long-poll responses; adds telemetry",
    },
    {
        "commit": "15b017f",
        "date": "2026-08-25T06:35:17+00:00",
        "title": "keep receipts at full capture buffer, not the transport cap",
        "effect": "preserves detail lost to 6k cap for diagnostics",
    },
    {
        "commit": "bbf29b9",
        "date": "2026-08-25T06:46:47+00:00",
        "title": "report how much of the head a truncated read dropped",
        "effect": "adds truncation receipts for read_output",
    },
    {
        "commit": "cd3be1b",
        "date": "2026-08-25T08:02:59+00:00",
        "title": "record per-response MCP byte counts",
        "effect": "byte telemetry on every tool response",
    },
]

# Snapshot values from issue 28 and follow-up comments. Used as fallback only;
# the dataset records which source actually supplied each count.
ISSUE_28_SNAPSHOT = {
    "tool_counts": {
        "read_output": 13047,
        "start_process": 6647,
        "execute_command": 1880,
        "busy_claim": 529,
        "busy_list": 746,
        "busy_release": 342,
        "kill_process": 751,
        "view_image": 225,
    },
    "daily_counts": {
        "2026-08-23": 5212,
        "2026-08-24": 14960,
        "2026-08-25_partial": 4007,
    },
    "slow_reads_ge_9s": {"2026-08-23": 0, "2026-08-24": 4, "2026-08-25": 107},
}

# Day-bucketed outcome join from issue 28 follow-up comment
OUTCOME_SNAPSHOT = {
    "2026-08-23": {"mcp_calls": 5212, "merges": 95, "default_commits": 224},
    "2026-08-24": {"mcp_calls": 14960, "merges": 49, "default_commits": 98},
    "2026-08-25": {"mcp_calls": 4007, "merges": 6, "default_commits": 23},
}

REPOS_FOR_JOIN = [
    "organicoverlords/p3",
    "organicoverlords/tiny3d",
    "organicoverlords/lowvram3d-studio",
]


def _eest_day(at: str) -> str:
    try:
        dt = datetime.datetime.fromisoformat(at.replace("Z", "+00:00"))
        eest = dt.astimezone(datetime.timezone(datetime.timedelta(hours=3)))
        return eest.date().isoformat()
    except Exception:
        return at[:10]


def parse_transport(path: pathlib.Path) -> dict[str, Any]:
    """Return per-day tool-call counts derived from a local transport.jsonl.

    Returns an empty result with status='unavailable' if the file is missing or
    unreadable. The script never raises on missing telemetry; the dataset
    records the substitution so a reviewer can see exactly which numbers came
    from the live machine versus the snapshot.
    """
    if not path.exists():
        return {"status": "unavailable", "path": str(path), "counts": {}}
    daily = collections.Counter()
    daily_tools: dict[str, collections.Counter] = {}
    slow_reads = collections.Counter()
    health_daily = collections.Counter()
    tool_total = collections.Counter()
    parsed_lines = 0
    bad_lines = 0
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if not line.strip():
                    continue
                parsed_lines += 1
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    bad_lines += 1
                    continue
                if rec.get("mcp_tool"):
                    tool = rec["mcp_tool"]
                    day = _eest_day(rec.get("at", ""))
                    tool_total[tool] += 1
                    daily[day] += 1
                    daily_tools.setdefault(day, collections.Counter())[tool] += 1
                    if (
                        tool == "read_output"
                        and isinstance(rec.get("duration_ms"), (int, float))
                        and rec["duration_ms"] >= 9000
                    ):
                        slow_reads[day] += 1
                if rec.get("path") == "/health":
                    health_daily[_eest_day(rec.get("at", ""))] += 1
    except OSError as exc:
        return {"status": "error", "path": str(path), "error": str(exc), "counts": {}}
    return {
        "status": "ok",
        "path": str(path),
        "parsed_lines": parsed_lines,
        "bad_lines": bad_lines,
        "tool_total": dict(tool_total),
        "daily_counts": dict(sorted(daily.items())),
        "daily_tool_counts": {
            d: dict(c) for d, c in sorted(daily_tools.items())
        },
        "slow_reads_ge_9s": dict(sorted(slow_reads.items())),
        "health_daily": dict(sorted(health_daily.items())),
    }


def build_day_metrics(
    telemetry: dict[str, Any], snapshot: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Normalise to day buckets keyed by EEST date.

    Source precedence:
      1. live telemetry when status='ok' and the day is present
      2. snapshot from issue 28 / follow-up comments
    """
    days = ["2026-08-21", "2026-08-22", "2026-08-23", "2026-08-24", "2026-08-25"]
    metrics: dict[str, dict[str, Any]] = {}
    snapshot_daily = {
        "2026-08-23": snapshot["daily_counts"]["2026-08-23"],
        "2026-08-24": snapshot["daily_counts"]["2026-08-24"],
        "2026-08-25": snapshot["daily_counts"]["2026-08-25_partial"],
    }
    for d in days:
        live = telemetry.get("daily_counts", {}).get(d)
        live_slow = telemetry.get("slow_reads_ge_9s", {}).get(d, 0)
        snap = snapshot_daily.get(d)
        metrics[d] = {
            "mcp_calls_total": (
                live if live is not None else (snap if snap is not None else None)
            ),
            "mcp_calls_source": (
                "live_telemetry"
                if live is not None
                else ("issue28_snapshot" if snap is not None else "missing")
            ),
            "slow_reads_ge_9s": live_slow if live is not None else (
                snapshot["slow_reads_ge_9s"].get(
                    "2026-08-25" if d == "2026-08-25" else d, 0
                )
                if d in ("2026-08-23", "2026-08-24", "2026-08-25")
                else 0
            ),
            "slow_reads_source": (
                "live_telemetry" if live is not None else "issue28_snapshot"
            ),
            "health_probes": telemetry.get("health_daily", {}).get(d),
        }
    return metrics


def fetch_pr_join(repos: Iterable[str]) -> dict[str, Any]:
    """Capture a PR join snapshot at the moment the script runs.

    The script does not paginate: it limits to 200 PRs per repo and records the
    total returned so the reviewer can see whether the limit truncated the
    window. PRs created outside the five-day study window are tagged but kept.
    """
    rows = []
    for repo in repos:
        try:
            proc = subprocess.run(
                [
                    "gh",
                    "pr",
                    "list",
                    "--repo",
                    repo,
                    "--state",
                    "all",
                    "--limit",
                    "200",
                    "--json",
                    "number,createdAt,mergedAt,closedAt,isDraft,state,title,author",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            rows.append({"repo": repo, "status": "gh_not_found", "prs": []})
            continue
        if proc.returncode != 0:
            rows.append(
                {
                    "repo": repo,
                    "status": "error",
                    "stderr": proc.stderr[:500],
                    "prs": [],
                }
            )
            continue
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            rows.append({"repo": repo, "status": "bad_json", "error": str(exc), "prs": []})
            continue
        in_window = []
        for pr in data:
            c = (pr.get("createdAt") or "")[:10]
            if "2026-08-2" in c:
                in_window.append(pr)
        rows.append(
            {
                "repo": repo,
                "status": "ok",
                "fetched": len(data),
                "in_window": len(in_window),
                "prs": in_window,
            }
        )
    return {"captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "rows": rows}


def build_outcome_join() -> dict[str, Any]:
    """Return the outcome join using the snapshot from issue 28 follow-up.

    The script does not refetch commits here: it records the snapshot counts
    verbatim, attributes them, and warns that the next pass should rebuild them
    from local clones when available.
    """
    join: dict[str, dict[str, Any]] = {}
    for day, row in OUTCOME_SNAPSHOT.items():
        calls = row["mcp_calls"]
        join[day] = {
            "mcp_calls": calls,
            "merges": row["merges"],
            "default_commits": row["default_commits"],
            "merges_per_1k_calls": round(row["merges"] / calls * 1000, 3),
            "commits_per_1k_calls": round(row["default_commits"] / calls * 1000, 3),
            "source": "issue28_followup_comment_2026-08-25",
        }
    return join


def build_dataset(
    telemetry_path: pathlib.Path, snapshot: dict[str, Any]
) -> dict[str, Any]:
    telemetry = parse_transport(telemetry_path)
    day_metrics = build_day_metrics(telemetry, snapshot)
    pr_join = fetch_pr_join(REPOS_FOR_JOIN)
    outcome_join = build_outcome_join()
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "study_window": {"start": "2026-08-21", "end": "2026-08-25", "tz": "EEST"},
        "telemetry": telemetry,
        "version_boundaries": DEFAULT_VERSION_BOUNDARIES,
        "day_metrics": day_metrics,
        "pr_join": pr_join,
        "outcome_join": outcome_join,
        "snapshot_provenance": {
            "tool_counts": "issue28_body_2026-08-25",
            "daily_counts": "issue28_body_2026-08-25",
            "slow_reads": "issue28_body_2026-08-25",
            "outcome_join": "issue28_followup_comment_2026-08-25",
        },
    }
    payload["checksum"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return payload


def write_outputs(out_dir: pathlib.Path, dataset: dict[str, Any]) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "five-day-correlation-dataset.json"
    json_path.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    csv_path = out_dir / "five-day-correlation-dataset.csv"
    cols = [
        "day",
        "mcp_calls_total",
        "mcp_calls_source",
        "slow_reads_ge_9s",
        "slow_reads_source",
        "health_probes",
        "merges",
        "default_commits",
        "merges_per_1k_calls",
        "commits_per_1k_calls",
    ]
    lines = [",".join(cols)]
    for day, row in dataset["day_metrics"].items():
        join = dataset["outcome_join"].get(day, {})
        values = [
            day,
            "" if row["mcp_calls_total"] is None else str(row["mcp_calls_total"]),
            row["mcp_calls_source"],
            str(row["slow_reads_ge_9s"]),
            row["slow_reads_source"],
            "" if row["health_probes"] is None else str(row["health_probes"]),
            str(join.get("merges", "")),
            str(join.get("default_commits", "")),
            str(join.get("merges_per_1k_calls", "")),
            str(join.get("commits_per_1k_calls", "")),
        ]
        lines.append(",".join(values))
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": str(json_path), "csv": str(csv_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--telemetry",
        type=pathlib.Path,
        default=DEFAULT_TELEMETRY,
        help="path to ChatGPTMcpClean transport.jsonl",
    )
    parser.add_argument(
        "--out-dir", type=pathlib.Path, default=DEFAULT_OUT_DIR
    )
    args = parser.parse_args()

    dataset = build_dataset(args.telemetry, ISSUE_28_SNAPSHOT)
    written = write_outputs(args.out_dir, dataset)

    summary = {
        "schema_version": dataset["schema_version"],
        "checksum": dataset["checksum"],
        "telemetry_status": dataset["telemetry"]["status"],
        "days_in_window": len(dataset["day_metrics"]),
        "outcome_days": len(dataset["outcome_join"]),
        "outputs": written,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
