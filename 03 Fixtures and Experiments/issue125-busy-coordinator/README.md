# #125 standalone BUSY coordinator

Purpose: move BUSY/job coordination out of the MCP tool schema without changing the user's workflow or creating a second authority.

Two interchangeable implementations are kept deliberately feature-equivalent:

- `python/busy.py`
- `rust/` (`busy-coordinator.exe` after build)

Both operate on the same canonical `%LOCALAPPDATA%\ChatGPTMcpClean\.state\busy-claims.json` plus its existing atomic `.lock`. They preserve unknown top-level metadata so current MCP0 and either standalone implementation can coexist during rollout.

Supported coordinator operations are `list`, `sweep`, `snapshot`, `enqueue`, `ready`, `next`, `claim`, `heartbeat`, `release`, `block`, `complete`, and `inspect`. Job identity is the canonical trimmed scope string. Optional operation IDs make retries idempotent across connector/runtime changes. Leases are renewable; expired coordinator-owned work returns to `ready`; a newer legacy/MCP claim timestamp disables automatic expiry rather than deleting newer ownership. Block/complete persist a checkpoint and release ownership automatically.

`snapshot` is a bounded read projection of live coordinator state: job-state counts, legacy-only claims, ready/blocked work, optional actor ownership, and optional exact-scope focus. Its result limit is clamped to 1-32 entries and is feature-equivalent across Python and Rust.

The tool apps are separate from MCP. They are intended to be invoked through an existing process tool or directly from the local machine; neither implementation is registered as a GPT/MCP tool. The MCP connectors remain interchangeable transport entrances, not ownership systems.

`install.ps1` installs stable local copies under `%LOCALAPPDATA%\BusyCoordinator` by default without changing the canonical store; generated wrappers resolve their installed Python/Rust payload relative to the wrapper location so alternate destinations remain self-contained.
The installer also overwrites the historical `%LOCALAPPDATA%\BusyCoordinator\busy.py` entrypoint with the current Python implementation so older callers cannot retain a destructive claims-only writer.

Verification:

```powershell
cargo build --release --manifest-path .\rust\Cargo.toml
cargo test --manifest-path .\rust\Cargo.toml
python .\tests\coordinator_parity.py
python .\tests\install_compatibility.py
python .\tests\mixed_contention.py
```

`coordinator_parity.py` proves cross-language idempotency, lifecycle continuation, exact ownership, lease expiry, legacy-refresh safety, metadata passthrough, snapshot parity, and blocked/next-work handoff. `install_compatibility.py` proves installation preserves coordinator state and Python/Rust snapshot parity. `mixed_contention.py` races Python and Rust writers against the same lock/store.

Do not add a dashboard, dispatcher UI, scoring system, workflow language, connector-specific ownership state, or another database. Normal user interaction remains an issue request, `go`, or `continue`.


## Scout finding fan-in

`handoff <actor> <parent-scope> --finding-id <id> --source <provenance> --summary <text>` creates a separate ready follow-up job at `<parent-scope>::handoff:<id>`. The job stores structured `handoff` provenance (`parent_scope`, `finding_id`, `reported_by`, `source`, `summary`, `reported_at`) and is selected by the existing `next` command. It does not require or create ownership of the parent scope, so a scout blocked by a real live owner can durably fan work in without weakening BUSY authority. Parent release, block, or completion does not remove the follow-up job. Handoff provenance is bounded at 2,048 characters for `source` and 4,096 characters for `summary` so a single finding cannot grow the canonical coordinator store without limit and the documented maxima remain callable through the canonical Windows `.cmd` wrappers.
