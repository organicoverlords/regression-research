# MCPv3 regression — first post-fix execution-binding failure

**Date:** 2026-09-03
**Severity:** High
**Status:** Open — current execution recovered; root cause unresolved

## Summary

MCPv3 had executed successfully earlier in the same ChatGPT session after the new MCP fix. Later, ChatGPT could still discover the expected MCPv3 tool schema, but invocation failed before any command reached the Windows machine or VPS backend.

This is the first observed execution-binding failure after the new MCP repair and is therefore a regression candidate against the repaired production route.

## Observed failure sequence

1. MCPv3 discovery returned the expected tools:
   - `start_process`
   - `read_output`
   - `kill_process`
2. A normal `MCPv3.start_process` invocation was rejected before execution with:
   - `Resource not found: MCPv3.start_process`
3. After rediscovery, another harmless invocation was rejected before execution with:
   - `The MCPv3 tool has been disabled.`
4. No failing command reached Windows or the VPS/backend.
5. No MCP configuration, service, VPS process, front door, backend, or repository state had been modified immediately before the failure.

## Expected invariant

Successful MCPv3 discovery should be followed by a callable semantic execution route.

The observed state violated that invariant: schema discovery succeeded while invocation binding failed.

## Reproduction used during failure

1. Discover MCPv3 tools.
2. Confirm `MCPv3.start_process` is returned.
3. Invoke:

```powershell
Write-Output 'MCPV3_REFRESH_OK'
```

4. Invocation is rejected before machine execution.

## Evidence boundary at failure

**PROVEN**

- ChatGPT could discover the MCPv3 schema.
- ChatGPT could not invoke the discovered semantic execution tool.
- The rejection occurred before machine execution.

**NOT PROVEN**

- VPS/backend failure.
- MCP front-door failure.
- Configuration regression.
- Root cause.

## Later positive control — 2026-09-03 21:31 EEST

After rediscovery in the same conversation, the exact harmless execution probe succeeded:

```powershell
Write-Output 'MCPV3_REFRESH_OK'
```

Returned execution evidence:

- `mcp_status`: `OK`
- `process_state`: `COMPLETED`
- `stdout`: `MCPV3_REFRESH_OK`
- `exit_code`: `0`
- Windows PID: `13072`
- MCP process ID: `f35a357c-ece7-4fcb-a95f-5bad75667ef4`
- Started: `2026-09-03T18:31:04.690Z`
- Finished: `2026-09-03T18:31:05.013Z`

This proves the MCPv3 execution path, Windows machine, and downstream backend path were callable at that later point.

It does **not** prove what caused the earlier rejection.

## Narrowed failing boundary

Current evidence narrows the regression candidate to the layer upstream of actual MCP machine execution:

**ChatGPT tool discovery / binding / invocation routing → MCPv3 transport entry**

Because the later semantic execution reached Windows successfully, the earlier failure must not be documented as a proven VPS, backend, front-door, service, or configuration outage.

The strongest defensible statement is:

> During the incident, ChatGPT exposed the MCPv3 schema but rejected invocation before downstream execution. The condition later cleared without any MCP stack mutation observed in this investigation.

## Stack Atlas context

Stack Atlas resolves the downstream transport owner as `mcp_front_door`, with canonical sources:

- `%LOCALAPPDATA%\ChatGPTMcpClean\keepalive.ps1`
- `chatgpt-mcp-clean/src/front-door.ts`

Atlas also states that production path-scoped minimal clones may bypass the root front door through direct Funnel handlers. Therefore no downstream component should be changed merely because the ChatGPT binding layer rejected an invocation.

## Investigation rule

Start at the exact failing boundary and move downstream only when evidence requires it:

**ChatGPT tool binding / invocation routing → MCPv3 transport/front-door path → VPS/backend**

Do not redesign the MCP stack or change unrelated components until the failing boundary is reproduced and identified.

## Required follow-up evidence

On recurrence, preserve these facts from the same attempt before changing anything:

1. Tool discovery result showing the MCPv3 schema/tool names.
2. Exact invocation rejection text and timestamp.
3. Whether any process receipt/process ID was returned.
4. Immediate semantic retry only after rediscovery, without MCP-side mutation.
5. If invocation reaches MCP, then and only then inspect downstream front-door/backend evidence.

## Current disposition

The production route is currently callable based on the 21:31 EEST positive control. The incident remains **Open** because the transient discovery-versus-invocation binding failure is real, first-seen post-fix, and its root cause is not yet proven.


## Log evidence - transport boundary

Read-only inspection of the live production clone log at `%LOCALAPPDATA%\ChatGPTMcpClean\minimal-connectors\clone-a\transport.jsonl` adds a stronger boundary.

1. For caller `caller_2bfa44f3de4c`, the first transport event in the file is `2026-09-03T18:30:55.861Z` (21:30:55.861 EEST), request `0d13b99d-3afc-4ca7-a672-56ffec4fd3e1`.
2. Therefore the reported ~21:27 EEST binding/disabled failures produced no downstream transport entry for this caller.
3. Other callers were receiving HTTP 200 `start_process` and `read_output` responses on clone-a during the surrounding window, so the production clone was not globally unavailable.
4. The recovered `MCPV3_REFRESH_OK` call reached clone-a at `2026-09-03T18:31:04.676Z`, started Windows process `f35a357c-ece7-4fcb-a95f-5bad75667ef4` at `18:31:04.690Z`, and completed its `tools/call start_process` response with HTTP 200 at `18:31:05.019Z`.
5. A bounded search across `ChatGPTMcpClean` `.log`, `.jsonl`, and `.txt` files found zero occurrences of the exact rejection strings `Resource not found: MCPv3.start_process` and `The MCPv3 tool has been disabled.`
6. Chrome has no `chrome_debug.log` enabled at `%LOCALAPPDATA%\Google\Chrome\User Data\chrome_debug.log`; there is no local browser debug log available to bridge the missing upstream event.

This materially strengthens the incident boundary: the rejected calls did not reach the MCPv3 production transport logger. The failure is upstream of clone-a request handling. The local MCP logs cannot establish which ChatGPT-side binding/enablement component rejected the call.
