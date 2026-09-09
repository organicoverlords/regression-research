# Worker-report-filtered reroute analysis — 2026-09-08

Generated: 2026-09-08T00:27:41.448069+03:00

## Method correction

Ordinary silence is excluded only when there is a **successful matching worker-report archive** for that caller/run. A report file merely saying `COMPLETED` is not enough. The Owl run demonstrates this directly: its `state=COMPLETED` archive attempt at 21:00:36.855 EEST was rejected as not finalized; the same caller changed the report to `DONE`, and the 21:00:50.956 EEST archive returned `ok:true`. That successful archive is the real stop boundary.

Using successful archives, 261 finalized runs were mapped back to 86 exact MCP callers (179 manual, 82 timed). Finalization transitions were excluded from the inactivity cohort.

## Main result

Across 19,214 in-run MCP transitions from 250 mapped runs, the prior broad-cohort claim that long gaps are primarily an old/tool-heavy-chat phenomenon **does not survive the stop filter**. The probability of a >=30 s in-run gap actually declines across report progress quartiles: 4.48%, 4.47%, 3.68%, 3.50%. In 133 runs with both cases and healthy 1–10 s controls, the median case occurs slightly *earlier* than its run controls (position delta -0.0417; cumulative-call delta -2.5).

The robust remaining correlate is the **immediately preceding MCP response size**, especially after a completed process result. Across all in-run transitions, P(next gap >=30 s) rises monotonically from 1.11% below 1 KiB to 11.74% at >=32 KiB. For `read_output` with `running=false`, the corresponding rates rise from 2.89% at 1–4 KiB to 20.69% at >=32 KiB.

After matching 278 case/control pairs within the same run, same tool, same running state, and same response-size bin, most command-content associations vanish: worker-report activity 0.41x discordance, Busy activity 0.96x, command length >2 KiB 1.06x, build/test 1.16x, GitHub 1.29x. Log/introspection probes remain mildly elevated at 1.49x but are not a dominant discriminator.

## What this does *not* prove

Large output is not a safety-buffering trigger by itself. Confirmed visible safety-buffering banners occur while MCP is active and can begin during ordinary 10-second `read_output` waits that return only ~365 bytes. The Owl capture later entered a distinct 113.366-second zero-MCP/zero-child interval, but that interval is now classified only as **tool-plane silence**. Exact v0.153.1 source shows that a still-in-progress turn can have zero MCP calls and zero connector children while the client is awaiting the next remote Responses event, so MCP silence does not establish backend/model inactivity.

`connection_id` is also not a worker identity. Across the transport history, 3.5% of connection IDs carried requests from multiple callers, with as many as 32 callers on one connection. The Owl-era `connection_760c145f0d75`, `connection_b25ef58cfa34`, and `connection_172b9f54f833` carried 7, 9, and 8 callers respectively. Connection changes therefore cannot establish backend-worker replacement.

## Operational classifier

A **confirmed tool-plane-silent interval** requires only the local facts we can actually observe: no successful matching stop archive, zero fresh MCP calls for the affected caller, and zero live affected-caller connector child processes over the interval. Independent screenshot/banner evidence can label the UI state that overlaps it. **Do not call this a backend or machine-side stall from MCP evidence alone.** Exact v0.153.1 execution code can legally be blocked in `stream.next().await` on the remote Responses stream with no MCP activity or local connector child. A backend stall would require additional inference/Responses-channel evidence, such as a stream idle timeout/error or server-side timing evidence.

Evidence JSON: `02 Evidence/2026-09-08_reroute-worker-report-filtered-analysis.json`

## Clean labeled positive: 2026-09-06 21:44 EEST

The 21:44:39–21:44:46 EEST screenshot-confirmed reroute is the cleanest worker-report-bounded positive found so far. It occurred inside `P3 convergence manual go` (`p3-convergence-20260906-go2-sol`), which started at 21:24:13 EEST and later archived successfully as `RUN_FINISHED` at 21:47:40.152 EEST. Therefore the banner interval is definitively not ordinary post-run waiting.

At screenshot time, caller `caller_86efff37c610` was polling the same preflight process `208be867-907a-407f-9923-b1d2cd326af6` (PID 37456). That process had started at 21:42:23.912 EEST and was running an exact-current P3 worker-editor preflight with a bounded 180-second timeout. A diagnostic at 21:44:03–21:44:04 showed its `UnrealEditor-Cmd.exe` child alive, CPU 20.73 s and ~1134 MiB working set, with its preflight log actively updating.

