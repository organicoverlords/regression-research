SECURITY INCIDENT EVIDENCE INDEX

User-supplied visible incident window:
  2026-09-06 20:27 through at least 20:39 EEST (+03:00)

Preserved MCP evidence:
  live receipt source instances in window: 323
  archived receipt source instances in window: 325
  total source instances represented in manifest: 648
  unique receipt UUID files after deduplication: 325
  exact caller_86efff37c610 receipt files: 47
  exact caller calls whose execution overlaps the incident window: 47

Primary exact-call files:
  exact-caller-start-process-calls.json
  exact-caller-start-process-calls.txt
  exact-caller-calls-overlapping-2027-2039.json
  exact-caller-calls-overlapping-2027-2039.txt
  exact-caller-receipts\

Broad preservation:
  raw-window-receipts-live\
  raw-window-receipts-archive\
  raw-window-receipts-all-callers\   (deduplicated by UUID)
  all-window-receipts-manifest.json   (all source instances with source path/time/size/SHA-256)

Long P3 build overlapping the incident:
  process_id: 5511a061-520b-44f9-a2ab-d92c9c8cc248
  request_id: 0400e987-4f54-4d5f-b66e-ec135999ff92
  started: 2026-09-06T17:22:29.191Z (20:22:29 EEST)
  finished: 2026-09-06T17:34:26.941Z (20:34:26 EEST)
  outcome: success, exit 0
  exact command is preserved in the caller manifests and raw receipt.

Screenshots supplied in chat are referenced by file ID + SHA-256 in incident.json and mcp-security-routing-events.jsonl.

Interpretation boundary:
  The evidence proves the user-reported visible incident window and concurrent MCP/process activity. It does not establish the internal platform routing/safety cause or prove that any P3 operation caused the UI behavior.