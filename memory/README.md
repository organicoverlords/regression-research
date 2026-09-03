# Shared Memory Bank

This directory is a searchable shared history/notebook/evidence layer for Regression Research and cooperating agents. It enhances memory and reconstruction but is not a startup gate or runtime behavior authority.

`memory-bank.jsonl` is append-only semantic history. Each line is one compact fact, decision, lesson, preference, status, or correction. Evidence belongs behind pointers rather than embedded transcripts or logs.

Current user instruction and live evidence always outrank recalled memory. A missing or unreachable bank is ordinary optional-context loss; continue from the current conversation, ChatGPT/harness memory, applicable policy, Atlas, and live sources. Ordinary corrections append a new entry and reference older entry IDs in `supersedes`; committed historical entries are not silently rewritten.

States are `PROVEN`, `PROVISIONAL`, and `REJECTED`. Ordinary recall must exclude rejected and superseded entries unless history is explicitly requested.

No credentials, secrets, huge tool output, or volatile process snapshots belong in `memory-bank.jsonl`. Historical full transcripts live separately in the private Git-ignored `memory/conversations/` corpus so they remain searchable without bloating curated memory.

## Commands

Validate the bank:

```powershell
python tools\memory_bank.py validate
```

Search ordinary current memory and matching preserved historical conversation turns (rejected/superseded curated entries hidden):

```powershell
python tools\memory_bank.py search "MCP safety blocks" --scope mcp
```

Build a task-scoped context pack for an assistant turn without dumping the whole bank:

```powershell
python tools\memory_bank.py context "p3 orchestrator: work on P3"
```

Add `--with-history` only when the task actually needs preserved full-conversation evidence. The default context path stays on the curated bank and does not fan out into the raw conversation corpus.

`context` uses the same validated retrieval path but applies a hard prompt budget and separates durable notes from historical conversation evidence. PROVISIONAL and stored `status` matches are omitted from the default durable section; they remain available through explicit `search`/`history`. Historical frequency and excerpts are always advisory evidence, never authority. This is the preferred compact handoff surface when product-level ChatGPT memory/history is disabled.

Inspect historical/rejected/superseded entries:

```powershell
python tools\memory_bank.py history "6KB threshold" --scope mcp
```

Glance at the bounded recent-title startup window (current entries only):

```powershell
python tools\memory_bank.py recent-titles
```

This returns at most 10 titles by default (hard cap 20), newest first, without dumping memory bodies. Use it as a cheap hint window when starting repo work or routing a quick note; it is not authority and does not replace live repo/runtime inspection or targeted semantic recall. Rejected and superseded entries are excluded just like ordinary recall. Existing entries derive a stable display title from bounded text; new entries may optionally supply `--title`.

Append one compact entry:

```powershell
python tools\memory_bank.py append --kind lesson --scope p3 --project p3 --tag fleet --tag convergence --text "Validated work must converge or retire." --state PROVEN --evidence "github:organicoverlords/p3#528"
```

New writes should set `--project` when a memory belongs to one project. Time-bounded facts/instructions may set `--expires-at <ISO-8601-with-offset>`; expired entries stay available to explicit history but are automatically excluded from ordinary recall, recent titles, hybrid retrieval, and behavioral authority. Stored `status` entries are also excluded from the default task context so live state is re-read instead of inherited.

These are ordinary repository commands. MCP/local workers may invoke them when they have repo access, but MCP availability is not part of the memory contract.

## Legacy behavior provenance metadata

Older records and registries preserve which statements were historically treated as behavior rules or policy. That metadata is retained for forensic reconstruction and regression research only; it no longer makes Vault records runtime ChatGPT behavior authority. Current conversation and ChatGPT Memory provide ChatGPT continuity, while shared/repo policy governs repository work.

Do not automatically promote or load Vault records into live behavior. Use targeted recall when history is relevant, and let current user instruction and verified live state override remembered material.

## Shared continuity and timeline views

The Vault is a shared knowledge surface, not a second coordinator. Orchestrators and workers read the same canonical memory and derived views concurrently. Read commands (`recent`, `search`, `context`, `orient`, `timeline`) are local, side-effect free, and do not claim BUSY/ownership, create queues, or require a daemon. The existing external coordinator remains the ownership/control plane for work; timeline/context tools never replace it.

Build an optional historical/project orientation from curated memory plus whatever canonical local Git repositories are available:

```powershell
python tools\memory_bank.py orient
```

`orient` uses `operator-live.json` only as an optional repository-path registry. Commit events are read directly from each local Git object database; dashboard `recent_progress` is not accepted as commit evidence. Missing repos degrade independently instead of blocking orientation. Mainline (`origin/main`) commits and unmerged lane commits are labeled separately so swarm activity stays visible without being mistaken for landed state.

Inspect chronology directly:

```powershell
python tools\memory_bank.py timeline --view general --with-repos
python tools\memory_bank.py timeline --view project --project p3 --with-repos
python tools\memory_bank.py timeline --view errors
```

