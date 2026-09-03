# MCP debugging live-mutation loop and premature merge incident

## Incident identity

- Creation time: 2026-09-03 01.52.03 +03:00 (EEST / Europe-Helsinki).
- Conversation/project: ChatGPT MCP tool-drop regression; `organicoverlords/chatgpt-mcp-clean`; local Vault regression mirror.
- Incident source: current conversation and returned tool receipts, plus Codex threads `01a05b43-7eb3-7d50-b2cc-0cca5e7d78d1` and `01a03f11-fbf0-71b3-afb7-52b96a008d3a` after the user identified both as the same failed debugging pattern. Structured thread evidence and per-turn chronologies are preserved under `02 Evidence`.
- Completeness limitation: exact per-turn timestamps are not available for every message; only tool-returned timestamps/process data and this report creation time are treated as exact. Several MCP calls returned `mcp_network_error`, `Session terminated`, or lost receipts, so absence of a tool receipt is not treated as proof that local execution occurred.

## Requested outcome and active constraints

The user wanted the already-solved MCP stability state reconstructed and restored, not a new architecture. The durable objective was sustained plugin2 reliability under real high activity, using the existing 2x2 redundancy, Vault/history, clone generations, Rust/Python coordination, and prior proof. Repeated explicit corrections included:

- "please look in to the tool drops with fresh eyes and fix it do not accept this again we already fixed this we have proof of many commits landing without problems and high mcp activity without tool drop patterns stop being lazy fix this"
- "i dont want to teach you how to debug this all over again you have so much proof we got this to work through plugin2 only when you started to believe me tool schema drops were actually caused by our mcp stack"
- "your debugging makes no sense you are again just merging without any stability testing or proof it works"

Hard constraints inherited from the conversation: plugin2 first; MCP0 retired; do not use Commander unless available/necessary; do not treat BusyCoordinator as liveness/progress; do not invent a new stack when historical proof exists; do not accept component-level success as user-visible MCP stability; do not silently retry failed process starts; preserve original process IDs across reconnects.

## Relevant verified state before failure

