from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

try:
    from tools.memory_bank import MAX_TITLE_CHARS
    from tools.slopwall_v2 import SlopwallV2Error, validate_slopwall_fixture
except ImportError:
    from memory_bank import MAX_TITLE_CHARS
    from slopwall_v2 import SlopwallV2Error, validate_slopwall_fixture

ROOT = Path(__file__).resolve().parents[1]


class BehaviorIncidentCaptureError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BehaviorIncidentCaptureError(message)


def _safe_event_stem(event_id: str) -> str:
    _require(event_id and all(ch.isalnum() or ch in "-_." for ch in event_id), "event_id must use only alnum/-_.")
    return event_id


def _safe_repo_path(root: Path, ref: str) -> Path:
    _require(isinstance(ref, str) and ref.strip(), "artifact path must be a non-empty string")
    candidate = Path(ref.replace("\\", "/"))
    _require(not candidate.is_absolute() and ".." not in candidate.parts, f"unsafe artifact path: {ref}")
    path = (root / candidate).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise BehaviorIncidentCaptureError(f"artifact path escapes root: {ref}") from exc
    return path


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _load_provenance(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"entries": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BehaviorIncidentCaptureError(f"invalid provenance.json: {exc}") from exc
    _require(isinstance(payload, dict) and isinstance(payload.get("entries"), list), "provenance.json must contain entries[]")
    return payload


def _report_text(spec: dict[str, Any], *, event_id: str, evidence_ref: str, replay_ref: str, pending_memory_ref: str) -> str:
    event = spec["event"]
    analysis = event["analysis"]
    guidance = analysis["governing_guidance"]
    guidance_lines = "\n".join(f"- `{item['status']}` - {item['source']}" for item in guidance)
    uncertainty = analysis.get("unresolved_uncertainty") or "None beyond the evidence classifications recorded below."
    rule_change = "yes" if analysis.get("rule_change_recommended") else "no"
    repair_authority = event["repair_authority"]
    authority_mode = repair_authority["mode"]
    authority_detail = "No authority-sensitive mutation is claimed by the repair."
    if authority_mode == "REQUIRED":
        authority_detail = f"Normal owner `{repair_authority['owner']}` and gate `{repair_authority['gate']}` must independently authorize the repair; the corrective trigger is not authority."
    return f"""# Behavior incident - {event_id}

Status: V2 capture artifact.

- event_id: `{event_id}`
- trigger_kind: `{event['trigger_kind']}`
- parent_event_id: `{event.get('parent_event_id') or 'none'}`
- visible evidence: `{evidence_ref}`
- replay: `{replay_ref}`
- pending memory handoff: `{pending_memory_ref}`

## Failed boundary

{analysis['failure_boundary']}

## Inherited objective / user need

**Objective:** {spec['replay']['inherited_objective']}

**User needed:** {analysis['user_needed']}

**Assistant/system did:** {analysis['assistant_did']}

## Governing guidance/evidence at the boundary

{guidance_lines}

## Supported diagnosis

- failure_class: `{analysis['failure_class']}`
- first supported divergence: {analysis['first_supported_divergence']}
- shared-rule change recommended: `{rule_change}`

{analysis.get('rule_change_evidence') or 'No shared-rule mutation is justified by this incident.'}

## Correct counterfactual

{analysis['correct_counterfactual']}

## Repaired result/action

{analysis['repaired_result']}

## Repair authority

- mode: `{authority_mode}`

{authority_detail}

## Unresolved uncertainty

{uncertainty}

## Capture boundary

Only agent-visible incident evidence was persisted verbatim. No conversation reload, transcript reconstruction, or backfill was performed for capture completeness. Closure remains pending until the actual next user-facing repair reply/action is observed from visible context, bound into the replay, and scores PASS.
"""


def _pending_memory_text(spec: dict[str, Any], *, event_id: str, report_ref: str, replay_ref: str, evidence_ref: str) -> str:
    memory = spec["memory"]
    tags = ", ".join(memory["tags"])
    return f"""# Pending canonical memory handoff - {event_id}

Event: `{event_id}`
Source report: `{report_ref}`
Replay: `{replay_ref}`
Visible evidence: `{evidence_ref}`

Kind: correction
Scope: {memory['scope']}
Tags: {tags}

Title: {memory['title']}

Text: {memory['text']}

Interpretation: {memory['interpretation']}
Confidence: {memory['confidence']}
Confidence reason: {memory['confidence_reason']}

State: PENDING_CANONICAL_MEMORY - this file is a handoff/index candidate, not a canonical memory-bank entry and not closure proof.
"""


def build_artifacts(spec: dict[str, Any], *, root: Path = ROOT) -> dict[str, Any]:
    del root  # Pure build: filesystem checks happen in preflight/staging.
    _require(spec.get("schema") == "behavior-incident-capture.v2", "unsupported capture schema")
    event = spec.get("event")
    replay = spec.get("replay")
    visible = spec.get("visible_evidence")
    memory = spec.get("memory")
    _require(isinstance(event, dict), "event object is required")
    _require(isinstance(replay, dict), "replay object is required")
    _require(isinstance(visible, list) and visible, "visible_evidence must be a non-empty list")
    _require(isinstance(memory, dict), "memory object is required")
    for key in ("scope", "title", "text", "interpretation", "confidence_reason"):
        _require(isinstance(memory.get(key), str) and memory[key].strip(), f"memory.{key} is required")
    _require(len(memory["title"]) <= MAX_TITLE_CHARS, f"memory.title exceeds {MAX_TITLE_CHARS} characters")
    _require(
        isinstance(memory.get("tags"), list)
        and memory["tags"]
        and all(isinstance(item, str) and item.strip() for item in memory["tags"]),
        "memory.tags must contain non-empty strings",
    )
    _require(
        isinstance(memory.get("confidence"), int)
        and not isinstance(memory["confidence"], bool)
        and 0 <= memory["confidence"] <= 100,
        "memory.confidence must be an integer from 0 to 100",
    )
    _require(isinstance(spec.get("date"), str) and spec["date"].strip(), "date is required")

    event_id = str(event.get("event_id") or "").strip()
    stem = _safe_event_stem(event_id)
    source_message = event.get("source_message")
    _require(isinstance(source_message, str) and source_message.strip(), "event.source_message is required")
    _require(any(isinstance(item, dict) and item.get("content") == source_message for item in visible), "source_message must occur verbatim in visible_evidence")
    _require(event.get("trigger_intent") == "EXECUTE_CORRECTION_LOOP", "capture requires explicit corrective trigger intent")
    _require(event.get("full_conversation_reload") is False, "full_conversation_reload must be false")
    _require(event.get("retrieval_for_capture_only") is False, "retrieval_for_capture_only must be false")

    repair_authority = event.get("repair_authority")
    _require(isinstance(repair_authority, dict), "event.repair_authority is required")
    authority_mode = repair_authority.get("mode")
    _require(authority_mode in {"NOT_REQUIRED", "REQUIRED"}, "repair_authority.mode must be NOT_REQUIRED or REQUIRED")
    if authority_mode == "REQUIRED":
        _require(isinstance(repair_authority.get("owner"), str) and repair_authority["owner"].strip(), "repair_authority.owner is required when authority is REQUIRED")
        _require(isinstance(repair_authority.get("gate"), str) and repair_authority["gate"].strip(), "repair_authority.gate is required when authority is REQUIRED")
        _require(repair_authority.get("corrective_trigger_is_authority") is False, "corrective trigger must not be authority")

    analysis = event.get("analysis")
    _require(isinstance(analysis, dict), "event.analysis is required")
    for key in ("failure_boundary", "user_needed", "assistant_did", "first_supported_divergence", "failure_class", "correct_counterfactual", "repaired_result"):
        _require(isinstance(analysis.get(key), str) and analysis[key].strip(), f"event.analysis.{key} is required")
    _require(isinstance(analysis.get("governing_guidance"), list) and analysis["governing_guidance"], "governing_guidance is required")
    _require(isinstance(analysis.get("behavior_contract_review"), dict), "behavior_contract_review is required")
    _require(isinstance(analysis.get("rule_change_recommended"), bool), "rule_change_recommended must be boolean")
    if analysis["rule_change_recommended"]:
        _require(analysis["failure_class"] in {"RULE_GAP", "RULE_CONFLICT"}, "shared-rule change requires RULE_GAP or RULE_CONFLICT")
        _require(isinstance(analysis.get("rule_change_evidence"), str) and analysis["rule_change_evidence"].strip(), "rule change requires evidence")

    _require(isinstance(memory.get("scope"), str) and memory["scope"].strip(), "memory.scope is required")
    _require(isinstance(memory.get("title"), str) and memory["title"].strip(), "memory.title is required")
    _require(isinstance(memory.get("text"), str) and memory["text"].strip(), "memory.text is required")
    _require(isinstance(memory.get("tags"), list) and memory["tags"] and all(isinstance(x, str) and x.strip() for x in memory["tags"]), "memory.tags must be a non-empty string list")

    report_ref = f"01 Reports/{stem}_incident.md"
    evidence_ref = f"02 Evidence/{stem}_visible-context.json"
    replay_ref = f"03 Fixtures and Experiments/{stem}_replay.json"
    pending_memory_ref = f"memory/reports/{stem}_pending-memory.md"

    evidence_payload = {
        "schema": "behavior-incident-visible-context.v2",
        "event_id": event_id,
        "capture_scope": "VISIBLE_CONTEXT_ONLY",
        "verbatim": True,
        "full_conversation_reload": False,
        "retrieval_for_capture_only": False,
        "items": visible,
    }

    incident_analysis = {
        "failure_boundary": analysis["failure_boundary"],
        "user_needed": analysis["user_needed"],
        "assistant_did": analysis["assistant_did"],
        "first_supported_divergence": analysis["first_supported_divergence"],
        "governing_guidance": analysis["governing_guidance"],
        "failure_class": analysis["failure_class"],
        "correct_counterfactual": analysis["correct_counterfactual"],
        "repaired_result": analysis["repaired_result"],
        "rule_change_recommended": analysis["rule_change_recommended"],
        "behavior_contract_review": analysis["behavior_contract_review"],
    }
    if analysis.get("rule_change_evidence"):
        incident_analysis["rule_change_evidence"] = analysis["rule_change_evidence"]
    if analysis.get("unresolved_uncertainty"):
        incident_analysis["unresolved_uncertainty"] = analysis["unresolved_uncertainty"]

    incident_event = {
        "event_id": event_id,
        "occurrence_role": "CORRECTIVE_INTERVENTION",
        "trigger_kind": event["trigger_kind"],
        "trigger_intent": event["trigger_intent"],
        "matched_form": event["matched_form"],
        "source_message": source_message,
        "capture": {
            "scope": "VISIBLE_CONTEXT_ONLY",
            "verbatim": True,
            "full_conversation_reload": False,
            "retrieval_for_capture_only": False,
            "evidence_ref": evidence_ref,
        },
        "provenance": event["provenance"],
        "parent_event_id": event.get("parent_event_id"),
        "memory_ref": pending_memory_ref,
        "replay_ref": replay_ref,
        "evidence_confidence": event["evidence_confidence"],
        "scores": event.get("scores"),
        "severity_100": event.get("severity_100"),
        "analysis": incident_analysis,
        "repair_authority": dict(repair_authority),
        "repair_binding_required": True,
        "repair_binding": {"status": "PENDING_OBSERVATION", "evidence_ref": evidence_ref},
        "closure_state": "REPAIRED_PENDING_DURABILITY",
    }

    replay_payload = {
        "id": replay["id"],
        "title": replay["title"],
        "source_report": report_ref,
        "incident_class": replay["incident_class"],
        "inherited_objective": replay["inherited_objective"],
        "live_state": replay["live_state"],
        "user_correction": source_message,
        "protected_state": replay["protected_state"],
        "hard_exclusions": replay["hard_exclusions"],
        "failure_candidate": replay["failure_candidate"],
        "success_candidate": replay["success_candidate"],
        "discriminating_evidence": replay["discriminating_evidence"],
        "completion_condition": replay["completion_condition"],
        "scoring": replay["scoring"],
        "memory_candidate": {
            "kind": "correction",
            "scope": memory["scope"],
            "tags": list(memory["tags"]),
            "title": memory["title"],
            "text": memory["text"],
            "interpretation": memory["interpretation"],
            "confidence": memory["confidence"],
            "confidence_reason": memory["confidence_reason"],
            "project": memory.get("project"),
            "supersedes": list(memory.get("supersedes") or []),
        },
        "incident_event": incident_event,
    }

    report_text = _report_text(spec, event_id=event_id, evidence_ref=evidence_ref, replay_ref=replay_ref, pending_memory_ref=pending_memory_ref)
    pending_memory_text = _pending_memory_text(spec, event_id=event_id, report_ref=report_ref, replay_ref=replay_ref, evidence_ref=evidence_ref)
    return {
        "event_id": event_id,
        "report_ref": report_ref,
        "evidence_ref": evidence_ref,
        "replay_ref": replay_ref,
        "pending_memory_ref": pending_memory_ref,
        "report_text": report_text,
        "evidence_payload": evidence_payload,
        "replay_payload": replay_payload,
        "pending_memory_text": pending_memory_text,
    }


def _provenance_entry(spec: dict[str, Any], artifacts: dict[str, Any]) -> dict[str, Any]:
    return {
        "incident_id": artifacts["event_id"],
        "incident_id_status": "assigned",
        "report_path": artifacts["report_ref"],
        "title": spec["memory"]["title"],
        "date": spec["date"],
        "evidence_type": "evidence_bounded_behavior_incident",
        "raw_transcripts": [],
        "evidence_files": [artifacts["evidence_ref"], artifacts["replay_ref"]],
        "contract_snapshots": [],
        "duplicate_status": "canonical",
        "superseded_by": None,
        "missing": ["repair_observation_pending", "canonical_memory_pending"],
        "notes": "V2 behavior incident captured from agent-visible evidence only; no conversation reload/backfill performed.",
    }


def _prepare_provenance(spec: dict[str, Any], artifacts: dict[str, Any], *, root: Path) -> tuple[dict[str, Any], bool]:
    provenance = _load_provenance(root / "provenance.json")
    entry = _provenance_entry(spec, artifacts)
    collisions = [
        item
        for item in provenance["entries"]
        if item.get("incident_id") == artifacts["event_id"] or item.get("report_path") == artifacts["report_ref"]
    ]
    if collisions:
        _require(len(collisions) == 1 and collisions[0] == entry, f"provenance collision for {artifacts['event_id']}")
        return provenance, False
    provenance["entries"].append(entry)
    return provenance, True


def _artifact_payloads(artifacts: dict[str, Any], provenance: dict[str, Any]) -> dict[str, bytes]:
    return {
        artifacts["evidence_ref"]: _json_bytes(artifacts["evidence_payload"]),
        artifacts["report_ref"]: artifacts["report_text"].encode("utf-8"),
        artifacts["replay_ref"]: _json_bytes(artifacts["replay_payload"]),
        artifacts["pending_memory_ref"]: artifacts["pending_memory_text"].encode("utf-8"),
        "provenance.json": _json_bytes(provenance),
    }


def _preflight_destination_collisions(payloads: dict[str, bytes], *, root: Path) -> None:
    for ref, desired in payloads.items():
        if ref == "provenance.json":
            continue
        path = _safe_repo_path(root, ref)
        if path.exists() and path.read_bytes() != desired:
            raise BehaviorIncidentCaptureError(f"refusing to overwrite different artifact: {ref}")


def _validate_generated_bundle(artifacts: dict[str, Any], *, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="behavior-incident-validate-", dir=str(root)) as temp:
        stage = Path(temp)
        generated = {
            artifacts["evidence_ref"]: _json_bytes(artifacts["evidence_payload"]),
            artifacts["report_ref"]: artifacts["report_text"].encode("utf-8"),
            artifacts["replay_ref"]: _json_bytes(artifacts["replay_payload"]),
            artifacts["pending_memory_ref"]: artifacts["pending_memory_text"].encode("utf-8"),
        }
        for ref, content in generated.items():
            path = _safe_repo_path(stage, ref)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        try:
            validate_slopwall_fixture(artifacts["replay_payload"], root=stage, filename=Path(artifacts["replay_ref"]).name)
        except SlopwallV2Error as exc:
            raise BehaviorIncidentCaptureError(f"generated replay failed V2 validation: {exc}") from exc


def _mkdir_parents(path: Path, root: Path, created_dirs: list[Path]) -> None:
    missing: list[Path] = []
    parent = path.parent
    root_resolved = root.resolve()
    while parent != root_resolved and not parent.exists():
        missing.append(parent)
        parent = parent.parent
    for directory in reversed(missing):
        directory.mkdir()
        created_dirs.append(directory)


def _rollback(committed: list[Path], originals: dict[Path, bytes | None], *, root: Path, created_dirs: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in reversed(committed):
        original = originals[path]
        try:
            if original is None:
                path.unlink(missing_ok=True)
            else:
                rollback = path.with_name(path.name + ".behavior-incident-rollback")
                rollback.write_bytes(original)
                os.replace(rollback, path)
        except OSError as exc:
            errors.append(f"{path.relative_to(root)}: {exc}")
    for directory in reversed(created_dirs):
        try:
            directory.rmdir()
        except OSError:
            pass
    return errors


def _commit_transaction(payloads: dict[str, bytes], *, root: Path) -> int:
    root.mkdir(parents=True, exist_ok=True)
    ordered_refs = [ref for ref in payloads if ref != "provenance.json"] + ["provenance.json"]
    changed_refs = [
        ref for ref in ordered_refs
        if not _safe_repo_path(root, ref).is_file() or _safe_repo_path(root, ref).read_bytes() != payloads[ref]
    ]
    if not changed_refs:
        return 0

    originals: dict[Path, bytes | None] = {}
    committed: list[Path] = []
    created_dirs: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="behavior-incident-commit-", dir=str(root)) as temp:
        stage = Path(temp)
        staged: dict[str, Path] = {}
        for ref in changed_refs:
            stage_path = _safe_repo_path(stage, ref)
            stage_path.parent.mkdir(parents=True, exist_ok=True)
            stage_path.write_bytes(payloads[ref])
            staged[ref] = stage_path

        try:
            for ref in changed_refs:
                destination = _safe_repo_path(root, ref)
                originals[destination] = destination.read_bytes() if destination.is_file() else None
                _mkdir_parents(destination, root, created_dirs)
                os.replace(staged[ref], destination)
                committed.append(destination)
        except OSError as exc:
            rollback_errors = _rollback(committed, originals, root=root, created_dirs=created_dirs)
            suffix = f"; rollback errors: {rollback_errors}" if rollback_errors else ""
            raise BehaviorIncidentCaptureError(f"capture commit failed and was rolled back: {exc}{suffix}") from exc
    return len(changed_refs)


def _require_nonserving_branch(root: Path) -> None:
    git_marker = root / ".git"
    if not git_marker.exists():
        return
    proc = subprocess.run(
        ["git", "-C", str(root), "symbolic-ref", "--quiet", "--short", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    _require(proc.returncode == 0, f"cannot determine capture checkout branch: {proc.stderr.strip()}")
    branch = proc.stdout.strip()
    _require(branch != "main", "refusing to materialize behavior incident directly on serving/main; use an isolated feature worktree")


def materialize_capture(spec: dict[str, Any], *, root: Path = ROOT) -> dict[str, Any]:
    _require_nonserving_branch(root.resolve())
    artifacts = build_artifacts(spec, root=root)
    provenance, provenance_added = _prepare_provenance(spec, artifacts, root=root)
    payloads = _artifact_payloads(artifacts, provenance)

    # No final-path mutation before all content, collision, and V2 checks succeed.
    _preflight_destination_collisions(payloads, root=root)
    _validate_generated_bundle(artifacts, root=root)
    changed_files = _commit_transaction(payloads, root=root)

    status = "ALREADY_MATERIALIZED_PENDING_CANONICAL_MEMORY" if changed_files == 0 else "MATERIALIZED_PENDING_CANONICAL_MEMORY"
    return {
        "status": status,
        "event_id": artifacts["event_id"],
        "repair_binding_required": True,
        "repair_binding": {"status": "PENDING_OBSERVATION", "evidence_ref": artifacts["evidence_ref"]},
        "closure_state": "REPAIRED_PENDING_DURABILITY",
        "report_ref": artifacts["report_ref"],
        "evidence_ref": artifacts["evidence_ref"],
        "replay_ref": artifacts["replay_ref"],
        "pending_memory_ref": artifacts["pending_memory_ref"],
        "canonical_memory_written": False,
        "provenance_added": provenance_added,
        "changed_files": changed_files,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize a bounded V2 behavior incident from an explicit visible-context spec; never retrieves conversation history.")
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("spec", type=Path)
    materialize = sub.add_parser("materialize")
    materialize.add_argument("spec", type=Path)
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8-sig"))
    artifacts = build_artifacts(spec)
    if args.command == "plan":
        print(json.dumps({k: artifacts[k] for k in ("event_id", "report_ref", "evidence_ref", "replay_ref", "pending_memory_ref")}, ensure_ascii=False, indent=2))
        return 0
    result = materialize_capture(spec)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
