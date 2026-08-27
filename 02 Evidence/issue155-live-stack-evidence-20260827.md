# Issue #155 ? live worker / MCP / control-plane evidence

Observed: 2026-08-27 EEST. This is a bounded source inventory for the architecture-map owner. It does not redesign the stack and does not mutate memory or Personal Instructions.

## Current-state findings

| Connection / component | Status | Current evidence |
|---|---|---|
| WebGPT conversation -> MCP0 connector binding | PROVEN | This exact conversation successfully invoked `busy_list`, `busy_claim`, `start_process`, and `read_output`; MCP transport telemetry records successful requests from the current pseudonymous caller. |
| WebGPT MCP0 binding -> MCP0 backend health | PROVEN | Local health probes returned HTTP 200 from stable front door `127.0.0.1:3003` and both loopback backends `3001` and `3002`. |
| MCP0 worker contract | PROVEN | `ChatGPTMcpClean/AGENTS.md`, `README.md`, server source, and live tool surface agree on exactly seven tools: `view_image`, `start_process`, `read_output`, `kill_process`, `busy_list`, `busy_claim`, `busy_release`. |
| MCP0 deployment shape | PROVEN | Stable front door on 3003 routes to replaceable/draining blue-green loopback backends on 3001/3002; process IDs are generation-pinned and BUSY state survives backend replacement. |
| Account connector configuration -> this conversation binding | UNKNOWN | Backend health and live callability are proven, but this lane has no direct account-settings source. Account configuration, conversation injection/binding, callability, and backend health must remain separate boxes. |
| Codex CLI -> MCP0 | PROVEN absent from current CLI MCP list | `codex mcp list` shows `node_repl`, `p3_local_coder`, and two Unreal MCP entries; it does not list MCP0. This says nothing about any other Codex product surface. |
| Other local execution clients | PROVEN installed; MCP bindings UNKNOWN here | `codex`, `claude`, `opencode`, and `command-code` resolve to installed local CLI launchers. This lane did not infer their MCP bindings from installation alone. |
| Shared policy inheritance | PROVEN | Regression Research, P3, Tiny3D, and LowVRAM expose generated shared-policy v1.18 dated 2026-08-27, sourced from `%USERPROFILE%\.agents\SHARED-AGENT-POLICY.md` via `sync-agent-policy.mjs`. |
| Shared-mutation ownership | PROVEN | Current v1.18 says MCP0 BUSY is the live ownership authority; GitHub BUSY titles are human-visible projections only and issues/PRs/branches/processes cannot substitute for the claim. |
| Repo/runtime activity truth | PROVEN | Current v1.18 treats issues, PRs, branches, processes and live runtime evidence as task/activity truth while keeping ownership separate in MCP BUSY. |
| Current timed WebGPT worker topology | PROVEN: one active worker | Live ChatGPT scheduler currently has one enabled hourly worker, `P3 Asset Sprint 3`, scheduled at minute 36 in `Europe/Helsinki`. Its scope is bounded P3 asset placement using existing P3/Tiny3D assets with live-state inspection and runtime/strongest proof. The issue's assumption of five currently live workers is therefore stale and must not be drawn as current fact. |
| Five-worker WebGPT topology | UNKNOWN / historical, not current | No current-state claim of five active workers is supported by the live scheduler snapshot. If the final map shows five, it must label that as intended/historical and cite a different activation source. |

## Current authority boundaries

- **PROVEN ? user authority:** current repo policy reserves destructive actions, spending, public publication, and genuine external authority for the user. Ordinary internal sequencing, branch/PR work, retries, verification, and worker supervision are not user-owned decisions.
- **INTENDED ? WebGPT continuity/orchestration:** issue #155 defines WebGPT as the continuity/orchestration surface because it has conversation history, memories, Personal Instructions, and timed workers. This lane does not re-prove the hidden context stores and does not expose their contents.
- **PROVEN ? repo operating authority:** each repo's current `AGENTS.md` governs work after current user instruction and live repo/runtime evidence; its shared block comes from `.agents/SHARED-AGENT-POLICY.md`.
- **PROVEN ? ownership authority:** MCP0 BUSY claim state alone decides shared-mutation ownership under v1.18. GitHub is evidence/publication, not a second lock.
- **PROVEN ? product/runtime acceptance:** player-visible claims require normal-runtime rendered proof; logs/build success alone are supporting evidence.

## Normal path evidenced in this session

`short user request -> WebGPT -> live MCP0 binding -> busy_list/claim -> local shell + gh + repo AGENTS.md -> isolated branch/worktree -> tests/proof -> PR/merge -> BUSY release -> concise WebGPT report`

For this exact conversation the path through live MCP0 binding, BUSY, local shell, GitHub CLI, and repo authority is PROVEN. Treating it as universal across every WebGPT conversation would be an overclaim because connector injection is conversation-scoped.

## Degraded-path constraints

