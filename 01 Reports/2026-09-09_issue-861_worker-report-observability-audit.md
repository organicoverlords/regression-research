# #861 worker-report / observability YAGNI audit

Captured: 2026-09-09  
Prerequisite: regression-research #820 is still **OPEN**, so this is bounded prework only.

## Current owner trace

The canonical worker-report stack has real consumers and should not be collapsed merely because several derived views mention the same fields:

- `tools/worker_report_history.py` owns report validation, immutable history metadata, and the timed/manual `metrics.json` projections.
- Stack Atlas reads the timed `metrics.json` directly for archived run-quality signals, while its fleet-watch path separately uses current reports/start receipts for current activity/recovery semantics.
- `memory_bank.py` reads timed/manual metrics for archived finding counts and examples and explicitly labels them historical self-report evidence, not liveness or policy authority.
- `timeline_materializer.py` derives a historical/materialized-horizon worker-quality view. Its semantics are intentionally different from the live metrics projection.

Those are **KEEP**, not duplicate telemetry authorities.

## Standalone findings summary: KEEP for now

`tools/worker_findings_summary.py` has no observed automatic caller or scheduled-task invocation, but it is not safely dead:

- it was introduced by commit `6f6e942` for closed issue #532, whose explicit acceptance required a direct read-only aggregate over **immutable history plus RUNNING current reports** across timed/manual populations;
- the current memory overview intentionally consumes archived metrics only, so it is not an equivalent replacement for active-run findings;
- deleting the CLI would therefore remove a distinct user-requested on-demand capability.

Classification: **KEEP** until an equivalent direct surface is deliberately chosen.

## Speculative sidecar: do not promote

There is currently an untracked local file `tools/worker_review_fleet_context.py`:

- **735 source lines / 32,586 bytes**;
- no git tracking/history;
- no repo/contract reference outside itself;
- no GitHub issue reference found by exact identifier/output search;
- no scheduled-task use;
- no live process use other than this inspection;
- its default persisted output `worker-reports/reviews/fleet-context.json` does not exist;
- it re-reads timed/manual worker history and defines a new hard-coded regex ontology for routing faults, resource bottlenecks, stale cohort churn, contention, scheduler recurrence, action mistakes, proof gaps, plus its own fault signatures/regression candidates.

That is exactly the shape #861 should resist unless a current consumer proves the need: another projection plus another classification ontology beside the existing history/metrics/Atlas/memory surfaces.

Because it is **foreign untracked WIP**, this audit does **not** modify or delete it. Classification is:

**REUSE/SHRINK / DO NOT PROMOTE:** if no current owner/unique consumer appears by #820 closure, prefer dropping the sidecar rather than landing a second fleet-context reporting ontology. If an owner does surface, require the unique consumer and missing capability to be demonstrated before deciding.

## Net conclusion

There is no justified deletion in the serving worker-report path today. The YAGNI win is to keep one canonical history/metrics owner and prevent new sidecar projections from becoming parallel authorities without a demonstrated consumer.
