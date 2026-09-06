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

Example:

```powershell
python tools\chatgpt_artifact_manifest.py .\connector-files.json --source-kind library
```

Use `--project p3` only when the artifact is explicitly attributable to P3. Otherwise leave it unscoped. Add `subject`, `tags`, `classification`, or `review_status` only when they are supported by actual review/evidence.

## Operational rule

The local scheduled materializer cannot directly enumerate the private ChatGPT Library connector. The model/operator bridge therefore performs the connector read when artifacts are created, uploaded, reviewed, or intentionally backfilled, then invokes the helper. Do not invent metadata or infer unseen attachment IDs. Do not create a new cloud/VPS/MCP service merely to move this metadata.
