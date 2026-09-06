# Major regression incident — MCP log retention semantics

**Observed:** 2026-09-06 ~02:02 EEST  
**Owner:** `chatgpt-mcp-clean` telemetry/log writer  
**Status:** Caught before commit/deploy; no serving logs deleted

## Symptom

While repairing the current MCP diagnostic-stall problem, the proposed off-path patch restored the historical `BoundedJsonlWriter` from PR #33. That implementation bounded the active JSONL by size/age but also enforced finite backup retention: default `maxAgeMs = 24h`, `maxBackups = 3`, and rotation removed the oldest backup. The user immediately rejected any behavior that deletes MCP logs after 24 hours or otherwise expires historical telemetry automatically.

This is a major regression because log-bounding was incorrectly conflated with log-retention deletion. Diagnostic performance may be bounded, but historical evidence must not be destroyed implicitly.

## Trigger and evidence

- Live `clone-a\transport.jsonl` had grown to about 244.7 MB; a naive whole-file text search ran for more than 24 seconds and was terminated.
- The dedicated bounded time-window analyzer remained responsive, so the large append-only file is a diagnostic-performance problem, not justification for deleting history.
- Git history showed PR #33 / merge `3a7316e2` introduced `BoundedJsonlWriter` with finite backup retention.
- Commit `9bdb6a4` later removed that writer and returned backend/front-door logging to append-only `createWriteStream`.
- The current serving candidate `d6e2972fd8da4247b164e2194366f84f2bdf8846` inherits append-only behavior. It is unbounded but does not automatically delete historical logs.
- During this turn, branch `chatgpt/26-restore-telemetry-bounds` restored the old writer and test off-path only. The change was not committed, pushed, or deployed. No serving generation or live log file was mutated by this patch.
- Issue `organicoverlords/chatgpt-mcp-clean#26` was reopened and annotated with the telemetry-bounding regression before this retention defect was caught.

## Causal finding

The failure was reuse of an old previously accepted mechanism without revalidating its retention semantics against the current preservation requirement. The implementation solved active-file size by deleting/evicting older segments. Those are separate concerns and must remain separate.

## Correct invariant

MCP transport/front-door telemetry may rotate active files for bounded read/write and diagnostic performance, but rotation must be **lossless**:

- every historical log segment is preserved indefinitely by default;
- no age-based deletion;
- no count-based backup eviction;
- no automatic `rm`, unlink, overwrite, or retention pruning of archived telemetry;
- cleanup/deletion requires explicit user authorization for the exact logs being removed;
- rotation should use immutable/collision-safe archive names and preserve all bytes across restarts.

## Required recurrence prevention

The owning repo should carry focused tests proving that many rotations and restart rotations preserve every historical record and never remove earlier segments. Tests should fail if telemetry rotation introduces finite retention, deletion, overwrite, or pruning. Active-log bounding and historical-log retention must be separate configuration/implementation concerns.

## Closure state

Source remediation completed. PR #126 merged as `10577bd8e292e8dc30ab29b96449fc780225a213` after the rebased full `npm test` contract passed. The corrected writer rotates active segments into unique archive files without deleting or overwriting historical telemetry, and the regression test proves earlier archives remain byte-identical across later rotations. The destructive retention semantics were caught before serving mutation, so there is no known data loss from this incident. Production remains unchanged; activating the source fix on the serving MCP is a separate production change and was not performed here.

## 2026-09-06 follow-up: supervisor test environment leak

Production-readiness verification found that `scripts/test-supervisor-continuity.mjs` launched its test keepalive supervisors with the caller environment unchanged. When the suite itself was launched through the production MCP backend, the test children therefore inherited production MCP state variables, including `MCP_TRANSPORT_LOG_PATH`.

At 2026-09-05T23:06:21Z the lossless writer under test renamed the live `clone-a/transport.jsonl` into a collision-safe file under `transport.jsonl.archive`. The serving backend PID 29480 retained the open file handle and continued appending to that archived file. A new canonical `transport.jsonl` was subsequently populated only by off-path test PIDs and then stopped changing, which made canonical-path telemetry consumers report stale/degraded MCP activity. No archived telemetry bytes were deleted.

Owner repair: PR #127 (`b0447185a8f82f61b7d84a1964ea385cd1bee7f6`) isolates supervisor-continuity children onto temporary transport, front-door request, OAuth, receipt, backend-config, and route paths. Its proof asserts both old and replacement test backend PIDs write to the isolated transport log and that inherited production-like sentinel paths are untouched. The guarded full `npm test` suite passed while the canonical live `clone-a/transport.jsonl` remained exactly unchanged in size and mtime.

Remaining production boundary: the current serving backend remains healthy and continues writing to the preserved archived segment. Restoring canonical-path live telemetry and/or activating the merged lossless writer in production requires a separately authorized serving/control-plane mutation; it was not performed during this follow-up.
