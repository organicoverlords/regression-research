# Issue #174 ? assistant tool-use mistake pilot

Date: 2026-08-27 EEST
Status: pilot complete; prevalence study not complete

## Frozen dataset

The live downloader was still changing the corpus during analysis, so the pilot was frozen at `2026-08-27T13:47:06.607000+03:00`. The frozen source set contains **279 raw conversation snapshots**, deduplicating to **276 conversations**. Within the Aug 24?27 message window it yields **1,361 user-task episodes that contain at least one assistant tool call**: 591 Unreal/P3-heuristic episodes and 770 non-Unreal episodes. Source-manifest SHA-256: `f466f150e29c40fad902f5f1d0ad841d00db4c732fb529e7bd6351ef83dce210`.

The pilot used fixed random seed **174** and sampled **24 episodes**, deliberately stratified 12 Unreal/P3-heuristic + 12 general. Because this is stratified and some sampled episodes share a conversation, the raw 24-episode proportion is **not a final population prevalence estimate**.

## Conservative pilot coding

Eight of 24 sampled episodes contain a clear avoidable mistake with a concrete counterfactual. The split is **6/12 general** and **2/12 Unreal/P3-heuristic**. The unweighted raw pilot fraction is 33.3%. A simple IID Wilson interval for 8/24 would be about 18.0?53.3%, but that interval is intentionally **not used as the population CI** because it ignores the stratified design and conversation clustering. The final study must weight strata and cluster uncertainty by conversation.

The eight clear pilot failures are:

1. `CAPABILITY_STATE_NOT_CHECKED`: proposed `wait_ms` as a remedy before checking that it was already present.
2. `SCOPE_EXPANSION_INTENT_INFERENCE`: converted historical-corpus preservation into an unwanted future-download queue.
3. `TEMPORAL_SCOPE_LEAKAGE`: retrieved repair-era instructions outside the user?s pre-break evidence window.
4. `RETRIEVAL_ROUTE_ERROR`: direct Library path failure was initially misclassified until file identity was rediscovered correctly.
5. `INTENT_ACTION_UNRESOLVED`: queue-pressure complaint triggered five scheduler mutations (pause workers) before the intended action (redirect workers) was resolved.
6. `UNNECESSARY_TOOL_USE`: a literal ?send exactly `busy_list`? request caused five needless tool calls.
7. `INTENT_DRIFT`: researched a tagging UI while the user wanted memory organization/debug surfaces.
8. `INVENTED_INFRASTRUCTURE`: designed a change around an orchestration queue that did not exist.

These are conservative: ambiguous episodes were left negative rather than forced into a category.

## Important controls

Not every tool failure was coded as an assistant mistake. Clean controls included:

- Unreal proof preflight: the assistant localized `P3_PREFLIGHT_TIMEOUT` to `Test-P3WorkerEditorPreflight.ps1`, withheld rendered acceptance, and named the decisive log instead of blindly rerunning the proof.
- A repository search 502 during Chain Lightning proof discovery: it switched evidence routes and did not fabricate local execution.
- MCP debugging: connector disappearance and Windows process-control slowdown were experimentally separated rather than collapsed into one cause.
- Integration recovery: an existing process/check was resumed and the merge waited for the required check instead of launching duplicate work.

This control set is essential because counting every backend error would inflate assistant-failure prevalence.

## Candidate classes discovered outside the random pilot

Chronological reading surfaced additional high-value classes that need targeted prevalence measurement, but they are not included in the 8/24 count unless sampled:

- `WRONG_ABSTRACTION_LAYER`: in the spell-animation conversation, the assistant initially chased gameplay/C++ VFX emission when the requested work was authoring the existing Niagara effect assets. The user corrected the layer explicitly. Epic?s Niagara documentation independently supports treating Systems, Emitters, Modules, and Parameters as a distinct asset-authoring surface rather than conflating it with gameplay trigger wiring.
- `RETRY_WITHOUT_NEW_EVIDENCE`: repeated attempts against the same failing MCP/Unreal control path occurred before a materially different discriminator was introduced.
- `OBSERVABILITY_DENOMINATOR_BIAS`: an earlier MCP-rate analysis used server-arrival logs to reason about failures that can occur before requests reach the server. That denominator cannot observe the failure class by construction.
- `PREMATURE_FINALIZATION`: prior conversations show a running process being abandoned by ending the turn rather than reading the existing process ID.

