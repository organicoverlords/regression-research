# MCP caller/session identity semantics correction

**Recorded:** 2026-09-08T03:15:21.902766+03:00

The production connector source proves that `caller_id` is a pseudonymous transport identifier, not a model-worker identifier. It hashes the first available `x-openai-session`, `mcp-session-id`, authorization, or IP value. `session_id` separately hashes `mcp-session-id || x-openai-session`. The deployed server creates a stateless `StreamableHTTPServerTransport` with `sessionIdGenerator: undefined`.

A transport snapshot counted 325,745 `request_start` events. 111,047 had both `caller_id` and `session_id`; all 111,047 had identical 12-hex suffixes and zero differed. In the Owl archive, all 699 requests under `caller_e89dd7b969dd` carried `session_e89dd7b969dd`. Therefore those fields are not independent evidence in this deployment.

The corrected interpretation is: **same caller/session = same observed connector fingerprint**, unless stronger identifiers are present. It does not prove the same backend model worker, inference request, app-server turn, or Responses stream. Connection ID is weaker transport plumbing and likewise cannot prove worker replacement or continuity.

The strongest continuity evidence already captured survives this correction. An identical external MCP `process_id`/PID observed before and after pause/Stop -> `go` proves that child process survived. Owl's concurrent-writer incident is likewise proven by overlapping exact process/PID evidence and worktree mutation.

The original flat evidence-order shorthand is superseded by the layer-specific ordering below; distributed trace IDs are stronger than connector fingerprints for tracing lineage but are not model-worker IDs.

Machine-readable evidence: `02 Evidence/2026-09-08_mcp-caller-session-identity-semantics.json`.

## Stronger upstream tracing evidence discovered after the connector-ID correction

Preserved edge telemetry provides a genuinely stronger signal than `caller_id`/`session_id`. The Owl final pre-gap request and first post-`go` request share the exact upstream Datadog trace ID `7894687964776873105` across an edge-visible **113.367-second** gap. This establishes continuity of that distributed tracing lineage across the Stop -> `go` boundary. It still does not prove one model worker, one inference request, or one app-server turn.

The same edge window also contains a second trace ID, `7050226915736017071`, which overlaps the first for **67.306 seconds**. The two trace contexts launch separate external processes only **49 ms apart**. Therefore the stronger statement now supported is: **one connector session carried overlapping upstream execution/tracing contexts**. Distinct trace IDs should not automatically be relabeled as distinct model workers.

Evidence by layer going forward:

- exact external `process_id`/PID proves identity/continuity of that child process;
- direct app-server thread/turn IDs and Responses request/response IDs are preferred for model-side identity;
- upstream distributed trace ID proves tracing lineage and can reveal overlapping trace contexts, but is not a model-worker identifier;
- MCP caller/session fingerprint proves connector association only;
- connection ID is transport plumbing.

Machine-readable evidence: `02 Evidence/2026-09-08_owl_edge_trace_overlap.json`.

Updated: 2026-09-08T04:19:20.877103+03:00

