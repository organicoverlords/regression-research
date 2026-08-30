# Assistant Stack Source Inventory — observed 2026-08-27

This inventory supports [regression-research #155](https://github.com/organicoverlords/regression-research/issues/155). Observation date is 2026-08-27 unless a source itself carries an earlier date. Credentials, raw private conversation content, hidden instructions, and unnecessary personal data are intentionally excluded.

| Source | Evidence used | Observation |
|---|---|---|
| [regression-research #155](https://github.com/organicoverlords/regression-research/issues/155) | Required architecture scope, triggering Codex/WebGPT conflation, intended WebGPT continuity role, acceptance criteria | Live issue snapshot; updated 2026-08-27 07:24:47Z |
| [regression-research #125](https://github.com/organicoverlords/regression-research/issues/125) | Stack-hardening goal, MCP BUSY single-authority target, local degradation, memory side-effect boundary | Live issue snapshot |
| [`regression-research/NORTH_STAR.md`](https://github.com/organicoverlords/regression-research/blob/main/NORTH_STAR.md) | “boring to use” finish line; evidence sources; ownership, capability routing, memory, repo workflow, user-experience acceptance | Blob observed on main; SHA `561ef73442a6ca513de24ce921f9ab67ceb236ab` |
| [`regression-research/AGENTS.md`](https://github.com/organicoverlords/regression-research/blob/main/AGENTS.md) | Shared policy v1.18 inheritance; MCP working-surface and BUSY rules | Live main |
| [`agents/SHARED-AGENT-POLICY.md`](https://github.com/organicoverlords/agents/blob/main/SHARED-AGENT-POLICY.md) | Auditable mirror of shared v1.18; MCP0 BUSY sole live ownership; GitHub BUSY projection only; precedence; no second authority | Blob SHA `d7bc088000ef1eaabcc3b66115ce8f4cc6ce62fd` |
| [`p3/AGENTS.md`](https://github.com/organicoverlords/p3/blob/main/AGENTS.md) | P3 “go work” flow, five-worker role, runtime proof gate, and repo-local ownership contradiction | Blob SHA `1ef389ddfe5940f2c84c9ac2901059a386da4cfd` |
| [`Tiny3D/AGENTS.md`](https://github.com/organicoverlords/Tiny3D/blob/main/AGENTS.md) | Shared v1.18 inheritance; no additional ownership authority observed in fetched file | Blob SHA `7855e142d87d4178ed663202db2176e0e64f86c3` |
| [`lowvram3d-studio/AGENTS.md`](https://github.com/organicoverlords/lowvram3d-studio/blob/main/AGENTS.md) | Shared v1.18 inheritance plus repo-local named authorities; duplicate “live lane/ownership authority” finding | Blob SHA `c8cdaf8cd2722d1acc139bfb9250403313a70162` |
| [`chatgpt-mcp-clean/README.md`](https://github.com/organicoverlords/chatgpt-mcp-clean/blob/master/README.md) | Stable-front-door intent and exact seven-tool worker contract | Blob SHA `bbd874b6f62e8f309480f5b7da1082f382406172` |
| [`chatgpt-mcp-clean/AGENTS.md`](https://github.com/organicoverlords/chatgpt-mcp-clean/blob/master/AGENTS.md) | Stable front door `127.0.0.1:3003/mcp`; replaceable 3001/3002 backends; Tailscale Funnel; process pinning; transparent adapter behavior | Blob SHA `184d48608254d79dc65356692979a0885b333eef` |
| [`chatgpt-mcp-clean/package.json`](https://github.com/organicoverlords/chatgpt-mcp-clean/blob/master/package.json) | MCP SDK 1.24.3 and current continuity/BUSY/smoke test suite | Blob SHA `1092c86d1cd1418e9dc16f49767b211c2b326017` |
| [`chatgpt-mcp-clean #7`](https://github.com/organicoverlords/chatgpt-mcp-clean/issues/7) | Failure-class boundary: pre-dispatch/non-arrival, listener, Funnel/public path, server response, intentional bounded wait | Live issue; updated 2026-08-26 |
| WebGPT live MCP0 observation | Exact seven tools were discovered; `busy_list` succeeded earlier in the same conversation; after changing connector surfaces and rediscovering, direct MCP0 calls returned `Resource not found` | **PROVEN conversation-scoped binding/callability transition**. No backend telemetry inspected; backend health remains **UNKNOWN** |
| WebGPT live task-scheduler state | Exact five `P3 Asset Sprint` records; schedules/scopes; enabled/paused state; last-run metadata | **PROVEN:** Sprint 3 enabled; Sprints 1/2/4/5 paused. Scheduler metadata did not expose attributable run outcomes |
| Current user-authored personal-instruction state | Establishes WebGPT startup continuity behavior and bounded-task completion behavior | Private source observed in WebGPT; **contents intentionally not copied** |
| Current ChatGPT memory context | Confirms existence of an advisory persistent-context layer distinct from conversation history and Vault corpus | Private source observed in WebGPT; **contents intentionally not copied** |
| Vault corpus / memory bank | External corpus role and read path are part of current user-authored continuity setup | Private/local source; exact current `recent` output **not observed in this work session** because MCP callability became unavailable |
| Recent P3 asset-placement PRs, including [#590](https://github.com/organicoverlords/p3/pull/590), [#577](https://github.com/organicoverlords/p3/pull/577), [#575](https://github.com/organicoverlords/p3/pull/575), [#567](https://github.com/organicoverlords/p3/pull/567), [#561](https://github.com/organicoverlords/p3/pull/561), [#553](https://github.com/organicoverlords/p3/pull/553) | Current concrete examples where source/build evidence can be green while rendered/runtime acceptance remains `NOT_PROVEN` | Used only as proof-gate examples; **not attributed to specific Sprint 1–5 workers** without run provenance |

## Live timed-worker snapshot

All schedules are hourly in `Europe/Helsinki`; the effective minute is derived from the live scheduler record.

| Worker | Effective schedule | Enabled | Scope summary | Outcome evidence observed |
|---|---|---:|---|---|
| P3 Asset Sprint 1 | Hourly at :36 | No | Convergence-first: finish/prove/merge existing asset-placement work before adding another increment | No attributable run result exposed |
| P3 Asset Sprint 2 | Hourly at :48 | No | Same convergence-first scope | No attributable GitHub result exposed by current scheduler read |
| P3 Asset Sprint 3 | Hourly at :36 | Yes | Bounded asset-placement improvement using existing Tiny3D/P3 assets; verify through normal/strongest proof path | Last-run metadata exists; no attributable GitHub result exposed |
| P3 Asset Sprint 4 | Hourly at :48 | No | Same bounded asset-placement scope as Sprint 3 | No attributable run result exposed |
| P3 Asset Sprint 5 | Hourly at :00 | No | Same bounded asset-placement scope as Sprint 3 | No attributable run result exposed |

The duplicate :36 and :48 schedule minutes occur only among records that are currently paused/enabled in different combinations. The observed active recurring capacity is therefore one enabled record, not five simultaneous active workers.

## Evidence boundaries

- **No current Codex tool discovery was performed from Codex.** Historical Codex MCP0 availability is recorded by #155; current Codex binding is **UNKNOWN**.
- **No MCP0 server/front-door telemetry was read for the later `Resource not found` calls.** Current backend health is **UNKNOWN**.
- **No account-level MCP connector configuration page/state was inspected.** Account configuration is **UNKNOWN** and must remain separate from conversation discovery/callability.
- **No memory or personal-instruction store was mutated.**
- **No shared repository state was mutated during this evidence pass after MCP BUSY became unreadable.**
