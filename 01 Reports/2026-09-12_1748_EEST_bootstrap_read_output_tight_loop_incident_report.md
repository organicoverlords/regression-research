# Incident: successful bootstrap `read_output` tight loop

**Date:** 2026-09-12 EEST  
**Issue:** organicoverlords/regression-research#1060  
**Classification:** assistant orchestration regression / repeated unchanged tool call  
**State:** PROVEN incident; causal change boundary narrowed, root cause not yet proven

## What happened

A supervising ChatGPT session was asked to update Stack Atlas / find / Vault / dependency information. Before doing that work it correctly performed the required bootstrap read, but then re-issued the same nonblocking bootstrap `read_output` call 13 additional times instead of transitioning to the requested task.

The conversation contains 14 bootstrap reads in the loop. The first was sufficient; 13 were redundant. The returned bootstrap snapshot kept the same `generated_at` value (`2026-09-12T14:39:25.594756+00:00`) while only its reported age increased from about 9.1 seconds to 56.7 seconds.

## Why this is an incident

The first response already satisfied every completion gate:

- `bootstrap_end.status=COMPLETE`
- no transport truncation or incompleteness was reported
- freshness was `FRESH`
- the tool returned `next_action=STOP_READING`
- the payload itself instructed consumers not to treat incomplete output as complete, but this output was complete

There was no changed binding, schema, authorization, route, freshness boundary, or other evidence that justified another read. This therefore was not recovery behavior. It was a tight unchanged-call loop caused by failure to latch the already-satisfied bootstrap prerequisite.

## Change-boundary investigation

### 1. Read-first bootstrap rollout is the enabling trigger surface

PR `regression-research#822` / merge `6c92a80c860a76fd375d87019273737dea73002c` made the persistent bootstrap `read_output(..., wait_ms=0)` the mandatory first machine action for fresh ChatGPT sessions. The contract explicitly also said not to loop and to reuse the already-consumed bootstrap on follow-ups.

This change made `read_output` the prerequisite action that can now be repeated, but it does **not** by itself explain the regression because its own stop/reuse wording is correct.

### 2. MCP tool-description sanitization removed an explicit model-side stop backstop

PR `chatgpt-mcp-clean#275` / merge `5ca1bcba6ebc66a4c69daac96921b75507b3e15a` changed the public process-tool descriptions. The prior `start_process` description explicitly stated:

> `If next_action=STOP_READING, do not call read_output.`

The live/sanitized description removed that model-directing behavior and kept only capability/parameter semantics. The current exposed tool schema matches the sanitized form.

This is the strongest recent change that could make a model-side repeat loop more likely: the response still carries `next_action=STOP_READING`, but the tool schema no longer explains that this is an imperative stop condition.

### 3. MCP revision semantics make `wait_ms=0` repeatable by design

PR `chatgpt-mcp-clean#284` / merge `cc680cbf354074b393151502c6f5ae556602a2e2` fixed first-read replay for positive waits, while deliberately preserving this behavior for zero-wait reads:

- positive waits can return `no_change=true` rather than replaying an already-delivered revision
- `wait_ms=0` remains a nonblocking retained-output snapshot

The bootstrap contract intentionally uses `wait_ms=0`. Therefore, once the assistant mistakenly re-enters the prerequisite, the tool can legitimately return the same retained bootstrap again instead of naturally breaking the loop with `no_change=true`.

### 4. Bootstrap hard-cap change is unlikely to be causal

PR `regression-research#1058` / merge `556e79888a2ebf2ddb9328f58a42f790eaa4e4a0` raised the hard bootstrap ceiling from 15,000 to 25,000 bytes while preserving the 15,000-byte compaction target. Its live canary was 14,932 bytes. The incident reads were complete and non-truncated.

This change may increase worst-case prompt/tool-result size, but there is no evidence that truncation or payload overflow caused this incident. Treat it as a weak contributing hypothesis only, not the cause.

## Current causal assessment

The most plausible failure chain is:

1. read-first bootstrap policy makes a zero-wait `read_output` mandatory at chat startup;
2. the assistant fails to persist the local state transition `bootstrap_verified=true` after the first successful read;
3. the newer MCP tool descriptions no longer contain the explicit `STOP_READING -> do not read again` model-side backstop;
4. zero-wait snapshot semantics continue returning retained output, so the erroneous prerequisite can repeat without a tool-level `no_change` breaker.

The **proven root failure** is the missing assistant-side prerequisite latch. The **strongest recent regression candidate** is the removal of the explicit STOP_READING behavioral instruction in MCP PR #275, interacting with the read-first bootstrap introduced by #822. PR #284 explains why the repeated zero-wait call remains mechanically repeatable. None of these observations prove that MCP itself initiated the loop; the tool returned the correct `STOP_READING` signal throughout.

## Recurrence-prevention rule

After one fresh, complete, non-truncated bootstrap response is consumed, mark the bootstrap prerequisite satisfied for the conversation. Do not issue another bootstrap read unless correctness materially depends on changed live state or the cached snapshot crosses the defined freshness boundary. `next_action=STOP_READING` is a terminal condition for the current read sequence.

Do not solve this by adding another retry layer. Do not change zero-wait snapshot semantics merely to compensate for assistant orchestration unless independent evidence shows that transport behavior is itself wrong.

## Stack Atlas / dependency-graph impact

No dependency-topology change is required. Current Stack Atlas discovery already resolves the relevant chain through `mcp.chatgpt_plugin_surface`, `execution.transport`, MCP topology/recovery, the bootstrap-read history, and the historical PRs above. This incident should be added as searchable Vault evidence rather than represented as a new component or dependency edge.

## Related

- `organicoverlords/regression-research#1060` — this incident
- `organicoverlords/regression-research#822` — read-first Personal Instructions bootstrap
- `organicoverlords/chatgpt-mcp-clean#275` — sanitized process-tool descriptions
- `organicoverlords/chatgpt-mcp-clean#284` — start/read revision semantics
- `organicoverlords/regression-research#1058` — bootstrap hard-cap change
- `organicoverlords/regression-research#820` — make Vault lessons affect future behavior
- `organicoverlords/agents#389` — separate single-fallback recurring-worker failure
