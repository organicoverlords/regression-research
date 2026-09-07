# Reroute-gap cohort analysis: strongest current explanation

**Date:** 2026-09-07 EEST
**Scope:** user-visible ChatGPT reroute/thinking incidents correlated with local MCP transport activity
**Status:** statistical correlate identified; internal platform mechanism not directly observable

## Short version

The broad evidence no longer supports GitHub credentials, secret output, Blender/UBT, repeated 10-second polling, a live child process, or machine-wide worker concurrency as the common cause.

The strongest measurable common link is **post-tool model re-entry in an old, tool-heavy chat/caller state**. Long action gaps become much more common after a caller has accumulated hundreds to thousands of tool interactions and multiple megabytes of MCP response payload. Large individual/recent tool results amplify the effect. This fits the live `stop -> go` behavior: `go` creates a fresh execution continuation, but it returns to the same heavily accumulated chat state, so one additional tool call can immediately enter the visible reroute state again.

This does **not** prove the private OpenAI routing/compaction implementation. It is the strongest observable correlate in our logs.

## Dataset

Transport snapshot across `clone-a/transport.jsonl` plus archives:

- 145,121 successful MCP tool calls with a later request in the same caller were available for gap analysis in the main feature snapshot.
- 540 callers represented.
- **3,800 same-caller 60-600 second action gaps** in the feature snapshot (the live log continued growing during analysis, reaching 3,804 shortly afterward).
- Control cohort: **86,246 calls followed by the next same-caller request within 1-10 seconds**.
- All 3,800 long-gap preceding MCP responses were HTTP 200.

A gap is a transport signature, not by itself proof that the UI showed a reroute. It is used because multiple user-confirmed live reroutes demonstrated exactly this sequence: successful tool result -> no further caller actions -> visible reroute persists -> `stop/go` -> caller resumes.

## 200 strongest recent gap candidates

The 200 longest recent 30-600 second gaps in the then-current transport snapshot ranged from **40.604 s to 554.712 s** across 19 callers.

Immediately preceding tool type:

- `start_process`: **165 / 200**
- `read_output`: **32 / 200**
- `kill_process`: **3 / 200**

Process state returned immediately before the gap:

- completed/not running: **170 / 200**
- still running: **20 / 200**
- state unavailable / kill: **10 / 200**

Other properties:

- response payload > 8 KiB: **61 / 200**
- response payload > 32 KiB: **10 / 200**
- next request used a different connection id: **186 / 200**
- receipts available for command/output classification: **197 / 200**

Exclusive command-domain classification of those 197 receipts:

- other/mixed: 59
- Git/GitHub other: 54
- status/log probe: 34
- Busy coordination: 19
- build/test: 16
- delayed monitor poll: 10
- credential-related: **5**

No secret-like output marker was detected in the retained output of these 200 cases.

## Long-gap cohort versus normal short-gap control

| Feature immediately before next-action gap | 60-600 s gap | 1-10 s control | Relative rate |
| --- | ---: | ---: | ---: |
| `start_process` | 77.76% | 67.27% | 1.16x |
| `read_output` | 21.50% | 31.92% | 0.67x |
| returned process `running=false` | **77.42%** | 60.96% | **1.27x** |
| completed `read_output` | **10.18%** | 5.88% | **1.73x** |
| returned process `running=true` | 16.05% | 27.93% | 0.57x |
| requested 10 s wait | 22.68% | 36.51% | 0.62x |
| response > 8 KiB | **26.39%** | 13.38% | **1.97x** |
| response > 32 KiB | **5.00%** | 1.98% | **2.53x** |
| next request changes connection | 87.08% | 64.10% | 1.36x |

Interpretation: the long-gap signature is more associated with **having just received a completed result**, especially a larger result, than with waiting on an active process. Ten-second polling is underrepresented, not overrepresented.

Connection changes are very common after long idle periods and are therefore treated as a likely consequence/correlate, not a proven trigger.

## GitHub credential / secret-output hypothesis

This does not explain the broad problem.

Current retained-receipt comparison:

- 60-600 s gaps: credential-related **4 / 133 = 3.01%**
- 1-10 s controls: credential-related **56 / 3411 = 1.64%**
- Git/GitHub network commands: **33.83%** of long gaps versus **38.17%** of controls
- secret-like output markers: **0** in both cohorts

Older archived receipt sample, where fewer receipts remain available:

- credential-related long gaps: **1.59%**
- credential-related controls: **1.97%**
- secret-like output markers: **0**

The credential category is small and inconsistent across snapshots; Git/GitHub activity itself is not elevated in the gap cohort. The current runner GCM hang is a real local Git problem but is not a credible common explanation for the widespread reroutes.

Raw credential-helper output should still never be dumped into model-visible logs as a hygiene rule, but there is no evidence that leaked GitHub secrets are driving this reroute class.

## Machine-wide swarm concurrency hypothesis

Also weak / mostly eliminated.

In the preceding 60 seconds:

- short-gap controls: median 10 *other* active callers
- long gaps: median 10 *other* active callers
- >=15 other callers: 13.69% of short controls versus only 7.84% of long gaps
- >=20 other callers: 2.11% of short controls versus 0.76% of long gaps

So the longest same-caller gaps are not concentrated at the highest shared-MCP concurrency levels.

## Strongest correlate: accumulated caller/tool state

This is the important result.

Immediately before normal 1-10 second continuation:

- median tool calls accumulated by that caller: **238**
- median cumulative MCP response bytes: **1,211,130 bytes**

