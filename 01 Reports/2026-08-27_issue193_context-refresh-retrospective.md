# #193 retrospective matched-control analysis: context refresh and callable-tool loss

Date: 2026-08-27
Status: **association supported; causal effect NOT_PROVEN**
Primary evidence: raw ChatPort exports under `C:\Users\Lauri\Downloads\ChatPortEvidence\raw\2026-08-25`, pinned by SHA-256 in `02 Evidence/issue193/2026-08-25_refresh-vs-continuation-retrospective.json`.

## Result

Branch-aware reading of the primary raw exports found two independent current-ancestry memory-work conversations that received the exact user treatment `refresh your memory` around 12:50 EEST on Aug 25. Both refresh turns contain PCA past-chat context-citation metadata. On the immediately following `go`, both conversations then report connector/tool-surface loss: one after 40.435 seconds and the other after 28.182 seconds.

The strongest contemporaneous control is the parallel P3 conversation created at 12:41:10 EEST. Its `current_node` ancestry contains **zero** refresh nodes. During the exact 12:50:24–12:52:11 window spanning the two treated failures, that active branch executed **12 MCP0 calls and received 12 tool results, all `finished_successfully`**. Its raw mapping does contain a refresh branch, but that branch is not on `current_node` ancestry; this analysis therefore does not splice mutually exclusive branches together.

A secondary continuation control set contains six later fresh GPT-5.6 lanes whose second user prompt was ordinary `go`/`gogo`. They executed 32–65 subsequent tool calls each and contain no connector-loss signal under the frozen classifier. Descriptively this is 2/2 losses after refresh versus 0/6 after ordinary continuation. The exploratory one-sided Fisher exact value is `1/28 = 0.035714...`.

That number is **not a confirmatory p-value**. The comparison is retrospective, non-randomized, selected after the incident, and task-confounded: the treated conversations are memory-work lanes while controls include P3 and later memory/P3 work. It is useful as a compact description of separation in the preserved sample, not as proof of a platform causal effect.

## What changed

The previous hypothesis was only temporal: a refresh happened and a tool surface later disappeared. The raw exports now establish three stronger facts:

1. The treatment was real context retrieval, not merely assistant prose: both refresh turns carry `conversation_context_citation_metadata` with `retrieval_origin: pca`.
2. The two independent treated current ancestries both degraded on their next continuation.
3. A parallel non-refreshed current ancestry remained actively healthy on MCP0 throughout the same wall-clock interval, weakening a common 12:50 outage explanation.

## Hypothesis disposition

**H1 — refresh/PCA context recomposition can alter conversation-scoped callable-tool binding:** **SUPPORTED ASSOCIATION, NOT_PROVEN causal.** The retrospective separation is strong enough to justify the preregistered prospective test in #193.

**H2 — binding loss is independent of refresh:** **still possible, but weakened as the complete explanation.** This current Aug 27 conversation itself produced `Resource not found` / disabled-route transitions before any new treatment, proving refresh is not a necessary condition for all binding failures.

**H3 — only visible presentation changes while dispatch remains callable:** **weakened.** Historical treated lanes report rediscovery/callability failure, and the Aug 27 technical incident preserves client failures with no matching local request arrival.

**H4 — local MCP/Tailscale/backend outage explains the common event:** **further weakened for the inspected Aug 25 boundary.** The parallel P3 active branch was completing real MCP0 calls at the same time. The separate Aug 27 transport report also shows pre-local-arrival failures while local Funnel traffic remained healthy.

## What remains required

Do not close #193 from this retrospective result. The preregistered fresh-conversation control/treatment remains the clean causal discriminator. A prospective treatment should be run only from a conversation whose baseline canaries are healthy before refresh; the current chat is already contaminated and cannot serve as that baseline.

No ChatGPT memory, Personal Instructions, Settings, MCP deployment, Tailscale configuration, or server topology was changed for this analysis.
