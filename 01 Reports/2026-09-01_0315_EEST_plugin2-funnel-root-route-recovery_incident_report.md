# Plugin2 Funnel root-route recovery incident

## Incident identity

- Date/time: 2026-09-01, approximately 03:15 EEST (local recording time).
- Conversation/project: local Tiny3D/P3 work; connector and MCP infrastructure only.
- Affected surface: `plugin2` public MCP ingress and the ChatGPTMcpClean stable front door.
- Repository inspected: `C:\Users\Lauri\AppData\Local\ChatGPTMcpClean`.
- Relevant live front door: `127.0.0.1:3003`, PID 30508, receiptfix worktree at `e918c08`.
- Completeness limitation: the two final plugin2 command receipts requested by the original acceptance criteria were not independently observed in this documentation turn. The final plugin2 recovery is recorded as the user's exact report, not as an assistant-generated execution proof.

## Requested outcome and active constraints

The user requested diagnosis and a narrowly scoped repair of the plugin2 connector failure, with no blind OAuth retries, credential rotation, unrelated reinstall, project-code workaround, scheduler/worker mutation, or Tiny3D/P3 changes. The user required separation of connector failure from local command failure, inspection of recent commits, preservation of routing semantics, and honest reporting of any missing end-to-end proof.

Relevant exact user messages:

> Cannot connect to host kone.tailbf0440.ts.net:443 ssl:default [None]

> also check last commits for changes that could cause this dont be blind

> its working now update docs and atlas and save info in vault how this happened

## Relevant verified state before recovery

- The stable front door was locally healthy and served the OAuth/OpenID metadata endpoints.
- The public Funnel status had a root handler pointing at the wrong local target while clone path handlers remained present.
- Root supervisor logs repeatedly reported that public health was failing while local health was healthy and that Funnel configuration was being left unchanged.
- The root worktree contained a four-line early-return guard in `EnsureFunnelConfiguration`. When `.state\\front-door\\static-routes.json` existed, it returned before reconciling the public root handler.
- The live front door process was not the root worktree's current commit; it was the clean receiptfix generation at `e918c08`. This constrained the repair to the live Funnel mapping and documentation, not an unsafe live-process restart.

## Failure boundary

The observed 503/OAuth failure happened before a local command reached the front door. The front-door request log had no corresponding `/mcp` arrival for that failed call, so the error was not a Tiny3D/P3 command failure and not evidence that the local executor was broken.

After the public route was repaired, a direct plugin2 tool attempt returned:

```text
tool call error: tool call failed for `codex_apps/plugin2.start_process`

Caused by:
    Mcp error: -32001: Unknown tool({"name":"plugin2.start_process"})
```

That attempt also did not appear in the front-door request log. It is preserved as a plugin2 binding/dispatch failure, not converted into a fabricated local receipt.

## First divergence

The earliest repository-side divergence was commit `39f205a`, `preserve root route during clone supervision`. Its static-route guard treated the presence of clone route configuration as a reason to skip all Funnel reconciliation. That preserved clone handlers but also prevented repair of a stale public root handler. The result was a locally healthy front door behind a publicly unhealthy or misdirected root route.

The first connector-side divergence remained separate: after transport recovery, the exposed plugin2 binding addressed `plugin2.start_process`, while the local MCP server registers the bare worker tool `start_process`. This is evidence of a plugin2 tool-binding/namespace mismatch or stale connector binding; the exact external plugin implementation was not available in the local MCP repository and is therefore not claimed as proven root cause.

## Available alternatives at divergence

- Inspect the stable front door, Funnel mapping, supervisor log, current live process, and recent commits.
- Re-point only the stale public root handler to `http://127.0.0.1:3003`, preserving `/clone-a` and `/clone-b`.
- Verify local health and then verify the external HTTPS path.
- Keep plugin2's pre-dispatch failure local and report its receipt gap.

Hard exclusions were blind OAuth retries, credential rotation, unrelated reinstall, project-code changes, scheduler/worker changes, and restarting user-owned or live infrastructure without proof that it was necessary.

## What actually happened