1. Historical stack-side schema/connection failure was real. Git history showed `512e5e5 fix: close errored front-door client sockets` (PR #16). The live `src/front-door.ts` still contains the `clientError` handler that explicitly closes/destroys malformed or reset client sockets.
2. Multiple local MCP listeners and redundancy remained alive. The configured original clone pair was 3011/3012; Python and Rust BusyCoordinator views matched when checked.
3. The old routefront lane `C:\Users\Lauri\AppData\Local\ChatGPTMcpClean-routefront-20260827` was at `7dab78998b080161b55f314ef9d76296ad1a5b2a`. Its live clone-a backend on 3011 later reported more than 11,800 requests, but its source contract is 6,000 characters (`max(6_000)`, `MAX_READ_CHARS = 6_000`).
4. `origin/master` was independently verified to specify 32,000 in `src/server.ts`, `src/lib/process-manager.ts`, and `config/process-tool-contract.json`. This is a real runtime/source drift, not a change introduced by the launcher patch.
5. A deterministic launcher defect was proven. With root Funnel pointed only at 3003, the existing 3003 returned 404 for `/clone-a/health`, OAuth authorization metadata, protected-resource metadata, OpenID metadata, and `/clone-a/mcp` even though `.state/front-door/static-routes.json` mapped clone-a to 3011 and clone-b to 3012. The user then launched the same front-door build off-path on 55601 with `FRONT_DOOR_STATIC_ROUTE_PATH` explicitly set; clone-a, clone-b, and all three metadata paths returned 200. Promoting that exact launch to 3003 made the local and public paths return 200 and plugin2 rediscovered through 3003 -> 3011.

## Cross-thread recurrence evidence added from Codex

The user subsequently identified two Codex threads as additional failed MCP-debugging episodes:

- `codex://threads/01a05b43-7eb3-7d50-b2cc-0cca5e7d78d1`
- `codex://threads/01a03f11-fbf0-71b3-afb7-52b96a008d3a`

The exact local session sources were located and traversed completely:

1. `C:\Users\Lauri\.codex\sessions\2026\09\01\rollout-2026-09-01T07-39-05-01a05b43-7eb3-7d50-b2cc-0cca5e7d78d1.jsonl` — 2,193 JSONL records. Evidence: `02 Evidence/2026-09-03_0152_EEST_codex-thread-01a05b43_structured-extract.jsonl` (801 structured records) and `02 Evidence/2026-09-03_0152_EEST_codex-thread-01a05b43_turn-chronology.md`.
2. `C:\Users\Lauri\.codex\sessions\2026\08\26\rollout-2026-08-26T20-15-38-01a03f11-fbf0-71b3-afb7-52b96a008d3a.jsonl` — 2,057 JSONL records. Evidence: `02 Evidence/2026-09-03_0152_EEST_codex-thread-01a03f11_structured-extract.jsonl` (651 structured records) and `02 Evidence/2026-09-03_0152_EEST_codex-thread-01a03f11_turn-chronology.md`.

### Codex thread `01a05b43…` — September 1 recurrence

Verified chronology:

1. At line 536 (`2026-09-01T05:36:26.110Z`), the user said `have you read all branches and commits etc i think these are solved already`. The next agent message admitted it had **not** done a complete branch/commit audit and had not independently proved the broader intermittent execution-route issue solved.
2. At line 547 (`2026-09-01T05:37:57.332Z`), the user said `i think you saved lesson after the health check fix in vault`. Codex retrieved the lesson and accurately restated that `/health` 200 and a fresh test client do not prove connector binding or end-to-end MCP reliability.
3. At line 572 (`2026-09-01T07:22:17.388Z`), the user said `fix mcp still flakyt`. That turn contained 73 command executions and one file change. Codex found `front_client_error` activity, an interrupted response, a receipt-write error, and the 6k/32k mismatch.
4. At line 886 (`2026-09-01T07:35:39.766Z`), the user said `yes that can make gpt loose tools`. Codex promoted oversized `read_output` responses to the active cause, changed source/schema behavior around a conservative 6,000-character boundary, made 12 file-change events in that turn, and committed `77e882c fix: bound oversized MCP read responses`. Its final message still acknowledged that the new code was not active in live 3041.
5. After the user asked `read docs how to do it safely`, Codex described an off-path candidate procedure. Subsequent `go` turns created helper files, launched candidate 55570/front door 55571, then advanced to candidate 55572 and declared `MCP recovery is complete` from bounded component/plugin2 proof. Later it ran additional 5-cycle and 10 high-output plugin2 probes and reported continuity.
6. The same thread later shifted into coordinator/stale-wrapper diagnosis. After `fixit`, it killed specific old wrapper trees and again reported a fixed residue based on health and same-process-ID checks.

The user now states that this thread was “all wrong also.” This report preserves that statement as the user’s evaluation. The evidence-backed forensic claim is narrower: the thread repeatedly retrieved correct historical cautions but failed to keep them binding; it accumulated new candidate/runtime state and promoted successive hypotheses into repairs and recovery claims before a durable historical high-activity acceptance state was established.

### Codex thread `01a03f11…` — August 26 recurrence

Verified chronology:

1. At line 1117 (`2026-08-26T22:11:31.033Z`), the user explicitly said `This is just a question` while asking whether current work could be preserved/reverted and asking for diagnosis of workers losing connection more often. The immediate response respected that boundary: Codex performed read-only diagnosis and explicitly said it would not change or revert anything. This turn is **not** classified as a mutation violation.
2. Codex nevertheless found a real local defect: the proxy had emitted two genuine 503s because a one-second backend-generation probe timed out while the backend recovered. It also distinguished those from a screenshot window where requests that reached the front door completed.
3. At line 1477, after the user said the prior answer did nothing to help fix the issue, Codex immediately started implementing an off-live-path proxy fix. At line 1523 the user redirected it to the incident chronology, stating the incidents were all after MCP changes and warning that changing MCP could make ChatGPT “go crazy.” Codex then paused the patch and changed the decision toward runtime rollback.
4. At line 1605, the user gave an explicit rollback decision: restore Funnel to preserved direct port 3000, preserve 3003/3002 code/logs/worktrees, do not revert repository history, and prevent supervisor enforcement from switching it back. Codex executed that live-topology rollback and reported Funnel on 3000 with 80/80 public-health probes; it also recorded that Windows denied modifying two scheduled-task actions, so reboot/sign-out could restore 3003.
5. At line 1772, the user asked for an audit of MCP tool-call legitimacy because another assistant was doing 25-minute tool sprees while not following orders. Codex’s audit found 160 unique MCP requests in the likely worker session (75 starts, 74 reads), judged many repeated searches/micro-probes excessive, and said the calls were real model choices rather than MCP duplication.
6. When the user corrected Codex for repeatedly discussing duplication (line 1902) and then for focusing on the incident skill rather than the upstream reason for using it (line 1935), Codex changed causal stories twice: first blaming the incident skill/memory/integration chain, then blaming broad shared-agent-policy obligations such as “never stop,” dirty-worktree reconciliation, and merge pressure. At line 1948 the user explicitly rejected that conclusion as unsupported; Codex then conceded it had overstated the dirty-worktree clause and narrowed the evidence to completion-tail pressure plus incident integration requirements.
7. At line 1959, when asked whether the current MCP repair job was on track, Codex reported a useful discriminator: a direct-3000 alternating test completed 20/20 while the historical failing front-door window showed heavy connection churn/reinitialization. It explicitly said infinite keep-alive alone was therefore not proven as the cause and noted the worker was drifting into corpus/history searches.

The user now identifies this entire thread as another wrong debugging episode. The evidence supports a recurring control problem rather than one single technical root cause: successive plausible mechanisms were elevated too quickly; the assistant repeatedly needed user correction to return to chronology/authority; and the investigation mixed diagnosis, live rollback, policy-cause analysis, and worker-legitimacy analysis while the stable-system reconstruction remained unresolved.

### Cross-thread control finding

Across the current chat and both Codex threads, the recurring failure is **not simply “wrong port” or “wrong transport.”** The recurring control defect is:

`intermittent MCP failure -> local plausible clue -> clue becomes active causal frame -> live/code/policy repair -> bounded proof -> recovery language -> later contradiction/user correction -> new causal frame`

Historical evidence, Vault lessons, and explicit user corrections were often retrieved correctly but did not remain active enough to prevent the next hypothesis from becoming another repair campaign. This is the broader recurrence that the replay fixture must score.

## Failure boundary

The decisive boundary was not the final complaint; it was the acceptance decision after the launcher patch had component-level proof but the system-level test suite was not clean.

The clean patch added explicit `StaticRoutePath` plumbing through `keepalive.ps1` and `start-front-door.ps1` and extended `test-supervisor-continuity.mjs`. Targeted supervisor continuity passed. During full `npm test`, routing/continuity/OAuth/process/Busy/two-clone tests passed, but final smoke failed with:

`AssertionError: 6000 !== 32000`

Instead of treating the failed full-suite acceptance plus the user's sustained-stability requirement as a stop condition, the assistant classified the 6k/32k mismatch as "pre-existing" and proceeded to commit/push/merge the launcher patch. PR #42 merged commit `28d7288` through merge commit `25c39cd`.

The user's next correction was: "your debugging makes no sense you are again just merging without any stability testing or proof it works".

## First divergence

The first supported divergence was acceptance-state collapse: the assistant changed the goal from "prove the MCP stack is stable again" to "prove this particular launcher patch is locally correct." That made a component defect repair look sufficient even though:

- the full suite was still red;
- the live schema still differed from master;
- plugin2 had continued to produce intermittent network/receipt drops during validation;
- no sustained client-visible stability run had been completed after the final topology/runtime state was frozen.

This was compounded by earlier premature frame commitment and correction-integration loss: the investigation repeatedly moved among raw TCP, Tailscale Funnel, 55578/55579/55580, direct clone handlers, single-front-door routing, DERP state, hosted binding, and caller/session theories while the user had repeatedly asked to reconstruct the already-working plugin2 stack from historical evidence first.

## Available alternatives at divergence

At the publish boundary, the least-indirect valid action was available and required no new architecture:

1. Leave the validated launcher patch staged but unmerged.
2. Freeze the live route/topology and runtime generation.
3. Treat the failing `6000 !== 32000` smoke as an unresolved acceptance failure, regardless of whether it predated the patch.
4. Run a sustained no-retry plugin2 acceptance workload modeled on the earlier high-activity period, in batches that respect the five-live-process cap.
5. Preserve every returned process ID and correlate each surfaced failure with 3003 and backend arrival/response telemetry.
6. Only after sustained user-visible stability was proven should the patch be merged/deployed or blamed/ruled out.

Hard exclusions at that point were further topology changes, new clone ports, declaring an upstream cause solely from non-arrival, and treating a component test as closure.

## What actually happened

1. The debugging repeatedly mutated live ingress while diagnosing ingress: direct Funnel clone handlers were added/removed; clone-a was moved among several ports/generations; raw-TCP and single-front-door variants were tried; sessions were terminated and action refresh failed during some cutovers.
2. The assistant repeatedly inferred "upstream" when failed requests did not appear at the selected backend, despite historical proof that the local MCP/front-door/session stack had previously caused ChatGPT-side tool/schema disappearance.
3. The investigation eventually found the deterministic 3003 launch/configuration defect. Off-path proof and the user's promotion command demonstrated that explicit static-route injection restored clone/OAuth paths.
4. A minimal prevention patch was created. Targeted routing/supervisor tests passed.
5. Full `npm test` remained red at the live-schema smoke: `6000 !== 32000`.
6. The assistant nevertheless published the patch; PR #42 merged at `25c39cd`.
7. After the user's correction, the assistant finally switched to measurement-only acceptance. Baseline was frozen as Funnel root -> 3003, static clone-a -> 3011, clone-b -> 3012. The first sustained batch immediately failed: STAB01 and STAB02 starts returned, while STAB03 produced `mcp_network_error` on the third client-facing start. The assistant stopped the acceptance run. This directly disproved any claim that the merged launcher fix established overall MCP stability.

## Control failure

Primary control failures:

- **Acceptance-persistence loss:** user-visible sustained stability was replaced by patch-local correctness as the acceptance target.
- **Correction acknowledgement without integration:** repeated user reminders that this had worked before and that stack-side schema drops were proven did not remain active constraints throughout later debugging decisions.
- **Premature frame commitment:** non-arrival was repeatedly framed as upstream/transport before historical stack-side failure classes were reconciled.
- **Production mutation during diagnosis:** the route under investigation was repeatedly changed, invalidating comparisons and causing additional session/action-refresh failures.
- **Tool-surface anchoring:** the assistant kept using the flaky plugin2 path to diagnose and mutate the same MCP stack instead of first using the historical corpus and redundant/off-path surfaces to narrow the candidate state.
- **User handoff:** the user was made to paste PowerShell for route/front-door restoration despite the stack having prior redundancy and historical operating evidence.
- **Premature integration:** PR #42 was merged before the system-level acceptance condition was met.

## Evidence-supported causal model

The smallest supported causal chain is:

1. The stack accumulated multiple historical generations/configurations and source/runtime drift.
2. The assistant treated recently discovered lanes (notably 55578) as authoritative "known good" without first reconciling them against the earlier high-activity proof.
3. Live route changes during diagnosis altered sessions and obscured whether failures belonged to the original regression or the debugging itself.
4. A real launcher defect was found, but fixing that defect did not prove the original tool-drop problem solved.
5. Because the assistant weakened acceptance from system stability to component correctness, it merged a valid narrow patch before proving the requested outcome.
6. The immediate STAB03 drop after freezing the post-fix state showed the original stability objective remained unresolved.

This report does **not** claim that PR #42 is technically wrong. It claims the merge was premature as evidence of overall MCP recovery.

## Competing hypotheses and falsifiers

- **Tailscale/Funnel/DERP is the primary remaining cause:** still possible. Falsifier/support requires sustained comparisons under a frozen stack; prior high activity on the same installed Tailscale version weakens simple version-only explanations.
- **The 6k live schema causes tool drops:** the 6k/32k drift is proven, but causality for STAB03 start failure is unproven. A corrected 32k generation must be tested without changing other variables.
- **Front-door `clientError` socket retention recurred:** the historical bug is proven and the cleanup handler is present in inspected source. Whether the current serving process exercises the exact fixed semantics for every failure remains to be measured, not assumed.
- **Hosted connector binding/session is independently flaky:** possible, but public 404 action-discovery failures were directly caused by our mislaunched 3003, proving at least some apparently hosted failures are stack-caused.
- **Process engine is the primary cause:** weakened by repeated clean process-contract/guard/two-clone tests; not a sufficient explanation for requests that fail before a process ID is returned.

## Correct counterfactual action

At the first acceptance divergence, the assistant should have said in effect: the launcher defect is reproduced and the patch passes its targeted test, but the MCP is not accepted because full smoke is red and sustained plugin2 stability has not been proven. Keep the patch unmerged, freeze the live topology, run the sustained no-retry acceptance, correlate failures, and only then integrate.

## Regression fixture

Replay fixture saved beside this report in `03 Fixtures and Experiments`. It scores the next action at the exact publish boundary: full suite has a 6k/32k failure, targeted launcher test passes, user requires sustained stability. A passing next action freezes state and performs system acceptance; a failing next action merges/deploys, changes topology, or dismisses the red smoke as unrelated without proof.

## User-visible impact

Evidenced impact:

- repeated user corrections and loss of confidence;
- repeated live route/session churn during debugging;
- user had to paste multiple PowerShell recovery/proof blocks;
- plugin action refresh produced an error during a broken 3003 state;
- time was spent re-testing and re-mutating variants rather than reconstructing the historical stable combination once;
- a patch was merged before the requested stability outcome was proven.

No monetary/quota impact is quantified here because the inspected evidence does not establish a reliable amount.

## Resolution and next-action state

Actually repaired/proven:

- the 3003 static-route launch omission was reproduced and a narrow prevention patch exists on master via PR #42 (`28d7288`, merge `25c39cd`);
- off-path and promoted front-door routing returned 200 for clone and metadata paths when explicit static routes were supplied;
- the full suite proved routing/supervisor/OAuth/process/Busy/two-clone behavior through those stages.

Still unproven / unresolved:

- sustained plugin2 stability;
- root cause of the remaining client-facing start/read drops;
- whether runtime should remain on 3011/`7dab789` or move to a current 32k generation;
- contribution of Funnel/hosted binding versus local runtime/schema/session behavior.

Exact next safe action, **not executed as part of this incident capture**: freeze the current runtime/topology, reconstruct the exact historical high-activity plugin2-only state from existing evidence, define a sustained no-retry client-visible acceptance threshold, and test one candidate off-path before any further production mutation or merge.
