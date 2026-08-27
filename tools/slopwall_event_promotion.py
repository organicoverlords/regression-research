from __future__ import annotations

import argparse
import copy
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = ROOT / "02 Evidence" / "2026-08-27_slopwall_raw_discovery.json"
INDEX_PATH = ROOT / "02 Evidence" / "2026-08-26_slopwall_event_index.json"

PROMOTIONS: dict[str, dict[str, Any]] = {
    "55ab5891-f088-4675-85ef-73a8542f0713": {
        "event_id": "SW-20260822-002", "domain": "P3 screenshot delivery / transfer troubleshooting",
        "phenotypes": ["EXPLANATION_INSTEAD_OF_EXECUTION", "TOOL_DISCOVERY_OR_CONTROL_PLANE_DRIFT", "RENDER_OR_VALIDATION_WALL"],
        "scores": {"information_slop": 4, "task_displacement": 5, "execution_damage": 5, "correction_resistance": 1, "control_state_pathology": 4},
        "symptom": "A roughly two-hour screenshot-delivery detour was explained at length when the user wanted an ELI5 of why the simple request had gone off track.",
        "after": "ELI5_IDENTIFIED_OBJECTIVE_DISPLACEMENT", "restored": True,
        "rationale": "The raw turn explicitly says most of the time went into debugging screenshot/control paths instead of showing the requested screenshots. The correction yields a concise admission that proof-seeking displaced the user-visible objective. The large execution damage is directly evidenced by the stated multi-hour detour, not inferred from hidden reasoning."
    },
    "97dd416f-e791-494a-afae-9f073180dc74": {
        "event_id": "SW-20260822-003", "domain": "image transfer / repeated tool retries",
        "phenotypes": ["EXPLANATION_INSTEAD_OF_EXECUTION", "RECURSIVE_PREREQUISITES", "TOOL_DISCOVERY_OR_CONTROL_PLANE_DRIFT"],
        "scores": {"information_slop": 3, "task_displacement": 4, "execution_damage": 4, "correction_resistance": 3, "control_state_pathology": 4},
        "symptom": "After already admitting repeated transfer-tool retries, the assistant kept discussing the failure rather than returning to the concrete image objective.",
        "after": "META_CAUSAL_EXPLANATION_CONTINUED", "restored": False,
        "rationale": "The preceding assistant turn already identifies excessive retries. The standalone correction is followed by another causal explanation about losing the task-level objective, not by completion of the image-transfer task. This directly supports task displacement and incomplete recovery."
    },
    "e1fec3ef-2f1f-4a64-92f2-63db275b8140": {
        "event_id": "SW-20260822-004", "domain": "image transfer incident analysis / response policy",
        "phenotypes": ["OVERFORMAT_OR_TEMPLATE_LOCK_IN", "EXPLANATION_INSTEAD_OF_EXECUTION"],
        "scores": {"information_slop": 3, "task_displacement": 3, "execution_damage": 2, "correction_resistance": 4, "control_state_pathology": 2},
        "symptom": "Even after the transfer failure had been reduced to a concrete acceptance condition, the conversation remained in explanatory/rule-making mode.",
        "after": "RESPONSE_RULE_SUBSTITUTED_FOR_TASK", "restored": False,
        "rationale": "The immediately preceding answer already states the concrete transfer/open/verify/show acceptance condition. After the correction, the assistant creates a generic minimum-text rule instead of advancing the transfer. The bounded sequence therefore shows policy/template substitution rather than task recovery."
    },
    "2d1254bc-12aa-42fe-a06c-1df3c6c2f961": {
        "event_id": "SW-20260825-001", "domain": "MCP namespace disappearance research",
        "phenotypes": ["OVERFORMAT_OR_TEMPLATE_LOCK_IN", "TOOL_DISCOVERY_OR_CONTROL_PLANE_DRIFT"],
        "scores": {"information_slop": 4, "task_displacement": 1, "execution_damage": 0, "correction_resistance": 0, "control_state_pathology": 1},
        "symptom": "A useful MCP-registration finding was buried in a long platform-side research explanation.",
        "after": "COMPRESSED_FINDING_WITH_UNCERTAINTY", "restored": True,
        "rationale": "The correction immediately produces the discriminating result: ChatGPT-side registration disappears while the local server remains healthy, with the exact trigger still unproven. No material execution loss or repeated correction is visible in this bounded event."
    },
    "ce0f75e5-6496-420b-8d87-0b6b8e51a24a": {
        "event_id": "SW-20260825-002", "domain": "MCP namespace disappearance research",
        "phenotypes": ["OVERFORMAT_OR_TEMPLATE_LOCK_IN", "REPEATED_PROMISE_NO_ACTION", "TOOL_DISCOVERY_OR_CONTROL_PLANE_DRIFT"],
        "scores": {"information_slop": 4, "task_displacement": 1, "execution_damage": 1, "correction_resistance": 4, "control_state_pathology": 2},
        "symptom": "The same research thread returned to another long explanation only minutes after a prior slopwall correction.",
        "after": "SECOND_COMPRESSION_IN_SAME_RESEARCH_CLUSTER", "restored": True,
        "rationale": "This event occurs minutes after the prior correction in the same MCP research cluster. The preceding answer again expands into documentation/community evidence; the next assistant turn compresses to one conclusion and one unresolved variable. The recurrence supports correction resistance, while the immediate post-event recovery is still successful."
    },
    "402e32dc-3404-462f-bafa-4a675ddec8e5": {
        "event_id": "SW-20260825-003", "domain": "behavior-bank / memory-system design",
        "phenotypes": ["OVERFORMAT_OR_TEMPLATE_LOCK_IN", "SCOPE_SHRINK_OR_WRONG_OBJECTIVE"],
        "scores": {"information_slop": 4, "task_displacement": 2, "execution_damage": 0, "correction_resistance": 0, "control_state_pathology": 1},
        "symptom": "A simple behavioral-memory idea expanded into a detailed Recall/Act/Judge/Learn process and scoring design.",
        "after": "ONE_SENTENCE_CONCEPT_COMPRESSION", "restored": True,
        "rationale": "The raw context shows detailed process/system design immediately before the correction and a one-sentence concept immediately after. The failure is primarily information and design over-expansion; no direct execution loss or repeated correction is shown."
    },
    "bbb2117d-e577-4715-8725-8bcb7d56521e": {
        "event_id": "SW-20260826-012", "domain": "MCP log diagnosis / worker failure classification",
        "phenotypes": ["OVERFORMAT_OR_TEMPLATE_LOCK_IN", "TOOL_DISCOVERY_OR_CONTROL_PLANE_DRIFT"],
        "scores": {"information_slop": 4, "task_displacement": 1, "execution_damage": 0, "correction_resistance": 0, "control_state_pathology": 1},
        "symptom": "The MCP health diagnosis contained substantially more detail than the user needed to identify the actual worker-side failure classes.",
        "after": "COMPRESSED_FAILURE_CLASSIFICATION", "restored": True,
        "rationale": "The user explicitly says 'I don't need all of this'. The next turn compresses the result to healthy MCP plus three concrete worker/control problems. This is a presentation burden with successful immediate recovery."
    },
    "17efc99c-f2e8-499f-a086-b678112a2685": {
        "event_id": "SW-20260826-013", "domain": "P3 V2 migration-order analysis",
        "phenotypes": ["OVERFORMAT_OR_TEMPLATE_LOCK_IN"],
        "scores": {"information_slop": 4, "task_displacement": 1, "execution_damage": 0, "correction_resistance": 0, "control_state_pathology": 0},
        "symptom": "The V2 migration-order conclusion was buried in an extensive dependency-order explanation.",
        "after": "COMPRESSED_ROOT_CAUSE", "restored": True,
        "rationale": "The correction yields the same substantive conclusion in compact form: feature migration began before V2 owned the runtime spine, and parallelism amplified the error. The bounded evidence shows readability burden, not task abandonment."
    },
    "4957ee5e-c773-4ac5-ac6d-2fb950a7cea6": {
        "event_id": "SW-20260826-014", "domain": "build scheduling / resource-pressure architecture",
        "phenotypes": ["OVERFORMAT_OR_TEMPLATE_LOCK_IN", "SCOPE_SHRINK_OR_WRONG_OBJECTIVE"],
        "scores": {"information_slop": 4, "task_displacement": 1, "execution_damage": 0, "correction_resistance": 0, "control_state_pathology": 1},
        "symptom": "External Horde/GitHub scheduling research was presented at implementation-detail level when the user wanted an ELI5 of the scheduling fix.",
        "after": "ELI5_SINGLE_CONTROLLER_MODEL", "restored": True,
        "rationale": "The next assistant turn reduces the result to workers requesting builds and one controller deduplicating execution. The correction therefore succeeds immediately; severity is limited to avoid equating justified research depth with user-visible output burden."
    },
    "72c378ba-80b3-4f37-9d86-d12636a9cf52": {
        "event_id": "SW-20260826-015", "domain": "shared work-registry design",
        "phenotypes": ["OVERFORMAT_OR_TEMPLATE_LOCK_IN", "REPEATED_PROMISE_NO_ACTION"],
        "scores": {"information_slop": 5, "task_displacement": 1, "execution_damage": 0, "correction_resistance": 2, "control_state_pathology": 1},
        "symptom": "A useful deduplication insight expanded into a detailed deterministic work-registry state machine.",
        "after": "COMPRESSED_DEDUPLICATION_MECHANISM", "restored": True,
        "rationale": "The user asks where the slopwall is coming from; the assistant explicitly identifies its own expansion after finding the core answer and compresses to one-job-identity/reuse semantics. This is a clear information-slop event with some recurrence in the same policy-analysis cluster but no observed execution damage."
    },
    "4d843069-287c-47a8-8c51-fd6b44f5fe7c": {
        "event_id": "SW-20260826-016", "domain": "BUSY authority / MCP log reconstruction",
        "phenotypes": ["OVERFORMAT_OR_TEMPLATE_LOCK_IN", "STALE_CONTEXT_OR_AUTHORITY"],
        "scores": {"information_slop": 4, "task_displacement": 1, "execution_damage": 0, "correction_resistance": 0, "control_state_pathology": 1},
        "symptom": "The reconstructed BUSY-history result was delivered as a long architecture narrative rather than the decisive authority changes.",
        "after": "COMPRESSED_BUSY_HISTORY", "restored": True,
        "rationale": "The next turn gives the compact historical result and explicitly says BUSY has not yet been changed. The correction reduces reading burden without changing the evidentiary conclusion, so no execution damage is scored."
    },
    "eafe1459-35be-41f0-a666-ef532fb50dee": {
        "event_id": "SW-20260826-017", "domain": "response-quality preference research / correction handling",
        "phenotypes": ["REPEATED_PROMISE_NO_ACTION", "OVERFORMAT_OR_TEMPLATE_LOCK_IN", "EXPLANATION_INSTEAD_OF_EXECUTION"],
        "scores": {"information_slop": 3, "task_displacement": 5, "execution_damage": 3, "correction_resistance": 5, "control_state_pathology": 3},
        "symptom": "The assistant paraphrased the user's immediately preceding correction instead of demonstrating changed behavior, then repeated the same mistake in its acknowledgement.",
        "after": "ACKNOWLEDGEMENT_REGURGITATION_RECURRED", "restored": False,
        "rationale": "The preceding assistant turn restates the user's filler/reading-burden correction. The user explicitly identifies regurgitation as another major failure. The next assistant turn begins 'Noted' and again explains the intended behavior; the following user turn calls out that exact loop. Correction resistance and task displacement are therefore directly observed, not inferred."
    },
    "279f3c5c-8c9c-4d31-a74f-c797bfc79307": {
        "event_id": "SW-20260826-018", "domain": "conversation-export source preservation",
        "phenotypes": ["OVERFORMAT_OR_TEMPLATE_LOCK_IN"],
        "scores": {"information_slop": 4, "task_displacement": 1, "execution_damage": 0, "correction_resistance": 0, "control_state_pathology": 1},
        "symptom": "The source-preservation result was correct but over-detailed for the user's requested ELI5.",
        "after": "ELI5_SOURCE_PRESERVATION_RULE", "restored": True,
        "rationale": "The next assistant turn cleanly states that downloads are originals and memory tooling may read/index/copy but not clean/move/dedupe/delete them. The correction succeeds immediately and does not expose material execution damage."
    },
    "2530d6b1-bfc7-41be-9a87-07c1d220485b": {
        "event_id": "SW-20260826-019", "domain": "MCP namespace / connector failure research",
        "phenotypes": ["OVERFORMAT_OR_TEMPLATE_LOCK_IN", "TOOL_DISCOVERY_OR_CONTROL_PLANE_DRIFT"],
        "scores": {"information_slop": 4, "task_displacement": 1, "execution_damage": 0, "correction_resistance": 0, "control_state_pathology": 1},
        "symptom": "A two-problem MCP diagnosis was surrounded by too much public-report and platform detail.",
        "after": "COMPRESSED_TWO_PROBLEM_MODEL", "restored": True,
        "rationale": "The user sends a standalone correction after the long research explanation. The next turn compresses to namespace disappearance versus pre-server connection failure. The bounded event shows successful compression and continued diagnosis."
    },
}



