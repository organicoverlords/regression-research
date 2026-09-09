# CORRECTED: visible safety-buffering banner — connector-session continuity, stop/go recovery, and child-process overlap

Date: 2026-09-07
Status: OBSERVED BEHAVIOR + BOUNDED HYPOTHESIS; internal platform cause unknown
Lineage: `thread:mcp-security-reroute-causality`

## Identity-semantics correction (2026-09-08)

The production MCP connector does **not** define `caller_id` as a model-worker identifier. `src/lib/caller-id.ts` calls it a stable pseudonymous ID for tool cards/logs and hashes the first available value among `x-openai-session`, `mcp-session-id`, authorization, or IP. `session_id` is separately a hash of `mcp-session-id || x-openai-session`. The production server is stateless (`sessionIdGenerator: undefined`).

A transport-wide check of 325,745 `request_start` events found 111,047 with both IDs present, and **all 111,047 had identical 12-hex suffixes**; none differed. Thus `caller_id` + `session_id` are not two independent continuity signals in this deployment. For the Owl archived caller specifically, all 699 request starts carried `session_e89dd7b969dd`. This is strong connector-association evidence, but it cannot establish backend model-worker, inference-request, or app-turn identity.

The direct process evidence remains unchanged. Where the exact same MCP `process_id`/PID survives across a pause/Stop -> `go` boundary, child-process continuity is proven independently of connector identity semantics. Likewise, the Owl concurrent-writer race is proven by overlapping concrete process IDs/PIDs and worktree mutation, not by `caller_id`.

Evidence: `02 Evidence/2026-09-08_mcp-caller-session-identity-semantics.json`.


## Upstream distributed trace-context upgrade (2026-09-08)

Preserved VPS Caddy access logs add a stronger continuity signal than the connector `caller_id`/`session_id` fingerprints. In the Owl incident window, 42 matching `/mcp` edge requests carried one raw `X-OpenAI-Session` value and one `X-OpenAI-Subject` value, but **two distinct upstream Datadog trace IDs**. The privacy-safe joined artifact emits neither raw session/subject values nor remote addresses.

The final pre-gap MCP request (`c566d5d3-1089-46d4-bb4e-b888ad4bc61a`) and the first post-`go` request (`44cb0e97-30a5-463b-997b-a4987271f6f7`) carry the exact same upstream trace ID, `7894687964776873105`. The edge-visible gap between those requests is **113.367 seconds**; the local request-start gap is **113.369 seconds**. This materially strengthens continuity of the upstream tracing lineage across the manual Stop -> `go` boundary. It still does **not** make that trace ID a backend model-worker, inference-request, or app-turn identifier.

A second trace ID, `7050226915736017071`, appears while the first trace is still active. At `22:14:10 EEST`, Trace B launched process `24ecba3c-7417-47ea-8404-d44b4c1993d4` and Trace A launched `b9486459-7bee-402e-8265-2fdca44a4dae`; their local request starts were only **49 ms apart**. The two trace contexts then interleaved MCP work for **67.306 seconds**. This proves overlapping upstream execution/tracing contexts under one observed connector session, but it does not by itself prove two model workers.

Evidence: `02 Evidence/2026-09-08_owl_edge_trace_overlap.json`.


## What was observed

During the Owl rigging workstream (`caller_e89dd7b969dd`, `session_e89dd7b969dd`, worktree `tiny3d-10-eagle-stretch-20260907`), the visible ChatGPT UI repeatedly showed the systems-thinking/safety-buffering banner while fresh MCP calls continued under the same observed connector `caller_id`/`session_id` fingerprints. Those fingerprints are connector transport identity, not backend/model-worker identity. Later product/source inspection established that this banner is driven by `model/safetyBuffering/updated`, which is distinct from the separate `model/rerouted` notification.

The strongest observed sequence was:

