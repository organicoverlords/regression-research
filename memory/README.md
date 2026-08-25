# Shared Memory Bank

This directory is the lightweight shared continuity layer for Regression Research and cooperating agents.

`memory-bank.jsonl` is append-only semantic history. Each line is one compact fact, decision, lesson, preference, status, or correction. Evidence belongs behind pointers rather than embedded transcripts or logs.

Current user instruction and live evidence always outrank recalled memory. A missing or unreachable bank is not a bootstrap failure; continue from current context and applicable policy. Ordinary corrections append a new entry and reference older entry IDs in `supersedes`; committed historical entries are not silently rewritten.

States are `PROVEN`, `PROVISIONAL`, and `REJECTED`. Ordinary recall must exclude rejected and superseded entries unless history is explicitly requested.

No credentials, secrets, full transcripts, huge tool output, or volatile process snapshots belong here. Regression Research reports/evidence remain the forensic source when deeper provenance is required.

## Commands

Validate the bank:

```powershell
python tools\memory_bank.py validate
```

Search ordinary current memory (rejected/superseded entries hidden):

```powershell
python tools\memory_bank.py search "MCP safety blocks" --scope mcp
```

Inspect historical/rejected/superseded entries:

```powershell
python tools\memory_bank.py history "6KB threshold" --scope mcp
```

Append one compact entry:

```powershell
python tools\memory_bank.py append --kind lesson --scope p3 --tag fleet --tag convergence --text "Validated work must converge or retire." --state PROVEN --evidence "github:organicoverlords/p3#528"
```

These are ordinary repository commands. MCP/local workers may invoke them when they have repo access, but MCP availability is not part of the memory contract.

## Source relevance and recall budget

Recall is relevance-first. Source authority may only reorder entries that already match the query, scope, or tags; it must never cause unrelated high-authority memories to surface.

Source classes are ranked in `sources.json`: current user instruction, live canonical policy, verified evidence, durable memory/personal context, historical context, then recovery-only material. Old seeds/backups remain searchable history but do not compete as current truth against canonical or verified sources.

Ordinary `search` is intentionally narrow: blank unscoped searches return no entries, the default is 5 results, and the hard maximum is 8. Explicit `history` may expand to at most 20 entries. Individual entries are bounded to 800 text characters, 12 tags, 16 evidence pointers, and 16 supersession pointers. Broader context requires an explicit follow-up search rather than one accidental dump.

## Candidate extraction

Prepare compact candidate records from bounded source snippets with python tools\extract_memory_candidates.py <sources.jsonl> <candidates.jsonl>. Source snippets declare source_id, source_class, scope, 	imestamp, evidence, and content. The extractor recognizes corrections, decisions, lessons, status receipts, explicit RULE: lines, and standalone ALL-CAPS rules. Extracted claims remain PROVISIONAL until curation; extractor-only provenance fields are removed when candidates are migrated into the strict bank schema.
