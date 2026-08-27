# Issue #125 standalone BUSY coordinator trial — 2026-08-27

## Purpose

Test whether BUSY ownership can move out of the GPT/MCP tool schema and be reached through the existing `start_process` capability, without adding any GPT-facing tool or changing the user's ordinary workflow.

This is a bounded implementation experiment, not a new control plane.

## Implementations

Two independent standalone clients were built against the same existing BUSY JSON/lock protocol:

- Python: `03 Fixtures and Experiments/issue125-busy-coordinator/python/busy.py`
- Rust: `03 Fixtures and Experiments/issue125-busy-coordinator/rust/`

Installed trial copies were exercised from `%LOCALAPPDATA%/BusyCoordinator`. The Rust release executable measured 338,944 bytes.

Both implementations expose only `list`, `claim`, and `release` in this parity stage. Neither is registered as an MCP or GPT tool.

## Live cross-visibility

Observed against the canonical live store `%LOCALAPPDATA%/ChatGPTMcpClean/.state/busy-claims.json`:

1. Python claimed `regression-research#125-python-live-parity`; the existing MCP `busy_list` immediately returned the same actor/scope/timestamp; MCP then released it successfully.
2. MCP claimed `regression-research#125-python-reverse-parity`; Python `list` returned it and Python released it successfully.
3. Rust claimed `regression-research#125-rust-live-parity`; MCP `busy_list` immediately returned it and MCP released it successfully.
4. MCP claimed `regression-research#125-rust-reverse-parity`; Rust `list` returned it and Rust released it successfully.

Result: **the ownership state is already transport-independent.** MCP is one client of the file/lock authority, not a requirement for the authority itself.

## Mixed-writer contention

`tests/mixed_contention.py` ran 20 rounds with 10 simultaneous contenders per round, alternating Python and Rust writers against one isolated scope/store.

- attempts: 200
- expected winners: 20
- observed rounds with anything other than exactly one winner: 0
- result: `PASS`

The two implementations therefore interoperate on the same O_EXCL-style lock protocol without lost-update or double-winner behavior in this bounded test.

The same 200-attempt proof seeds versioned coordinator/job checkpoint metadata before every contention round and verifies it survives every mixed Python/Rust write. `chatgpt-mcp-clean` PR #17 independently makes current MCP BUSY mutations preserve the same unknown top-level metadata.

## Startup comparison

50 isolated `list` invocations per implementation on the same machine:

| implementation | median | mean | p95 |
|---|---:|---:|---:|
| Python | 51.38 ms | 52.71 ms | 56.76 ms |
| Rust release | 7.51 ms | 8.65 ms | 9.15 ms |

This difference is small relative to a normal MCP `start_process` round trip, so startup speed alone should not decide the design. Rust gives a small self-contained executable; Python is easier to modify. Keep both during the experiment until automation behavior is exercised.

## MCP-specific coupling discovered

Current MCP BUSY code has special `session:` / `process:` scope pruning and front-door generation routing. Repository search shows these semantics are MCP process/session plumbing and test coverage, not the normal durable job-ownership scopes used by current work.

Do not automatically transplant that coupling into the standalone job coordinator. If MCP BUSY tools are removed, process/session routing should remain owned by the process transport layer rather than by job ownership.

## Next bounded step

After this parity proof, remove only `busy_list`, `busy_claim`, and `busy_release` from the GPT/MCP schema and invoke the standalone coordinator through `start_process`. Then measure discovery/callability behavior before extracting any other tool.

The automation target remains the small #125 lifecycle already recorded on the issue: exact admission dedupe, renewable ownership, blocked checkpoint/release, recoverable stale/completion cleanup, and immediate bounded redirection to existing actionable work. No dashboard, semantic scoring, new job database, or user-facing procedure.
