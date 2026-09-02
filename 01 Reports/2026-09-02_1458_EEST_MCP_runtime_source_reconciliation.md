# MCP runtime/source reconciliation — 2026-09-02 14:58 EEST

## Outcome

The MCP/plugin2 runtime was reconciled back to the current `organicoverlords/chatgpt-mcp-clean` `master` instead of preserving a divergent deployed lineage.

Canonical merged repair: PR #29, merge commit `d8deeca5d260d3c717a2f6c96b27465d4199d7fa`. The deployed source tree was verified identical to merged `origin/master` after the merge.

## Durable process contract

1. `read_output` maximum remains **32,000 characters**. The earlier 6,000-character cap was stale regression state, not a newly proven safety requirement. Validation delivered a 24,026-character result whole and truncated oversized output at 32,000.
2. `start_process` performs an automatic bounded wait of **750 ms by default**. Fast commands may complete and return output inline; longer commands return `RUNNING` with the same stable process ID.
3. The per-caller live-process ceiling is **5**. Five simultaneous processes are admitted; the sixth is rejected.
4. The rolling launch/token bucket is **removed**. There is no per-caller launch-refill throttle in the reconciled source.
5. Front-door clone routing preserves ordered array fallback, process-generation pinning, and backend connection reuse.
6. Replacement clone generations must explicitly reuse the stable public clone OAuth store and shared process receipts.

## Live clone-a checkpoint

After authenticated live smoke and semantic canaries, clone-a was reduced to two reconciled backends only:

- primary: `55575`, generation `clone-a-reconcile-48714af`
- fallback: `55577`, generation `clone-a-reconcile-48714af-b`

Obsolete temporary canaries `55574` and `55573` were stopped. Older 6 KB / 3-process / token-bucket generations were removed from the clone-a fallback route so a primary failure cannot silently restore the regression.

The exact ports and PIDs remain volatile live state; verify them from `.state/front-door/static-routes.json` and `/health` before operational use. The invariants above are the durable contract.

## Validation evidence

- TypeScript build: PASS.
- Read-window regression: PASS (`whole=24026`, `truncated=32000`).
- Process guard: PASS for duplicate reuse, five-live concurrency, restart receipts, cross-clone live control, nonblocking zero-wait, and bounded wait.
- Front-door continuity: PASS, including static auth fallback, static transport fallback, in-flight draining, process pinning, and unavailable-route preservation.
- Off-path backend replacement: PASS.
- Supervisor continuity: PASS.
- OAuth retention: PASS.
- BusyCoordinator concurrency tests: PASS.
- Minimal clone cross-client/cross-clone tests: PASS.
- Authenticated public MCP smoke through clone-a: PASS after the reconciled candidate became primary.

## Root cause / prevention

The failure was not that 32 KB suddenly became unsafe. `master` and the deployed branch had diverged; the deployed lineage reintroduced an older 6 KB transport assumption and also retained the 3-process ceiling plus rolling token bucket. Future MCP repair must start from current `origin/master`, compare the live deployment tree against it, and reconcile missing runtime behavior onto current master rather than promoting an old deployed branch wholesale.

Do not infer the live contract from a cached ChatGPT tool schema alone. Validate the actual public connector with authenticated `tools/list` / smoke and semantic process calls when schema freshness matters.
