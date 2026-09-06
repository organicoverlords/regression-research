#!/usr/bin/env python3
"""Persist ChatGPT conversation/Library artifact metadata for Vault timeline ingestion.

This is a provenance bridge, not a file-copy mechanism.  The ChatGPT-side Files
connector supplies metadata; this helper validates, normalizes, de-duplicates,
and writes the existing ``*chatgpt_artifact_occurrences*.jsonl`` format consumed
by ``timeline_materializer.py``.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "02 Evidence" / "chatgpt_artifact_occurrences.jsonl"
MANIFEST_GLOB = "*chatgpt_artifact_occurrences*.jsonl"


def _nonempty(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def _iso(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def _artifact_type(row: dict[str, Any]) -> str:
    declared = str(row.get("artifact_type") or "").strip()
    if declared:
        return declared
    library_type = str(row.get("library_artifact_type") or "").strip().casefold()
    if library_type == "writing_block":
        return "library_artifact"
    if library_type:
        return library_type
    suffix = Path(str(row.get("filename") or row.get("name") or "")).suffix.casefold()
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
        return "image"
    return "library_artifact"


def normalize_row(
    raw: dict[str, Any], *, observed_at: str, default_source_kind: str | None = None,
    default_project: str | None = None,
) -> dict[str, Any]:
    library_file_id = str(raw.get("library_file_id") or "").strip() or None
    file_id = str(raw.get("file_id") or "").strip() or None
    stable_id = library_file_id or file_id
    if not stable_id:
        raise ValueError("artifact row requires library_file_id or file_id")
    filename = str(raw.get("filename") or raw.get("name") or stable_id).strip()
    if not filename:
        filename = stable_id

    row: dict[str, Any] = {
        "file_id": file_id or library_file_id,
        "filename": filename,
        "artifact_type": _artifact_type(raw),
        "observed_at": _iso(raw.get("observed_at")) or observed_at,
        "source_kind": str(raw.get("source_kind") or default_source_kind or "library").strip(),
        "provenance": str(raw.get("provenance") or "CHATGPT_FILES_CONNECTOR").strip(),
    }
    if library_file_id:
        row["library_file_id"] = library_file_id

    aliases = {
        "created_at_utc": ("created_at_utc", "created_at"),
        "uploaded_at_utc": ("uploaded_at_utc", "uploaded_at"),
        "modified_at_utc": ("modified_at_utc", "modified_at"),
        "capture_time_local": ("capture_time_local",),
    }
    for target, keys in aliases.items():
        value = next((raw.get(key) for key in keys if _nonempty(raw.get(key))), None)
        if value is not None:
            row[target] = _iso(value)

    for key in (
        "library_artifact_type", "subject", "description", "classification", "review_status",
        "timestamp_source", "text_path", "text_sha256", "user_turn_index", "size_bytes",
    ):
        if _nonempty(raw.get(key)):
            row[key] = raw.get(key)

    if "model_generated" in raw and raw.get("model_generated") is not None:
        row["model_generated"] = bool(raw.get("model_generated"))

    project = str(raw.get("project") or default_project or "").strip()
    if project:
        row["project"] = project

    tags = raw.get("tags") or []
    if isinstance(tags, str):
        tags = [part.strip() for part in tags.split(",") if part.strip()]
    row["tags"] = sorted({str(tag).strip() for tag in tags if str(tag).strip()})
    return row


def _stable_id(row: dict[str, Any]) -> str:
    return str(row.get("library_file_id") or row.get("file_id") or "").strip()


def merge_rows(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Merge richer/newer metadata without discarding previously reviewed fields."""
    merged = dict(old)
    for key, value in new.items():
        if key == "tags":
            merged["tags"] = sorted({
                str(tag).strip()
                for tag in [*(old.get("tags") or []), *(new.get("tags") or [])]
                if str(tag).strip()
            })
            continue
        if key == "observed_at" and _nonempty(old.get("observed_at")):
            continue
        if key == "artifact_type":
            prior = str(old.get(key) or "").strip()
            incoming = str(value or "").strip()
            if prior and incoming in {"image", "library_artifact"} and prior not in {"image", "library_artifact"}:
                continue
        if key == "source_kind":
            prior = str(old.get(key) or "").strip()
            if prior in {"upload", "generated"} and str(value or "").strip() == "library":
                continue
        if key == "provenance":
            prior = str(old.get(key) or "").strip()
            if prior and str(value or "").strip() == "CHATGPT_FILES_CONNECTOR":
                continue
        if _nonempty(value) or key == "model_generated":
            merged[key] = value
    return merged