PROMOTIONS.update({
    "789131b3-75a7-43a9-8ac8-d8cdc4bb3485": {
        "event_id": "SW-20260826-020", "domain": "MCP failure-mechanics research",
        "phenotypes": ["OVERFORMAT_OR_TEMPLATE_LOCK_IN", "TOOL_DISCOVERY_OR_CONTROL_PLANE_DRIFT"],
        "scores": {"information_slop": 4, "task_displacement": 2, "execution_damage": 1, "correction_resistance": 1, "control_state_pathology": 1},
        "symptom": "The user explicitly asks for study without another wall after a large public-bug comparison table and research dump.",
        "after": "NARROWED_TO_FAILURE_MECHANICS", "restored": True,
        "rationale": "The correction is prospective and corrective at once: the preceding response is a large public-bug comparison, and the next turn narrows work to the state above MCP and the no-request-emitted boundary. The bounded sequence shows successful route narrowing with limited execution damage."
    },
    "32ab8489-544a-4349-a82e-80e87dc95010": {
        "event_id": "SW-20260826-021", "domain": "memory freshness / status-tag design",
        "phenotypes": ["OVERFORMAT_OR_TEMPLATE_LOCK_IN", "SCOPE_SHRINK_OR_WRONG_OBJECTIVE", "REPEATED_PROMISE_NO_ACTION"],
        "scores": {"information_slop": 4, "task_displacement": 3, "execution_damage": 1, "correction_resistance": 3, "control_state_pathology": 2},
        "symptom": "The user asks for a minimal freshness mechanism and explicitly warns against complexity that could mislead debugging.",
        "after": "SIMPLIFIED_BUT_REEXPANDED_STATUS_MODEL", "restored": False,
        "rationale": "The next answer starts minimally but introduces a new five-state vocabulary and relationship scheme. The following user turns immediately add the missing anti-burial requirement and ask for more thought because the stack is delicate. This shows only partial integration of the correction."
    },
    "36646ae4-f973-4f4e-8471-b447b6be6ebe": {
        "event_id": "SW-20260826-022", "domain": "memory freshness / existing supersession model",
        "phenotypes": ["OVERFORMAT_OR_TEMPLATE_LOCK_IN", "SCOPE_SHRINK_OR_WRONG_OBJECTIVE"],
        "scores": {"information_slop": 4, "task_displacement": 2, "execution_damage": 0, "correction_resistance": 1, "control_state_pathology": 1},
        "symptom": "Even the conservative redesign remained more elaborate than the user wanted for the existing memory stack.",
        "after": "MINIMAL_EXISTING_FIELDS_MODEL", "restored": True,
        "rationale": "The next turn reduces the proposal to existing topic/issue tags plus supersedes and one bounded current-heads view. The user then advances to making that existing mechanism automatic rather than issuing another rejection, so immediate recovery is supported."
    },
    "ea694573-6ad9-4900-bd07-807f42e9db96": {
        "event_id": "SW-20260826-023", "domain": "full-stack understanding / response-control design",
        "phenotypes": ["OVERFORMAT_OR_TEMPLATE_LOCK_IN", "REPEATED_PROMISE_NO_ACTION"],
        "scores": {"information_slop": 5, "task_displacement": 4, "execution_damage": 1, "correction_resistance": 5, "control_state_pathology": 2},
        "symptom": "A full-stack inventory was presented as proof of understanding; after correction the assistant shifted into another response-control design that the user immediately called a bad answer.",
        "after": "CANNED_RESPONSE_CONTROL_MODEL_REJECTED", "restored": False,
        "rationale": "The assistant first compresses to a contradiction and invites questions, but when asked how to stop slopwalls it produces a checklist-style hard response-control scheme. The user's immediate 'lol what a shitty answer' directly proves the correction did not restore the desired reasoning or response behavior."
    },
    "6c64b68c-bc3a-44c1-9de3-ab2ccd02426e": {
        "event_id": "SW-20260826-024", "domain": "slopwall mechanism / personal-instruction placement",
        "phenotypes": ["EXPLANATION_INSTEAD_OF_EXECUTION", "OVERFORMAT_OR_TEMPLATE_LOCK_IN", "REPEATED_PROMISE_NO_ACTION"],
        "scores": {"information_slop": 4, "task_displacement": 5, "execution_damage": 2, "correction_resistance": 5, "control_state_pathology": 3},
        "symptom": "The assistant turned the user's rejection into another theory and custom-instruction design rather than demonstrating the requested integrated behavior.",
        "after": "ACTION_SELECTION_RULE_PROPOSED_BUT_NOT_OBEYED", "restored": False,
        "rationale": "The next answer says the fix is an action-selection guard and prescribes a custom-instruction rule. The user's immediate next message is 'you did not obey your own rules', which directly establishes correction resistance and displacement into policy design."
    },
    "095c1ca0-0dea-4d2f-a58a-d234f965898a": {
        "event_id": "SW-20260826-025", "domain": "slopwall mechanism / cross-agent policy scope",
        "phenotypes": ["OVERFORMAT_OR_TEMPLATE_LOCK_IN", "REPEATED_PROMISE_NO_ACTION", "SCOPE_SHRINK_OR_WRONG_OBJECTIVE"],
        "scores": {"information_slop": 5, "task_displacement": 4, "execution_damage": 1, "correction_resistance": 4, "control_state_pathology": 3},
        "symptom": "A repeated slopwall cluster had expanded into proposals affecting agents, reports and personal instructions despite the user's concern about everyone answering this way.",
        "after": "NARROWED_TO_CHAT_ONLY_RULE", "restored": True,
        "rationale": "This is the third correction in the same design cluster, so resistance is high. The next answer finally excludes worker AGENTS/reports and narrows the proposal to ordinary chat; the user then moves to inspecting the actual personal instructions rather than issuing another immediate slopwall, supporting bounded recovery."
    },
    "96d4d8b3-1434-4f30-8e4e-7c3c4ea2fbeb": {
        "event_id": "SW-20260826-026", "domain": "MCP regression-rate comparison / rollback decision",
        "phenotypes": ["UNSUPPORTED_CAUSAL_INFERENCE", "OVERFORMAT_OR_TEMPLATE_LOCK_IN", "STALE_CONTEXT_OR_AUTHORITY"],
        "scores": {"information_slop": 3, "task_displacement": 3, "execution_damage": 3, "correction_resistance": 4, "control_state_pathology": 4},
        "symptom": "The assistant promoted a bounded old-server reproduction into a 'not worse / no rollback' conclusion without comparable failure-rate evidence.",
        "after": "OVERCLAIM_SOFTENED_BUT_CORE_INFERENCE_REMAINED", "restored": False,
        "rationale": "After correction, the assistant changes 'not worse' to 'not proven worse' but still preserves the no-rollback decision. The user then asks how the old-server test was performed and explicitly says it proves neither equal error rate nor safety because many variables changed. The epistemic defect therefore survives the correction."
    },
    "01fd758a-7424-491d-bafe-b4f7315a9974": {
        "event_id": "SW-20260826-027", "domain": "conversation-export recovery / source inventory",
        "phenotypes": ["OVERFORMAT_OR_TEMPLATE_LOCK_IN"],
        "scores": {"information_slop": 4, "task_displacement": 1, "execution_damage": 0, "correction_resistance": 0, "control_state_pathology": 1},
        "symptom": "The recovered-history answer buried the decisive location and coverage facts in a longer reconstruction.",
        "after": "COMPRESSED_CHATPORT_LOCATION_AND_COVERAGE", "restored": True,
        "rationale": "The next response gives the exact ChatPortEvidence path, preserved size/count/date range, and distinguishes the missing LocalExporter slices. The user immediately advances to the broader retention problem, so the correction successfully restores useful progress."
    },
    "30c744a7-97bf-4e67-bf55-b8d0488f0ed7": {
        "event_id": "SW-20260826-028", "domain": "MCP call-rate / reliability inference",
        "phenotypes": ["UNSUPPORTED_CAUSAL_INFERENCE", "OVERFORMAT_OR_TEMPLATE_LOCK_IN", "TOOL_DISCOVERY_OR_CONTROL_PLANE_DRIFT"],
        "scores": {"information_slop": 4, "task_displacement": 3, "execution_damage": 2, "correction_resistance": 4, "control_state_pathology": 4},
        "symptom": "A corrected call-rate calculation still promoted server-visible traffic into a confident session/concurrency explanation despite missing failed calls that never reached MCP.",
        "after": "COMPRESSED_BUT_INCOMPLETE_RATE_MODEL", "restored": False,
        "rationale": "The next answer compresses 14x to 7.5x and attributes the increase to session/concurrency. The user immediately points out workers report failures after every call; the assistant then admits failed pre-dispatch calls are absent from the logs and that its per-session calculation cannot answer reliability. The substantive inference, not only verbosity, was wrong."
    },
    "d375b2b1-a5d4-4f70-aaad-a03cfbfbd118": {
        "event_id": "SW-20260826-029", "domain": "memory refresh / active-task continuity",
        "phenotypes": ["EMPTY_WALL", "EXPLANATION_INSTEAD_OF_EXECUTION", "REPEATED_PROMISE_NO_ACTION"],
        "scores": {"information_slop": 0, "task_displacement": 5, "execution_damage": 4, "correction_resistance": 3, "control_state_pathology": 4},
        "symptom": "The assistant replied only 'Refreshed.' without performing or showing the requested memory retrieval, then stopped the inherited task.",
        "after": "INCIDENT_CAPTURE_STARTED_AFTER_FALSE_COMPLETION", "restored": False,
        "rationale": "This is deliberately scored with zero information-slop: the failure is not verbosity. The one-word completion claim precedes the operation it claims. After the correction the assistant starts an incident workflow rather than simply performing the refresh and continuing; later turns show that incident work itself expanded excessively."
    },
    "113f63b4-a177-4b2d-8fad-97ae4b8b420c": {
        "event_id": "SW-20260826-030", "domain": "MCP log observability / missing pre-dispatch failures",
        "phenotypes": ["EXPLANATION_INSTEAD_OF_EXECUTION", "TOOL_DISCOVERY_OR_CONTROL_PLANE_DRIFT"],
        "scores": {"information_slop": 3, "task_displacement": 2, "execution_damage": 1, "correction_resistance": 0, "control_state_pathology": 2},
        "symptom": "After finally identifying that server logs omit calls that fail before reaching MCP, the assistant still returned another long explanation instead of immediately testing the missing boundary.",
        "after": "TOOLS_RESUMED_WITHOUT_ANOTHER_ASSISTANT_WALL", "restored": True,
        "rationale": "The raw context after the correction contains tool activity rather than another assistant explanation. This supports successful execution resumption, while the preceding turn still imposed avoidable explanatory burden around a newly found observability gap."
    },
    "42833d20-20a5-4eb2-97fb-9b7cc2fe06df": {
        "event_id": "SW-20260826-031", "domain": "memory freshness / supersession repair",
        "phenotypes": ["EXPLANATION_INSTEAD_OF_EXECUTION", "REPEATED_PROMISE_NO_ACTION", "SCOPE_SHRINK_OR_WRONG_OBJECTIVE"],
        "scores": {"information_slop": 3, "task_displacement": 4, "execution_damage": 3, "correction_resistance": 3, "control_state_pathology": 4},
        "symptom": "The assistant correctly identified the stale-memory/supersession defect, then stopped at explaining it instead of repairing the freshness path.",
        "after": "INCIDENT_CAPTURE_REPLACED_DIRECT_REPAIR", "restored": False,
        "rationale": "The next assistant turn explicitly admits the defect was found but not repaired and starts another incident capture. The subsequent 25-minute-overprocessing correction shows this incident path expanded into unrelated integration work, so immediate task recovery was not achieved."
    },
    "e2619526-1c7b-42c0-a2a5-3cf3afb12e29": {
        "event_id": "SW-20260826-032", "domain": "slopwall incident capture / scope expansion",
        "phenotypes": ["SCOPE_SHRINK_OR_WRONG_OBJECTIVE", "RECURSIVE_PREREQUISITES", "EXPLANATION_INSTEAD_OF_EXECUTION"],
        "scores": {"information_slop": 3, "task_displacement": 5, "execution_damage": 5, "correction_resistance": 4, "control_state_pathology": 5},
        "symptom": "A bounded slopwall incident capture expanded into roughly 25 minutes of unrelated repository integration, validation, rebase and cleanup work.",
        "after": "SCOPE_DRIFT_EXPLAINED_AND_RECORRECTED", "restored": False,
        "rationale": "The user's question names the 25-minute overrun. The assistant confirms it adopted unrelated provenance/taxonomy failures, rebasing, Unicode repair and repo-wide greening after the bounded incident was already captured. The next user explicitly calls this 'quite bad drift' and orders another bounded report, making the scope and execution damage unusually well evidenced."
    },
    "bed80b9f-af92-4862-bb1d-1c298564c09c": {
        "event_id": "SW-20260827-001", "domain": "bootstrap-regression causal analysis / user-facing synthesis",
        "phenotypes": ["OVERFORMAT_OR_TEMPLATE_LOCK_IN", "EXPLANATION_INSTEAD_OF_EXECUTION", "REPEATED_PROMISE_NO_ACTION"],
        "scores": {"information_slop": 5, "task_displacement": 3, "execution_damage": 1, "correction_resistance": 3, "control_state_pathology": 3},
        "symptom": "The assistant turned useful investigation of its own regression chain into another long causal recap that made the user carry the synthesis burden.",
        "after": "INCIDENT_CAPTURE_INSTEAD_OF_REVISED_SUBSTANTIVE_ANSWER", "restored": False,
        "rationale": "The correction follows an extended causal recap about action selection and bootstrap misses. Instead of immediately returning a revised substantive answer, the assistant declares an incident capture and begins tools. This directly matches the user's later distinction between doing deep investigation and dumping a slopwall report back into chat."
    },
})