1. The current MCP repo instructions, Vault `NORTH_STAR.md`, Stack Atlas, live process/worktree state, Funnel status, supervisor log, and recent commit history were inspected before changing anything.
2. Commit history review found no recent TLS/OAuth transport change that explained the public connection failure. `268cb53` and `3b28997` changed the read window; `41c8345` changed backend keepalive; `ad45690` and related commits changed OAuth identity retention; `0591c2e` added static clone routing; `39f205a` introduced the root-reconciliation guard.
3. The four-line guard was removed from the effective root worktree, leaving `keepalive.ps1` byte-identical to its current `HEAD`; no new code commit was created for that removal because it was an uncommitted delta rather than a new committed change.
4. The live public root Funnel handler was directly re-pointed to `http://127.0.0.1:3003`. The existing `/clone-a` and `/clone-b` handlers were preserved.
5. Local `/health` returned the stable front-door response. The public HTTPS `/health` path returned HTTP 200 with the same stable front-door body when resolved against all three current public IPv4 addresses (`185.40.234.210`, `185.40.234.172`, and `185.40.234.37`).
6. The isolated OAuth retention test passed: `churn=96`, dormant registration persisted, orphan refresh recovered, stale ChatGPT authorize recovered, and secrets were not printed. This validates the local OAuth-store retention path; it does not prove a plugin2 connector call.
7. The user then reported, verbatim, `its working now`. That is the current plugin2 recovery signal. No independent plugin2 receipt is asserted in this report.

## Control failure

The repo-side control failure was over-broad route suppression: clone-route presence disabled root-route reconciliation. The connector-side symptom was a pre-dispatch plugin2 binding failure. The recovery correctly kept the route failure local and avoided treating it as a project or local-executor failure.

## Evidence-supported causal model

The strongest supported chain is:

`39f205a` early return on static-route presence -> supervisor skipped root Funnel reconciliation -> public HTTPS root no longer reached the stable front door -> plugin2 reported a 503/OAuth transport failure before `/mcp` arrival.

The root Funnel re-point restored the public transport path. The later `Unknown tool({"name":"plugin2.start_process"})` response shows an additional plugin2 binding problem that is distinct from the Funnel/TLS path. The user's later “working now” report indicates that the external connector state subsequently recovered, but the exact external transition is not observable in this local repository.

## Competing hypotheses and falsifiers

- Expired or invalid OAuth credentials: weakened by healthy metadata and the passing local OAuth-retention test; not fully falsified for the external plugin2 account.
- TLS certificate or Tailscale service failure: weakened by three direct public-IP HTTPS 200 responses after the root re-point.
- Recent application-level read-window, keepalive, or OAuth-retention commits: weakened by commit diffs showing no TLS ingress change and by the live front door using `e918c08`.
- Plugin2-specific stale tool namespace/binding: supported by the observed `Unknown tool` error and lack of `/mcp` arrival; exact external configuration remains unavailable.

## Correct counterfactual action

When local health is good but public health fails, reconcile the root Funnel handler independently of path-scoped clone routing, then prove the external HTTPS path. Treat any subsequent plugin2 pre-dispatch error as connector-local until a front-door arrival and a real receipt are observed.

## Regression fixture

Replay fixture: `03 Fixtures and Experiments/2026-09-01_plugin2-funnel-root-route-recovery.json`.

The fixture scores the next action after the user reports a public connector failure: inspect recent routing changes, preserve clone handlers, restore the stable root route, verify external reachability, and never claim a local execution receipt from a pre-dispatch connector error.

## User-visible impact

The user experienced a connector outage while working on local Tiny3D/P3 tasks and had to report the failure/recovery state across several turns. No Tiny3D/P3 repository, scheduler state, or user-owned Unreal state was changed. The incident reduced connector availability but did not invalidate the local project or executor.

## Resolution and next-action state

- Resolved: public root Funnel mapping was restored to the stable front door; clone path handlers were preserved.
- Verified: local health, public HTTPS health across three public IPv4s, metadata availability, and local OAuth retention.
- User-reported: plugin2 is working again.
- Not independently proven in this report: two fresh plugin2 command receipts after recovery; exact external plugin2 OAuth/binding transition.
- Documentation: MCP README/changelog and generated Stack Atlas were updated with the root-route invariant and external-path proof requirement.
- No restart, credential rotation, scheduler mutation, or Tiny3D/P3 change was performed.
