# Cross-incident upstream trace-context analysis

Recorded: 2026-09-08T04:51:02.394636+03:00

## Result

Across six independently preserved user-confirmed/screenshot-correlated visible safety-buffering-era incidents, every expanded edge window contains two upstream Datadog trace IDs. **Five of six have the second trace begin while the original trace is still active.** The observed trace-range overlaps are 23.339 s, 88.255 s, 129.007 s, 67.306 s, and 53.588 s. UBT is the counterexample: its later trace starts 414.726 s after the primary trace ends.

The crucial timing result is that the second trace is **downstream of the visible-buffering onset**, not its prerequisite. In the cleanest cases, its first command is directly identifiable as work caused by the user's subsequent intervention: incident evidence lookup (P3 20:27), creation of the incident/screenshot evidence directory (P3 21:44), or resumed post-`go` work (Owl). Tiny3D 17:50 starts the second trace with a Vault/history helper; the Sep-6 case starts it with a later Tiny3D task.

Therefore **trace overlap does not explain why the safety-buffering banner is initially attached**. It explains a different and operationally important behavior: an older upstream execution/tracing lineage can remain alive and continue issuing MCP work after a later trace/new intervention has begun. This directly supports the hidden-continuation/shared-worktree-race concern without relabeling trace IDs as model workers.

| Incident | Primary trace | Secondary trace | Observed overlap | First secondary-trace action |
| --- | --- | --- | ---: | --- |
| P3 extended visible buffering window | `13970740731662145258` | `14438024013644839374` | 23.339s | incident-preservation / reroute-evidence lookup |
| P3 screenshot-confirmed visible buffering recurrence | `11979959086653714598` | `4567811657637384089` | 88.255s | incident-preservation |
| Tiny3D user-confirmed visible buffering recurrence | `18390751640097337760` | `18270779821811564795` | 129.007s | Vault/history helper inspection |
| Owl live-confirmed visible buffering + Stop/go experiment | `7894687964776873105` | `7050226915736017071` | 67.306s | post-go work / claim renewal |
| Sep 6 visible buffering/reroute observation | `839899393597634971` | `14425975242048362587` | 53.588s | later/new Tiny3D task |
| UBT build visible buffering observation | `4665732008252562748` | `7176397038412619597` | 0.000s | later read of completed long-running build process |

## Strong examples

**P3 20:27-20:39.** The secondary trace first appears at 20:39:30 EEST. Its first local process runs the explicit security/reroute incident-evidence lookup and lists recent incident files. The original trace remains visible at the edge for another 23.339 seconds. The second trace is therefore incident handling after the reported window, not the cause of the earlier banner.

**P3 21:44.** Both screenshot timestamps, 21:44:39.301 and 21:44:46.291 EEST, occur before the secondary trace exists. The secondary trace begins at ~21:46:10 and its first process creates the incident evidence directory/screenshot placeholders. The primary trace then remains active concurrently for 88.255 seconds.

**Owl Stop -> `go`.** The primary trace `7894687964776873105` itself spans the 113.367-second pre/post-`go` edge gap. A second trace appears only later in the resumed phase. The two traces then interleave for 67.306 seconds; at 22:14:10 their process-start requests are 49 ms apart. This is direct evidence of overlapping upstream execution/tracing contexts after intervention, but not of two model workers.

**UBT counterexample.** The original trace ends at 22:58:56.670 EEST. A new trace appears ~414.726 seconds later and performs one `read_output` against the already-completed long build. There is no trace overlap.

## What the MCP edge does and does not expose

For the tested incidents, every inspected request had Datadog sampling priority `-1`; the observed Datadog tag keys were only `_dd.p.tid` and `_dd.p.dm`. The MCP edge exposes trace/parent/session metadata but no safety-buffering `use_cases`, `reasons`, risk label, or other direct trigger field. Thus these traces are useful for execution-lineage timing, not for reconstructing the safety classifier decision.

## Current causal split

1. **Safety-buffering trigger:** still server-side and historically unobserved. The local client receives the decision; these MCP edge traces do not reveal the predicate.
2. **Execution overlap after intervention:** now repeatedly demonstrated. An older trace can continue after a later trace/new user action begins, and external connector processes can independently survive in some incidents. This is a credible source of hidden continuation and shared-state races.
3. **Tool-plane silence:** remains a separate observable phase. Zero MCP calls/zero connector children does not by itself establish backend inactivity.

Machine-readable evidence: `02 Evidence/2026-09-08_cross_incident_upstream_trace_context_comparison.json`.

## Pause/go control: same-trace continuity is not buffering-specific

A preserved non-diagnostic pause/`go` control closes another interpretation gap. On 2026-09-06, process `7c029a8c-5298-4710-8485-d748a3429ba4` survived a 12.145-second pause/`go` boundary. The final pre-pause read (`85f35d87...`), first post-`go` request (`ccdf5738...`), and later read (`3e783a44...`) all carry the exact same upstream trace ID `15663332817498453395`.

Therefore **same trace across manual Stop/pause -> `go` is not specific to safety buffering**. Owl's same-trace 113-second boundary remains valid tracing-lineage continuity evidence, but it is not a trigger signature. The stronger diagnostic value of the trace work is the later overlap/race behavior, not same-trace pause/go by itself.

Control evidence: `02 Evidence/2026-09-08_pause_go_upstream_trace_control.json`.

Updated: 2026-09-08T04:57:58.452183+03:00