The first screenshot timestamp is 21:44:39.301. It falls *inside* a `read_output` call that began at 21:44:35.790 and completed at 21:44:45.802 with HTTP 200 and only 365 response bytes. The second screenshot at 21:44:46.291 is immediately after that read completed. The caller then issued another `read_output` at 21:44:48.721, followed by more polls through 21:45:36.155. The preflight process itself ended at 21:45:32.712 with its expected bounded timeout error, not at reroute onset.

After the first screenshot and before the valid report archive, the same caller produced 14 additional MCP requests/responses (7 `read_output`, 7 `start_process`) and launched 8 processes including the final report archive. Substantive post-banner work included verifying the hydrated showroom map remained byte-identical and the owned preflight editor was reaped; posting the #1773 convergence checkpoint; preserving the reroute screenshots by exact SHA-256; recording the reusable map-package LFS-preflight lesson; and finally archiving the run successfully.

**Implication:** this confirmed positive is a visible safety-buffering banner with *continuous MCP/tool-plane activity inside a report-bounded run*. There is no tool-plane silence at banner onset, no process death at onset, and no large result at onset. The 365-byte no-change read is operationally indistinguishable from healthy polling immediately before and after. The later valid worker stop proves the UI event happened mid-run, not at an end-of-turn boundary.


## MCP identity correction: caller/session fingerprints are not worker identity

The production connector source now closes an important interpretation gap. `caller_id` is generated by hashing `x-openai-session`, then `mcp-session-id`, then authorization/IP fallback; its own source describes this as a **stable pseudonymous ID for live tool cards and transport logs**. `session_id` separately fingerprints `mcp-session-id || x-openai-session`. The HTTP MCP server is stateless (`sessionIdGenerator: undefined`).

In a transport-wide snapshot of 325,745 `request_start` events, 111,047 had both caller and session IDs and **all 111,047 shared the same 12-hex suffix**; zero had different suffixes. So in this deployment the two fields are not independent evidence. The Owl archived caller had 699 request starts and all 699 carried `session_e89dd7b969dd`.

Correct evidence boundary: same `caller_id`/`session_id` means the connector associated those requests with the same pseudonymous session material. It does **not** prove the same backend model worker, inference request, app-server turn, or Responses stream. Same exact external `process_id`/PID is materially stronger evidence for child-process continuity; direct app-server thread/turn IDs and Responses request/response IDs are stronger for model-side continuity. `connection_id` is weaker still and is transport plumbing.

Practical identity evidence should now be treated by layer rather than as one flat ranking: exact external process ID/PID proves child-process identity; direct app-server thread/turn IDs or Responses request/response IDs are the strongest available model-side identifiers; an upstream distributed trace ID proves tracing lineage across requests but is not itself a model-worker ID; MCP caller/session fingerprints are weaker connector association; connection ID is transport plumbing.


## Upstream distributed trace-context evidence from the Owl edge capture

A preserved VPS Caddy access-log segment supplies an upstream signal that was not available in the local connector logs. Forty-two Owl `/mcp` requests in the incident window map to one raw `X-OpenAI-Session` value and one `X-OpenAI-Subject` value, yet they contain **two distinct Datadog trace IDs**. The joined artifact intentionally omits the raw session, subject, and remote addresses. Across those 42 requests the edge saw 41 remote sockets and 16 remote IPs, further demonstrating that socket/connection churn is much noisier than the stable trace contexts.

The final MCP request before the 113-second tool-plane silence (`c566d5d3-1089-46d4-bb4e-b888ad4bc61a`) and the first request after manual Stop -> `go` (`44cb0e97-30a5-463b-997b-a4987271f6f7`) share exact trace ID `7894687964776873105`. The edge gap is **113.367 s** and the local request-start gap is **113.369 s**. This is direct continuity of an upstream distributed tracing context across the manual interruption/restart boundary and is materially stronger than the pseudonymous connector caller/session match. It remains insufficient to identify the backend model worker, inference request, or exact app turn because distributed traces can span multiple internal operations.

