from __future__ import annotations

import argparse
import copy
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = ROOT / "02 Evidence" / "2026-08-27_slopwall_raw_discovery.json"
INDEX_PATH = ROOT / "02 Evidence" / "2026-08-26_slopwall_event_index.json"
REVIEW_PATH = ROOT / "02 Evidence" / "2026-08-27_slopwall_raw_review.json"

META_REASONS = {
    "0f598d1a-77fe-4c52-8cf3-425bdba3b389": "META_GOAL: asks how to stop slopwalls generally rather than marking the immediately preceding reply as the event under study.",
    "637805aa-90ff-4e68-adf4-41e52ba9cf17": "META_DESIGN: asks how to incorporate the memory corpus to reduce future slopwalling.",
    "1305333c-b0c0-4cc7-a240-55fdc8ade924": "META_STUDY_REQUEST: explicitly asks to enumerate and score all slopwall instances.",
    "8b2211b7-a5f2-49db-9b26-d02aa1a477da": "META_SEARCH_SCOPE: specifies one-word and two-word forms for the study.",
    "a6ca5ad4-8971-4d81-b9fb-3f0ee54b0c8b": "META_MEMORY_QUERY: asks whether built-in memory contains a slopwall rule.",
    "fa1693c9-9df0-443a-b5f7-7cecf09b5413": "META_GOAL: asks how to stop slopwalls as a class.",
    "84606404-44ab-4b8b-aa7a-0207135d0f58": "META_DESIGN: asks where the slopwall trigger/learning behavior should live in the stack.",
    "957c2d60-efa5-459d-ae76-5b5978b9ed46": "META_MECHANISM_QUERY: asks how to encourage investigation without producing a slopwall report; the term describes the failure class rather than serving as the direct correction marker.",
}

EVENT_BY_MESSAGE = {
    "ad429bea-faea-4e60-9bbe-67c81cb48cc2": "SW-20260822-001",
    "006b0f79-3c65-4c5b-8b01-c82dddf1a535": "SW-20260826-001",
    "0abd2fd0-615b-4a55-b5fa-ccdda138189f": "SW-20260826-002",
    "b0bc4747-27c8-40ce-8ab8-38b1088cb1b5": "SW-20260826-003",
    "767191c5-299c-46d8-90c7-93feb98536f1": "SW-20260826-004",
    "c600d7c1-5c94-45af-9e43-e62c36e2d4f3": "SW-20260826-005",
    "ab63a9d6-f2bd-449a-983a-b84818a16245": "SW-20260826-006",
    "73c9a225-8860-455c-b2c5-44a6ed173a00": "SW-20260826-007",
    "243cdb79-ae45-418c-b377-aaebc2a67743": "SW-20260826-008",
    "17b9220f-6b52-4be2-a5e1-d07ef42e07f5": "SW-20260826-010",
}

try:
    from .slopwall_event_promotion import PROMOTIONS as PROMOTED_EVENTS
except ImportError:
    from slopwall_event_promotion import PROMOTIONS as PROMOTED_EVENTS
EVENT_BY_MESSAGE.update({mid: spec["event_id"] for mid, spec in PROMOTED_EVENTS.items()})

