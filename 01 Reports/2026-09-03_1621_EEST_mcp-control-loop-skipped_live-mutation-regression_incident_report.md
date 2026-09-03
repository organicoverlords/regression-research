# MCP control-loop skipped and live-mutation regression incident

## Incident identity

Creation time: 2026-09-03 16:21 EEST (Europe/Helsinki).

System: `organicoverlords/chatgpt-mcp-clean`; ChatGPT `plugin2`; clone-a public endpoint `https://kone.tailbf0440.ts.net/clone-a/mcp`; redundant clone-debug endpoint on local port 3002.

Incident class: debugging-control regression. The underlying MCP transport defect remains unresolved; this report is about the debugging process that repeatedly obscured it.

Primary method: Matt Pocock `diagnosing-bugs` skill. The skill requires a tight red-capable feedback loop before hypotheses, explicit reproduction/minimisation, 3–5 ranked falsifiable hypotheses, one-variable probes, and re-running the original loop after a fix.

## Requested outcome

The user wanted the previously achieved high-reliability MCP state restored and then tested with 100 separate real ChatGPT-to-plugin2 calls. The historical expectation was approximately one failure per 128 calls, not call-1 or call-2 failure.

The user repeatedly required the test to exercise the real hosted connector path rather than a local PowerShell loop. Later, the user explicitly pointed out the missing control experiment: run the same 100-call test against another already-running clone without switching or mutating the failing clone first.

## Exact user-visible failure

1. A fresh-chat 100-call test was stopped at the first failure as requested.
2. Result: `Successes: 0/100`.
3. Failure: call 1.
4. Error: `mcp_network_error` / `Connection failed`.
5. Endpoint: `https://kone.tailbf0440.ts.net/clone-a/mcp`.
6. An earlier run had already failed after only two calls.

These outcomes disqualified the serving clone-a state as a recovery baseline.
## Skill-phase analysis

### Phase 1 — feedback loop: failed

The skill states that the feedback loop is the core of the method and that no hypothesis work should proceed until one red-capable command or harness exists. It also specifically recommends looping nondeterministic triggers many times and using a differential loop between versions/configurations.

The user had already supplied the correct system-level loop: 100 separate hosted plugin2 calls, with an untouched redundant clone available as the differential control. That loop was not completed before further changes were made.

Instead, component checks, log correlation, OAuth-store comparison, launcher guards, runtime rebuilds, metadata changes, reconnects, and refreshes were allowed to substitute for the requested client-visible loop. None of those tests asserted the user's exact symptom: sustained hosted plugin2 call delivery.

### Phase 2 — reproduce and minimise: incomplete

The symptom was reproduced, but it was not minimised before new fixes were attempted. The smallest high-value differential was available: same ChatGPT client behavior, same machine, same Funnel host, different already-running clone. That comparison was not run first.

Because the control clone was skipped, the investigation retained too many possible variables: backend generation, OAuth state, tool metadata, ChatGPT binding state, Funnel path, runtime source, and connection behavior.

### Phase 3 — ranked hypotheses: skipped

The skill requires 3–5 ranked, falsifiable hypotheses before testing. This did not happen. Successive plausible explanations became active repair frames one at a time: stale OAuth identity, contaminated runtime, hosted binding/cache, connection/session continuity, and missing tool metadata.

The user was therefore not given the cheap checkpoint the skill explicitly requires, and could not re-rank the obvious control-clone hypothesis before mutations occurred.

### Phase 4 — one variable at a time: violated

The investigation changed multiple variables while the original failure remained unbounded. Changes/actions included restoring OAuth state, patching the OAuth launcher guard, replacing the runtime tree, adding tool titles/annotations, asking for reconnect, and asking for metadata refresh.

Several of those changes may be independently valid, but they cannot establish the cause of the tool-drop regression because the original 100-call loop was not held constant around them.
### Phase 5 — fix and regression test: wrong seam

The OAuth-store guard regression test correctly covered one launcher defect, but it did not cover the user-visible MCP drop. Likewise, the metadata build checks covered tool metadata, not sustained connector delivery.

The skill requires the regression test to exercise the real bug pattern at the correct seam and then requires the original Phase-1 loop to be rerun. That closure never happened. A component test was repeatedly allowed to create confidence about a system-level failure.