At `22:14:10 EEST`, a second trace, `7050226915736017071`, was simultaneously active. Trace `7050...` launched process `24ecba3c-7417-47ea-8404-d44b4c1993d4`; trace `7894...` launched `b9486459-7bee-402e-8265-2fdca44a4dae`. Their local request starts were separated by **49 ms**, and the two traces interleaved Owl MCP traffic for **67.306 s**. This proves **overlapping upstream execution/tracing contexts** under one observed connector session. It does not by itself prove two concurrently executing model workers.

The capture also corrects the earlier point-in-time end boundary. After `00bf3ca2-3ade-4611-a56f-b97cd884510c` exited at `22:17:01.575`, trace `7050...` later launched `0471f991-e8ec-42fe-a712-0731720f7747` at `22:17:35.289` and `daf3b885-e2f1-4339-a697-56a548244e79` at `22:18:28.689`; the latter finished at `22:18:56.993`. Therefore `22:17:01` was only the latest-work boundary at that earlier live check, not the final Owl work boundary.

Machine-readable evidence: `02 Evidence/2026-09-08_owl_edge_trace_overlap.json`.

Updated: 2026-09-08T04:19:20.877103+03:00

## Product-artifact distinction: safety buffering is not `model/rerouted`

Direct inspection of the installed Codex package now resolves the naming ambiguity. The package handles `model/safetyBuffering/updated` and `model/rerouted` as **different app-server notifications**. The former writes turn-local `safetyBuffering` state; the latter appends a `modelRerouted` timeline item carrying `fromModel`, `toModel`, and `reason`. Therefore the visible faster-model thinking banner must not be called a model reroute merely because it appears.

The safety-buffering banner selector explicitly looks for a turn with `safetyBuffering.showBufferingUi === true` and displays it only while that turn is still in progress. The payload exposed to the UI includes `fasterModel`, `reasons`, and `useCases`. The packaged English defaults are **“Giving this request a little extra thought”** and **“If you'd rather not wait, retry with a faster model. It may be less capable of handling complex requests.”** This is the same faster-model/wait UI family as the user-observed banner, although exact host/version wording can differ.

The built-in Retry path is also now directly verified. `retrySafetyBufferedTurn` locates the buffered turn, interrupts that specific active turn, reverts/rolls back one *conversation* turn, and starts a replacement with the buffered input, the selected faster model, and `turnTrigger=safety_buffer_retry`. The current confirmation explicitly says that file changes and other actions already taken **remain**. This built-in Stop-and-retry flow is therefore distinct from the user's manual **Stop -> `go`** experiment; the latter has separate empirical transport/process evidence and should not be modeled as `retrySafetyBufferedTurn`.

This explains an important part of the transport observations: the banner is turn/UI state above MCP, so its appearance does not imply that the MCP worker or its external child process has stopped. A buffered turn can continue doing real MCP work under the banner. The later Owl 113.366-second zero-MCP/zero-child interval is a **tool-plane-silent phase** that happened while the banner remained visible; it is not by itself evidence that remote model inference or server-side safety processing had stopped.

The installed package inspected here is `OpenAI.Codex_26.901.4073.0`, `app.asar` SHA-256 `689A59ECCD6B4D38F3DDAF202DAC05B7CF5CA9CBA93B2703F7AA8A44BE90B23E`. The current `~/.codex/logs_2.sqlite` contains no literal persisted matches for the safety-buffering or model-reroute notification names, so exact historical notification payloads (`reasons`, `useCases`, etc.) cannot be recovered from that database.

Product-artifact evidence: `02 Evidence/2026-09-08_safety-buffering-product-artifact.json`

## Banner lifecycle and manual Stop mechanics

The banner persistence now has a concrete frontend explanation. `model/safetyBuffering/updated` stores the buffering payload on the turn. The banner selector requires `safetyBuffering.showBufferingUi === true`, but its actual render visibility is additionally gated by the turn remaining `inProgress`. Direct search found no obvious `safetyBuffering = null` or `delete safetyBuffering` path. `turn/completed` instead updates the turn's status from the app-server completion notification. Therefore the banner can remain on screen through a zero-MCP interval **without any repeated safety-buffering event**; it naturally stays eligible while the turn itself has not completed.

