# MCP worker liveness policy-blindness incident

**Observed:** 2026-09-05 23:09-23:12 EEST  
**Issue:** regression-research #569  
**Classification:** observability / policy-blindness gap; no serving-path failure established

## Symptom

During an auditability task, current worker activity was initially interpreted from archived worker-report freshness. That was wrong. The user correctly pointed out that workers were actively executing through MCP and that worker reports are not live evidence.

## Live evidence

`bootstrap-glance` at 2026-09-05T20:09:59Z reported four active MCP sessions and a five-minute MCP activity window containing 84 starts, 84 exits, 90 reads, and fresh events. Its worker-report section separately described archived run quality and explicitly stated that archived reports are not current worker-liveness or scheduler-membership evidence.

Direct production-clone telemetry from `minimal-connectors/clone-a/transport.jsonl` then showed current work, not historical reports:

- `caller_41ec8dbacb48`: 57 `process_started` and 57 `process_exit_observed` events in the observed five-minute slice; latest activity at 2026-09-05T20:11:24Z; current P3 workspaces included `C:\Users\Lauri\Documents\Unreal Projects\p3` and `...\Temp\p3-pine-1068-20260905-2257`; 360,926 HTTP response bytes observed in the slice.
- `caller_9b3546f32286`: 18 starts and 18 exits in the same slice; latest activity at 2026-09-05T20:11:19Z; P3 workspace; 188,501 HTTP response bytes observed.
- `caller_e60fe53012d5`: 6 starts and 6 exits in the slice, with Vault workspace activity at 2026-09-05T20:08:35Z.

These are live MCP execution events. They prove current execution activity for those caller identities at the sampled times. They do **not** by themselves prove scheduler membership, worker display-name identity, semantic correctness of the work, or task completion.

## Blindness gap

The operational view exposes two correct but disconnected evidence classes:

1. MCP active-session / transport / process telemetry: suitable for current activity and execution liveness.
2. Archived worker reports: suitable for historical run quality, findings, duration, and archival compliance.

The gap was interpretive and structural: stale archival-report notices were prominent, while the live MCP activity was not joined to an auditor-friendly worker/execution/output view. This made it easy to answer a current-liveness question from the wrong evidence class even though live evidence was already available.

## Required boundary

- Never use worker-report freshness, archive age, schedule claims, or enabled state as proof that a worker is currently active or inactive.
- Current activity must come from live MCP/session/process/runtime evidence.
- Scheduler membership must come from current scheduler authority.
- Worker reports remain evidence of completed/archived run quality and findings only.
- Where caller identity cannot be proven to a named scheduler worker, report the MCP caller/session/process identity without inventing the name mapping.

## Auditability follow-up

The existing MCP owner already records `request_id`, `caller_id`, `process_id`, response bytes, process exit state, timing, stdout/stderr, and truncation state across transport telemetry and durable process receipts. The next change should make that join explicit for auditors and expose output amount plus evidence-completeness/integrity fields without claiming subjective work quality from transport data.

Target evidence semantics:

`request_id -> caller_id -> process_id -> execution timing/outcome -> stdout/stderr amount -> truncation/completeness -> durable receipt`

Semantic work quality must remain a separate, higher-level assessment tied to task-specific proof; transport/output volume alone is not quality.

## Recurrence prevention

Update the smallest live owner so audit consumers can retrieve or derive the execution/output join directly, and ensure operational summaries keep live MCP activity visibly separate from archived worker-report status. Do not introduce a parallel liveness registry or use reports as a substitute for runtime evidence.