- `22:09:54.075 EEST`: process `231e5941-42ea-4034-8517-b908447284db` started.
- From `22:09:57` through `22:11:32`: repeated new `read_output` / process-wait calls were issued while the visible reroute was already present.
- `22:11:35.851`: process `231e5941...` finished successfully.
- `22:11:41.313`: final read of that completed process returned HTTP 200.
- After that final read, there were no new MCP calls and no live child processes for the affected caller until `22:13:34.679`.
- The resulting **tool-plane-silent** interval was 113.366 seconds: no fresh MCP calls and no observed live connector child for this caller. This does **not** establish backend/model inactivity.
- The user then stopped the visibly buffered turn and sent `go`. Fresh substantive MCP work resumed under the same observed connector `caller_id`/`session_id` fingerprints. Edge evidence now additionally shows that the final pre-gap request and first post-`go` request share the exact upstream trace ID `7894687964776873105`; this proves continuity of that tracing lineage across the boundary, while backend model-worker, inference-request, and app-turn identity remain unproven.
- `22:13:34.679`: fresh MCP work resumed and process `bee76a43-7ceb-4db7-9f20-9fdb13b60f46` started.
- `22:14:10`: two distinct upstream trace contexts launched separate processes almost simultaneously: trace `7050226915736017071` launched `24ecba3c-7417-47ea-8404-d44b4c1993d4`, while trace `7894687964776873105` launched `b9486459-7bee-402e-8265-2fdca44a4dae`; the local request starts were 49 ms apart. The trace contexts then overlapped for 67.306 seconds.
- The UI safety-buffering banner reappeared immediately after `go`, but new MCP calls and Blender experiments continued underneath it.
- `22:14:18`: process `86afdf23-92b0-489a-861e-108e124bbe5a` started and completed successfully at `22:14:49.136`.
- `22:17:01.575`: process `00bf3ca2-3ade-4611-a56f-b97cd884510c` exited successfully. A check immediately afterward saw no live target-owned process, but this was only a point-in-time snapshot, not the final end of Owl work.
- `22:17:35.289`: upstream trace `7050226915736017071` launched another substantive Blender helper experiment, process `0471f991-e8ec-42fe-a712-0731720f7747` (PID 9416), which finished at `22:18:01.071`.
- `22:18:28.689`: the same trace launched process `daf3b885-e2f1-4339-a697-56a548244e79` (PID 32440), another Blender analysis, which finished successfully at `22:18:56.993`. Thus the earlier `22:17:01` endpoint is superseded as a final-work boundary.

## Log signature

The observed banner pattern is therefore not simply "banner = no work". It has at least two phases that can be distinguished in local MCP evidence:

1. **Visible safety-buffering banner while tool work is still active:** the same observed connector fingerprint continues to launch processes and issue repeated `read_output` calls. This is tool-plane continuity, not proof of backend-worker continuity.
2. **Visible safety-buffering banner during tool-plane silence:** after a final process exit/read, MCP activity can go completely silent with no live connector child process. In this capture that interval lasted 113.366 seconds. Exact v0.153.1 client source later showed that this state is compatible with the still-in-progress turn awaiting the next remote Responses event, so it must not be called a backend stall from MCP evidence alone. A user stop -> `go` was followed by fresh MCP work, and preserved edge telemetry now shows the final pre-gap and first post-`go` calls on the same upstream distributed trace. That is stronger continuity evidence than the connector fingerprint, but it still does not identify a backend model worker or exact app turn.

This makes a useful operational detector for future incidents:

`active MCP traffic during visible safety-buffering -> final process exit/read -> long zero-MCP/no-child tool-plane-silent interval while the banner remains visible -> user stop/go -> the same connector fingerprint carries fresh MCP work again`

Connection-ID changes are not sufficient on their own to identify safety buffering, model rerouting, or backend-worker replacement; they occurred during otherwise healthy activity as well.

## Child-process overlap finding

A separate but related Owl incident showed that asynchronous children can outlive the model's immediate active tool-call sequence and continue affecting shared state. An older PowerShell process, Windows PID `25764`, remained alive with Blender child PID `4064` and repeatedly copied/tuned `src/tiny3d/workers/avian_rigging.py` while newer activity under the same observed connector fingerprint was already evaluating the same worktree. A newer Blender run then observed code written by the older process, demonstrating a real concurrent-writer race.

