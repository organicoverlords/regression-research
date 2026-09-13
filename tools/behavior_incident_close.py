from __future__ import annotations

import argparse
import copy
import json
import os
import re
from pathlib import Path
from typing import Any

try:
    from tools.memory_bank import BankError, append_entry, load_bank
    from tools.slopwall_v2 import SlopwallV2Error, validate_slopwall_fixture
except ImportError:
    from memory_bank import BankError, append_entry, load_bank
    from slopwall_v2 import SlopwallV2Error, validate_slopwall_fixture

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_BANK_REF = "memory/memory-bank.jsonl"


class BehaviorIncidentCloseError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BehaviorIncidentCloseError(message)


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BehaviorIncidentCloseError(f"invalid {label}: {exc}") from exc
    _require(isinstance(payload, dict), f"{label} must be a JSON object")
    return payload


def _safe_repo_file(root: Path, path: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise BehaviorIncidentCloseError(f"{label} must stay inside the Vault checkout") from exc
    _require(resolved.is_file(), f"{label} does not exist: {resolved}")
    return resolved


def _event(raw: dict[str, Any]) -> dict[str, Any]:
    event = raw.get("incident_event") or raw.get("slopwall_event")
    _require(isinstance(event, dict), "replay must contain incident_event/slopwall_event")
    return event


def _memory_id(event_id: str) -> str:
    stem = re.sub(r"[^a-z0-9._-]+", "-", event_id.casefold()).strip("-._")
    _require(bool(stem), "event_id cannot produce an empty memory id")
    return f"mem-{stem}"


def _dedupe_strings(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = value.strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _memory_values(raw: dict[str, Any]) -> dict[str, Any]:
    event = _event(raw)
    event_id = str(event.get("event_id") or "").strip()
    candidate = raw.get("memory_candidate")
    _require(isinstance(candidate, dict), f"{event_id}: replay requires structured memory_candidate")
    for key in ("scope", "title", "text", "interpretation", "confidence_reason"):
        _require(isinstance(candidate.get(key), str) and candidate[key].strip(), f"{event_id}: memory_candidate.{key} is required")
    _require(candidate.get("kind") == "correction", f"{event_id}: behavior incident memory_candidate.kind must be correction")
    tags = candidate.get("tags")
    _require(isinstance(tags, list) and all(isinstance(item, str) and item.strip() for item in tags), f"{event_id}: memory_candidate.tags must contain strings")
    confidence = candidate.get("confidence")
    _require(isinstance(confidence, int) and not isinstance(confidence, bool) and 0 <= confidence <= 100, f"{event_id}: memory_candidate.confidence must be 0..100")
    supersedes = candidate.get("supersedes") or []
    _require(isinstance(supersedes, list) and all(isinstance(item, str) and item.strip() for item in supersedes), f"{event_id}: memory_candidate.supersedes must contain strings")

    source_report = raw.get("source_report")
    replay_ref = event.get("replay_ref")
    evidence_ref = (event.get("capture") or {}).get("evidence_ref")
    for value, label in ((source_report, "source_report"), (replay_ref, "replay_ref"), (evidence_ref, "capture.evidence_ref")):
        _require(isinstance(value, str) and value.strip(), f"{event_id}: {label} is required for memory closure")

    trigger_tag = "slopwall" if event.get("trigger_kind") == "SLOPWALL" else "incident-report"
    all_tags = _dedupe_strings([*tags, trigger_tag, "behavior-incident", "assistant-recorded", "verbatim-source"])
    values: dict[str, Any] = {
        "id": _memory_id(event_id),
        "kind": "correction",
        "scope": candidate["scope"],
        "title": candidate["title"],
        "text": candidate["text"],
        "state": "PROVEN",
        "tags": all_tags,
        "evidence": [str(source_report), str(replay_ref), str(evidence_ref)],
        "supersedes": list(supersedes),
        "source_messages": [event["source_message"]],
        "interpretation": candidate["interpretation"],
        "confidence": confidence,
        "confidence_reason": candidate["confidence_reason"],
        "thread": f"behavior-incident:{event_id}",
    }
    project = candidate.get("project")
    if isinstance(project, str) and project.strip():
        values["project"] = project.strip()
    return values


def _stable_memory_projection(entry: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "id", "kind", "scope", "title", "text", "state", "tags", "evidence", "supersedes",
        "source_messages", "interpretation", "confidence", "confidence_reason", "thread", "project",
    )
    return {key: entry.get(key) for key in fields if key in entry or key == "project"}


def _find_memory(bank_path: Path, memory_id: str) -> dict[str, Any] | None:
    try:
        matches = [item for item in load_bank(bank_path) if item.get("id") == memory_id]
    except BankError as exc:
        raise BehaviorIncidentCloseError(f"canonical memory could not be read: {exc}") from exc
    _require(len(matches) <= 1, f"duplicate canonical memory id: {memory_id}")
    return matches[0] if matches else None


def _load_provenance_for_event(root: Path, event_id: str, source_report: str) -> tuple[Path, dict[str, Any], int]:
    path = root / "provenance.json"
    payload = _load_json(path, "provenance.json")
    entries = payload.get("entries")
    _require(isinstance(entries, list), "provenance.json must contain entries[]")
    matches = [
        (index, item)
        for index, item in enumerate(entries)
        if isinstance(item, dict) and (item.get("incident_id") == event_id or item.get("report_path") == source_report)
    ]
    _require(len(matches) == 1, f"{event_id}: expected exactly one provenance entry, found {len(matches)}")
    index, entry = matches[0]
    _require(entry.get("incident_id") == event_id, f"{event_id}: provenance incident_id mismatch")
    _require(entry.get("report_path") == source_report, f"{event_id}: provenance report_path mismatch")
    return path, payload, index


def _closed_payloads(raw: dict[str, Any], provenance: dict[str, Any], provenance_index: int, memory_ref: str) -> tuple[dict[str, Any], dict[str, Any]]:
    closed_replay = copy.deepcopy(raw)
    closed_event = _event(closed_replay)
    closed_event["memory_ref"] = memory_ref
    closed_event["closure_state"] = "CLOSED"

    closed_provenance = copy.deepcopy(provenance)
    entry = closed_provenance["entries"][provenance_index]
    missing = entry.get("missing") or []
    _require(isinstance(missing, list), "provenance missing must be an array")
    entry["missing"] = [item for item in missing if item != "canonical_memory_pending"]
    entry["canonical_memory_ref"] = memory_ref
    note = f"Canonical behavior-incident memory closure is bound to {memory_ref}."
    current_notes = str(entry.get("notes") or "").strip()
    if note not in current_notes:
        entry["notes"] = (current_notes + " " + note).strip()
    return closed_replay, closed_provenance


def _commit_updates(updates: dict[Path, bytes]) -> None:
    originals: dict[Path, bytes] = {}
    changed: list[Path] = []
    try:
        for path, payload in updates.items():
            originals[path] = path.read_bytes()
            if originals[path] == payload:
                continue
            temp = path.with_name(path.name + ".v2-close.tmp")
            temp.write_bytes(payload)
            try:
                os.replace(temp, path)
            finally:
                if temp.exists():
                    temp.unlink()
            changed.append(path)
    except Exception as exc:
        rollback_errors: list[str] = []
        for path in reversed(changed):
            try:
                path.write_bytes(originals[path])
            except Exception as rollback_exc:
                rollback_errors.append(f"{path}: {rollback_exc}")
        detail = f"; rollback errors: {rollback_errors}" if rollback_errors else ""
        raise BehaviorIncidentCloseError(f"closure finalization failed and repository artifacts were rolled back: {exc}{detail}") from exc


def plan_closure(replay_path: Path, *, root: Path = ROOT, bank_path: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    replay_path = _safe_repo_file(root, replay_path, "replay")
    raw = _load_json(replay_path, "replay")
    event = _event(raw)
    event_id = str(event.get("event_id") or "").strip()
    closure = event.get("closure_state")
    _require(closure in {"REPAIRED_PENDING_DURABILITY", "CLOSED"}, f"{event_id}: closure requires repaired pending or closed state, got {closure}")
    try:
        validate_slopwall_fixture(raw, root=root, filename=replay_path.name)
    except SlopwallV2Error as exc:
        raise BehaviorIncidentCloseError(f"{event_id}: replay/event validation failed before closure: {exc}") from exc

    expected_ref = str(event.get("replay_ref") or "").replace("\\", "/")
    actual_ref = replay_path.relative_to(root).as_posix()
    _require(expected_ref == actual_ref, f"{event_id}: replay_ref does not match closure target ({expected_ref} != {actual_ref})")
    memory_values = _memory_values(raw)
    memory_id = memory_values["id"]
    memory_ref = f"{CANONICAL_BANK_REF}#{memory_id}"
    source_report = str(raw.get("source_report") or "")
    provenance_path, provenance, provenance_index = _load_provenance_for_event(root, event_id, source_report)
    canonical_bank = (bank_path or (root / CANONICAL_BANK_REF)).resolve()
    _require(canonical_bank == (root / CANONICAL_BANK_REF).resolve(), "closure bank_path must be the Vault canonical memory/memory-bank.jsonl path")

    return {
        "event_id": event_id,
        "closure_state": closure,
        "memory_id": memory_id,
        "memory_ref": memory_ref,
        "memory_values": memory_values,
        "replay_path": replay_path,
        "provenance_path": provenance_path,
        "provenance": provenance,
        "provenance_index": provenance_index,
        "bank_path": canonical_bank,
        "raw": raw,
    }


def close_incident(replay_path: Path, *, root: Path = ROOT, bank_path: Path | None = None, publish: bool = False) -> dict[str, Any]:
    plan = plan_closure(replay_path, root=root, bank_path=bank_path)
    raw = plan["raw"]
    event = _event(raw)
    event_id = plan["event_id"]

    if event.get("closure_state") == "CLOSED":
        return {
            "status": "ALREADY_CLOSED",
            "event_id": event_id,
            "memory_ref": event["memory_ref"],
            "canonical_memory_written": False,
        }

    memory_values = plan["memory_values"]
    existing = _find_memory(plan["bank_path"], plan["memory_id"])
    wrote_memory = False
    if existing is None:
        try:
            saved = append_entry(plan["bank_path"], memory_values, publish=publish)
        except BankError as exc:
            raise BehaviorIncidentCloseError(f"{event_id}: canonical memory write rejected: {exc}") from exc
        wrote_memory = True
    else:
        expected_projection = _stable_memory_projection(memory_values)
        existing_projection = _stable_memory_projection(existing)
        _require(existing_projection == expected_projection, f"{event_id}: deterministic memory id already exists with different content")
        saved = existing

    closed_replay, closed_provenance = _closed_payloads(
        raw,
        plan["provenance"],
        plan["provenance_index"],
        plan["memory_ref"],
    )
    replay_bytes = (json.dumps(closed_replay, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    provenance_bytes = (json.dumps(closed_provenance, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    _commit_updates({plan["replay_path"]: replay_bytes, plan["provenance_path"]: provenance_bytes})
    try:
        validate_slopwall_fixture(closed_replay, root=Path(root), filename=plan["replay_path"].name)
    except SlopwallV2Error as exc:
        # Memory is intentionally not deleted. It is durable and rerunnable; repository
        # closure artifacts remain the repair target if this validation ever fails.
        raise BehaviorIncidentCloseError(f"{event_id}: memory exists but CLOSED replay validation failed: {exc}; rerun closure after repairing repository artifacts") from exc

    return {
        "status": "CLOSED",
        "event_id": event_id,
        "memory_ref": plan["memory_ref"],
        "memory_id": saved["id"],
        "canonical_memory_written": wrote_memory,
        "published": bool(publish),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Close a repaired V2 behavior incident through canonical memory without retrieving conversation history.")
    sub = parser.add_subparsers(dest="command", required=True)
    plan_parser = sub.add_parser("plan")
    plan_parser.add_argument("replay", type=Path)
    close_parser = sub.add_parser("close")
    close_parser.add_argument("replay", type=Path)
    close_parser.add_argument("--publish", action="store_true", help="explicitly request the memory owner's canonical Git reconciliation after recording")
    args = parser.parse_args()

    if args.command == "plan":
        plan = plan_closure(args.replay)
        print(json.dumps({key: plan[key] for key in ("event_id", "closure_state", "memory_id", "memory_ref")}, ensure_ascii=False, indent=2))
        return 0
    result = close_incident(args.replay, publish=args.publish)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
