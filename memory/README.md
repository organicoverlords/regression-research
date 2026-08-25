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