### Phase 6 — cleanup/closure: not met

The original repro still failed. The most recent system-level evidence was 0/100 with failure on call 1. Therefore no state reached the skill's completion criterion.

## First divergence

The first decisive divergence was after the user requested the 100-call test. Once plugin2 failed, the investigation should have established the same 100-call harness on the already-running alternate clone before changing clone-a or asking the user to reconnect/refresh.

The later fresh-chat call-1 failure made this even more explicit. Instead of immediately running the untouched-clone differential, the investigation continued into metadata and transport theories.

## Secondary regression: freezing failure instead of evidence

After the user identified the missing control test, the proposed response was to freeze clone-a while testing clone-debug. This repeated an earlier control mistake: preserving a known failing runtime as though it were a valid baseline.

The correct rule is: preserve the evidence of a failing state, not the failing state itself. Record generation, hashes, launch command, transport trace, OAuth metadata and route mapping, then restore production toward the last empirically high-reliability state while keeping the captured failure reproducible off-path if needed.

A state that fails 0/100 or on call 1 cannot be called known-good, cannot be used as recovery authority, and must not be frozen merely for diagnostic convenience.

## Evidence-supported root cause of this incident

The root cause of this incident is not yet the technical MCP defect. It is failure to keep the debugging feedback loop as the controlling authority.

The causal chain was:

1. User requested a system-level 100-call acceptance loop.
2. The loop went red almost immediately.
3. Instead of first running the same loop on an untouched redundant clone, local clues were promoted into causal theories.
4. Each theory caused another mutation or user-side reconnect/refresh step.
5. Component tests passed while the actual hosted-call loop remained unproven.
6. The user had to identify the missing differential experiment and then correct the attempt to freeze the 100%-failure state.
## Correct counterfactual

At the first failed 100-call attempt, the correct sequence was:

1. Capture the failing clone-a evidence without changing it further than necessary for capture.
2. Run the same 100 separate hosted calls against the already-running alternate clone, stopping at first failure under the same rule.
3. Compare only the clone target as the primary variable.
4. If the control passes materially better, diff the two clone generations/configurations and bisect from that evidence.
5. If both fail similarly, move the boundary upward toward shared Funnel/hosted-client behavior.
6. Only after the differential loop identifies a load-bearing variable should a fix be applied.
7. Rerun the original 100-call loop after the fix before declaring recovery.

## Prevention rules

1. **No-red-loop, no-theory rule:** for MCP flakiness, do not begin a new causal campaign until a red-capable hosted-call harness exists.
2. **Redundant-clone-first rule:** when an untouched redundant clone exists, test it before mutating the failing clone.
3. **Evidence freeze, not failure freeze:** preserve traces and exact state identifiers; do not preserve a 100%-failure runtime as production baseline.
4. **Baseline disqualification rule:** any generation that fails at call 1 or produces 0/100 is automatically disqualified as known-good/recovery authority.
5. **One-variable rule:** OAuth, runtime generation, Funnel routing, tool metadata, and ChatGPT reconnect/refresh state must not be changed in the same diagnostic step.
6. **No reconnect/refresh ritual:** reconnect or refresh only when a falsifiable hypothesis predicts it and the control loop can measure the result.
7. **Correct-seam regression rule:** launcher/unit/schema tests may validate narrow fixes but cannot close a hosted MCP reliability incident.
8. **Closure rule:** recovery requires the original client-visible loop to pass at the requested scale; component health, HTTP 200, or tool discovery are not substitutes.

## User-visible impact

1. The user had to supply the correct differential-debugging experiment despite not being responsible for implementation details.
2. Production clone-a was repeatedly changed while the central acceptance test remained incomplete.
3. The user was asked to reconnect and refresh despite those actions not being established by a completed differential loop.
4. Repeated changes destroyed clean comparisons and extended the incident.
5. A 100%-failure state was briefly proposed as something to freeze, requiring another user correction.

## Current status

The debugging-control failure is identified. The technical MCP root cause is still unresolved.

The next valid diagnostic action is the untouched-clone differential: run the same hosted 100-call test against clone-debug/3002 without first changing that clone. The result must be compared with clone-a's call-1 failure before any new MCP mutation is justified.

A regression fixture for this decision boundary is stored beside this report under `03 Fixtures and Experiments`.