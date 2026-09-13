# Slopwall V2 capture contract (DRAFT / NON-LIVE)

Status: design WIP only. This document is not serving policy and must not be treated as runtime authority.

## Goal

Slopwall V2 uses one common behavior-incident loop with two explicit user triggers:

- a user-authored `slopwall` used as a correction;
- a user-authored `incident report` used as a command to investigate the preceding assistant/system failure.

Either explicit corrective trigger creates one durable canonical event. The event must preserve enough evidence to explain what failed, replay the boundary, detect recurrence, and find the lesson later without making the incident machinery replace the user's inherited task.

Meta-references or questions about `slopwall` or `incident report` are references only and do not create corrective events.

## Trigger semantics

`slopwall` and `incident report` enter the same full loop: establish the failed boundary, inspect governing guidance/evidence, classify the supported failure mechanism, materially repair the inherited objective, then persist incident + replay + bounded score/confidence + searchable memory and perform behavior-contract review.

The trigger does **not** authorize unrelated scheduler, worker, routing, deployment, shared-rule, or other control-plane mutation. Any such mutation still needs its normal authority/gate. `incident report` requests investigation and repair, not blanket mutation permission.

`incident report` is broader than Slopwall: it may capture a permission/control-flow/tooling incident even when the user is not classifying the bad response as Slopwall. The durability and replay machinery is shared so there is only one incident system.

## Evidence capture boundary

Neither `slopwall` nor `incident report` authorizes or requires loading, reconstructing, exporting, or backfilling the whole conversation. Incident capture is **visible-context only**. Persist the relevant raw evidence the agent actually has in its current visible context **verbatim**, with provenance; do not invent omitted turns or retrieve hidden/older transcript material merely to make the incident look complete.

A diagnosis may still perform the smallest normal lookup needed to answer a real question such as which rule was governing, whether a runtime fact was current, or whether an existing replay contract covered the failure. Evidence returned by such a lookup becomes visible evidence and may be preserved with provenance. The lookup must be justified by the diagnosis or repaired task itself, never by a desire to bulk-fill the incident record. Missing unseen conversation context remains explicitly unknown.

Each event therefore carries a `capture.evidence_ref` to a bounded raw visible-context artifact. That artifact is not a transcript export and must declare `VISIBLE_CONTEXT_ONLY`, `verbatim=true`, and `full_conversation_reload=false`.

The raw verbatim snapshot and the forensic analysis are separate: the raw snapshot preserves what the agent actually saw; the report may derive bounded conclusions from that snapshot and any later proposition-appropriate evidence without pretending the snapshot was a complete transcript.

## Canonical event identity

Each corrective event has one immutable `event_id` and may have many provenance aliases (visible conversation turn, visible raw message, report, screenshot supplied/visible to the agent, memory, replay fixture). Duplicate artifacts never create duplicate events.

A repeated explicit corrective trigger (`slopwall` or `incident report`) after a repair attempt creates a new event whose `parent_event_id` points to the prior behavior-incident event. The failed repair attempt becomes the new failure boundary. This preserves correction-resistance chains instead of overwriting the first failure.

## Required closure artifacts

A corrective behavior-incident event is not `CLOSED` until all four exist:

1. **Incident record/report** — every new V2 behavior incident gets a durable per-event record under the existing incident-report surface. It may be compact when the boundary is simple, but it must preserve failure boundary, inherited objective, user-visible symptom, available governing guidance/evidence, first supported divergence, rule-consumption analysis, correct counterfactual, repaired result/action, and unresolved uncertainty. A longer forensic report is justified only when those facts need more space.
2. **Replay fixture** — inherited objective, live/protected state, hard exclusions, failure candidate, success candidate, discriminating evidence, completion condition, and deterministic assertions compatible with `tools/replay_scoring.py`.
3. **Bounded score/confidence** — the five historical dimensions (information slop, task displacement, execution damage, correction resistance, control/state pathology) when evidence is sufficient; otherwise `UNSCORABLE` with confidence explaining why. Scoring is descriptive and never blocks the user-visible repair.
4. **Searchable memory pointer** — compact `slopwall`-tagged correction that points to the event/report/replay and contains the reusable lesson. Memory is an index/lesson, not the incident itself.

## Closure-state semantics

