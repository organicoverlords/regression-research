# 2026-09-07 ~17:50 EEST user-confirmed security reroute recurrence

The user supplied a screenshot immediately after the Tiny3D #10 avian review/full-pack proof sequence and stated that the assistant was security-rerouted. The screenshot itself shows the assistant/tool UI (`Posted verified immutable avian review evidence and monitored output`, then a collapsed `Called tool` card); it does not expose an internal classifier reason or exact timestamp.

## Bounded finding

This occurrence matches the previously preserved 17:17 EEST subtype more closely than an MCP/process outage: the same MCP caller continued successfully, the in-flight Hummingbird `compile_avian` process completed with exit code 0, and the post-message cleanup read recovered the completed receipt without restarting or replacing the process.

The strongest recurring correlate remains dense process-tool orchestration, especially repeated `read_output` around long-running work. That is correlation only. It does **not** prove that polling density, connection churn, Blender, command content, output size, or MCP itself is the internal security-routing cause.

## Counts from the conversation-visible pre-message trace

- Visible `start_process` launches after `go`: **39**.
- Visible `read_output` polls: **24**.
- Visible process-tool interactions total: **63**.
- These are conversation-visible counts, not a transport-level completeness claim. Prior preserved incidents proved that transport logs can contain more calls than abbreviated conversation traces.
- Poll distribution: full Tiny3D suite 13 reads / 107.403 s; Hummingbird worker 3 / 28.436 s; Eagle worker 3 / 31.450 s; Eagle-verification+Owl worker 3 / 24.388 s; final Hummingbird full-pack process 2 pre-message reads / 36.434 s.

## Immediate avian-review window

Approximate transport-correlated window from visible receipts: `2026-09-07T14:44:35.964Z` through `2026-09-07T14:50:35.910Z` (17:44:35.964..17:50:35.910 EEST).

- 15 visible `start_process` calls.
- 11 visible `read_output` calls.
- 26 process-tool interactions in about 6 minutes (~4.3/minute).
- Several calls returned large receipts; one source/owner inspection hit the 100,000-character retention bound. A hard response-size reroute threshold is **not** inferred; Vault already contains rejected evidence against a simplistic hard-size theory.
- Two benign command-shape/import errors occurred during the avian review and were corrected by the next bounded call; later calls succeeded. They are not evidence of reroute causation.

## Immediate final process at the screenshot boundary

Process: `fce55e17-0afb-4160-889f-d6e6030ae1ac`

Purpose: run the immutable Hummingbird checkpoint through the complete Tiny3D `compile_avian` portable-pack path in a disposable workspace, then verify the pack and print bound hashes/QA.

- started: `2026-09-07T14:49:59.476Z`
- pre-message poll 1: process age 26.136 s, `no_change=true`
- pre-message poll 2: process age 36.356 s, stdout already contained the successful pack result while the process was still marked running
- finished: `2026-09-07T14:50:35.910Z`, exit code 0
- the second pre-message read landed about 78 ms before process exit
- post-message cleanup read was intentionally kept separate and returned the completed exact receipt
- result: `PACK_ACCEPTED=True`, source SHA `94c6ef8e...9a707f`, GLB SHA `453eb1e3...58dd3`, FBX SHA `5b113ed3...cd57`, unchanged deformation QA PASS

This rules out “the underlying compile failed/stopped” as an explanation for the visible interruption.

## Comparison to preserved 17:17 EEST event

The 17:17 incident bundle recorded 38 MCP calls in a 190-second window: 29 `read_output`, 9 `start_process`; all recorded responses were HTTP 200 and the long Blender process completed successfully. The current event is less dense overall but has the same key shape: successful long-running process + repeated process-output observation + user-visible reroute.

Therefore the current evidence strengthens the **recurring correlate** of read-output-heavy orchestration during successful long-running jobs, while still not establishing the platform classifier rule.

## Operational implication

For future long jobs, fewer read calls with longer `read_output(wait_ms=10000)` windows or one discriminating check near expected completion would reduce tool churn. Treat that only as an orchestration hygiene improvement, not a proven security-reroute fix.

The screenshot itself remains a conversation attachment; Vault preserves its SHA-256, byte count, visible-text transcription, and conversation container reference. No MCP/edge serving-path mutation was made while preserving this event.

