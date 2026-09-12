# ChatGPT Library artifact timeline ingestion

## Purpose

Preserve the provenance of artifacts visible to ChatGPT—user uploads, screenshots, model-generated files/images, writing blocks, and other Library files—inside the canonical Vault timeline without copying every artifact byte into Vault.

## Boundary

The ChatGPT Files/Library connector is the observation source. It is not local runtime authority. Vault stores bounded historical metadata: stable file IDs when available, filename, artifact type, source kind, creation/upload/modification timestamps, the time Vault observed the metadata, size, model-generated status, project/tags, and reviewed subject/classification when supplied.

Artifact bytes remain in ChatGPT Library/conversation storage unless a separate workflow explicitly preserves them. A timeline occurrence proves that the artifact was observed with the recorded metadata; it does not prove current file availability, current machine state, causality, or incident identity.

## Ingestion path

1. Read relevant conversation/Library metadata with the ChatGPT Files connector. Prefer exact file IDs and connector timestamps.
2. Pass those metadata rows as JSON or JSONL to `tools/chatgpt_artifact_manifest.py`.
3. The helper normalizes and de-duplicates by `library_file_id` when available, otherwise `file_id`, and stamps `observed_at`.
4. It writes `02 Evidence/chatgpt_artifact_occurrences.jsonl`, which is already consumed by the canonical timeline materializer.
5. The periodic timeline materializer makes the observation queryable. Old durable Library proof remains in the bounded historical-evidence section even after it ages outside the high-volume active horizon.

## Unified discovery projection

`python tools\stack_atlas.py find <natural-language-query>` is the canonical first search surface over this materialized Library evidence and the other local evidence classes. A single query may correlate Library occurrences with local Git commits/branch refs, cached/materialized GitHub issue/PR/body/comments, MCP process receipts and transport/watchdog events, runner/CI/machine/coordinator observations, worker reports, Vault memories/timeline, Atlas owner navigation, and live-swarm hints. This is discovery correlation only: every hit keeps its source authority, timestamp, identity, and verdict. A search evidence cluster never becomes incident/work identity, liveness proof, visual acceptance, or shared truth.

The search path must not fall back to repository-content grep, recursive repo/Vault scans, or GitHub network fanout. Once discovery resolves an exact owner/path, targeted source reads and implementation tracing are allowed. Bootstrap stays intentionally smaller: it may expose current machine/route/topology/recovery/live-swarm and source freshness/health, but it must not embed Library chronology or the other detailed search histories.

Example:

```powershell
python tools\chatgpt_artifact_manifest.py .\connector-files.json --source-kind library
```

Use `--project p3` only when the artifact is explicitly attributable to P3. Otherwise leave it unscoped. Add `subject`, `tags`, `classification`, or `review_status` only when they are supported by actual review/evidence.

## Operational rule

The local scheduled materializer cannot directly enumerate the private ChatGPT Library connector. The model/operator bridge therefore performs the connector read when artifacts are created, uploaded, reviewed, or intentionally backfilled, then invokes the helper. Do not invent metadata or infer unseen attachment IDs. Do not create a new cloud/VPS/MCP service merely to move this metadata.

## Tool-loss incident continuity

For a RED ALERT or other operator-caused interruption where the active tool/connector failure prevents writing the canonical Vault report immediately:

1. Use the existing ChatGPT Library artifact path to preserve an interim incident report with the incident ID, exact user report, known event/report times, observed impact, actions attempted, and last verified live state. Unknown times or states remain unknown.
2. When Vault-capable tools return, before resuming the interrupted engineering task, create or update the canonical incident report under `01 Reports`.
3. Run the existing timeline materializer so the outage, restoration, and report are visible through unified `stack_atlas.py find` and targeted timeline drill-down. Bootstrap may expose only source freshness/health for this history, not the incident chronology itself. Do not create a parallel incident, blocker, scheduler, or monitoring system for this purpose.
4. Never leave an incident chronology ending at tool loss when later evidence establishes the restoration or failure outcome; close the gap in the Vault report when tools return.
5. This continuity rule does not authorize any production mutation. It only preserves evidence when the normal Vault write path is temporarily unavailable.
