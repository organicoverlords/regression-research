# RED ALERT — unproven MCP batching-ban policy regression

Timestamp: 2026-09-06 03:46 EEST
Severity: RED ALERT / major assistant-orchestration regression

## What happened
A real user-visible security-reroute/stall investigation contained one compound MCPv3 `start_process` command. The assistant incorrectly promoted that single co-occurrence into a global shared-agent rule requiring MCP process payloads to be short and single-purpose, preferring sequences of short calls or wrappers. Agents PR #107 added the rule and PR #110 added a dedicated guard.

## Why this was a regression
The evidence did not establish that command batching caused the reroute. Earlier confirmed events already showed the underlying MCP session/process surviving while the assistant turn stalled above MCP. Treating one command shape as causal skipped controlled comparison and converted a provisional hypothesis into shared policy.

The blanket rule also had an unproven adverse-risk direction: forcing multi-step work into more tool calls can increase call churn, connection transitions, orchestration handoffs, and audit fragmentation. That risk is not itself proven causal either; the correct conclusion is that neither batching nor splitting should be globally mandated from the current evidence.

## Correct invariant
- Preserve MCP batching/compound calls as an available efficiency mechanism when they are appropriate and bounded.
- Do not globally ban or require batching, splitting, wrapper use, or a particular command shape based on one or a few correlated reroutes.
- Security-reroute/stall attribution requires correlated turn/session/process evidence and, where practical, controlled comparisons.
- A working MCP backend must not be restarted, rolled, or modified solely because the assistant turn stalls above it.
- New global shared-agent policy requires evidence proportional to its blast radius; a provisional debugging hypothesis is not sufficient.

## Correction performed
- agents PR #111 merged at c150f1c9e48b160b36e305bde15830f6fb2444f7.
- PR #111 reverts PR #107 and PR #110.
- The #107 one-line global command-shape rule is removed from canonical agents/main.
- Test-McpCommandShapeRule.ps1 from #110 is removed.
- MCP runtime, Caddy, WireGuard, and serving configuration were not changed.
- Live C:\Users\Lauri\.agents\RULES.md was not overwritten while another exact Busy owner was active; the bad #107 line had not been activated there during this lane.

## Validation
Focused agents policy tests passed: Test-AgentEntrypoints.ps1, Test-BusyQuiescenceRule.ps1, Test-WorkIdentityRule.ps1, and git diff --check. The broad local test sweep exposed an unrelated pre-existing Test-GoContinuationRule invariant failure on current main; that was not folded into this rollback.

## Evidence
- https://github.com/organicoverlords/agents/issues/106
- https://github.com/organicoverlords/agents/pull/107
- https://github.com/organicoverlords/agents/pull/110
- https://github.com/organicoverlords/agents/pull/111
- User correction: do not turn one non-proven bug report into a blanket anti-batching rule.
