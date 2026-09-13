# Slopwall V2 capture contract (DRAFT / NON-LIVE)

Status: design WIP only. This document is not serving policy and must not be treated as runtime authority.

## Goal

A literal user-authored `slopwall` used as a correction creates one durable canonical event. The event must preserve enough evidence to explain what failed, replay the boundary, detect recurrence, and find the lesson later without making the incident machinery replace the user's inherited task.

Meta-references to the word `slopwall` are indexed as references only and do not create corrective events.

## Canonical event identity

Each corrective event has one immutable `event_id` and may have many provenance aliases (conversation turn, raw transcript message, report, screenshot, memory, replay fixture). Duplicate artifacts never create duplicate events.

A repeated literal `slopwall` after a repair attempt creates a new event whose `parent_event_id` points to the prior Slopwall event. The failed repair attempt becomes the new failure boundary. This preserves correction-resistance chains instead of overwriting the first failure.

## Required closure artifacts

A corrective Slopwall event is not `CLOSED` until all four exist:

1. **Incident record/report** — every new V2 Slopwall gets a durable per-event record under the existing incident-report surface. It may be compact when the boundary is simple, but it must preserve failure boundary, inherited objective, user-visible symptom, available governing guidance/evidence, first supported divergence, rule-consumption analysis, correct counterfactual, repaired result/action, and unresolved uncertainty. A longer forensic report is justified only when those facts need more space.
2. **Replay fixture** — inherited objective, live/protected state, hard exclusions, failure candidate, success candidate, discriminating evidence, completion condition, and deterministic assertions compatible with `tools/replay_scoring.py`.
3. **Bounded score/confidence** — the five historical dimensions (information slop, task displacement, execution damage, correction resistance, control/state pathology) when evidence is sufficient; otherwise `UNSCORABLE` with confidence explaining why. Scoring is descriptive and never blocks the user-visible repair.
4. **Searchable memory pointer** — compact `slopwall`-tagged correction that points to the event/report/replay and contains the reusable lesson. Memory is an index/lesson, not the incident itself.

## Required analysis order

Before proposing any shared-rule change, determine from observable evidence:

- what the user actually needed;
- what the assistant answered/did instead;
- which user/system/shared/canonical guidance was actually available at the failed boundary;
- whether the relevant rule was known/loaded and violated, unavailable/missed, stale/conflicting, or genuinely incomplete;
- what observable selection/evidence/route decision produced the bad result;
- whether the defect is a rule gap, rule-consumption/enforcement failure, authority-selection failure, or ordinary reasoning/action-selection failure.

A bad answer is not by itself evidence that policy needs another rule. Shared-rule changes are proposed only when the incident proves a concrete gap or ambiguity that allowed the failure.

## User-visible repair

The Slopwall analysis may be visible. It should expose the useful diagnosis, not hidden chain-of-thought. The inherited objective remains live. The assistant must then provide/execute a materially improved answer or action. Incident persistence follows without replacing the repaired task.

If the user sends another literal corrective `slopwall` before accepting the repair, the current repair becomes the next failed boundary and the process restarts as a linked event.

## Preservation rules

- Never delete a canonical Slopwall event because a later interpretation supersedes it.`r`n- Never delete an existing incident report because a later event record, memory, replay, or interpretation supersedes it; preserve it as historical evidence with explicit supersession/rejection metadata when needed.`r`n- Legacy Slopwall events already preserved in the historical event index/raw provenance remain valid durable evidence. Do not fabricate retrospective reports or replay details that the preserved evidence cannot support; backfill only what can be reconstructed from bounded evidence.
- Corrections append/supersede fields with provenance; they do not erase the original failure boundary.
- Incident reports are retained once created. Rejected or mistaken incident claims remain preserved as rejected/superseded evidence rather than silently removed.
- Replay fixtures are versioned by event and may gain stronger assertions as evidence improves.
- Bulk corpus reconstruction/discovery is not part of the per-event live loop.

## V2 implementation direction

Reuse current owners where possible:

- `01 Reports/` for incident records;
- `03 Fixtures and Experiments/` + `tools/replay_scoring.py` for replay;
- `memory_bank.py` for searchable pointer/lesson;
- a small Slopwall event manifest/validator for identity, closure state, linkage, score/confidence, and artifact references.

Do not restore the retired raw-discovery/raw-review/promotion pipeline as a live dependency. Historical code remains useful as schema/test source only.

