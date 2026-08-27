# Issue #155 failure-boundary forensics - 2026-08-27

Purpose: preserve the smallest evidence-backed explanation of the #155 WebGPT/MCP/artifact failure without adding a control plane, policy rule, telemetry product, or worker-scoring mechanism.

Status vocabulary follows #155: **PROVEN**, **INTENDED**, **UNKNOWN**. A user-visible observation captured on the issue is identified separately from backend telemetry.

## Result in one paragraph

The #155 failure localizes above a healthy MCP0 backend. The architecture caller had successful MCP0 traffic before the failure interval, disappeared from backend transport for about 147 seconds, then resumed successful calls. During that exact gap eight other callers completed 118 responses, all HTTP 200, including 30 `/health` responses; no backend process/server fault event was recorded. The issue's contemporaneous WebGPT observation says MCP0 remained discoverable while calls returned `Resource not found` after a connector-surface switch. Because those failed calls do not appear as normal backend requests, the evidence supports a conversation/connector/call-path failure, not a backend outage. The exact platform layer producing `Resource not found` remains **UNKNOWN**.

## Timestamped sequence

Times below are UTC with EEST (+03:00) in parentheses.

| Time | Evidence | Classification |
|---|---|---|
| 07:28:16.904Z (10:28:16.904 EEST) | Live BUSY store records `ChatGPT-155-architecture` claiming `regression-research#155-stack-architecture-map`. MCP transport records a successful `busy_claim` response for the affected caller one millisecond later. | **PROVEN** correlation of the architecture scope to the affected MCP caller. |
| 07:39:31-07:40:16Z (10:39:31-10:40:16 EEST) | Affected caller continues successful `start_process`, `read_output`, and process telemetry. Its final pre-gap event is a successful `kill_process`/`process_kill_skipped` at 07:40:16.425Z. | **PROVEN** MCP0 callability before the gap. |
| 07:40:15.536Z (10:40:15.536 EEST) | A second exact-scope claim, `regression-research#155-stack-map`, is acquired by a different caller; transport records its successful `busy_claim` at 07:40:15.538Z. | **PROVEN** semantic duplicate scope strings existed concurrently. |
| 07:40:16.425Z-07:42:43.316Z (10:40:16-10:42:43 EEST) | No normal MCP backend response is recorded for the affected caller. In the same interval, eight other callers complete 118 responses, all status 200; 30 are `/health`; no `process_exit`, `process_signal`, `process_uncaught_exception`, or `http_server_error` server-fault event occurs. | **PROVEN** backend remained live for other callers; affected path is absent from backend transport. |
| same interval, exact client timestamp unavailable | #155 live-test review records that after a connector-surface switch MCP0 remained discoverable but WebGPT calls returned `Resource not found`. | **OBSERVED in WebGPT / issue record**; exact failing platform layer **UNKNOWN**. |
| 07:42:30Z (10:42:30 EEST) | PR #158 merges independent live control-plane evidence. | **PROVEN** separate worker/GitHub path was functioning during the affected caller's gap/recovery period. |
| 07:42:43.316Z (10:42:43.316 EEST) | Affected caller successfully starts a new MCP process; successful `read_output` follows at 07:42:49.411Z. | **PROVEN** callability recovered for the same backend caller identity. |
| 07:45:27-07:45:34Z (10:45:27-10:45:34 EEST) | Three recovered WebGPT architecture files are created in `%USERPROFILE%/Downloads`; SHA-256 values match the hashes recorded in #155. Each carries Windows `Zone.Identifier` provenance with `HostUrl=https://chatgpt.com/`. | **PROVEN** browser download/export boundary and exact downloaded bytes. |
| 07:55:48.116Z (10:55:48 EEST) | That later `stack-map` caller successfully releases its claim. | **PROVEN** for that known claim/caller pair. |
| 08:31:19Z (11:31:19 EEST) | PR #166 merges the three recovered files byte-for-byte under `02 Evidence/issue155-recovered-webgpt-artifacts/`. | **PROVEN** recovered artifact durability in GitHub; manual user transfer was still required for the original copies. |

## Backend/front-door boundary

### Backend transport

The affected caller is the caller whose successful `busy_claim` aligns with the live architecture claim timestamp. Its MCP responses are all status 200 in the inspected pre-gap and post-gap windows. During its 146.891-second transport absence, the backend continued serving other callers normally.

This is strong negative evidence against "MCP0 backend outage" as the explanation for the WebGPT `Resource not found` result.

### Front door

`ChatGPTMcpClean/.state/front-door/request.jsonl` records `ECONNRESET` client errors at:

- 07:36:57.076Z
- 07:37:40.645Z
- 07:37:47.100Z
- 07:44:18.351Z

Those front-door error records do not carry enough caller/request identity to tie them specifically to the affected #155 WebGPT call. They are therefore **UNKNOWN** with respect to causality and must not be promoted into the explanation.

## Artifact durability: what is and is not proven

The recovered files are exactly:

| File | Download creation time EEST | SHA-256 |
|---|---|---|
| `assistant-stack-source-inventory-20260827.md` | 10:45:27-10:45:28 | `B325F412748C80FB8D97674C103F7BC7135AA8A440E6DFAEC88111E3B9BC73B5` |
| `assistant-stack-companion-20260827.md` | 10:45:31 | `8DF12063346EC4E735FAA5A524A419739345E0D92AC659AA5E375769426C6DEF` |
| `assistant-stack-architecture-20260827.md` | 10:45:34 | `A0C7B83753CB98255BCD37559E45CC555B279DFADE2C8D0E403505A19C63088C` |