The stop/go recovery capture also showed multiple child processes active close together under the same observed connector fingerprint, including simultaneous process launches on different MCP connection IDs.

## Hypothesis to test

The user's hypothesis is plausible and should be tested explicitly: **spawning multiple asynchronous child processes may allow work to continue after the model/turn is no longer actively issuing calls, and overlapping children may create hidden progress or state races during reroute periods.**

What is supported now:

- background OS child processes can continue independently after launch;
- more than one child can be active under the same observed connector fingerprint;
- an older child can continue mutating the shared worktree while newer work is active;
- visible safety buffering can coexist with ongoing MCP activity;
- visible safety buffering can later persist through tool-plane silence after MCP activity and connector child processes have stopped;
- stop -> `go` can be followed by fresh work under the same observed connector fingerprint; this is not by itself backend-worker or turn continuity.
- the same upstream distributed trace ID spans the final pre-gap request and first post-`go` request, proving tracing-lineage continuity across that boundary;
- two distinct upstream trace IDs can interleave MCP work and launch separate external processes under one connector session, proving overlapping upstream execution/tracing contexts without proving separate model workers.

What is **not** established:

- that spawning multiple children causes safety buffering or model rerouting;
- that a second backend model worker necessarily exists when multiple children overlap;
- that every safety-buffering interval contains an orphaned child;
- that the 113.366-second tool-plane-silent interval was caused by child-process management;
- that the 113.366-second interval proves the remote model/backend was idle or stalled.

The child-process hypothesis currently explains hidden continuation and shared-state contamination better than it explains the reroute trigger itself. Future captures should record, at each user-visible reroute boundary, the count of live children, their parent PIDs/process IDs, start times, final reads, and whether any remain alive after the affected caller stops issuing MCP calls.

## 2026-09-08 source-level correction

Exact public source matching the installed CLI (`rust-v0.153.1`, commit `985641272869835d01d025ed2a218fbbce35fa9f`) changes the interpretation of the zero-MCP/no-child phase. `try_run_sampling_request` can remain inside an in-progress turn while awaiting `stream.next()` from the remote Responses transport, with no MCP call and no connector child. The default stream-idle timeout is 300 seconds; the Owl 113.366-second interval is below that client timeout. Therefore this report's original phrase **"machine-side silent interval"** is superseded by **"tool-plane-silent interval; backend/model state unknown."**

The same source confirms that `ResponseEvent::SafetyBuffering` is only forwarded as UI/metadata state and does not itself pause/cancel the turn. `model/safetyBuffering/updated` and `model/rerouted` are separate notification paths.

## Cross-incident correction: the second trace is a downstream overlap phenomenon

Comparing Owl with P3 20:27, P3 21:44, Tiny3D 17:50, Sep-6 03:54, and UBT shows that Owl's two-trace overlap is **not** a unique or plausible banner-onset trigger. Five of six incidents later develop overlapping trace contexts, but the second trace begins only after the visible buffering episode/onset; several first secondary-trace commands are explicitly user-requested incident-preservation or resumed/new work. UBT has no overlap at all.

The stronger general finding is therefore: **user intervention/new work can begin on a later upstream trace while the earlier trace remains active.** This explains hidden continuation and race potential; it does not explain the upstream safety-buffering classification itself. Evidence: `02 Evidence/2026-09-08_cross_incident_upstream_trace_context_comparison.json`.

Updated: 2026-09-08T04:51:02.394636+03:00

## Pause/go trace-control correction

A separate pause/`go` control (`caller_963063535760`) also preserves one upstream trace ID across the boundary while an exact external child survives. Thus Owl's same upstream trace across Stop -> `go` is **not safety-buffering-specific**. It strengthens request-lineage continuity compared with connector fingerprints, but it cannot be used as an onset/cause discriminator. Evidence: `02 Evidence/2026-09-08_pause_go_upstream_trace_control.json`.

Updated: 2026-09-08T04:57:58.452183+03:00