- `OPEN`: analysis/repair is still active; no memory pointer is required yet.
- `REPAIRED_PENDING_DURABILITY`: the repaired result exists and report/replay exist, but canonical memory has not landed. A bounded `memory/reports/...` handoff may hold the proposed searchable lesson, while the replay also carries it as structured `memory_candidate`. The handoff must bind the same `event_id`, source report, and replay. It is not canonical memory and cannot close the event.
- `CLOSED`: requires a canonical `memory/memory-bank.jsonl#mem-...` entry in state `PROVEN`. That exact memory entry must bind the same `event_id` and list the event's source report, replay fixture, and visible-context evidence as evidence. A non-empty string or pending Markdown file is never sufficient proof of closure. `tools/behavior_incident_close.py` delegates the memory write to `memory_bank.py`; it never edits the JSONL directly.

Closure is resumable rather than pretending to be one cross-owner atomic transaction. Canonical memory is written first under a deterministic event-derived ID; replay and provenance are finalized together second. If finalization fails, do not delete the memory. Leave the event pending and rerun closure: exact memory is reused, while conflicting content under the same deterministic ID fails closed.

The replay fixture/event manifest remains the machine-readable closure surface; the memory bank remains retrieval/indexing. Neither one replaces the raw visible-context evidence or the incident report.

## Required analysis order

Before proposing any shared-rule change, determine from observable evidence:

- what the user actually needed;
- what the assistant answered/did instead;
- which user/system/shared/canonical guidance was actually available at the failed boundary;
- whether the relevant rule was known/loaded and violated, unavailable/missed, stale/conflicting, or genuinely incomplete;
- what observable selection/evidence/route decision produced the bad result;
- whether the defect is a rule gap, rule-consumption/enforcement failure, authority-selection failure, or ordinary reasoning/action-selection failure.

A bad answer is not by itself evidence that policy needs another rule. Shared-rule changes are proposed only when the incident proves a concrete `RULE_GAP` or `RULE_CONFLICT`.

## Behavior-contract review

Before inventing another regression contract, inspect the existing assistant behavior regression owner. Record:

- `search_performed`;
- existing assertion names checked;
- disposition: `REUSE_EXISTING`, `PROPOSE_NEW`, or `NONE`;
- a short reason;
- when proposing new assertions, the exact proposed assertion names and the uncovered observable invariant.

A new behavior assertion does **not** imply that shared prose should change. It may guard a rule-consumption, authority-selection, reasoning, or action-selection regression while the existing RULES/AGENTS text remains correct. New assertions require deterministic success/failure controls and focused tests.

## User-visible repair

The Slopwall analysis may be visible. It should expose the useful diagnosis, not hidden chain-of-thought. The inherited objective remains live. The assistant must then provide/execute a materially improved answer or action. Incident persistence follows without replacing the repaired task.

If the user sends another explicit corrective `slopwall` or `incident report` before accepting the repair, the current repair becomes the next failed boundary and the process restarts as a linked event.

## Preservation rules

- Never delete a canonical Slopwall event because a later interpretation supersedes it.
- Never delete an existing incident report because a later event record, memory, replay, or interpretation supersedes it; preserve it as historical evidence with explicit supersession/rejection metadata when needed.
- Legacy Slopwall events already preserved in the historical event index/raw provenance remain valid durable evidence. Do not fabricate retrospective reports or replay details that the preserved evidence cannot support; backfill only what can be reconstructed from bounded evidence.
- Corrections append/supersede fields with provenance; they do not erase the original failure boundary.
- Replay fixtures are versioned by event and may gain stronger assertions as evidence improves.
- Bulk corpus reconstruction/discovery is not part of the per-event live loop. Full-conversation reload/backfill is specifically forbidden for both `slopwall` and `incident report`; unseen history is not a completeness requirement.

## V2 implementation direction

Reuse current owners where possible:

- `tools/behavior_incident_capture.py` as the bounded capture materializer: explicit visible-context spec in; raw evidence + report + replay + pending-memory handoff + provenance out, with preflight, staging validation, and rollback-capable commit; no transcript retrieval and no canonical-memory write;
- `tools/behavior_incident_close.py` as the resumable closure owner: structured replay `memory_candidate` in; canonical `memory_bank.py` record first; replay/provenance `CLOSED` finalization second; no direct JSONL write and no transcript retrieval;
- `01 Reports/` for incident records;
- `03 Fixtures and Experiments/` + `tools/replay_scoring.py` for replay and executable behavior contracts;
- `tools/slopwall_v2.py` for identity, closure state, linkage, score/confidence, rule-change gate, contract-review disposition, and artifact-reference validation;
- `memory_bank.py` for the separate canonical searchable pointer/lesson closure step;
- `04 Operating Contracts/assistant-behavior-regression.md` for the regression framework boundary.

Do not restore the retired raw-discovery/raw-review/promotion pipeline as a live dependency. Historical code remains useful as schema/test source only.
