# Issue #174: BUSY process-profile route boundary

Date: 2026-08-27 EEST

## Observed live sequence

During a `regression-research` work turn, the visible connector profile exposed process execution operations but no dedicated BUSY tool name. The assistant initially promoted that visible-surface absence into a capability conclusion and said the coordination route was unavailable.

The user corrected the interpretation directly: `busy is baked in the app you use`.

The same turn then established the actual route with live execution evidence:

- The connector documentation states that the process-only profile intentionally leaves BUSY/job coordination in the standalone BusyCoordinator rather than duplicating BUSY into that tool schema.
- `%LOCALAPPDATA%\BusyCoordinator` was present and invocable through the already-visible process execution adapter.
- Running the standalone coordinator's `list` command through that process route returned the canonical live BUSY claims, including `regression-research#194-busy-lifecycle-admission-aging` owned by `ChatGPT-194-lifecycle-audit-20260827`; that scope was yielded.
- A later `claim` for `regression-research#174-tool-use-mistakes-tranche3` returned `ok:true` and a matching `release` returned `ok:true`.
- After narrowing the work, a claim for `regression-research#174-busy-app-route-regression` also returned `ok:true`.

The entrance changed; the authority did not. The standalone coordinator operates on the same canonical live ownership state. The process adapter is a route to that capability, not a second BUSY authority.

## Failure classification

This is a concrete tool-routing error under issue #174. The immediate mechanism is `CAPABILITY_STATE_NOT_CHECKED`: absence of a dedicated visible tool was treated as absence of the capability before testing a supported indirect route. It is also consistent with the previously observed `WRONG_ROUTE_AFTER_CAPABILITY_LOSS` family.

This evidence does not claim that every process-only surface always has coordination available. Availability must be established from current reachable adapters. If the provider route itself fails, coordination may correctly degrade while read-only/independent work continues.

## Regression contract

1. Visible tool names are not the capability boundary.
2. A currently reachable adapter may provide another capability role indirectly.
3. Indirect reachability counts only while the provider route itself is reachable.
4. Coordination still resolves to exactly one `live_ownership` authority; indirect transport must not create a second authority.
5. A capability may be downgraded only after its currently supported direct and indirect reachable routes have failed or are absent.
