# Initial memory population acceptance

Issue #18 records the first ranked population pass over the compact memory
bank. The pass is intentionally bounded: it uses only prepared candidate and
curated JSONL from this repository, preserves evidence as pointers, and leaves
ambiguous claims `PROVISIONAL` rather than promoting them automatically.

## Evidence and report

The durable inputs are:

- `memory/migrations/2026-08-25-population-candidates.jsonl` — extracted,
  bounded candidates;
- `memory/migrations/2026-08-25-population-curated.jsonl` — the reviewed pass;
- `memory/migrations/2026-08-25-population-audit.jsonl` — per-candidate
  migration decisions; and
- `memory/memory-bank.jsonl` — the append-only canonical bank.

Run the read-only acceptance report from the repository root:

```powershell
python tools\memory_population.py --format text
python tools\memory_population.py --format json --output memory\reports\2026-08-25-population-acceptance.json
```

The report gives exclusive record counts by primary source, authority class,
kind, and state (and separately shows all source-pointer matches); duplicate
and supersession statistics; and a fixed recall matrix. The matrix covers
all-caps rules/corrections, MCP safety-routing history, anti-churn behavior,
P3 fleet convergence, prior project status, shared policy changes, and rejected
historical theories. Ordinary recall is checked against the five-result
default and eight-result hard cap; history is checked against the twenty-result
hard cap, and rejected/superseded claims must stay hidden from ordinary recall.

The current local result is `PROVEN`: 18 entries before the pass, 32 after it,
14 candidates and 14 curated records, with three provisional claims retained
as provisional. The local service/report is proven by repository validation;
ChatGPT-web exposure remains `NOT_PROVEN` until an actual live WebGPT tool call
is observed.

## Scope boundary

This report is a local read-only CLI. It does not download, import raw
transcripts, start an MCP server, add MCP tools, or change the existing
WebGPT/shell-MCP transport. Rich incident reports remain in `01 Reports/` and
the provenance index; the bank stores compact claims and evidence pointers.
