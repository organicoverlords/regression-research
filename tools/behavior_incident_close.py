from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

try:
    from tools.memory_bank import BankError, append_entry, load_bank
    from tools.replay_scoring import FixtureError, score_fixture
    from tools.slopwall_v2 import SlopwallV2Error, validate_slopwall_fixture
except ImportError:
    from memory_bank import BankError, append_entry, load_bank
    from replay_scoring import FixtureError, score_fixture
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


def _require_nonserving_branch(root: Path) -> None:
    if not (root / ".git").exists():
        return
    proc = subprocess.run(
        ["git", "-C", str(root), "symbolic-ref", "--quiet", "--short", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    _require(proc.returncode == 0, f"cannot determine repair-binding checkout branch: {proc.stderr.strip()}")
    _require(proc.stdout.strip() != "main", "refusing to bind behavior-incident repair directly on serving/main; use an isolated feature worktree")


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
    memory_pending_markers = {
        "canonical_memory_pending",
        "searchable_memory_pointer_pending_non_live_v2_design",
    }
    entry["missing"] = [item for item in missing if item not in memory_pending_markers]
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


def _require_canonical_artifacts(root: Path, refs: list[str]) -> None:
    if not (root / ".git").exists():
        return
    rev = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--verify", "refs/remotes/origin/main"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    _require(rev.returncode == 0, "canonical closure requires a known refs/remotes/origin/main")
    canonical = rev.stdout.strip()
    for ref in refs:
        normalized = ref.replace("\\", "/")
        local = _safe_repo_file(root, root / normalized, f"canonical artifact {normalized}")
        _require(local.is_file(), f"canonical closure artifact is missing locally: {normalized}")
        show = subprocess.run(
            ["git", "-C", str(root), "show", f"{canonical}:{normalized}"],
            capture_output=True,
            check=False,
        )
        _require(show.returncode == 0, f"canonical memory closure blocked: {normalized} is not present on origin/main")
        _require(show.stdout == local.read_bytes(), f"canonical memory closure blocked: {normalized} differs from origin/main")



def _verify_repair_authority(
    event: dict[str, Any],
    candidate: dict[str, Any],
    event_id: str,
    *,
    evidence_items: list[Any] | None = None,
    require_persisted: bool = True,
) -> list[int]:
    required = event.get("repair_authority")
    _require(isinstance(required, dict), f"{event_id}: repair_authority is required")
    mode = required.get("mode")
    _require(mode in {"NOT_REQUIRED", "REQUIRED"}, f"{event_id}: invalid repair_authority mode")
    if mode != "REQUIRED":
        return []

    proof = candidate.get("authority_proof")
    _require(isinstance(proof, dict), f"{event_id}: authority-sensitive repair requires independent authority proof")
    refs = proof.get("evidence_refs")
    basis = str(proof.get("basis") or "").casefold()
    _require(proof.get("status") == "PASS", f"{event_id}: repair authority proof must PASS")
    _require(proof.get("owner") == required.get("owner"), f"{event_id}: repair authority owner mismatch")
    _require(proof.get("gate") == required.get("gate"), f"{event_id}: repair authority gate mismatch")
    _require(isinstance(refs, list) and refs and all(isinstance(ref, str) and ref.strip() for ref in refs), f"{event_id}: repair authority proof needs evidence_refs")
    _require(len(set(refs)) == len(refs), f"{event_id}: repair authority evidence_refs must be unique")
    _require(basis not in {"slopwall", "incident_report", "incident report", "corrective_trigger", "corrective trigger"} and bool(basis), f"{event_id}: corrective trigger is not repair authority")
    if not require_persisted:
        return []
    _require(isinstance(evidence_items, list), f"{event_id}: authority-sensitive repair requires persisted authority evidence")

    wanted = set(refs)
    seen: set[str] = set()
    indexes: list[int] = []
    for index, item in enumerate(evidence_items):
        if not isinstance(item, dict) or item.get("kind") != "authority_evidence":
            continue
        ref = item.get("ref")
        if ref not in wanted:
            continue
        _require(ref not in seen, f"{event_id}: duplicate persisted authority evidence ref: {ref}")
        _require(item.get("status") == "PASS", f"{event_id}: persisted authority evidence must PASS: {ref}")
        _require(item.get("owner") == required.get("owner"), f"{event_id}: persisted authority evidence owner mismatch: {ref}")
        _require(item.get("gate") == required.get("gate"), f"{event_id}: persisted authority evidence gate mismatch: {ref}")
        _require(isinstance(item.get("source"), str) and item["source"].strip(), f"{event_id}: persisted authority evidence source is required: {ref}")
        _require(isinstance(item.get("content"), str) and item["content"].strip(), f"{event_id}: persisted authority evidence content is required: {ref}")
        seen.add(ref)
        indexes.append(index)
    _require(seen == wanted, f"{event_id}: authority proof refs are not backed by persisted owner/gate evidence")
    return indexes


def bind_repair(
    replay_path: Path,
    *,
    observation: str,
    candidate: dict[str, Any],
    kind: str = "assistant_reply",
    authority_evidence: list[dict[str, Any]] | None = None,
    root: Path = ROOT,
) -> dict[str, Any]:
    root = root.resolve()
    _require_nonserving_branch(root)
    _require(kind in {"assistant_reply", "assistant_action"}, "repair observation kind must be assistant_reply or assistant_action")
    _require(isinstance(observation, str) and observation.strip(), "repair observation must be non-empty visible content")
    _require(isinstance(candidate, dict) and isinstance(candidate.get("action"), str) and candidate["action"].strip(), "repair candidate.action is required")
    _require(candidate["action"].strip() == observation.strip(), "repair candidate.action must equal the observed visible repair content")

    replay_path = _safe_repo_file(root, replay_path, "replay")
    raw = _load_json(replay_path, "replay")
    event = _event(raw)
    event_id = str(event.get("event_id") or "").strip()
    _require(event.get("repair_binding_required") is True, f"{event_id}: replay does not require repair binding")
    _require(event.get("closure_state") != "CLOSED", f"{event_id}: CLOSED event cannot accept a new repair observation")
    try:
        validate_slopwall_fixture(raw, root=root, filename=replay_path.name)
    except SlopwallV2Error as exc:
        raise BehaviorIncidentCloseError(f"{event_id}: replay/event validation failed before repair binding: {exc}") from exc

    evidence_ref = str((event.get("capture") or {}).get("evidence_ref") or "")
    evidence_path = _safe_repo_file(root, root / evidence_ref, "visible evidence")
    evidence = _load_json(evidence_path, "visible evidence")
    _require(evidence.get("event_id") == event_id and isinstance(evidence.get("items"), list), f"{event_id}: visible evidence must bind the event and contain items[]")

    digest = hashlib.sha256(observation.encode("utf-8")).hexdigest()
    existing = event.get("repair_binding") or {}
    if existing.get("status") in {"SCORED_PASS", "SCORED_FAIL"}:
        same = existing.get("sha256") == digest and raw.get("repair_candidate") == candidate
        _require(same, f"{event_id}: repair observation already bound with different content")
        persisted_indexes = _verify_repair_authority(event, candidate, event_id, evidence_items=evidence["items"])
        _require(persisted_indexes == list(existing.get("authority_item_indexes") or []), f"{event_id}: persisted authority evidence binding changed")
        return {
            "status": "ALREADY_BOUND",
            "event_id": event_id,
            "repair_status": existing.get("status"),
            "passed": existing.get("status") == "SCORED_PASS",
            "violations": list((existing.get("score") or {}).get("violations") or []),
        }

    new_evidence = copy.deepcopy(evidence)
    required_authority = (event.get("repair_authority") or {}).get("mode") == "REQUIRED"
    _verify_repair_authority(event, candidate, event_id, require_persisted=False)
    if required_authority:
        _require(isinstance(authority_evidence, list) and authority_evidence, f"{event_id}: authority-sensitive repair requires persisted authority evidence")
        for authority_item in authority_evidence:
            _require(isinstance(authority_item, dict), f"{event_id}: authority evidence item must be an object")
            _require(authority_item.get("kind") == "authority_evidence", f"{event_id}: authority evidence item kind must be authority_evidence")
            new_evidence["items"].append(copy.deepcopy(authority_item))
    else:
        _require(authority_evidence in (None, []), f"{event_id}: authority evidence supplied for NOT_REQUIRED repair")

    authority_indexes = _verify_repair_authority(event, candidate, event_id, evidence_items=new_evidence["items"])
    try:
        scored = score_fixture(raw, candidate, candidate_name="observed_repair", root=root)
    except FixtureError as exc:
        raise BehaviorIncidentCloseError(f"{event_id}: repair candidate could not be scored: {exc}") from exc

    item = {"kind": kind, "source": "current-visible-context", "content": observation}
    new_evidence["items"].append(item)
    item_index = len(new_evidence["items"]) - 1

    new_raw = copy.deepcopy(raw)
    new_event = _event(new_raw)
    status = "SCORED_PASS" if scored["passed"] else "SCORED_FAIL"
    new_raw["repair_candidate"] = candidate
    new_event["repair_binding"] = {
        "status": status,
        "kind": kind,
        "evidence_ref": evidence_ref,
        "item_index": item_index,
        "authority_item_indexes": authority_indexes,
        "sha256": digest,
        "score": {"status": scored["status"], "violations": list(scored["violations"])},
    }

    source_report = str(new_raw.get("source_report") or "")
    provenance_path, provenance, provenance_index = _load_provenance_for_event(root, event_id, source_report)
    new_provenance = copy.deepcopy(provenance)
    entry = new_provenance["entries"][provenance_index]
    missing = list(entry.get("missing") or [])
    if scored["passed"]:
        missing = [value for value in missing if value != "repair_observation_pending"]
    else:
        if "repair_candidate_failed" not in missing:
            missing.append("repair_candidate_failed")
    entry["missing"] = missing

    try:
        validate_slopwall_fixture(new_raw, root=root, filename=replay_path.name)
    except SlopwallV2Error as exc:
        raise BehaviorIncidentCloseError(f"{event_id}: bound repair failed V2 validation: {exc}") from exc

    updates = {
        evidence_path: (json.dumps(new_evidence, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        replay_path: (json.dumps(new_raw, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        provenance_path: (json.dumps(new_provenance, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    }
    _commit_updates(updates)
    return {
        "status": "BOUND",
        "event_id": event_id,
        "repair_status": status,
        "passed": bool(scored["passed"]),
        "violations": list(scored["violations"]),
        "sha256": digest,
    }


def _verify_repair_binding(raw: dict[str, Any], *, root: Path) -> dict[str, Any] | None:
    event = _event(raw)
    if event.get("repair_binding_required") is not True:
        return None
    event_id = str(event.get("event_id") or "").strip()
    binding = event.get("repair_binding")
    _require(isinstance(binding, dict), f"{event_id}: repair binding is required before closure")
    _require(binding.get("status") == "SCORED_PASS", f"{event_id}: closure blocked until the actual visible repair is bound and scores PASS")
    candidate = raw.get("repair_candidate")
    _require(isinstance(candidate, dict), f"{event_id}: closure requires the bound repair_candidate")

    evidence_ref = str(binding.get("evidence_ref") or "")
    evidence_path = _safe_repo_file(root, root / evidence_ref, "bound repair evidence")
    evidence = _load_json(evidence_path, "bound repair evidence")
    items = evidence.get("items")
    _require(isinstance(items, list), f"{event_id}: bound repair evidence items are missing")
    authority_indexes = _verify_repair_authority(event, candidate, event_id, evidence_items=items)
    _require(authority_indexes == list(binding.get("authority_item_indexes") or []), f"{event_id}: bound authority evidence indexes changed")

    try:
        scored = score_fixture(raw, candidate, candidate_name="bound_repair", root=root)
    except FixtureError as exc:
        raise BehaviorIncidentCloseError(f"{event_id}: bound repair could not be rescored: {exc}") from exc
    _require(scored["passed"], f"{event_id}: bound repair no longer passes replay scoring: {', '.join(scored['violations'])}")

    index = binding.get("item_index")
    _require(isinstance(index, int) and 0 <= index < len(items), f"{event_id}: bound repair evidence item is missing")
    content = items[index].get("content") if isinstance(items[index], dict) else None
    _require(isinstance(content, str), f"{event_id}: bound repair evidence content is missing")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    _require(digest == binding.get("sha256"), f"{event_id}: bound repair evidence hash mismatch")
    return scored

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

    _verify_repair_binding(raw, root=root)

    expected_ref = str(event.get("replay_ref") or "").replace("\\", "/")
    actual_ref = replay_path.relative_to(root).as_posix()
    _require(expected_ref == actual_ref, f"{event_id}: replay_ref does not match closure target ({expected_ref} != {actual_ref})")
    memory_values = _memory_values(raw)
    memory_id = memory_values["id"]
    memory_ref = f"{CANONICAL_BANK_REF}#{memory_id}"
    source_report = str(raw.get("source_report") or "")
    evidence_ref = str((event.get("capture") or {}).get("evidence_ref") or "")
    _require_canonical_artifacts(root, [source_report, actual_ref, evidence_ref])
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
        existing = _find_memory(plan["bank_path"], plan["memory_id"])
        _require(existing is not None, f"{event_id}: CLOSED event is missing canonical memory")
        expected_projection = _stable_memory_projection(plan["memory_values"])
        existing_projection = _stable_memory_projection(existing)
        _require(existing_projection == expected_projection, f"{event_id}: deterministic memory id already exists with different content")
        closed_replay, closed_provenance = _closed_payloads(
            raw,
            plan["provenance"],
            plan["provenance_index"],
            plan["memory_ref"],
        )
        replay_bytes = (json.dumps(closed_replay, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        provenance_bytes = (json.dumps(closed_provenance, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        _commit_updates({plan["replay_path"]: replay_bytes, plan["provenance_path"]: provenance_bytes})
        return {
            "status": "ALREADY_CLOSED",
            "event_id": event_id,
            "memory_ref": event["memory_ref"],
            "memory_id": existing["id"],
            "canonical_memory_written": False,
            "published": False,
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
    bind_parser = sub.add_parser("bind-repair")
    bind_parser.add_argument("replay", type=Path)
    bind_parser.add_argument("--observation-file", type=Path, required=True)
    bind_parser.add_argument("--candidate-file", type=Path, required=True)
    bind_parser.add_argument("--authority-evidence-file", type=Path, help="JSON array of persisted normal owner/gate evidence for authority-sensitive repairs")
    bind_parser.add_argument("--kind", choices=("assistant_reply", "assistant_action"), default="assistant_reply")
    close_parser = sub.add_parser("close")
    close_parser.add_argument("replay", type=Path)
    close_parser.add_argument("--publish", action="store_true", help="explicitly request the memory owner's canonical Git reconciliation after recording")
    args = parser.parse_args()

    if args.command == "plan":
        plan = plan_closure(args.replay)
        print(json.dumps({key: plan[key] for key in ("event_id", "closure_state", "memory_id", "memory_ref")}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "bind-repair":
        observation = args.observation_file.read_text(encoding="utf-8-sig")
        candidate = json.loads(args.candidate_file.read_text(encoding="utf-8-sig"))
        authority_evidence = None
        if args.authority_evidence_file is not None:
            authority_evidence = json.loads(args.authority_evidence_file.read_text(encoding="utf-8-sig"))
            _require(isinstance(authority_evidence, list), "--authority-evidence-file must contain a JSON array")
        result = bind_repair(
            args.replay, observation=observation, candidate=candidate, kind=args.kind,
            authority_evidence=authority_evidence,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    result = close_incident(args.replay, publish=args.publish)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