def _load_json_rows(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig")
    stripped = text.strip()
    if not stripped:
        return []
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        rows = []
        for number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"JSONL line {number} is not an object")
            rows.append(value)
        return rows
    if isinstance(payload, list):
        if not all(isinstance(row, dict) for row in payload):
            raise ValueError("JSON array must contain only objects")
        return list(payload)
    if isinstance(payload, dict):
        for key in ("files", "items", "results", "artifacts"):
            values = payload.get(key)
            if isinstance(values, list):
                if not all(isinstance(row, dict) for row in values):
                    raise ValueError(f"{key} must contain only objects")
                return list(values)
        return [payload]
    raise ValueError("input must be a JSON object, array, or JSONL objects")


def _read_input(path_text: str) -> list[dict[str, Any]]:
    if path_text != "-":
        return _load_json_rows(Path(path_text))
    text = sys.stdin.read()
    stripped = text.strip()
    if not stripped:
        return []
    try:
        payload = json.loads(stripped)
        if isinstance(payload, list):
            if not all(isinstance(row, dict) for row in payload):
                raise ValueError("JSON array must contain only objects")
            return list(payload)
        if isinstance(payload, dict):
            for key in ("files", "items", "results", "artifacts"):
                values = payload.get(key)
                if isinstance(values, list):
                    return list(values)
            return [payload]
    except json.JSONDecodeError:
        pass
    rows = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"JSONL line {number} is not an object")
        rows.append(value)
    return rows


def load_known_rows(evidence_root: Path, output: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    known: dict[str, dict[str, Any]] = {}
    output_rows: dict[str, dict[str, Any]] = {}
    paths = sorted({*evidence_root.glob(MANIFEST_GLOB), output})
    for path in paths:
        if not path.is_file():
            continue
        try:
            rows = _load_json_rows(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        for row in rows:
            stable = _stable_id(row)
            if not stable:
                continue
            known[stable] = merge_rows(known.get(stable, {}), row)
            if path.resolve() == output.resolve():
                output_rows[stable] = merge_rows(output_rows.get(stable, {}), row)
    return known, output_rows


def ingest(
    rows: Iterable[dict[str, Any]], *, output: Path = DEFAULT_OUTPUT,
    observed_at: str | None = None, source_kind: str | None = None,
    project: str | None = None, dry_run: bool = False,
) -> dict[str, Any]:
    observed = _iso(observed_at) if observed_at else datetime.now(timezone.utc).isoformat()
    assert observed is not None
    evidence_root = output.parent
    known, output_rows = load_known_rows(evidence_root, output)
    inserted = updated = unchanged = 0
    incoming = 0
    for raw in rows:
        incoming += 1
        normalized = normalize_row(
            raw, observed_at=observed, default_source_kind=source_kind, default_project=project,
        )
        stable = _stable_id(normalized)
        prior = known.get(stable)
        merged = merge_rows(prior or {}, normalized)
        if prior is None:
            inserted += 1
        elif merged == prior:
            unchanged += 1
        else:
            updated += 1
        known[stable] = merged
        output_rows[stable] = merged

    if not dry_run:
        output.parent.mkdir(parents=True, exist_ok=True)
        ordered = sorted(output_rows.values(), key=lambda row: (_stable_id(row).casefold(), str(row.get("filename") or "").casefold()))
        temp = output.with_suffix(output.suffix + ".tmp")
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            for row in ordered:
                handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        temp.replace(output)

    return {
        "ok": True,
        "input_rows": incoming,
        "inserted": inserted,
        "updated": updated,
        "unchanged": unchanged,
        "output_rows": len(output_rows),
        "output": str(output),
        "dry_run": dry_run,
        "observed_at": observed,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Persist ChatGPT Files metadata for Vault timeline ingestion.")
    parser.add_argument("input", help="JSON/JSONL file path, or - for stdin")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--observed-at", help="ISO-8601 time Vault observed this connector metadata")
    parser.add_argument("--source-kind", default="library")
    parser.add_argument("--project")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = ingest(
            _read_input(args.input), output=args.output, observed_at=args.observed_at,
            source_kind=args.source_kind, project=args.project, dry_run=args.dry_run,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
