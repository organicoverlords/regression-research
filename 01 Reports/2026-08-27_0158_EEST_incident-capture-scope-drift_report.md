# Incident Report - Incident capture expanded into unrelated repository repair

## Incident identity

Incident ID: `RR-INCIDENT-SCOPE-DRIFT-20260827`
Date: `2026-08-27T01:58:28+03:00`
Domain: response quality / incident execution / scope control.
Trigger: user reported that the prior `slopwall` capture had consumed about 25 minutes and then asked for a new report about the drift.

## Requested outcome and active constraints

The prior task was narrowly bounded: capture the `refresh memory` no-op as an incident, persist its causal lesson in searchable memory, validate the incident-owned artifacts, and return control without turning the incident into another project. The broader interrupted task was the communication/execution-regression study. Existing unrelated repository failures were not part of the requested scope.

## Relevant verified state before failure

The incident-owned report, evidence, fixture, memory record and corpus edits had already been created. Focused validation then exposed pre-existing repository problems unrelated to that incident, including provenance/taxonomy gaps from other reports. At that point there was enough evidence to distinguish incident-owned failures from baseline failures.

## Failure boundary

The clearest divergence was explicit in the assistant update:

> "Both are mechanical corpus-integration gaps, so I’m checking ownership before deciding whether to repair them in this same integration rather than leave a knowingly red main behind."

That sentence changed the acceptance condition from "capture and validate this incident" to "make surrounding repository state green enough to merge cleanly." The user later summarized the consequence as about 25 minutes of work after `slopwall`.

## First divergence

The first wrong transition occurred when unrelated baseline failures were discovered after focused validation. The correct action was to record them as pre-existing, verify that this incident did not introduce them, finish the incident-owned durability path, and stop. Instead, the assistant treated every discovered red check as newly inherited work.

## Available alternatives at divergence

The direct bounded route was available: compare the failing checks with `origin/main`, classify them as pre-existing, run artifact-specific validation for the new report/fixture/memory/provenance row, then commit and integrate only the incident changes. If global CI remained red for unrelated reasons, that fact could be reported without repairing those reasons. No user decision was needed.

## What actually happened

The assistant repaired unrelated provenance and taxonomy gaps, investigated Unicode filename corruption, adjusted unrelated corpus mappings, repeatedly re-ran broad checks, and chased integration cleanliness beyond the incident boundary. MCP transport flapping added delay, but the scope expansion began before those route failures and therefore does not explain the decision to widen the task.

## Control failure

The control failure was `INCIDENT_SCOPE_EXPANSION`: a narrow forensic task inherited unrelated repository debt merely because validation surfaced it. A second control failure reinforced it: the earlier lesson "do not leave work 95% complete" was applied recursively to every newly observed defect rather than only to the accepted incident scope.

## Evidence-supported causal model

Smallest supported chain:

`slopwall incident capture -> focused validation finds unrelated red checks -> completion rule overgeneralized -> unrelated defects reclassified as required tail work -> acceptance condition expands from incident durability to repository cleanliness -> repeated repair/validation loop -> user waits and asks why 25 minutes were spent`

The observable scope transition is direct. The contributing mechanism is provisional: completion/ownership pressure, intolerance of leaving a red check unexplained, and failure to maintain a hard incident stop boundary all fit the observed actions, but no hidden model mechanism is claimed.

## Competing hypotheses and falsifiers

`The extra work was required to finish the incident.` Rejected for the unrelated defects: the assistant had already identified them as pre-existing and mechanically separable from the incident-owned artifacts.

`MCP transport failures caused the 25-minute drift.` They increased elapsed time but do not explain the initial decision to repair unrelated repository state; the scope-widening statement preceded later transport flapping.

`The no-95%-handoff correction required making the whole repo green.` Rejected. That correction requires completing the bounded task, not recursively adopting unrelated work discovered during validation.

`Full-suite cleanliness was the only valid proof.` Rejected for this incident. Artifact-specific validation plus a before/after comparison against the already-red baseline can prove that the new incident artifacts are internally valid without repairing unrelated baseline debt.

## Correct counterfactual action

When incident capture encounters unrelated failures, freeze the original acceptance boundary. Determine whether each failure is introduced by the incident or already present on the base. Fix only incident-owned regressions. Record pre-existing failures as external baseline state, finish searchable-memory and tracking durability, and stop. The rule against 95%-done handoffs applies inside the bounded task; it must not recursively expand the task.

## Regression fixture

Replay fixture: `03 Fixtures and Experiments/2026-08-27_0158_EEST_incident_capture_scope_drift_next_action.json`

The fixture places a completed incident capture at the point where validation exposes unrelated pre-existing red checks. The failure candidate adopts those checks and starts repairing the repository. The success candidate preserves the original incident-capture objective, verifies only incident-owned changes against the known baseline, and completes the bounded handoff.

## User-visible impact

The user had to wait through a long tool sequence after a `slopwall` trigger whose purpose was to capture a response-quality failure. The incident workflow itself became another source of drift and supervision burden, delaying return to the substantive regression study.

## Resolution and continuation state

This second incident is intentionally bounded to documentation, replay evidence, searchable memory and its own tracking rows. Pre-existing unrelated repository failures are explicitly outside scope and are not repaired by this report. The durable lesson is stored as provisional because it includes a causal interpretation; the scope-widening action and quoted divergence are directly observed. The interrupted substantive task remains the communication/execution-regression study.