All three have Windows Internet-zone metadata whose redacted origin reduces to `https://chatgpt.com/`.

Therefore:

- **PROVEN:** WebGPT exposed a browser-download/export route that produced those exact local files.
- **PROVEN:** PR #166 later made the exact recovered bytes durable in the repository.
- **UNKNOWN:** the storage location, retention period, addressing scheme, and cross-worker accessibility of the pre-download ChatGPT-created artifact objects.
- **NOT PROVEN:** that another worker could have fetched those pre-download objects without the user's manual download.

The architecture should not gain an artifact service or checkpoint daemon from this evidence. The missing product capability, if any, is simply cross-worker durability/accessibility of an already-created artifact.

## Process recovery across callers

Current MCP0 source intentionally records the process owner caller separately from the reading caller and emits `reassociated: true` when they differ. Historical transport telemetry contains **14** `process_read` events with `reassociated: true`; several reads occurred while the process was still running. Examples include:

- 2026-08-24 23:11:27.703Z - owner and reader caller identities differ; process still running.
- 2026-08-25 06:45:43.155Z - cross-caller read while running.
- 2026-08-26 19:12:01.061Z and 19:12:36.249Z - another caller reads the same still-running process.

So the backend capability is **PROVEN**: a known `process_id` can be read from another caller identity. What remains **UNKNOWN** for the #155 failure is whether a WebGPT conversation whose MCP tool binding is unavailable can reach `read_output` at all. A backend capability cannot repair missing conversation injection by itself.

## BUSY history limitation

MCP0's durable BUSY file is a current-state store (`.state/busy-claims.json`), not an append-only history. Transport telemetry records `busy_list` / `busy_claim` / `busy_release` with timestamp, caller, tool name, request ID and status, but it does not persist the claim arguments or response body.

Consequences:

- The architecture claim is exactly correlatable because its live-store timestamp matches a `busy_claim` transport event at 07:28:16.905Z.
- The later `stack-map` claim is exactly correlatable from its known live-store timestamp and the 07:40:15.538Z transport event; its 07:55:48.116Z release is also recorded.
- A **complete historical ledger** of every #155 scope/actor acquisition/release cannot be reconstructed from current MCP0 state after claims have been removed unless another source captured the tool result at the time.

This is a telemetry limitation, not evidence that BUSY needs a second authority. The current single-authority model remains simpler than adding a parallel ownership database.

## P3 and LowVRAM authority wording

Current shared `AGENTS.md` text in both P3 and LowVRAM is explicit: MCP0 BUSY is the live shared-mutation ownership authority; GitHub BUSY markers are projections/evidence and do not establish ownership.

Two other documents use the word `authority`/`source of truth` in narrower domains:

- P3 `docs/v2/P3_V2_NORTH_STAR.md` says GitHub remains the P3 control plane/source of truth, while current P3 `AGENTS.md` separately describes GitHub issues as the durable backlog/orchestration surface.
- LowVRAM `docs/production-lanes.yaml` says its canonical external `production-lanes.yaml` is the live authority for the production queue and also states that the global contract is `AGENTS.md`.

The evidence supports a domain distinction rather than a new ownership system: GitHub can be the durable P3 backlog/product record, and the production-lanes file can be the canonical queue record, while MCP0 remains live shared-mutation ownership. P3's generic "control plane/source of truth" phrase is still semantically broad enough to be **ambiguous wording**, but it is not evidence of a second implemented BUSY mechanism.

## What remains genuinely unknown

1. Exact ChatGPT product component that returned `Resource not found` while MCP0 remained healthy elsewhere.
2. Exact pre-download storage/durability semantics of WebGPT-created artifacts.
3. Which write/export capabilities, beyond browser artifact download, were available to the affected WebGPT conversation during the no-backend-request interval.
4. A controlled WebGPT case where MCP0 is absent from initial conversation injection. Current local MCP telemetry cannot manufacture that product state.
5. Reliable scheduler-run-to-PR/commit attribution for the historical five worker records; scheduler metadata alone is not semantic work evidence.

These unknowns should stay evidence targets. None currently justifies a dashboard, dispatcher, worker score, new BUSY authority, global policy rule, memory schema, or artifact daemon.

## Sources

- `organicoverlords/regression-research#155`, especially live-test review comment `#issuecomment-5436059056`.
- PR #158 (`9215e1f`), #159 (`9427fa5`), #160 (`bd97ff6`), #161 (`a27eb38`), and #166 (`b23aa69`).
- `%USERPROFILE%/AppData/Local/ChatGPTMcpClean/.state/transport.jsonl`.
- `%USERPROFILE%/AppData/Local/ChatGPTMcpClean/.state/front-door/request.jsonl`.
- `%USERPROFILE%/AppData/Local/ChatGPTMcpClean/.state/busy-claims.json`.
- `%USERPROFILE%/AppData/Local/ChatGPTMcpClean/src/index.ts`, `src/lib/process-manager.ts`, and `src/lib/busy-store.ts`.
- The three `%USERPROFILE%/Downloads/assistant-stack-*-20260827.md` files and their Windows `Zone.Identifier` streams; no URL query/token data was recorded.
- Current P3 `AGENTS.md` and `docs/v2/P3_V2_NORTH_STAR.md`.
- Current LowVRAM `AGENTS.md` and `docs/production-lanes.yaml`.

No ChatGPT memory, Personal Instructions, MCP configuration, scheduler configuration, shared policy, P3 policy, or LowVRAM policy was changed by this investigation.