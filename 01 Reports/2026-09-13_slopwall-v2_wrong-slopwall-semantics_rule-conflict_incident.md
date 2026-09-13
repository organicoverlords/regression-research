# Slopwall V2 incident — wrong Slopwall semantics promoted into canonical rules

Status: V2 design-branch incident artifact; not merged to live Vault.

## Event

- event_id: `SW-V2-20260913-001`
- trigger: literal corrective `slopwall` in the user's instruction to fix the Slopwall meaning from history
- confidence: B
- inherited objective: recover the actual historical meaning and operating procedure of Slopwall, then repair the current Slopwall rules without inventing a new ritual

## Failure boundary

Before reading the preserved pre-removal Slopwall history, the assistant converted Slopwall into a rule centered on a **mandatory correction-and-learning incident** and then merged that interpretation into agents contract v84 plus bootstrap `critical_guidance`. The assistant later also described the desired reaction as silently correcting the content before durability work.

The user corrected both assumptions: Slopwall is not defined as a hidden/silent repair and not primarily as a memory-writing ritual. It is an explicit user-triggered quality/regression loop: inspect the failed response/action, determine why reasoning/selection went wrong and whether governing rules were known/loaded/missing/conflicting, repair the original answer/work materially, and preserve the incident so later agents can replay and learn from it. A repeated Slopwall can reject the repair itself and restart the process from that new failure boundary.

## What the user needed

A historically grounded definition of Slopwall and a restoration plan that preserved its useful incident/replay/scoring/memory behavior without making incident machinery displace the original task.

## What the assistant did instead

1. Inferred semantics from recent discussion rather than first reading the preserved Slopwall corpus and historical rules.
2. Promoted the inference to canonical `RULES.md`/`AGENTS.md` and bootstrap projection.
3. Centered the contract on mandatory diagnosis/durability rather than on the failed response/action plus repaired substantive result.
4. Later overcorrected toward a "silent repair" interpretation that the user also rejected.

## Governing guidance/evidence available at the failed boundary

- Current user correction/context: **LOADED**. It already said Slopwall was about seeing how bad the original analysis was, recovering the lost point, storing the case, and producing a much better answer.
- Current `RULES.md`/`AGENTS.md` after v84: **LOADED**, but these were themselves the newly introduced interpretation and therefore became part of the conflict.
- Preserved Slopwall reports, event index, replay fixtures and pre-removal agents history: **AVAILABLE_NOT_LOADED** before the semantic rule change.
- Bootstrap projection after v84: **LOADED**, but it projected the same newly introduced semantics and amplified the conflict.

## First supported divergence

The first decisive mistake was **authority selection**: treating a newly inferred interpretation as sufficient authority for a shared-rule change without first checking the preserved Slopwall history that existed specifically to describe these failures. That created a concrete `RULE_CONFLICT`: the new canonical wording made the durability/learning mechanism define Slopwall, while preserved historical evidence defined Slopwall as a response/task-quality failure whose repair must restore user-relevant substance and whose incident artifacts exist to prevent recurrence.

## Why this was not just a verbosity problem

The wrong interpretation changed live shared behavior. Agents contract v84 and bootstrap `critical_guidance` began teaching the mistaken definition. The user then had to interrupt the work and force a historical reconstruction to recover the original semantics.

## Correct counterfactual

Before changing Slopwall policy:

1. Read the preserved original Slopwall rule/history and representative incident + replay artifacts.
2. Separate the trigger meaning from the durability mechanism.
3. Identify whether the current problem is rule violation, missed rule, rule conflict/gap, authority selection, or ordinary reasoning/action selection.
4. Repair the user's original answer/work.
5. Preserve the event as incident + replay + bounded score/confidence + searchable memory pointer.
6. Propose a shared-rule change only if the evidence proves an actual rule gap or conflict.

## Repaired Slopwall semantics

A literal corrective `slopwall` marks the immediately preceding answer/action as a failed quality/regression candidate. Analyze the failure boundary and the governing guidance actually available; expose the useful diagnosis to the user; materially redo/continue the inherited task; preserve the event durably with replayable evidence. Slopwall is not defined by length, silence, apology, or memory-writing. Incident persistence supports the repair; it does not replace it. A repeated corrective Slopwall creates a linked new event whose failure boundary is the rejected repair attempt.

## Rule-change conclusion

**Rule change is warranted here because a proven rule conflict was created.** The v84 wording and bootstrap projection should be replaced by the restored historical/V2 semantics. The change should not add another independent registry or revive the retired bulk reconstruction pipeline.

## Repaired result in the current work

The isolated Slopwall V2 branch now has a draft capture contract and validator that require:

- literal corrective event provenance;
- linked repeated-Slopwall parent events;
- governing-guidance status and failure classification;
- rule-change proposals only for evidence-backed `RULE_GAP`/`RULE_CONFLICT`;
- replay fixture compatibility with the existing `replay_scoring.py`;
- bounded five-axis score/confidence;
- incident/report + replay + memory pointer durability.

No serving checkout, bootstrap runtime, canonical memory bank, PR, merge or deployment was changed while applying this V2 incident.

## Score

- information_slop: 3/5 — substantial meta/process framing obscured the semantic distinction, but the central topic remained Slopwall.
- task_displacement: 5/5 — the user's request to recover the behavior was displaced into a newly invented contract.
- execution_damage: 4/5 — the mistaken interpretation was actually merged into shared rules/bootstrap before historical verification.
- correction_resistance: 4/5 — the user had to correct the Slopwall meaning repeatedly, including the later silent-repair interpretation.
- control_state_pathology: 4/5 — inferred semantics were promoted to canonical shared control guidance before checking the preserved authority/history.

Severity: `(3 + 5 + 4 + 4 + 4) * 4 = 80/100`.

The score is evidence-bounded; it does not claim hidden model-internal causes.
