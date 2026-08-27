# Issue #174 ? frozen random tranche 2

Date: 2026-08-27 EEST

This tranche was drawn from the exact frozen 279-snapshot source manifest already landed in PR #181. It excludes all 24 tranche-1 episode keys, uses fixed seed **1742**, and again samples 12 Unreal/P3-heuristic plus 12 general tool-using user-task episodes.

## Result

Using the unchanged conservative codebook, **2/24** tranche-2 episodes are clear avoidable assistant tool-use mistakes: one general and one Unreal/P3-heuristic. Tranche 1 was 8/24. The combined frozen sample is therefore **10/48**: 7/24 general and 3/24 Unreal/P3-heuristic.

The large tranche swing (33.3% to 8.3%) is itself important: the original 24-episode pilot was too small to support a stable prevalence claim. The combined unweighted fraction is 20.8%. Applying only the known population stratum weights gives an exploratory point estimate of about **21.9%**, but no final confidence interval is reported because episodes remain clustered within conversations and the Unreal label is still a heuristic sampling label rather than manual domain coding.

## Two newly coded mistakes

`TASK_SUBSTITUTION`: a P3 forward-progress/fix episode was diverted into writing regression/memory artifacts and creating research worktrees instead of continuing the requested fix. The next user response was `?`. Counterfactual: complete the requested P3 repair path first; research artifacts are secondary unless required for that outcome.

`WRONG_ROUTE_AFTER_CAPABILITY_LOSS`: after the user asked to keep trying MCP periodically without stopping useful work, the assistant reported a Commander timeout and switched routes without first querying the generic connector registry for MCP0. The next user turn explicitly supplied that missing route and said not to use Commander. Counterfactual: generic namespace discovery before substituting another connector.

## Cases deliberately *not* counted

This tranche stress-tested construct validity. Several tempting positives were rejected:

- A web-research answer was followed by `slopwall` and was ~6.6k visible characters. Because the user explicitly requested online research, this is recorded as an adjacent response-synthesis/presentation failure, not automatically a tool-use mistake.
- One Unreal proof episode used **91 tool calls** and still produced no screenshot. It is a serious cost outlier, but it also discovered and repaired a missing `UnrealEditor.modules` manifest and moved the failure boundary. Call volume alone is not proof of avoidable tool misuse, so it stays out of the numerator pending root-incident analysis.
- A contact-sheet episode acknowledged that a previously shown sheet contained base/generation images rather than useful renders. The sampled episode itself did not repeat the delivery error, so the previous episode owns that candidate failure.

## Repeated positive controls

- Existing Unreal build state was preserved when terminal state could not be safely resolved; no duplicate build/runtime was launched.
- Shell execution was genuinely stuck even for a trivial `cmd echo`; no mutation was fabricated and claims were released.
- Build success remained explicitly separate from runtime visual proof.
- A prior unsupported `CONNECTOR_DROPS=6` claim was corrected from exact request/response evidence.
- Memory search correctly distinguished ?latest relevant saved entry returned? from ?actual latest occurrence.?

## Current interpretation

Across 48 frozen random episodes, the strongest mechanically preventable families remain **intent/action resolution before mutation**, **state/capability verification before proposing or routing**, **temporal/retrieval boundary enforcement**, and **avoiding substitution of adjacent work for the requested outcome**. Unreal-specific high-cost failures need a larger manually domain-coded sample before their incidence is ranked.