- **PROVEN policy:** backend healthy + no conversation binding is a connector-binding failure, not an MCP server failure. Do not restart the backend merely because one conversation cannot call the tool.
- **PROVEN policy:** if live BUSY ownership cannot be checked/claimed, read-only and genuinely isolated work can continue, but shared mutation/merge must not invent GitHub or branch state as replacement ownership authority.
- **PROVEN MCP contract:** a transport drop does not end a task; preserve `process_id` and BUSY claim, reconnect, then perform one bounded `busy_list` / `read_output` check and resume the interrupted step.
- **UNKNOWN:** which exact client-side condition causes WebGPT conversation binding to appear/disappear. Keep account configuration, conversation injection, callability and backend health separate until a direct source proves the linkage.

## Source inventory

1. Live ChatGPT automation scheduler snapshot, 2026-08-27 EEST ? active automation names/schedule/current enabled state.
2. Current conversation MCP0 calls and `ChatGPTMcpClean/.state/transport.jsonl` ? successful current-caller request/response/process telemetry; no raw auth values used.
3. `%USERPROFILE%\AppData\Local\ChatGPTMcpClean\AGENTS.md`, `README.md`, `package.json`, `src/server.ts`; current HEAD `8a1ada9` ? seven-tool contract and front-door/backend architecture.
4. Local health probes for ports 3003/3001/3002 ? all HTTP 200 at observation time.
5. `codex mcp list` and `%USERPROFILE%\.codex\config.toml` ? current Codex CLI MCP configuration; no MCP0 entry observed.
6. `Get-Command` for `codex`, `claude`, `opencode`, `command-code` ? local CLI presence only.
7. Current `AGENTS.md` in Regression Research, P3, Tiny3D, and LowVRAM ? shared-policy v1.18 inheritance and BUSY/authority rules.
8. `%USERPROFILE%\.agents\SHARED-AGENT-POLICY.md` / `sync-agent-policy.mjs` ? canonical shared-policy source identified by generated headers.
9. Regression Research issues #155 and #125 ? requested architecture scope and current capability/BUSY distinction.

## Map-owner corrections to carry forward

1. Do not draw five timed WebGPT workers as currently active. The live scheduler proves one active worker at observation time.
2. Draw four separate MCP states: account configuration, conversation binding/injection, tool callability, backend health.
3. Draw WebGPT and Codex separately. Current WebGPT->MCP0 is proven; current local Codex CLI->MCP0 is not configured in `codex mcp list`.
4. Draw GitHub as task/publication/evidence transport, not ownership authority. MCP0 BUSY remains the sole live shared-mutation authority under current policy.
5. Keep the user above the stack for real decisions, not inside its maintenance loop.


## Executor activity snapshot - Aug 25 through 2026-08-27 10:57:52 EEST

These counts measure local execution activity, not quality. The snapshot is frozen at **2026-08-27 10:57:52 EEST**; Codex was still active, so its figures are not a stable Aug 25-27 total. The clients expose different event schemas and token/cache accounting, so token totals are not used as a cross-client score.

| Surface | Local log evidence | GitHub evidence in regression-research |
|---|---:|---|
| Codex | 27 session logs; 3,673 explicit tool calls; 318 task starts, 302 completes, 10 aborts | PRs #140/#145 merged; 2 commits, 9 changed files |
| Claude | 5 sessions with timestamped in-window events; 875 tool calls | PRs #22/#26 merged; 4 commits, 4 changed files |
| OpenCode | 5 sessions; 512 tool parts | PRs #35/#36 merged; 2 commits, 10 changed files |
| Command Code | 4 recent session logs; 33 tool calls | no Command-Code-prefixed branch/PR found in the current repo search |

Method: Codex JSONL uses explicit `custom_tool_call` events and last-per-session cumulative token counters; Claude JSONL was filtered by event timestamps; OpenCode was read from the local SQLite `session`/`part` tables; Command Code JSONL used `tool_use` entries. GitHub PR state, commit count and changed-file count were checked from the repository. Raw message/private conversation bodies were not copied into this evidence.

Interpretation: the three larger execution surfaces each landed two bounded PRs despite substantially different activity volume. Tool-call or token volume is therefore not a useful acceptance metric. Keep execution routing capability-based and evaluate accepted artifacts/evidence instead of adding a worker-scoring or telemetry-control layer.

## Anti-GigStack boundary evidence

Historical regression sources record project-local `WORKER REPORT`, `REVIEW CARD`, progress/status schemas, gates, receipts, and volatile MCP state leaking into global behavior. The resulting failure was extra ceremony and process invention, not a lack of control mechanisms.

For #155 this constrains the map: project-local protocols stay local; volatile schedule/route/tool state stays timestamped evidence; GitHub remains evidence/publication rather than a second BUSY authority; and the architecture map must not create a dashboard, daemon, memory schema, scoring system, or new lifecycle framework. Primary sources include `90 Raw Transcripts/share-6a86831f-6b54-83ed-8209-a1f4bf4e3caf.txt` and `02 Evidence/deleted_memory_recovery_2026-08-20.md`.