## MCP telemetry boundary

For 2026-08-24 through the pilot analysis window, the local transport telemetry contains about **95.8k request starts and 95.8k response finishes**, overwhelmingly successful server arrivals. This is useful for server-side latency/error characterization, but not as the outer denominator for connector-side disappearances that never arrive. Conversation task episodes therefore remain the outer behavioral denominator; MCP telemetry validates what reached the server.

## Unreal-specific guardrails suggested by evidence

The Unreal slice should route by **work layer before tool choice**:

- Build/compile question ? build target/configuration tooling.
- Automation/functional verification ? Unreal Automation test route where appropriate. Epic documents command-line automation through `-ExecCmds="Automation RunTest ...;Quit"` and report export.
- Niagara asset authoring ? inspect/edit Niagara System/Emitter/Module/Parameter state, not gameplay C++ merely because the effect is triggered from gameplay.
- Runtime visual acceptance ? worker-owned Editor/PIE/offscreen proof route. Epic?s current command-line reference explicitly documents `RenderOffScreen` and `unattended`.
- Failure ? classify the phase (admission/preflight, build, Editor startup, PIE, capture, pixel/proof gate) and inspect the decisive phase log before rerunning the whole chain.

The highest-value mechanical guardrail seen so far is an **action-target precondition** for fan-out mutations: before changing multiple workers/processes/schedules, the plan must have a resolved action, target set, and destination/state. This would have blocked the sampled ?pause all five workers? mistake.

## Statistical plan after pilot

1. Freeze every analysis release with a source manifest; never let a live downloader silently alter denominators.
2. Expand to a larger stratified random sample, but sample conversations first or use conversation-cluster-aware inference.
3. Manually recode the Unreal heuristic stratum into actual Unreal-domain opportunities.
4. Report conversation incidence, episode incidence, root-incident cascade size, and per-call cost separately.
5. Use stratum weights for population estimates and cluster-aware bootstrap/design variance for uncertainty. CDC guidance on clustered samples notes that ignoring within-cluster correlation generally understates variance and effective sample size.
6. Keep a held-out recode set and report coding disagreements/borderline cases.
7. Rank prevention mechanisms by estimated prevented high-severity incidents per unit of added complexity, not by raw call count.

## External references checked

- Epic Games, *Overview of Niagara Effects for Unreal Engine 5.8*: https://dev.epicgames.com/documentation/en-us/unreal-engine/overview-of-niagara-effects-for-unreal-engine
- Epic Games, *Run Automation Tests in Unreal Engine 5.8*: https://dev.epicgames.com/documentation/en-us/unreal-engine/run-automation-tests-in-unreal-engine
- Epic Games, *Unreal Engine Command-Line Arguments Reference 5.8*: https://dev.epicgames.com/documentation/unreal-engine/unreal-engine-command-line-arguments-reference
- NIST/SEMATECH, *Confidence intervals for a proportion* (Wilson method): https://itl.nist.gov/div898/handbook/prc/section2/prc241.htm
- CDC/NCHS NHANES, *Variance Estimation Module*: https://wwwn.cdc.gov/nchs/nhanes/tutorials/varianceestimation.aspx/SampleDesign.aspx

## Artifacts

- `02 Evidence/issue174/2026-08-27_pilot-source-snapshot.json` ? exact frozen source membership and denominator metadata.
- `02 Evidence/issue174/2026-08-27_pilot-codebook.md` ? coding and statistics rules.
- `03 Fixtures and Experiments/2026-08-27_issue174_pilot-coded.csv` ? 24-row machine-readable coding table.

Raw transcripts remain in the private local corpus and are not duplicated into Git.