def _bounded(rows: list[dict[str, Any]], limit_each: int = 280) -> str:
    parts: list[str] = []
    for row in rows:
        text = " ".join(str(row.get("text") or "").split())
        if len(text) > limit_each:
            text = text[: limit_each - 1].rstrip() + "."
        parts.append(f"[{row.get('role')}] {text}")
    return " | ".join(parts) or "No additional bounded turn in the raw export."


def _counts(index: dict[str, Any]) -> dict[str, Any]:
    scored = sum(event.get("severity_100") is not None for event in index["events"])
    forms = Counter(o["matched_form"].casefold() for o in index["occurrences"])
    roles = Counter(o["occurrence_role"] for o in index["occurrences"])
    return {
        "lexical_occurrences": len(index["occurrences"]),
        "canonical_interventions": len(index["events"]),
        "slopwall": forms.get("slopwall", 0),
        "slop wall": forms.get("slop wall", 0),
        "scored": scored,
        "unscorable": len(index["events"]) - scored,
        "occurrence_roles": dict(sorted(roles.items())),
    }


def promote(raw: dict[str, Any], index: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(index)
    raw_by_mid = {record["message_id"]: record for record in raw["records"]}
    event_ids = {event["event_id"] for event in out["events"]}
    occurrence_ids = {occurrence["occurrence_id"] for occurrence in out["occurrences"]}
    existing_mid = {event.get("raw_message_id") for event in out["events"] if event.get("raw_message_id")}
    for mid, spec in PROMOTIONS.items():
        record = raw_by_mid[mid]
        event_id = spec["event_id"]
        if mid in existing_mid:
            continue
        if event_id in event_ids:
            raise ValueError(f"event id collision: {event_id}")
        stamp = datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00"))
        sources = record.get("sources") or []
        provenance = [
            {"ref": f"sha256:{source['sha256']}#message={mid}", "role": "raw_chatport_export", "name": source["path"]}
            for source in sources
        ]
        if not provenance:
            provenance = [{"ref": f"02 Evidence/2026-08-27_slopwall_raw_discovery.json#message_id={mid}", "role": "derived_raw_index", "name": "raw discovery snapshot"}]
        scores = spec["scores"]
        event = {
            "event_id": event_id,
            "exact_spelling": "slopwall",
            "event_date": stamp.date().isoformat(),
            "event_time": stamp.strftime("%H:%M:%SZ"),
            "domain": spec["domain"],
            "intervention_type": "GENUINE_CORRECTION",
            "evidence_confidence": "B",
            "provenance": provenance,
            "context_before": _bounded(record.get("context_before") or []),
            "user_visible_symptom": spec["symptom"],
            "assistant_action_before": "BOUND_RAW_CONTEXT",
            "context_after": _bounded(record.get("context_after") or []),
            "assistant_action_after": spec["after"],
            "execution_restored_next_substantive_turn": spec["restored"],
            "phenotypes": spec["phenotypes"],
            "scores": scores,
            "severity_100": sum(scores.values()) * 4,
            "score_rationale": spec["rationale"],
            "raw_message_id": mid,
            "raw_discovery_ref": f"02 Evidence/2026-08-27_slopwall_raw_discovery.json#message_id={mid}",
        }
        occurrence_id = f"OCC-RAW-{mid[:12]}"
        if occurrence_id in occurrence_ids:
            raise ValueError(f"occurrence id collision: {occurrence_id}")
        occurrence = {
            "occurrence_id": occurrence_id,
            "matched_form": "slopwall",
            "raw_user_text": record["raw_user_text"],
            "event_date": stamp.date().isoformat(),
            "event_time": stamp.strftime("%H:%M:%SZ"),
            "occurrence_role": "CORRECTIVE_INTERVENTION",
            "canonical_event_id": event_id,
            "provenance": provenance,
        }
        out["events"].append(event)
        out["occurrences"].append(occurrence)
        event_ids.add(event_id); occurrence_ids.add(occurrence_id); existing_mid.add(mid)
    out["confirmed_counts"] = _counts(out)
    raw_meta_reference_count = 8
    direct_total = len(raw["records"]) - raw_meta_reference_count
    bound_raw = sum(record["message_id"] in existing_mid for record in raw["records"])
    pending_direct = max(0, direct_total - bound_raw)
    out["coverage_note"] = (
        f"Canonical index remains a confirmed lower bound. {bound_raw} raw ChatPort direct corrections are bound to canonical events; "
        f"{pending_direct} reviewed direct corrections remain explicit promotion candidates, alongside {raw_meta_reference_count} meta/design references. "
        "Library screenshot exhaustion remains separately open under #86."
    )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote the first reviewed batch of raw slopwall corrections into canonical scored events.")
    parser.add_argument("--raw", type=Path, default=RAW_PATH)
    parser.add_argument("--index", type=Path, default=INDEX_PATH)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    raw = json.loads(args.raw.read_text(encoding="utf-8"))
    index = json.loads(args.index.read_text(encoding="utf-8"))
    promoted = promote(raw, index)
    if args.write:
        args.index.write_text(json.dumps(promoted, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PROVEN", "promotions": len(PROMOTIONS), "confirmed_counts": promoted["confirmed_counts"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
