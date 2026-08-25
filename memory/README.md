# Shared Memory Bank

This directory is the lightweight shared continuity layer for Regression Research and cooperating agents.

`memory-bank.jsonl` is append-only semantic history. Each line is one compact fact, decision, lesson, preference, status, or correction. Evidence belongs behind pointers rather than embedded transcripts or logs.

Current user instruction and live evidence always outrank recalled memory. A missing or unreachable bank is not a bootstrap failure; continue from current context and applicable policy. Ordinary corrections append a new entry and reference older entry IDs in `supersedes`; committed historical entries are not silently rewritten.

States are `PROVEN`, `PROVISIONAL`, and `REJECTED`. Ordinary recall must exclude rejected and superseded entries unless history is explicitly requested.

No credentials, secrets, full transcripts, huge tool output, or volatile process snapshots belong here. Regression Research reports/evidence remain the forensic source when deeper provenance is required.