Manual Stop is a different mechanism again. The installed `interruptConversation`/`ptn` path sends `turn/interrupt`, marks the app turn interrupted, explicitly cleans active `node_repl` executions, and separately interrupts descendant subagent turns. The inspected path does not establish ownership over arbitrary connector-managed MCP subprocesses. That matches the stronger empirical evidence already captured: an exact MCP child can survive a manual pause/Stop -> `go` boundary.

This gives the current layered model:

1. **Safety-buffering UI state** is turn-local app-server/frontend state and can coexist with normal MCP work.
2. **MCP child processes** are a separate execution layer; some can continue even when the app turn is interrupted or buffered.
3. **Tool-plane silence** is the narrower *observable* condition where the same still-open logical run has no new MCP calls and no live owned connector child. The Owl 113.366-second interval is in this category. It is ambiguous with respect to remote inference because the exact client can be awaiting the Responses stream during such an interval.
4. **Backend/model stall** is stronger and is **not established** for Owl. It requires Responses/inference-channel evidence beyond MCP transport and child-process absence.
5. **Valid worker stop** remains independent again: it requires the successful worker-report finalization marker.

## Exact v0.153.1 execution-path correction: zero MCP is not backend idle

This report previously overclassified the Owl 113.366-second zero-MCP/zero-child interval as a “machine-side stall.” Inspection of the **exact public source tag matching the installed binary**, `rust-v0.153.1` at commit `985641272869835d01d025ed2a218fbbce35fa9f`, shows that classification is too strong.

In `core/src/session/turn.rs`, `run_turn` builds a sampling request and awaits `run_sampling_request`; `try_run_sampling_request` opens the remote Responses stream and then repeatedly awaits `stream.next()` under the turn cancellation token. Safety-buffering events are handled passively: `ResponseEvent::SafetyBuffering` only forwards a `SafetyBufferingEvent` containing model, use cases, reasons, UI flag, and faster model. It does not cancel, pause, or block tool execution. The exact release test `process_sse_emits_all_safety_buffering_notifications_without_dropping_response_events` interleaves safety-buffering metadata with normal text deltas and `response.completed`, proving that buffering metadata and ordinary response progress coexist in the same stream.

The same release defines `DEFAULT_STREAM_IDLE_TIMEOUT_MS = 300_000` (**300 seconds / 5 minutes**). The built-in OpenAI provider leaves `stream_idle_timeout_ms` unset and therefore uses that global default. The current user `~/.codex/config.toml` has no provider or stream-idle-timeout override. Both SSE and WebSocket transports apply this timeout around each wait for the next stream event and only convert the wait into an idle-timeout error after that duration. A single 113.366-second no-event wait is therefore **well inside the client's normal 300-second wait budget** (37.8% of it).

This does not prove Owl spent all 113.366 seconds inside one `stream.next()` call, because the historical Responses stream itself was not retained. It does prove that the local evidence pattern — in-progress turn + visible safety-buffering banner + zero MCP calls + zero connector child — has a normal execution state consistent with the exact installed release. Therefore the correct label is **confirmed tool-plane silence, backend state unknown**.

A related correction: `x-codex-turn-state` is a sticky-routing token captured from the Responses transport and replayed for continuation/retry routing. It is not evidence of a special “paused turn” state. Earlier interpretation of that header as pause semantics is withdrawn.

Updated: 2026-09-08T01:07:35.171091+03:00

## Trigger boundary: the client does not decide `user_risk` / safety-buffering eligibility

The exact `rust-v0.153.1` source moves the remaining trigger question decisively upstream. In the SSE path, safety-buffering treatment is read from **server response headers** (`stream_response.headers`). The event parser emits `SafetyBuffering` only when the incoming Responses stream contains either a top-level `safety_buffering` object or a `response.metadata` event with `type = safety_buffering`; once that payload exists, the client explicitly sets `show_buffering_ui = true`.

The `x-codex-safety-buffering-faster-model` header is only a fallback source for the retry-model name. An exact WebSocket regression test deliberately supplies `x-codex-safety-buffering-enabled: false` and then a `safety_buffering` event; the expected result still has `show_buffering_ui: true`. In other words, the streamed event payload controls visibility. Searching the production client source finds no local `user_risk` classifier or prompt/tool-history predicate; `user_risk` appears as test/protocol fixture data.