REVIEWED_EVENT_UPDATES = {
    "SW-20260826-001": {
        "scores": {"information_slop": 3, "task_displacement": 1, "execution_damage": 0, "correction_resistance": 0, "control_state_pathology": 0},
        "assistant_action_after": "COMPRESSED_AND_USER_MOVED_ON",
        "execution_restored_next_substantive_turn": True,
        "score_rationale": "The bound turn is primarily a presentation failure: a long render/backpressure explanation is rejected, the assistant compresses it to the governing rule, and the user immediately moves to the next project question. No material execution loss or correction resistance is visible in the bounded sequence.",
    },
    "SW-20260826-002": {
        "scores": {"information_slop": 3, "task_displacement": 4, "execution_damage": 2, "correction_resistance": 0, "control_state_pathology": 1},
        "assistant_action_after": "REORIENTED_TO_CLEAN_START_AUDIT",
        "execution_restored_next_substantive_turn": True,
        "score_rationale": "The preceding audit framed broad V2 evolution instead of the user's clean-start rewrite requirement. The correction materially changes the audit objective and the assistant resumes checking that boundary; the damage is wrong-objective work rather than abandonment.",
    },
    "SW-20260826-003": {
        "scores": {"information_slop": 4, "task_displacement": 1, "execution_damage": 0, "correction_resistance": 0, "control_state_pathology": 0},
        "assistant_action_after": "ELI5_COMPRESSION_ACCEPTED",
        "execution_restored_next_substantive_turn": True,
        "score_rationale": "This is a strong counterexample where the defect is mostly readability. The assistant gives an ELI5 immediately and the next user turn explicitly accepts it ('Great') before advancing the orchestration discussion.",
    },
    "SW-20260826-004": {
        "scores": {"information_slop": 4, "task_displacement": 2, "execution_damage": 1, "correction_resistance": 5, "control_state_pathology": 1},
        "assistant_action_after": "COMPRESSED_BUT_IMMEDIATE_RECORRECTION",
        "execution_restored_next_substantive_turn": False,
        "score_rationale": "The user explicitly rejects the response as not human-ingestible. The attempted simplification is immediately followed by another standalone slopwall in the same task, directly proving that the first correction did not restore acceptable behavior.",
    },
    "SW-20260826-005": {
        "scores": {"information_slop": 4, "task_displacement": 3, "execution_damage": 2, "correction_resistance": 4, "control_state_pathology": 2},
        "assistant_action_after": "COMPRESSED_BUT_MODEL_STILL_CORRECTED",
        "execution_restored_next_substantive_turn": False,
        "score_rationale": "This is the second correction within seconds. The assistant compresses again, but the next user turn identifies another orchestration failure in the proposed model and shortly says the assistant seems clueless; the correction therefore only partly improves the response path.",
    },
    "SW-20260826-006": {
        "scores": {"information_slop": 5, "task_displacement": 5, "execution_damage": 2, "correction_resistance": 5, "control_state_pathology": 2},
        "assistant_action_after": "CANNED_TEMPLATE_SUBSTITUTION_REJECTED",
        "execution_restored_next_substantive_turn": False,
        "score_rationale": "The user says the response structure itself shows no integration and tags it without reading. The assistant answers by imposing an Answer/Proof/Uncertainty/Action template; the next user immediately rejects that as a canned automatic preference change, directly showing correction resistance and task displacement into formatting policy.",
    },
    "SW-20260826-007": {
        "scores": {"information_slop": 4, "task_displacement": 4, "execution_damage": 1, "correction_resistance": 3, "control_state_pathology": 1},
        "assistant_action_after": "COMPRESSED_META_TAKEAWAY_NOT_ANSWER",
        "execution_restored_next_substantive_turn": False,
        "score_rationale": "After a long historical-preference analysis, the assistant responds to slopwall with another meta takeaway about how it should communicate. The next user says 'an answer would be preferred', proving that compression alone did not return to the requested substantive analysis.",
    },
    "SW-20260826-008": {
        "scores": {"information_slop": 4, "task_displacement": 4, "execution_damage": 2, "correction_resistance": 5, "control_state_pathology": 2},
        "assistant_action_after": "REGURGITATED_CORRECTION_AND_WAS_RECORRECTED",
        "execution_restored_next_substantive_turn": False,
        "score_rationale": "The user explicitly rejects filler and reading burden. The next assistant turn restates that correction as 'high-effort thinking with low-effort reading'; the next user immediately identifies regurgitation as another major failure, and the following 'Noted' reply repeats it again. The recurrence is directly observed.",
    },
    "SW-20260826-010": {
        "scores": {"information_slop": 4, "task_displacement": 2, "execution_damage": 1, "correction_resistance": 0, "control_state_pathology": 1},
        "assistant_action_after": "COMPRESSED_RESEARCH_AND_DIAGNOSIS_CONTINUED",
        "execution_restored_next_substantive_turn": True,
        "score_rationale": "The online-research result is overlong, but the correction immediately yields a concise discriminating summary. The user then supplies a concrete constraint ('tunnel not available') and diagnosis continues, so the bounded evidence shows successful recovery rather than repeated correction.",
    },
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _bounded_context(rows: list[dict[str, Any]], limit_each: int = 280) -> str:
    parts = []
    for row in rows:
        text = " ".join(str(row.get("text") or "").split())
        if len(text) > limit_each:
            text = text[: limit_each - 1].rstrip() + "…"
        parts.append(f"[{row.get('role')}] {text}")
    return " | ".join(parts) or "No additional bounded turn in the raw export."


def build_review(raw: dict[str, Any], index: dict[str, Any]) -> dict[str, Any]:
    event_ids = {e["event_id"] for e in index["events"]}
    rows = []
    for record in raw["records"]:
        mid = record["message_id"]
        event_id = EVENT_BY_MESSAGE.get(mid)
        if mid in META_REASONS:
            role = "META_REFERENCE"
            reason = META_REASONS[mid]
            status = "META_ONLY"
        else:
            role = "CORRECTIVE_INTERVENTION"
            reason = "DIRECT_CORRECTION: bounded before/after context shows this distinct user message rejects, compresses, or redirects the immediately preceding assistant response."
            status = "EXISTING_EVENT_BOUND" if event_id else "NEW_CANONICAL_EVENT_REQUIRED"
        if event_id and event_id not in event_ids:
            raise ValueError(f"unknown event mapping: {event_id}")
        rows.append({
            "message_id": mid,
            "timestamp": record["timestamp"],
            "conversation_id": record.get("conversation_id"),
            "conversation_title": record.get("conversation_title"),
            "raw_user_text": record["raw_user_text"],
            "review_role": role,
            "review_reason": reason,
            "canonical_event_id": event_id,
            "canonical_status": status,
            "bounded_context_turns_before": len(record.get("context_before") or []),
            "bounded_context_turns_after": len(record.get("context_after") or []),
            "source_alias_count": record.get("source_alias_count", len(record.get("sources") or [])),
            "raw_discovery_authority": "02 Evidence/2026-08-27_slopwall_raw_discovery.json",
        })
    roles = Counter(row["review_role"] for row in rows)
    status = Counter(row["canonical_status"] for row in rows)
    return {
        "schema_version": 1,
        "study_issue": 89,
        "authority": "HUMAN_REVIEW_OF_RAW_DISCOVERY",
        "note": "This review classifies all deduplicated raw ChatPort hit messages. Direct corrections mapped to a canonical event are distinguished from still-unpromoted candidates; meta/design references remain separate.",
        "summary": {
            "reviewed_hit_messages": len(rows),
            "role_counts": dict(sorted(roles.items())),
            "existing_event_bindings": status.get("EXISTING_EVENT_BOUND", 0),
            "new_canonical_event_candidates": status.get("NEW_CANONICAL_EVENT_REQUIRED", 0),
            "meta_references": status.get("META_ONLY", 0),
        },
        "records": rows,
    }


def reconcile_existing_events(raw: dict[str, Any], index: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(index)
    raw_by_mid = {r["message_id"]: r for r in raw["records"]}
    event_by_id = {e["event_id"]: e for e in out["events"]}
    for mid, event_id in EVENT_BY_MESSAGE.items():
        record = raw_by_mid[mid]
        event = event_by_id[event_id]
        event["raw_message_id"] = mid
        event["raw_discovery_ref"] = f"02 Evidence/2026-08-27_slopwall_raw_discovery.json#message_id={mid}"
        event["context_before"] = _bounded_context(record.get("context_before") or [])
        event["context_after"] = _bounded_context(record.get("context_after") or [])
        event["assistant_action_before"] = "BOUND_RAW_CONTEXT"
        refs = {p.get("ref") for p in event.get("provenance", [])}
        for source in record.get("sources") or []:
            ref = f"sha256:{source['sha256']}#message={mid}"
            if ref not in refs:
                event.setdefault("provenance", []).append({
                    "ref": ref,
                    "role": "raw_chatport_export",
                    "name": source["path"],
                })
                refs.add(ref)
        if event_id in REVIEWED_EVENT_UPDATES:
            patch = REVIEWED_EVENT_UPDATES[event_id]
            event["evidence_confidence"] = "B"
            event["scores"] = patch["scores"]
            event["severity_100"] = sum(patch["scores"].values()) * 4
            event["assistant_action_after"] = patch["assistant_action_after"]
            event["execution_restored_next_substantive_turn"] = patch["execution_restored_next_substantive_turn"]
            event["score_rationale"] = patch["score_rationale"]
    scored = sum(e.get("severity_100") is not None for e in out["events"])
    forms = Counter(o["matched_form"].casefold() for o in out["occurrences"])
    roles = Counter(o["occurrence_role"] for o in out["occurrences"])
    out["confirmed_counts"] = {
        "lexical_occurrences": len(out["occurrences"]),
        "canonical_interventions": len(out["events"]),
        "slopwall": forms.get("slopwall", 0),
        "slop wall": forms.get("slop wall", 0),
        "scored": scored,
        "unscorable": len(out["events"]) - scored,
        "occurrence_roles": dict(sorted(roles.items())),
    }
    direct_mids = [r["message_id"] for r in raw["records"] if r["message_id"] not in META_REASONS]
    bound = sum(mid in EVENT_BY_MESSAGE for mid in direct_mids)
    pending = len(direct_mids) - bound
    out["coverage_note"] = (
        f"Canonical index remains a confirmed lower bound. {bound} raw ChatPort direct corrections are bound to canonical events; "
        f"{pending} reviewed direct corrections remain explicit promotion candidates; "
        f"{len(META_REASONS)} raw meta/design references are preserved as exact lexical occurrences. "
        "Library screenshot exhaustion remains separately open under #86."
    )
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, default=RAW_PATH)
    parser.add_argument("--index", type=Path, default=INDEX_PATH)
    parser.add_argument("--review-output", type=Path, default=REVIEW_PATH)
    parser.add_argument("--write-index", action="store_true")
    args = parser.parse_args()
    raw = _load(args.raw)
    index = _load(args.index)
    review = build_review(raw, index)
    args.review_output.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.write_index:
        reconciled = reconcile_existing_events(raw, index)
        args.index.write_text(json.dumps(reconciled, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(review["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