Immediately before 60-600 second gaps:

- median tool calls accumulated by that caller: **402**
- median cumulative MCP response bytes: **2,338,277 bytes**

The last 20 tool responses also matter:

- >=100 KiB across last 20 responses: 59.86% long-gap versus 40.46% short-gap
- >=200 KiB across last 20 responses: **16.38% long-gap versus 6.06% short-gap = 2.70x**

Long-gap frequency by caller tool-call age:

| Calls already accumulated | 60-600 s gap rate | >=30 s gap rate |
| --- | ---: | ---: |
| <100 | 2.75% | 5.37% |
| 100-299 | 1.92% | 4.11% |
| 300-599 | 2.33% | 5.30% |
| 600-999 | **3.64%** | **9.54%** |
| >=1000 | **4.94%** | **24.90%** |

Long-gap frequency by cumulative MCP response bytes in the caller:

| Cumulative response bytes | 60-600 s gap rate | >=30 s gap rate |
| --- | ---: | ---: |
| <0.5 MB | 2.44% | 4.70% |
| 0.5-1 MB | 2.16% | 4.55% |
| 1-2 MB | 1.84% | 3.99% |
| 2-4 MB | 2.73% | 6.43% |
| >=4 MB | **4.69%** | **18.37%** |

This is not a simple linear threshold, but there is a clear high-age/high-volume regime where action gaps become much more frequent.

## User-confirmed reroutes fall inside that high accumulated-state regime

Cumulative tool state at several preserved user-confirmed reroute points:

| Incident | Caller | Tool calls accumulated | MCP response bytes accumulated |
| --- | --- | ---: | ---: |
| 2026-09-06 20:27 EEST extended reroute | `caller_86efff37c610` | 543 | 3,031,527 |
| 2026-09-06 21:44 EEST reroute | `caller_86efff37c610` | 734 | 4,460,007 |
| 2026-09-07 17:50 EEST reroute | `caller_09918a517358` | 309 | 2,375,848 |
| 2026-09-07 22:10 EEST Owl reroute | `caller_e89dd7b969dd` | 862 | 2,936,513 |
| 2026-09-07 22:59 EEST UBT reroute | `caller_cf4d3c2b8796` | 614 | 3,711,146 |
| 2026-09-06 03:54 EEST reroute | `caller_a018b0cbc049` | 478 | 3,349,208 |

These are independent workstreams and command domains, yet all were already deep into a long-lived tool-heavy caller state.

## Working explanation

The best current explanation for the recurring **gap subtype** is:

1. A long-lived ChatGPT worker/chat accumulates a large tool transcript / orchestration state.
2. An MCP tool returns successfully (often with the target process already complete).
3. Control returns to the platform/model side.
4. The next model action is delayed or absent while the UI remains in the visible reroute/thinking state.
5. `stop -> go` creates a new execution continuation and immediately restores MCP activity under the same logical caller/session.
6. Because the underlying chat/caller state is still large, a single additional tool call can enter the same reroute state again.

This fits the user's key correction that **one `go` + one tool call can be enough**. The relevant accumulation is not necessarily the new turn; it is the already-large worker/chat state that the new continuation inherits.

This points toward **platform-side post-tool orchestration / routing / state-compaction pressure** rather than a deterministic local command or secret classifier. The private platform mechanism is not observable, so this remains a bounded explanation, not a claim about internal implementation.

## What is now substantially weakened or eliminated

- GitHub credential manager / GitHub secrets as the broad cause: **no**
- Git/GitHub network calls generally: **no; underrepresented versus controls**
- Blender or Unreal builds specifically: **no**
- repeated 10-second `read_output`: **no; underrepresented**
- child must still be running: **no; completed process state dominates long gaps**
- multiple simultaneous children required: **no**
- MCP request failure required: **no; long-gap preceding responses are HTTP 200**
- highest global worker concurrency: **no**
- connection id change as deterministic trigger: **not supported; likely idle-gap consequence**

## Immediate mitigation direction

Until a platform-side root cause is directly observable, the safest high-value mitigations are:

1. **Keep model-visible tool results small.** Target <8 KiB where practical; never dump whole logs/status inventories when a narrow projection will do.
2. **Rotate long-lived worker chats before the high-risk regime.** A practical trial threshold is around 500-600 tool interactions or roughly 2-4 MB cumulative MCP response payload, preserving a compact checkpoint into a fresh worker/chat instead of continuing indefinitely.
3. **Do not use `stop -> go` as the long-term recovery mechanism for a heavily accumulated caller.** It restarts execution but keeps the same accumulated chat state, which explains immediate recurrence.
4. **Keep credential-helper output redacted/bounded anyway**, but treat that as security hygiene, not the reroute fix.
5. Run a controlled A/B next: same task and tool shape in a fresh caller versus a heavily accumulated caller, with deliberately tiny (<1 KiB) tool responses. User-visible reroute rate is the outcome. This directly tests whether caller/chat age is causal rather than merely correlated.

## Evidence lineage

Related preserved incidents and reports include:

- `02 Evidence/mcp-security-routing-events.jsonl`
- `02 Evidence/2026-09-06_2027-2039_EEST_security-reroute/`
- `02 Evidence/2026-09-06_2144_EEST_security-reroute-recurrence/`
- `02 Evidence/2026-09-07_1750_EEST_security-reroute-recurrence/`
- `01 Reports/2026-09-07_security-reroute-worker-continuity-stop-go.md`
- `01 Reports/2026-09-07_security-reroute-build-status-observations.md`