The timeline is a derived projection, not another journal. Vault records retain meaning, claim state, evidence, supersession, and explicit incident/thread membership; local Git contributes observed commit chronology. General/project views also merge immutable finalized worker-report history by default and expose the current 24-hour `worker_metrics` summary (run duration, 24-minute target utilization, worker-minutes, short-run count, normalized stop reasons, unexplained early stops, pending-gate classes, tool-drop impact, and latest per-worker metrics). These worker events remain lagging self-report evidence, not current-state/liveness authority; `--no-workers` suppresses them when needed. Git commits are never automatically promoted into memory or interpreted as fixes/causes merely because their titles contain words such as `fix` or `error`.

New durable/event writes may optionally supply `--event-at <ISO-8601-with-offset>` when the event occurred earlier than it was recorded and `--thread <stable-id>` when an explicit cross-scope relationship is known. Otherwise chronology falls back to the record timestamp and conservative specific-scope grouping. Broad scopes do not imply one incident.

The normal continuity path has **no full-conversation download dependency**. Current work is distilled into Vault records as it happens. The preserved full-conversation corpus is legacy/forensic evidence only and is consulted only through explicit history retrieval; its absence or age must not block startup, project work, error recurrence lookup, or timeline construction.

## Durability and GitHub mirror

A successful canonical memory write is not fully handed off until GitHub `main` contains it. Canonical **writes** reconcile with `origin/main` automatically: entries are merged by immutable memory ID, remote-only entries are pulled into the local bank, and local-only entries are published through an isolated memory-only commit. Canonical reads intentionally do not fetch, reconcile, claim, or mutate anything; they read the local snapshot and degrade locally. Unrelated dirty files and unrelated local branch commits are never staged into a synchronization commit.

Canonical `note`, `append`, and `record` operations run under a bounded local sync lock, reconcile before writing, then publish after writing. That lock protects atomic file/Git reconciliation only; it is not task ownership, a worker lease, or a second coordinator. A racing `main` update is fetched and retried without overwriting either side. After a proven sync, a checkout that tracks `origin/main` is fast-forwarded when Git can preserve unrelated dirty work; the memory-only fallback advances the branch only when the working bank exactly matches the remote result, so a successful write does not normally leave the canonical checkout one commit behind or the bank spuriously dirty. If the local append succeeds but GitHub publication cannot be proven, the command fails visibly with an explicit `local memory was saved` message; do not append a duplicate. Any later canonical CLI call retries pending reconciliation.

A GitHub-only worker may read the bank directly from `main`. Before changing `memory-bank.jsonl` through GitHub, it must start from current `main`, preserve append-only history, and merge the coherent memory-only change promptly rather than leaving it stranded on a worker branch. The next canonical local CLI call imports remote-only entries automatically.

If a GitHub-only worker cannot prove the mirror is current, **do not replace or reconstruct the bank from GitHub**. Preserve new information as an append-only timestamped file under `memory/reports/` (or another explicitly pending append-only artifact), record which canonical memory it should join, and let the next local reconciliation merge it safely. A stale mirror is a durability gap, not permission to discard unseen local history and not a reason to stop the active task.

## Source relevance and recall budget

Recall is relevance-first. Source authority may only reorder entries that already match the query, scope, or tags; it must never cause unrelated high-authority memories to surface.

Source classes are ranked in `sources.json`: current user instruction, live canonical policy, verified evidence, durable memory/personal context, historical context, then recovery-only material. Old seeds/backups remain searchable history but do not compete as current truth against canonical or verified sources.

Ordinary `search` is intentionally narrow: blank unscoped searches return no entries, the default is 5 results, and the hard maximum is 8. Explicit `history` may expand to at most 20 entries. Individual entries are bounded to 2000 text characters, 12 tags, 16 evidence pointers, and 16 supersession pointers. Broader context requires an explicit follow-up search rather than one accidental dump.

## Classification and normalization

Every bank/candidate record can be classified through the bounded deterministic taxonomy documented in [`docs/memory-normalization.md`](../docs/memory-normalization.md). The classifier derives semantic category, primary domain, project/role/entity labels, durability, sensitivity and review reasons without changing claim state or authority. Project/role inference uses descriptors only; a project name mentioned only in the body does not silently re-scope a record.

Ordinary recall excludes records classified as historical, ephemeral, expired or strongly sensitive, while explicit `history` preserves their evidence trail. `PROVISIONAL` remains explicit review work. New writes auto-fill `project` only when exactly one descriptor project can be inferred safely; explicit `--project` wins.

Classify one bank record incrementally with `python tools\memory_classification.py --bank memory\memory-bank.jsonl --id <memory-id>`. The completed #87 exhaustive normalization receipts remain preserved under `02 Evidence/` as historical acceptance evidence; current operation does not regenerate them.

## Candidate extraction

Prepare compact candidate records from bounded source snippets with python tools\extract_memory_candidates.py <sources.jsonl> <candidates.jsonl>. Source snippets declare source_id, source_class, scope, \timestamp, evidence, and content. The extractor recognizes corrections, decisions, lessons, status receipts, explicit RULE: lines, and standalone ALL-CAPS rules. Extracted claims remain PROVISIONAL until curation; extractor-only provenance fields are removed when candidates are migrated into the strict bank schema.
