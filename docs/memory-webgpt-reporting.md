# Bounded WebGPT reporting

This repository now provides a read-only report workflow for the existing
`shell-mcp` route. It does not add an MCP server or a tool: the frozen
seven-tool shell-mcp invokes the CLI with `start_process`, and `read_output`
returns its result. The repository workflow reads only the already-available
local corpus; it does not download, import, fetch, or open raw transcript
content.

## Commands

Run from the repository root:

```powershell
python tools\memory_report.py status --format json
python tools\memory_report.py report --query "MCP safety routing" --format text
python tools\memory_report.py report --query "policy history" --scope global --limit 5 --format json
python tools\memory_report.py report --query "superseded threshold" --history --limit 20 --format text
```

The normal WebGPT sequence is:

1. Call the existing shell-mcp `start_process` with the command above and the
   repository as `working_directory`.
2. Use `read_output` for that process once it completes.
3. Treat the report's `receipt` as the exact local corpus/provenance snapshot
   used for the answer.

The default report is relevance-first and returns at most five memory entries.
Ordinary recall is hard-capped at eight; explicit history is hard-capped at
twenty. Individual memory text is capped at 2000 characters and the worker-facing
output is hard-capped at 6,000 characters. A blank query is rejected so a
routine status/report request cannot flood model context.

## Report contract

Each report contains:

- compact memory findings with `id`, state, scope, text, and evidence pointers;
- matching provenance records with report paths and bounded evidence pointers;
- `service_status`, which is `PROVEN` only when the canonical local inputs
  validate;
- `integration_status`, which remains `NOT_PROVEN` until a live ChatGPT-web
  call is actually observed;
- a deterministic `receipt` containing `report_id`, a combined corpus SHA-256,
  and byte/hash records for `memory/memory-bank.jsonl`, `memory/sources.json`,
  and `provenance.json`.

The report never treats memory as current authority: current user instruction
and live evidence outrank recalled entries. Rejected and superseded entries are
hidden from ordinary recall and are returned only when `--history` is explicit.
The provenance layer returns pointers, not transcript contents.

## Least privilege

`memory_report.py` has no write path, subprocess, network, download, import, or
arbitrary-file argument. It resolves its three canonical inputs relative to the
repository checkout and rejects absolute/traversal provenance paths. Query,
scope, tag, entry, and output bounds are enforced in code. The local report is
therefore safe to invoke through the existing shell-mcp's process/read route;
the shell-mcp repository itself remains unchanged.

The current route is observed locally at `http://127.0.0.1:3000/health` and
through the OAuth-gated public Funnel at `https://kone.tailbf0440.ts.net/health`.
Those health observations do not prove that ChatGPT web has called this
repository workflow; the CLI deliberately reports `NOT_PROVEN` for that claim
until such a call is observed.
