# Vault audit addendum for regression-research #569

**Observed:** 2026-09-05 23:13-23:26 EEST  
**Scope:** current dirty Vault changes plus live MCP activity relevant to worker-liveness auditability  
**Preservation:** existing foreign/uncommitted implementation and the original incident report were not edited

## Live MCP baseline

`bootstrap-glance` at 2026-09-05T20:13:26Z reported five caller identities with recent MCP process activity in its 300-second activity window. Detail output was intentionally capped at four callers. The same snapshot reported workspace counts of two `ChatGPTMcpMinimal`, one `P3`, and two `Vault`, with 114 process starts, 114 exits, 116 reads, five nonzero exits, and zero kills in the sampled five-minute window.

This is valid recent runtime activity evidence, but it is not scheduler-membership evidence and it is not identical to "process currently running" evidence. In the current implementation, `active_session_count` is derived from callers with at least one process start/read whose last activity is <=300 seconds old.

## Findings

### 1. Auditor-output join is implemented in the MCP owner, but is not live on the serving frozen generation yet

While this audit was in progress, another auditor merged `organicoverlords/chatgpt-mcp-clean` PR #115 at 2026-09-05T20:18:45Z (`cff7a7cfc7bec8cdddacf3b71b34b670ad0e3b5d`; feature commit `2717f74`). That owner change adds `request_id`, retained stdout/stderr character and UTF-8 byte counts, SHA-256 hashes, `evidence_completeness`, and `execution_outcome` to completed process responses and durable receipts. This satisfies the code-level auditor join requested by #569 without requiring `stack_atlas.py` to become a second telemetry owner.

However, the serving production clone observed after that merge is still the frozen older backend generation. At 2026-09-05T20:19:48.627Z, live server PID `28128` emitted a `process_receipt_persisted` row containing only the pre-change request/caller/process identifiers, with none of the new retained-output/hash/completeness/outcome fields. `bootstrap-glance` also still identifies the serving frozen backend commit as `d6e2972fd8da4247b164e2194366f84f2bdf8846`, not the merged owner change.

**Impact:** the owner fix is merged, so this is no longer a code-acceptance blocker. It is a live-deployment/proof gap only. Production must not be moved off the current frozen serving path without the separate explicit authorization required for a live shared-production change. Until then, auditors can still derive the join from raw transport plus durable receipts, but the new compact evidence fields are not yet proven on the serving generation.

### 2. Live workspace attribution can be stale after a caller revisits an earlier CWD

`_bootstrap_mcp_status()` appends a CWD only when that value has not appeared previously for the caller, then later treats `cwds[-1]` as the caller's latest/current CWD. If a caller moves `A -> B -> A`, the retained list remains `[A, B]`, so the summary reports `B` even though the latest process started in `A`.

A bounded live 300-second production-clone slice reproduced this on three callers during the audit. For example, `caller_464554ce7f9c` had its latest `process_started` CWD at `C:\Users\Lauri\Desktop\vault` at 2026-09-05T20:17:39.086Z, while the current unique-list algorithm would select `C:\Users\Lauri\AppData\Local\ChatGPTMcpClean`.

**Impact:** `workspace_counts` and sampled session `workspace` can misattribute current/recent work, which directly weakens the liveness/auditability view this issue is trying to improve.

### 3. Manual-history dedupe has a reproducible Windows crash path

`tools/worker_report_history.py::_dedupe_manual_run_records()` uses `datetime.min.astimezone()` as the fallback sort timestamp when `archived_at` is absent or invalid. On this Windows host, `datetime.min.astimezone()` raises `OSError: [Errno 22] Invalid argument`.

Reproduction against the current dirty implementation:

`_dedupe_manual_run_records([{'run_id':'x','archived_at':None},{'run_id':'x','archived_at':'2026-09-05T20:00:00+00:00'}])`

raises from the fallback expression. This path is reachable through `worker_history_events()` because `_history_chronology_is_plausible()` currently treats missing `finished_at`/`archived_at` as plausible rather than rejecting the record before manual dedupe.

**Impact:** malformed/legacy duplicate manual-history metadata can crash event projection on Windows. Existing tests did not cover the missing-`archived_at` duplicate case.

## Follow-up live evidence (23:24-23:26 EEST)

### Recent-active callers are not equivalent to currently running child processes

A refreshed `bootstrap-glance` at 2026-09-05T20:24:15Z reported **8 recently active caller identities** in the 300-second activity window, with **171 starts, 169 exits, 182 reads, 16 nonzero exits, and zero kills**. Forty seconds later, a bounded transport/process correlation saw 173 distinct `process_started` IDs in the same moving five-minute window, 169 of which already had an observed exit/kill. The remaining four PIDs were still alive in the Windows process table; one of those four was the audit probe itself, leaving **three other caller-owned MCP child processes demonstrably alive at that instant**.

