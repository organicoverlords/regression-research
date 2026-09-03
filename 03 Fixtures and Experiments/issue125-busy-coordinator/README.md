# #125 standalone BUSY coordinator

Purpose: keep exact shared-mutation ownership outside the MCP tool schema without creating a second authority or turning coordination into a work queue.

Two interchangeable core implementations are deliberately retained for redundancy and parity:

- `python/busy.py`
- `rust/` (`busy-coordinator.exe` after build)

Both operate on the same canonical `%LOCALAPPDATA%\ChatGPTMcpClean\.state\busy-claims.json` plus its atomic `.lock`. Python and Rust must remain feature-equivalent. The coordinator owns collision/ownership only; GitHub issues/PRs own delivery work and operator boards remain projections.

Core operations are `list`, `sweep`, `snapshot`, `recover`, `claim`, `heartbeat`, `release`, and `inspect`. The former queue/workflow operations `enqueue`, `ready`, `next`, `handoff`, `block`, and `complete` are intentionally retired from the command contract because they created backlog/scheduling semantics with no current operational consumers.

The existing `coordinator.jobs` store key is retained for migration compatibility, but it now contains only exact-scope ownership/checkpoint metadata:

- `active` metadata accompanies a live managed claim and may carry its renewable lease and checkpoint.
- `checkpoint` metadata is unowned context for the same exact scope. It is not ready work, priority, liveness, capacity, or admission.

Legacy `ready`/`blocked`/`completed` records are normalized on the next coordinator operation. Records with no live claim and no checkpoint disappear; records with a checkpoint are reduced to unowned `checkpoint` metadata; records with a live claim become `active` ownership metadata. This migration removes queue state without introducing another database.

New or renewed ownership (`claim`, `heartbeat`) requires an actor identity with an approved harness (`ChatGPT`, `Codex`, `Claude`, `OpenCode`, `CommandCode`, or `Traycer`) plus a task/session suffix. `release` and `recover` intentionally accept historical actor strings so old claims can still be relinquished or recovered safely.

`release` removes ownership. A caller may explicitly pass `--checkpoint <text>` to preserve exact-scope context after release; without an explicit release checkpoint the managed metadata is removed. `recover <expected-owner> <scope> --expected-claim-timestamp <timestamp>` is compare-and-swap guarded and removes only the exact observed claim. If that scope carried a checkpoint, recovery preserves it as unowned checkpoint metadata rather than manufacturing a ready job.

`snapshot` is a bounded ownership projection: claim count, managed active ownership, legacy-only claims, unowned checkpoints, optional actor ownership, and optional exact-scope focus. It contains no queue depth, blocked count, completed count, or next-work selection.

The tool apps are separate from MCP and can be invoked through any supported process route. MCP/plugin routes are transports, not ownership systems.

`coordinator-contract.json` is the machine-readable compatibility contract. Installed Python and Rust wrappers share one append-only observability sidecar and expose the same additional `contract`, `log`, and `audit` commands without adding authority to the canonical ownership store. Audit failure is non-authoritative.

`install.ps1` installs stable local copies under `%LOCALAPPDATA%\BusyCoordinator` by default, preserving both Python and Rust implementations and the canonical store. The installer also refreshes the historical `%LOCALAPPDATA%\BusyCoordinator\busy.py` compatibility entrypoint with the current Python core.

Verification:

```powershell
cargo fmt --manifest-path .\rust\Cargo.toml
cargo test --manifest-path .\rust\Cargo.toml
python .\tests\contract_guard.py
python .\tests\coordinator_parity.py
python .\tests\install_compatibility.py
python .\tests\mixed_contention.py
```

Do not add a dashboard, dispatcher UI, scoring system, workflow language, queue, priority system, connector-specific ownership state, or another database. Normal user interaction remains an issue request, `go`, or `continue`.