**Boundary conclusion:** this release's local client does not compute the rule that decides whether a turn is cyber/user-risk/otherwise safety-buffered. It parses and presents an upstream/server-provided decision. Determining the actual trigger predicate therefore requires capture of the Responses/app-server safety-buffering payload or server-side evidence; MCP transport statistics cannot recover that predicate.

## Local log retention and future capture probe

`logs_2.sqlite` has two independent retention limits in the exact release: startup removes rows older than **10 days**, but inserts also enforce a much tighter per-thread/per-process cap of **10 MiB or 1,000 rows**, whichever is exceeded first. This makes retrospective high-volume traces fragile even inside the ten-day age window.

For the Owl incident window itself (`19:08-19:19 UTC`), the current database contains **zero rows of any kind**. The nearest retained row before the window is `17:48:06 UTC`; the next is `19:22:17 UTC`. Therefore there is no historical Responses trace available to decide what Owl's backend was doing during the 113.366-second tool-plane-silent interval. This is an evidence gap, not evidence of backend inactivity.

A new read-only probe, `tools/safety_buffering_probe.py`, now snapshots the MCP caller transport state, live connector children, latest receipt, optional/auto-mapped Codex thread tracing, Responses-span markers, safety-buffering log evidence, and stream-idle-timeout evidence. Its classification contract intentionally stops at **tool-plane silence** unless additional Responses-channel evidence exists. Auto-mapping is best-effort: for Owl's latest retained receipt it correctly returns `no_match` because the local Codex log database has no matching retained rows.

Updated: 2026-09-08T01:18:12.169552+03:00

## Exact UI lifecycle: the banner is intentionally decoupled from execution progress

Inspection of the exact installed-release source (`rust-v0.153.1`) makes the transport observations substantially less ambiguous. The safety-buffering UI is a **display/lifecycle state for an in-progress turn**, not an execution-state indicator.

In `tui/src/chatwidget/safety_buffering.rs`, an active safety-buffering record tracks the turn id, whether a retry is available, and whether an assistant message has started. The UI accepts `showBufferingUi` and a server-selected faster model, but it does not use `useCases` or `reasons` to decide execution behavior. While safety buffering is in its waiting state, `tui/src/chatwidget/streaming.rs` still appends incoming reasoning deltas to the reasoning buffer; it merely suppresses replacing the banner/status with reasoning-derived headers. Tool execution is not paused by this code path.

The upstream change that introduced this test, PR #30490 (`fix(tui): clear completed safety buffering prompt`), states the intended lifecycle even more explicitly: keep the safety notice visible while the turn is active, then remove it when the turn becomes terminal. Its test instructions say to let the turn continue and confirm the prompt remains visible while active. PR #32286 later clarified the copy to tell users that no action is required and waiting continues. This is design intent, not an accidental stale-banner interpretation.

The strongest source-level confirmation is the exact regression test `safety_buffering_remains_visible_until_turn_completes` (`tui/src/chatwidget/tests/app_server.rs:193-215`). The test deliberately:

1. starts a turn and receives `ModelSafetyBufferingUpdated`;
2. verifies the buffered turn is initially retryable;
3. injects a real assistant text delta (`"Visible response"`);
4. verifies retry is now disabled **while the safety-buffering banner is still rendered**;
5. completes the turn; and only then verifies the banner disappears.

So even visible assistant output is not sufficient to make the banner disappear in this release. This is stronger than the earlier MCP-only observation: the product's own tests require a state where useful response progress has happened while the banner remains visible. Therefore **banner lifetime must never be used as the interval of a worker stall, model stall, or tool stall**.

The retry path is also distinct from the user's manual stop -> `go` experiment. `RetrySafetyBufferedTurn` explicitly interrupts the buffered turn, reads the source thread, verifies the interrupted turn is the latest, forks the source thread *before* that turn with `fork_thread_at(... before_turn_id=turn_id)`, obtains a **new thread id**, replaces the active chat widget with that fork, and resubmits the original turn using the server-selected faster model at low reasoning effort. The Owl stop -> `go` capture instead produced fresh MCP activity under the same observed connector caller/session fingerprints. Those fingerprints do not establish backend-worker or app-turn identity, and the two mechanisms should not be conflated.

## Cyber-state taxonomy: four separate channels, with different evidentiary weight

The exact release exposes several cyber-related states that must not be collapsed into one "security reroute" concept.