This proves the distinction numerically: an `active_session_count` of 8 did not mean eight processes were currently executing. It meant eight caller identities had qualifying start/read activity within the previous five minutes. Conversely, a process older than the sampled transport window could in principle still be alive without contributing a matching `process_started` row in that bounded slice, so the correlated alive count is a bounded observation rather than a global process census.

The live child processes seen in that sample were parented directly by serving node PID `28128`, including P3 work, Vault work, and this audit probe. That provides stronger current-execution evidence than report freshness or the five-minute caller heuristic.

### Workspace-attribution error is materially affecting the current view

A second bounded projection at 2026-09-05T20:25:25Z found **9 recently active callers**, of which **4 had a different latest `process_started` CWD than the CWD selected by the current unique-list algorithm**. The four live mismatches were:

- `caller_41ec8dbacb48`: algorithm `Vault`; latest process-start workspace `P3`.
- `caller_464554ce7f9c`: algorithm `source-compile-b`; latest process-start workspace `Vault`.
- `caller_9b3546f32286`: algorithm `P3`; latest process-start workspace `Vault`.
- `caller_5f176c45677d`: algorithm `P3`; latest process-start workspace `Tiny3D`.

Using the current algorithm, those 9 callers projected as `Vault=3`, `P3=3`, `ChatGPTMcpMinimal=2`, `source-compile-b=1`. Using each caller's actual latest `process_started` CWD instead, the same caller set projected as `Vault=4`, `P3=2`, `ChatGPTMcpMinimal=2`, `Tiny3D=1`. The bug therefore changes not only individual labels but aggregate workspace counts.

### Serving-generation identity is independently confirmed

The deployment gap for PR #115 is supported by current runtime evidence separate from the known-good freeze pointer:

- `http://127.0.0.1:3011/health` reported PID `28128`, generation `backend-3011-28128-1788590585408`, `active_requests: 0`, and `total_requests: 11911` at the sampled moment.
- Stack Atlas blast-radius resolved PID `28128` as the listener on `127.0.0.1:3011`, with parent `launch-production.ps1`.
- `launch-production.ps1` sets its runtime root to `C:\Users\Lauri\AppData\Local\ChatGPTMcpMinimal` and invokes that checkout's `start-minimal-clone.ps1` with `-SkipBuild`.
- The `ChatGPTMcpMinimal` checkout was clean at `d6e2972fd8da4247b164e2194366f84f2bdf8846`, matching the candidate freeze pointer.
- Neither `ChatGPTMcpMinimal/src/lib/process-manager.ts` nor `ChatGPTMcpMinimal/dist/lib/process-manager.js` contained `process-output-evidence.v1`; live receipt telemetry also lacked the new PR #115 evidence fields.
- PID `28128` started at **2026-09-05 09:43:04 EEST**, before PR #115 merged at 23:18:45 EEST.

This makes the state boundary explicit: PR #115 is merged in the owner repository, while the currently serving production checkout/build is still the earlier frozen generation. A merge is therefore not deployment evidence, and a source update alone would not prove the serving binary changed because the production launcher currently uses `-SkipBuild`.

### Manual-history Windows crash is latent in the current corpus

The `datetime.min.astimezone()` failure remains a valid code defect and direct reproduction still fails on this Windows host. However, a targeted scan of the current canonical manual-history metadata found **61 records, 61 distinct logical `run_id`s, zero duplicate run IDs, and zero records missing `archived_at`**. Therefore the current stored corpus does not presently contain the malformed duplicate shape required to trigger this crash through `worker_history_events()`.

This narrows the severity: it is a robustness/regression risk for malformed, migrated, or future duplicate metadata, not evidence that today's 61-record manual history is already unreadable.

## Validation

`python -m pytest tests/test_stack_atlas.py tests/test_worker_report_history.py -q` completed with **74 passed, 33 subtests passed**. The findings above are therefore coverage/semantic gaps rather than failures already caught by the current suite.

## Recommended next changes

1. Preserve PR #115 as the MCP telemetry owner implementation and obtain live proof only when/if the serving production generation is explicitly authorized to move; do not duplicate the projection into Vault as a second telemetry owner.
2. Track `latest_cwd` separately from the unique set/list of observed CWDs; derive workspace from `latest_cwd`.
3. Replace the Windows-invalid `datetime.min.astimezone()` fallback with an explicitly timezone-aware safe sentinel and add a duplicate manual-record test with missing `archived_at`.
4. Make the 300-second nature of `active_session_count` explicit in field naming or evidence semantics so recent activity is not mistaken for a currently running process.
