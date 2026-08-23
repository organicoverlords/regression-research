#!/usr/bin/env python3
"""Catalogue ChatPort evidence without copying the raw corpus into git."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

CAPTURE_RE = re.compile(r"^(\d{8}T\d{6}(?:\d{3})?Z)_")
SHA_RE = re.compile(r"_sha256-([0-9a-fA-F]+)")


def iso_utc(value):
    if value is None:
        return ""
    try:
        value = float(value)
        if not (946684800 <= value <= 4102444800):
            return ""
        return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def parse_capture(name: str):
    m = CAPTURE_RE.match(name)
    if not m:
        return ""
    raw = m.group(1)
    fmt = "%Y%m%dT%H%M%SZ" if len(raw) == 16 else "%Y%m%dT%H%M%S%fZ"
    try:
        return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        return ""


def min_nonempty(values):
    vals = [v for v in values if v]
    return min(vals) if vals else ""


def max_nonempty(values):
    vals = [v for v in values if v]
    return max(vals) if vals else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    ap.add_argument("output_dir", type=Path)
    args = ap.parse_args()
    root = args.root.resolve()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    files = []
    conversations = defaultdict(list)
    errors = []
    ext_counts = Counter()
    ext_bytes = Counter()
    folder_counts = Counter()
    folder_bytes = Counter()
    capture_days = Counter()
    raw_capture_days = Counter()
    content_hashes = Counter()
    role_counts = Counter()
    message_total = 0
    parseable_json = 0
    raw_json_files = 0
    parseable_raw_json = 0

    paths = sorted(p for p in root.rglob("*") if p.is_file())
    for i, path in enumerate(paths, 1):
        rel = path.relative_to(root).as_posix()
        stat = path.stat()
        ext = path.suffix.lower() or "[none]"
        top = rel.split("/", 1)[0] if "/" in rel else "[root]"
        ext_counts[ext] += 1
        ext_bytes[ext] += stat.st_size
        folder_counts[top] += 1
        folder_bytes[top] += stat.st_size
        capture = parse_capture(path.name)
        if capture:
            capture_days[capture[:10]] += 1
            if rel.startswith("raw/"):
                raw_capture_days[capture[:10]] += 1

        is_raw_json = rel.startswith("raw/") and ext == ".json"
        if is_raw_json:
            raw_json_files += 1

        row = {
            "relative_path": rel,
            "bytes": stat.st_size,
            "mtime_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
            "capture_utc": capture,
            "filename_sha_prefix": (SHA_RE.search(path.name).group(1).lower() if SHA_RE.search(path.name) else ""),
            "sha256": "",
            "conversation_id": "",
            "title": "",
            "conversation_create_utc": "",
            "conversation_update_utc": "",
            "message_first_utc": "",
            "message_last_utc": "",
            "messages": 0,
            "user_messages": 0,
            "assistant_messages": 0,
            "tool_messages": 0,
            "system_messages": 0,
            "parse_status": "not-json",
        }

        if ext == ".json":
            try:
                raw = path.read_bytes()
                row["sha256"] = hashlib.sha256(raw).hexdigest()
                content_hashes[row["sha256"]] += 1
                obj = json.loads(raw)
                if not isinstance(obj, dict):
                    raise ValueError("top-level JSON is not an object")
                parseable_json += 1
                row["parse_status"] = "ok"
                cid = str(obj.get("conversation_id") or "")
                row["conversation_id"] = cid
                row["title"] = str(obj.get("title") or "").replace("\r", " ").replace("\n", " ")
                row["conversation_create_utc"] = iso_utc(obj.get("create_time"))
                row["conversation_update_utc"] = iso_utc(obj.get("update_time"))
                msg_times = []
                local_roles = Counter()
                mapping = obj.get("mapping") or {}
                nodes = mapping.values() if isinstance(mapping, dict) else []
                for node in nodes:
                    if not isinstance(node, dict):
                        continue
                    msg = node.get("message")
                    if not isinstance(msg, dict):
                        continue
                    role = ((msg.get("author") or {}).get("role") or "unknown")
                    local_roles[role] += 1
                    t = iso_utc(msg.get("create_time"))
                    if t:
                        msg_times.append(t)
                count = sum(local_roles.values())
                row["messages"] = count
                row["user_messages"] = local_roles["user"]
                row["assistant_messages"] = local_roles["assistant"]
                row["tool_messages"] = local_roles["tool"]
                row["system_messages"] = local_roles["system"]
                row["message_first_utc"] = min(msg_times) if msg_times else ""
                row["message_last_utc"] = max(msg_times) if msg_times else ""
                if is_raw_json:
                    parseable_raw_json += 1
                    message_total += count
                    role_counts.update(local_roles)
                    if cid:
                        conversations[cid].append(row)
            except Exception as exc:
                row["parse_status"] = "error"
                errors.append((rel, f"{type(exc).__name__}: {exc}"))
        files.append(row)
        if i % 50 == 0 or i == len(paths):
            print(f"processed {i}/{len(paths)}", flush=True)

    conv_rows = []
    for cid, rows in conversations.items():
        latest = max(rows, key=lambda r: (r["capture_utc"], r["mtime_utc"], r["bytes"]))
        conv_rows.append({
            "conversation_id": cid,
            "title_latest": latest["title"],
            "captures": len(rows),
            "total_capture_bytes": sum(r["bytes"] for r in rows),
            "largest_capture_bytes": max(r["bytes"] for r in rows),
            "first_capture_utc": min_nonempty(r["capture_utc"] for r in rows),
            "last_capture_utc": max_nonempty(r["capture_utc"] for r in rows),
            "conversation_create_utc": min_nonempty(r["conversation_create_utc"] for r in rows),
            "conversation_update_utc": max_nonempty(r["conversation_update_utc"] for r in rows),
            "message_first_utc": min_nonempty(r["message_first_utc"] for r in rows),
            "message_last_utc": max_nonempty(r["message_last_utc"] for r in rows),
            "max_messages_in_capture": max(r["messages"] for r in rows),
            "latest_relative_path": latest["relative_path"],
            "latest_sha256": latest["sha256"],
        })
    conv_rows.sort(key=lambda r: (r["conversation_create_utc"], r["conversation_id"]))

    file_csv = out / "chatport-file-index-2026-08-23.csv"
    with file_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(files[0].keys()) if files else [])
        if files:
            w.writeheader(); w.writerows(files)

    conv_csv = out / "chatport-conversation-index-2026-08-23.csv"
    with conv_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(conv_rows[0].keys()) if conv_rows else [])
        if conv_rows:
            w.writeheader(); w.writerows(conv_rows)

    total_bytes = sum(r["bytes"] for r in files)
    capture_values = [r["capture_utc"] for r in files if r["capture_utc"]]
    raw_capture_values = [r["capture_utc"] for r in files if r["capture_utc"] and r["relative_path"].startswith("raw/")]
    conv_create_values = [r["conversation_create_utc"] for r in conv_rows if r["conversation_create_utc"]]
    conv_update_values = [r["conversation_update_utc"] for r in conv_rows if r["conversation_update_utc"]]
    msg_first_values = [r["message_first_utc"] for r in conv_rows if r["message_first_utc"]]
    msg_last_values = [r["message_last_utc"] for r in conv_rows if r["message_last_utc"]]
    duplicate_ids = sum(1 for rows in conversations.values() if len(rows) > 1)
    duplicate_captures = sum(max(0, len(rows) - 1) for rows in conversations.values())
    duplicate_hash_groups = sum(1 for n in content_hashes.values() if n > 1)
    duplicate_hash_files = sum(n - 1 for n in content_hashes.values() if n > 1)

    month_counts = Counter()
    for r in conv_rows:
        if r["conversation_create_utc"]:
            month_counts[r["conversation_create_utc"][:7]] += 1

    summary = {
        "source_root": str(root),
        "scanned_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "files": len(files),
        "bytes": total_bytes,
        "gib": round(total_bytes / (1024**3), 6),
        "extensions": {k: {"files": ext_counts[k], "bytes": ext_bytes[k]} for k in sorted(ext_counts)},
        "top_level_folders": {k: {"files": folder_counts[k], "bytes": folder_bytes[k]} for k in sorted(folder_counts)},
        "capture_range_utc": [min(capture_values) if capture_values else "", max(capture_values) if capture_values else ""],
        "capture_days": dict(sorted(capture_days.items())),
        "raw_capture_range_utc": [min(raw_capture_values) if raw_capture_values else "", max(raw_capture_values) if raw_capture_values else ""],
        "raw_capture_days": dict(sorted(raw_capture_days.items())),
        "parseable_json": parseable_json,
        "raw_json_files": raw_json_files,
        "parseable_raw_json": parseable_raw_json,
        "json_parse_errors": len(errors),
        "unique_conversations": len(conv_rows),
        "conversation_ids_with_multiple_captures": duplicate_ids,
        "extra_captures_of_known_conversation_ids": duplicate_captures,
        "duplicate_sha256_groups": duplicate_hash_groups,
        "duplicate_sha256_extra_files": duplicate_hash_files,
        "conversation_create_range_utc": [min(conv_create_values) if conv_create_values else "", max(conv_create_values) if conv_create_values else ""],
        "conversation_update_range_utc": [min(conv_update_values) if conv_update_values else "", max(conv_update_values) if conv_update_values else ""],
        "message_range_utc": [min(msg_first_values) if msg_first_values else "", max(msg_last_values) if msg_last_values else ""],
        "messages_across_raw_captures": message_total,
        "roles_across_raw_captures": dict(sorted(role_counts.items())),
        "unique_conversations_by_create_month": dict(sorted(month_counts.items())),
        "errors": errors,
    }
    (out / "chatport-corpus-summary-2026-08-23.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    md = out / "chatport-corpus-catalogue-2026-08-23.md"
    def rng(name, values):
        return f"- {name}: `{values[0] or 'unknown'}` to `{values[1] or 'unknown'}`"
    lines = [
        "# ChatPort downloaded corpus catalogue — 2026-08-23",
        "",
        f"Source root: `{root}`. This catalogue records metadata and hashes; the raw downloaded corpus is not copied into this repository.",
        "",
        "## Quantity",
        "",
        f"- Files: **{len(files):,}**",
        f"- Bytes: **{total_bytes:,}** ({total_bytes / (1024**3):.3f} GiB)",
        f"- Parseable JSON files (all corpus metadata + raw): **{parseable_json:,}**",
        f"- Raw JSON conversation captures: **{parseable_raw_json:,} / {raw_json_files:,}**",
        f"- Unique conversation IDs in raw captures: **{len(conv_rows):,}**",
        f"- Conversation IDs with multiple captures: **{duplicate_ids:,}** ({duplicate_captures:,} extra captures)",
        f"- Exact duplicate JSON content by SHA-256: **{duplicate_hash_groups:,} groups / {duplicate_hash_files:,} extra files**",
        f"- JSON parse errors: **{len(errors):,}**",
        "",
        "## Time coverage",
        "",
        rng("Filename capture range, all timestamped corpus files (UTC)", summary["capture_range_utc"]),
        rng("Raw conversation capture range (UTC)", summary["raw_capture_range_utc"]),
        rng("Conversation creation range (UTC)", summary["conversation_create_range_utc"]),
        rng("Conversation update range (UTC)", summary["conversation_update_range_utc"]),
        rng("Message timestamp range across unique conversations (UTC)", summary["message_range_utc"]),
        "",
        "## Unique conversations by creation month",
        "",
        "| Month (UTC) | Conversations |",
        "|---|---:|",
    ]
    lines += [f"| {month} | {count} |" for month, count in sorted(month_counts.items())]
    lines += [
        "",
        "## Capture days",
        "",
        "| Raw capture day (UTC) | Timestamped raw files |",
        "|---|---:|",
    ]
    lines += [f"| {day} | {count} |" for day, count in sorted(raw_capture_days.items())]
    lines += [
        "",
        "## Machine-readable indexes",
        "",
        "`chatport-file-index-2026-08-23.csv` records every downloaded file, byte size, timestamps, SHA-256 for JSON files, conversation id, title, and message-role counts.",
        "",
        "`chatport-conversation-index-2026-08-23.csv` collapses recaptures by conversation id and records first/last capture, conversation/message time range, capture count, largest capture, latest source path, and latest SHA-256.",
        "",
        "`chatport-corpus-summary-2026-08-23.json` contains the aggregate metrics used in this report.",
        "",
        "## Interpretation limits",
        "",
        "A downloaded capture can contain messages much older than its download date. Capture timestamps therefore describe acquisition, while conversation/message timestamps describe historical evidence coverage. Counts labelled ‘across captures’ can double-count messages when one conversation was captured repeatedly; the conversation index removes that inflation for conversation-level coverage.",
    ]
    if errors:
        lines += ["", "## Parse errors", ""] + [f"- `{p}` — {e}" for p, e in errors[:50]]
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"WROTE {md}")
    print(f"WROTE {file_csv}")
    print(f"WROTE {conv_csv}")

if __name__ == "__main__":
    main()