| State | Wire/client source | Client behavior in v0.153.1 | What it proves |
|---|---|---|---|
| `model/safetyBuffering/updated` | Server Responses stream carries a `safety_buffering` payload with `use_cases`, `reasons`, optional retry model | Client forwards those values and shows buffering UI | Direct evidence that the server attached a safety-buffering payload; the payload's `use_cases`/`reasons` are server-originated |
| `model/rerouted` / `HighRiskCyberActivity` | Client sees an `OpenAI-Model`/server-model value different from the requested model | **Client itself** labels any model mismatch as `HighRiskCyberActivity` and emits a fixed high-risk-cyber warning | Evidence of a requested/server model mismatch. In this release, the `HighRiskCyberActivity` reason is client-synthesized, not a separately parsed server reason |
| `model/verification` / `trustedAccessForCyber` | `response.metadata.openai_verification_recommendation` array | Client parses known verification strings and forwards a typed verification notification | Direct evidence that server metadata recommended additional account verification; distinct from safety buffering and rerouting |
| `turn/moderationMetadata` | `response.metadata.openai_chatgpt_moderation_metadata` | Client forwards arbitrary presentation metadata | Direct moderation-presentation metadata; distinct channel |
| hard `cyber_policy` | Response failure/error has code `cyber_policy` | Client converts it to fatal `ApiError::CyberPolicy` / typed app-server error | Direct hard policy failure, not a buffering banner |

The `model/rerouted` distinction is especially important. `maybe_warn_on_server_model_mismatch` compares only normalized requested and server model strings. If they differ, it unconditionally emits `ModelRerouteReason::HighRiskCyberActivity` and a hard-coded warning about high-risk cyber routing. There is no server-supplied reroute-reason field involved in that decision path. Thus a `model/rerouted` notification in v0.153.1 is weaker causal evidence than a safety-buffering payload whose `use_cases` and `reasons` arrived on the Responses stream.

This also means the user-visible safety-buffering banner should not be renamed "reroute" merely because both mechanisms can appear in cyber-related workflows. They are separate app-server notifications, are generated from different inputs, and can exist independently.

## The banner text does not identify the safety use-case or reason

The installed desktop artifact (`OpenAI.Codex_26.901.4073.0`, `app.asar` SHA-256 `689A59ECCD6B4D38F3DDAF202DAC05B7CF5CA9CBA93B2703F7AA8A44BE90B23E`) confirms another important limit on screenshot evidence. The banner component receives `useCases` and `reasons`, computes booleans for `bio`, `cyber`, and `user_risk`, and sends those booleans as safety-UX telemetry. But the rendered Codex title and ordinary description are generic: `Giving this request a little extra thought` and the faster-model explanation. The component does not branch that visible title on `bio`, `cyber`, or `user_risk` in the inspected path.

The selector simply finds a turn whose `safetyBuffering.showBufferingUi === true`, returns its `reasons` and `useCases`, and renders the banner while that turn's status is `inProgress`. Consequently, a screenshot of the generic banner proves **visible safety buffering**, but does **not** prove the payload was `useCases=["cyber"]`, `reasons=["user_risk"]`, or any other specific classification. Those values require a captured notification/payload or equivalent runtime state.

This narrows the Owl evidence: its screenshots prove the banner state and can be aligned to MCP activity, but they do not by themselves establish a cyber classification. Public `user_risk` false-positive reproductions are useful analogues, not a label that can be retroactively assigned to Owl.

## Banner visibility is lossy in both directions

The installed desktop component has explicit dismissal state on top of the underlying turn safety-buffering state. It maintains a per-turn dismissed flag and a persisted `safety-buffering-banner-dismissed-v1` preference. The menu exposes `This time` and `Don’t show again`. The final render predicate is effectively:

`turn has safetyBuffering.showBufferingUi` **and** `turn is inProgress` **and** `not dismissed for this turn` **and** `not permanently dismissed`.

Dismissing the banner does not clear the turn's `safetyBuffering` payload; it only changes the display predicate. Therefore visibility is lossy in both directions:

- **banner present** does not mean the worker/model/tool plane is stalled; it can remain through normal progress until terminal turn state;
- **banner absent** does not mean no safety-buffering state exists; a user can hide it per turn or permanently while the underlying turn state remains buffered.

