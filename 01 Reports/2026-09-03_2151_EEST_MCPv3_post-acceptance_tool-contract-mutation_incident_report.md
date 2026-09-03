# MCPv3 incident — post-acceptance tool-contract mutation and first execution-binding drop

**Date:** 2026-09-03  
**Severity:** High  
**Status:** Mitigated — accepted tool contract restored and revalidated 300/300; ChatGPT-side binding root cause remains unproven

## Summary

After MCPv3 had reached an accepted working state, including the user-referenced 300/300 successful-call run, an unrelated PowerShell command-generation hardening task was allowed to mutate the model-facing `start_process` tool description.

That mutation was not required to enforce PowerShell safety. The runtime guard could and should have remained entirely behind the existing `start_process` boundary. Changing the description altered the accepted MCPv3 process-tool contract after acceptance, invalidated the prior acceptance result, and violated the stack rule that tool descriptions/schema are connector identity rather than an instruction/prompt channel.

Later in the same day, MCPv3 experienced its first post-fix execution-binding failure: discovery still returned `start_process`, `read_output`, and `kill_process`, but invocation was rejected upstream of machine execution with `Resource not found: MCPv3.start_process`, followed by `The MCPv3 tool has been disabled.` The transport log proves those failing calls did not reach clone-a.

The exact host-side causal link between the contract mutation and the ChatGPT binding rejection is not directly observable from local MCP logs. However, the post-acceptance contract mutation itself is a confirmed assistant-caused regression in change control and acceptance validity, and it temporally precedes the first binding drop.

Related initial boundary report:

`01 Reports/2026-09-03_2132_EEST_MCPv3_first-post-fix_execution-binding_failure_incident_report.md`

## What the assistant changed incorrectly

PR #48 (`5e715643186addbfe06a1e4b96c15680c552b23d`) changed the accepted `start_process` description from:

> Start a noninteractive PowerShell process. By default this call waits up to 750 ms ...

into a longer Windows PowerShell 5.1 compatibility/policy description that instructed the caller not to use `&&`, `||`, `??`, `$PID`, `$args`, or direct `foreach` piping.

The same change updated `config/process-tool-contract.json` and the pinned server hash. This meant the process-tool contract itself changed even though the requested fix only needed internal command validation.

PR #49 retained rejected-command evidence but did not undo the contract mutation.

## Why this was wrong

1. The production tool contract had already been accepted and should have been frozen.
2. The user had not requested a tool-description or schema migration.
3. The repository already required the front door not to change tool descriptions or schemas.
4. Compatibility guidance belongs in implementation/policy, not in model-facing tool descriptions.
5. The PowerShell guard was independently implementable inside `start_process`; therefore the description mutation had no necessary functional justification.
6. Any acceptance run performed before the contract mutation no longer established the behavior of the mutated connector identity.

## Binding-failure evidence boundary

The initial incident report established:

- discovery still exposed the expected three MCPv3 tools;
- invocation then failed with `Resource not found: MCPv3.start_process`;
- after rediscovery, invocation was rejected with `The MCPv3 tool has been disabled.`;
- no failing command reached Windows or clone-a;
- clone-a continued serving other callers around the same window;
- the exact rejection strings do not occur in the MCP backend/transport logs.

Therefore the execution-binding rejection remains upstream of clone-a request handling. Local evidence cannot prove which ChatGPT-side binding/enablement component rejected the calls.

## Confirmed process root cause

The confirmed process failure was **scope expansion after acceptance**:

- a separate PowerShell command-generation problem was treated as justification to modify the connector contract;
- the assistant used a tool description as a behavioral instruction channel;
- the assistant did not treat the accepted tool contract as frozen after the successful acceptance run;
- the existing contract test was insufficient because both the runtime description and its expected JSON contract were changed together, so the verifier accepted the migration rather than rejecting it.

This is independently actionable even though the host-side binding mechanism is not locally observable.

## Corrective change

PR #51 restores the accepted process-tool contract and adds a freeze guard.

Change set:

1. Restore `config/process-tool-contract.json` to the exact pre-mutation accepted bytes.
2. Restore the `start_process` runtime description to the exact accepted text.
3. Keep PowerShell 5.1 hardening entirely internal to `start_process`.
4. Add a byte-level SHA-256 assertion for the accepted process-tool contract in `scripts/verify-process-contract.mjs`.
5. Add an explicit repo rule: model-facing tool names, descriptions, and schemas are frozen connector identity; tool descriptions must not be used for operating instructions, compatibility advice, prompts, or policy text.
6. Require explicit user approval plus a fresh end-to-end acceptance run for any future contract migration.

Accepted contract SHA-256:

`5d56d724d622fe5bc3e946fe4125b19491ac3e0d4c67177792744a446529c9ac`

Restored `dist/server.js` SHA-256:

`7c2fd4be29b79146935cbc4a9af8dfe9c431407d31f14cc6fcecd4255e2565a5`

The restored server hash is the same pinned server hash used before PR #48 changed the description.

## Deployment evidence

PR #51 merged as:

`1fb6b8f8461aa07263fe23a24da4e1be1dd9428e`

Production clone 3011 was restarted without changing Caddy, the VPS tunnel, OAuth topology, or production ingress.

Deployment log:

`%LOCALAPPDATA%\ChatGPTMcpClean\minimal-connectors\clone-a\restore-frozen-contract-deploy-20260903.log`

Observed restart:

- old listener PID: `26096`
- new listener PID: `5604`
- ready timestamp: `2026-09-03T21:48:49.5048428+03:00`

A direct ChatGPT MCPv3 semantic call after restart succeeded:

```powershell
Write-Output 'MCPV3_FROZEN_CONTRACT_OK'
```

Result:

- process id: `adddd3a2-f6a7-4ab3-ab04-c6090289e66f`
- exit code: `0`
- stdout: `MCPV3_FROZEN_CONTRACT_OK`

A public-path schema/semantic probe through `https://5-61-91-127.sslip.io` also passed with exactly:

- `kill_process`
- `read_output`
- `start_process`

and a successful `start_process`/read result.

A subsequent public-path acceptance loop asserted the restored `start_process` description exactly and completed 300/300 sequential `initialize -> initialized -> start_process` iterations with matching stdout and exit code 0. Total loop time was `414995 ms`. The production transport recorded 300 `process_started` events for the acceptance caller. A fresh direct ChatGPT MCPv3 call after that loop also completed successfully with stdout `MCPV3_POST_300_OK`.

## Validation

Focused validation after restoration:

- TypeScript build: PASS
- process contract verifier: PASS
- accepted contract byte hash: PASS
- restored server hash: PASS
- PowerShell preflight regression test: PASS
- README timeline check: PASS
- minimal-clone identity preflight: PASS after the change was committed into a clean tracked tree
- direct ChatGPT MCPv3 semantic call after deployment: PASS
- public schema/semantic probe after deployment: PASS
- 300-iteration public `initialize -> initialized -> start_process` acceptance: PASS, 300/300, elapsed `414995 ms`
- direct ChatGPT MCPv3 semantic call after the 300/300 run: PASS (`MCPV3_POST_300_OK`)

## Recurrence prevention

The contract verifier now fails if `config/process-tool-contract.json` differs byte-for-byte from the accepted contract hash, even if someone edits both the server description and the expected JSON together.

The operational rule is now explicit:

> Runtime implementation may change behind the existing contract. Tool names, descriptions, and schemas do not change unless the user explicitly authorizes a contract migration. Tool descriptions are not an instruction/prompt channel.

Any authorized contract migration invalidates prior acceptance and requires a fresh end-to-end acceptance run before production is considered accepted again.

## Remaining uncertainty

The local stack cannot prove that the description mutation technically caused ChatGPT's `Resource not found` / `tool has been disabled` state. The failing requests never reached the transport logger, and no ChatGPT-side binding telemetry is locally available.

What is established is sufficient to classify the assistant's post-acceptance contract mutation as a real regression in its own right: it broke the frozen-contract invariant, invalidated prior acceptance, and created avoidable binding churn immediately before the first observed post-fix binding failure.
