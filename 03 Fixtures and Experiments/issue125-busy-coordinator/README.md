# #125 standalone BUSY coordinator

Purpose: move BUSY/job coordination out of the MCP tool schema without changing the user's workflow or creating a second authority.

Two interchangeable implementations are kept deliberately feature-equivalent:

- `python/busy.py`
- `rust/` (`busy-coordinator.exe` after build)

Both operate on the same canonical `%LOCALAPPDATA%\ChatGPTMcpClean\.state\busy-claims.json` plus its existing atomic `.lock`. They preserve unknown top-level metadata so current MCP0 and either standalone implementation can coexist during rollout.

Supported coordinator operations are `list`, `sweep`, `enqueue`, `ready`, `next`, `claim`, `heartbeat`, `release`, `block`, `complete`, and `inspect`. Job identity is the canonical trimmed scope string. Optional operation IDs make retries idempotent across connector/runtime changes. Leases are renewable; expired coordinator-owned work returns to `ready`; a newer legacy/MCP claim timestamp disables automatic expiry rather than deleting newer ownership. Block/complete persist a checkpoint and release ownership automatically.

The tool apps are separate from MCP. They are intended to be invoked through an existing process tool or directly from the local machine; neither implementation is registered as a GPT/MCP tool. The MCP connectors remain interchangeable transport entrances, not ownership systems.

`install.ps1` installs stable local copies under `%LOCALAPPDATA%\BusyCoordinator` without changing the canonical store.
The installer also overwrites the historical `%LOCALAPPDATA%\BusyCoordinator\busy.py` entrypoint with the current Python implementation so older callers cannot retain a destructive claims-only writer.

Verification:

```powershell
cargo build --release --manifest-path .\rust\Cargo.toml
cargo test --manifest-path .\rust\Cargo.toml
python .\tests\coordinator_parity.py
python .\tests\mixed_contention.py
```

`coordinator_parity.py` proves cross-language idempotency, lifecycle continuation, exact ownership, lease expiry, legacy-refresh safety, metadata passthrough, and blocked/next-work handoff. `mixed_contention.py` races Python and Rust writers against the same lock/store.

Do not add a dashboard, dispatcher UI, scoring system, workflow language, connector-specific ownership state, or another database. Normal user interaction remains an issue request, `go`, or `continue`.


## Scout finding fan-in

`handoff <actor> <parent-scope> --finding-id <id> --source <provenance> --summary <text>` creates a separate ready follow-up job at `<parent-scope>::handoff:<id>`. The job stores structured `handoff` provenance (`parent_scope`, `finding_id`, `reported_by`, `source`, `summary`, `reported_at`) and is selected by the existing `next` command. It does not require or create ownership of the parent scope, so a scout blocked by a real live owner can durably fan work in without weakening BUSY authority. Parent release, block, or completion does not remove the follow-up job.