This closes off another tempting classifier. UI screenshots are useful for proving that a banner was visible at a particular instant, but banner presence/absence is not a faithful state machine for the underlying Responses or execution layers.

## Future incident capture: preserve the transient evidence before SQLite pruning

A read-only watcher now exists at `tools/safety_buffering_watch.py`. It is designed around the failure mode encountered in the Owl retrospective: transport JSONL survives, but the relevant per-thread Responses trace can disappear from `logs_2.sqlite` before later analysis.

The watcher archives three independent evidence streams into one append-only JSONL file:

- every newly observed MCP transport event owned by one `caller_id`;
- every newly inserted Codex `logs_2.sqlite` row for an explicitly supplied thread id;
- operator/UI markers such as `banner_on`, `banner_off`, `stop`, and `go` with capture timestamps.

It also emits periodic heartbeats containing the current observed live connector-child set and the exact age of the last target transport/request event. The heartbeat vocabulary deliberately distinguishes `connector_child_active` from `tool_plane_quiet_no_live_child`; every heartbeat leaves `backend_model_state = unknown`.

By default the watcher starts at the current end of the transport file and current max thread-log id, so it captures **future** evidence rather than copying the historical corpus. `--include-existing` is available for bounded forensic tests. A partial final JSONL line is not consumed until the writer completes it, and transport truncation/rotation produces an explicit warning record.

The probe at `tools/safety_buffering_probe.py` was also upgraded to schema v2. It now reports last transport-event, last MCP request-start, and last process-event ages separately; distinguishes a live connector child with no fresh MCP request from true no-child tool-plane quiet; and checks whether `logs_2.sqlite` retains *any* rows in the latest process-receipt time window before attempting thread correlation.

Focused watcher tests cover caller filtering, partial-line handling, incremental thread-scoped SQLite reads, future-clock-skew clamping, live-child state, and operator markers: **5 passed**.

## Retry semantics are surface-specific: installed Desktop does not use the TUI fork path

The installed Windows desktop artifact contains its own safety-buffer retry implementation (`Rln`, reached by `retrySafetyBufferedTurn`) and it is materially different from the Rust TUI implementation described above.

For an active buffered turn, the installed Desktop path:

1. locates the addressed buffered turn;
2. resolves the requested faster model and preserves the existing reasoning effort only if that model supports it, otherwise falling back to `low`;
3. interrupts that exact turn;
4. verifies it is still the latest turn;
5. on a paginated thread with `threadRevert` support, sends `thread/revert {threadId: e, beforeTurnId: a}`; otherwise sends legacy `thread/rollback {threadId: e, numTurns: 1}`;
6. starts the replacement on the **same conversation/thread id `e`** with `turnTrigger: safety_buffer_retry`, the original input, and the faster model.

If the buffered turn is already no longer `inProgress`, Desktop does not replay it; it updates the thread's model/reasoning settings for the next turn and returns.

By contrast, the exact Rust TUI source uses a before-turn fork and receives a new app-server thread id before resubmitting. These are two product surfaces with different implementations. Therefore the correct statement is not “built-in Retry always forks” or “built-in Retry always preserves the thread”; it is **surface-dependent**. The installed Desktop evidence is the relevant implementation for the user's Windows banner.

This does not change the Owl manual Stop -> `go` finding. The user did not invoke the banner's Retry action in that experiment, so neither Desktop safety retry nor TUI safety retry explains the observed manual stop/go continuation.

## Cross-incident trace comparison: overlap is post-intervention, not banner onset

A six-incident edge comparison now separates two previously conflated phenomena. Five of six incidents develop a second upstream trace while the original trace is still active (overlaps: 23.339 s, 88.255 s, 129.007 s, 67.306 s, 53.588 s), but in each inspectable case the second trace begins **after** visible safety buffering was already present and its first action is incident preservation, resumed post-intervention work, or later/new work. UBT is a no-overlap counterexample.

This rejects **trace overlap as a necessary safety-buffering onset condition**. What it does establish is hidden continuation: an older upstream execution/tracing lineage can continue issuing MCP work after a later trace/new intervention begins, creating real shared-worktree/process-race risk. See `02 Evidence/2026-09-08_cross_incident_upstream_trace_context_comparison.json`.

Updated: 2026-09-08T04:51:02.394636+03:00

