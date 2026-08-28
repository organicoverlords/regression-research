# Memory normalization and classification

Issue #87 uses one bounded deterministic classifier over the canonical append-only memory bank and candidate layer. Classification is derived metadata, not a second source of truth and not permission to promote an unsupported claim.

## Bounded taxonomy

Semantic categories are limited to: `CORRECTION`, `PREFERENCE`, `DECISION`, `WORKFLOW_POLICY`, `INCIDENT`, `PROJECT_STATE`, `STATE_SNAPSHOT`, `CHECKPOINT`, `FACT`, `PROJECT_LESSON`, `LESSON`, and `HYPOTHESIS`. Specific topics belong in scopes, projects, roles, entities, and tags rather than new categories.

Primary domains are limited to: `project:p3`, `project:tiny3d`, `project:lowvram`, `cross-project`, `memory-system`, `assistant-orchestration`, `mcp-control-plane`, `regression-research`, `machine-ops`, `chatgpt-personalization`, and `global`.

Durability is one of `DURABLE`, `HISTORICAL`, `TIME_BOUNDED`, `EPHEMERAL`, or `REVIEW`. Sensitivity is `CLEAR`, `REVIEW`, or `EXCLUDE`. The existing canonical dispositions remain `CURRENT_DURABLE`, `HISTORICAL_DURABLE`, `SUPERSEDED`, `REJECTED`, `PROVISIONAL/NEEDS_EVIDENCE`, `DUPLICATE_MERGED`, `EPHEMERAL/DO_NOT_RECALL`, and `SENSITIVE_EXCLUDED`.

## Classification rules

Project and role classification is deliberately conservative. An explicit `project` field wins. Otherwise project/role are inferred only from descriptor fields such as scope, title, and tags. A project name mentioned only inside a memory body does not silently re-scope a global or cross-project rule.

`PROVISIONAL` remains review work; classification never converts it to `PROVEN`. Rejected and superseded records stay historical. Point-in-time checkpoints and volatile snapshots are historical or ephemeral rather than current durable context. Expired entries are historical. Strong secret-like values are excluded from ordinary recall; ambiguous sensitivity language is routed to review instead of being silently dropped.

Ordinary recall, recent-title orientation, hybrid recall, and behavioral authority use the same lifecycle boundary: rejected, superseded, expired, historical, ephemeral, or strongly sensitive records cannot become current task context. Explicit history remains the route for preserved evidence.

## Incremental operation

New canonical writes through `memory_bank.py append` and `record` automatically persist a `project` when exactly one project is safely inferable from descriptors. Explicit `--project` remains authoritative. The classifier itself can inspect one existing record without rescanning the corpus:

```powershell
python tools\memory_classification.py --bank memory\memory-bank.jsonl --id <memory-id>
```

The full derived audit is regenerated with:

```powershell
python tools\memory_normalization_report.py --output "02 Evidence\2026-08-29-memory-normalization.json"
```

That report accounts for every current bank/candidate record, includes the taxonomy, counts by category/domain/project/role/source/state/disposition, supersession and exact-duplicate accounting, and explicit `review_queue`, `ambiguous_records`, and `uncategorized` sections. A committed report is a point-in-time receipt tied to source hashes; it is not a mutable recall database.

## Review boundary

A record is allowed to remain unresolved only by appearing explicitly in the report review queue. Ambiguous project assignment, sensitivity review, unsupported hypothesis state, or an unreviewed candidate must never disappear into an implicit default. Candidate-only records use the same classifier and accounting path as bank records; source-specific ingestion does not create a parallel memory format.
