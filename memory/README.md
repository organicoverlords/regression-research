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

`context` uses the same validated retrieval path but applies a hard prompt budget and separates durable notes from historical conversation evidence. PROVISIONAL and stored `status` matches are omitted from the default durable section; they remain available through explicit `search --history`. Historical frequency and excerpts are always advisory evidence, never authority. This is the preferred compact handoff surface when product-level ChatGPT memory/history is disabled.

Inspect historical/rejected/superseded entries:

```powershell
python tools\memory_bank.py search "6KB threshold" --scope mcp --history
```

Glance at the bounded recent-title startup window (current entries only):

```powershell
python tools\memory_bank.py recent-titles
```

This returns at most 10 titles by default (hard cap 20), newest first, without dumping memory bodies. Use it as a cheap hint window when starting repo work or routing targeted recall; it is not authority and does not replace live repo/runtime inspection or targeted semantic recall. Rejected and superseded entries are excluded just like ordinary recall. Existing entries derive a stable display title from bounded text; new entries may optionally supply `--title`.

Assistant-authored durable writes use the single provenance-preserving `record` command. It requires the verbatim user source message plus a separate assistant interpretation and confidence rationale; this prevents a second free-form write path from bypassing provenance.

New writes should set `--project` when a memory belongs to one project. Time-bounded facts/instructions may set `--expires-at <ISO-8601-with-offset>`; expired entries stay available to explicit history but are automatically excluded from ordinary recall, recent titles, and hybrid retrieval. Stored `status` entries are also excluded from the default task context so live state is re-read instead of inherited.

These are ordinary repository commands. MCP/local workers may invoke them when they have repo access, but MCP availability is not part of the memory contract.

## Legacy behavior provenance metadata

Older records and registries preserve which statements were historically treated as behavior rules or policy. That metadata is retained for forensic reconstruction and regression research only; it no longer makes Vault records runtime ChatGPT behavior authority. Current conversation and ChatGPT Memory provide ChatGPT continuity, while shared/repo policy governs repository work.

Do not automatically promote or load Vault records into live behavior. Use targeted recall when history is relevant, and let current user instruction and verified live state override remembered material.

## Shared continuity and timeline views

The Vault is a shared knowledge surface, not a second coordinator. Orchestrators and workers read the same canonical memory and derived views concurrently. Read commands (`recent`, `search`, `context`, `timeline`) are local, side-effect free, and do not claim BUSY/ownership, create queues, or require a daemon. The existing external coordinator remains the ownership/control plane for work; timeline/context tools never replace it.

Inspect chronology directly:

```powershell
python tools\memory_bank.py timeline --view general --with-all --days 7
python tools\memory_bank.py timeline --view project --project p3 --with-all --days 7
python tools\memory_bank.py timeline --view errors
```

The timeline is the canonical derived continuity chronology, not another journal. Vault records retain meaning, state, evidence, supersession, and explicit incident/thread membership. `--with-all` merges the other bounded local evidence surfaces into that same chronology: all-branch Git commits/ref decorations for the known repos, immutable timed and manual worker-report history, and Git-tracked Vault artifacts from `01 Reports`, `02 Evidence`, `03 Fixtures and Experiments`, `04 Operating Contracts`, and `90 Raw Transcripts`. Evidence form and event meaning are separate: a preserved item may be a report, evidence file/log, screenshot, proof, fixture, contract, transcript, memory, commit, or worker report, while its continuity case may independently carry incident, regression, slopwall, or security-incident traits plus RED severity. `provenance.json`, explicit incident IDs/threads, report/proof paths, and other strong anchors join observations into one continuity case; broad GitHub issue references corroborate but do not by themselves merge continuity cases. Untracked WIP is deliberately not promoted into durable history merely because a file exists.

Every general/project timeline report also contains cumulative **24h / 3d / 7d snapshots** over the same merged event stream. The 24h snapshot gets the richest highlights; 3d highlights come only from the 24h-72h slice and 7d highlights from the 72h-168h slice so startup does not repeat the same newest events three times. Snapshots report raw observation/source counts, unique preserved artifacts by evidence form, signal-observation counts, and stronger unique continuity-case counts. A legacy label fallback exists only for old records that predate structured tags/provenance and is marked as inferred; incidental body prose is not allowed to create a case. Source diversity and shared broad anchors are corroboration evidence only: they are not independent-witness proof, current-state authority, case identity, or causal inference. Bounded repo/artifact collectors expose saturation/coverage so a capped count is treated as a lower bound rather than an exhaustive claim. Malformed external event timestamps are skipped and counted instead of breaking the whole chronology.

Worker events remain lagging self-report evidence, not current-state/liveness authority; `--no-workers` suppresses them when needed. Git commits and artifact changes are never automatically promoted into memory or interpreted as fixes/causes merely because titles or filenames contain words such as `fix`, `error`, or `incident`.

New durable/event writes may optionally supply `--event-at <ISO-8601-with-offset>` when the event occurred earlier than it was recorded and `--thread <stable-id>` when an explicit cross-scope relationship is known. Otherwise chronology falls back to the record timestamp and conservative specific-scope grouping. Broad scopes do not imply one incident. A single unambiguous GitHub issue/PR or `INC-...` evidence anchor may also join incident chronology automatically; multiple conflicting anchors deliberately abstain rather than guessing.

`overview` exposes bounded `incident_rollups` for recurring incident threads and can attach the compact 24h/3d/7d timeline snapshots for startup. Rollups retain the observation count, latest durable finding, source memory IDs for drill-down, and a timeline command; they do not delete or rewrite member records. `bootstrap-glance` strips rollup member IDs, suppresses duplicate recent titles, and byte-bounds the whole memory/timeline orientation. The startup memory budget is **3,800 compact JSON bytes** so the canonical timeline can retain richer 24h evidence plus at least bounded 3d/7d context without returning to an unbounded bootstrap. Under byte pressure the canonical timeline snapshot is prioritized over generic project/tag/recent summaries, with the 24h examples retained longest. Rollups and snapshots remain historical evidence only and never become current runtime truth or behavior authority through repetition.

The normal continuity path has **no full-conversation download dependency**. Current work is distilled into Vault records as it happens. The preserved full-conversation corpus is legacy/forensic evidence only and is consulted only through explicit history retrieval; its absence or age must not block startup, project work, error recurrence lookup, or timeline construction.

## Durability and GitHub mirror

A successful canonical memory write is not fully handed off until the dedicated GitHub mirror `origin/memory/live` contains it. Canonical **writes** reconcile with that non-protected branch automatically: entries are merged by immutable memory ID, remote-only entries are pulled into the local bank, and local-only entries are published through an isolated memory-only commit. Canonical reads intentionally do not fetch, reconcile, claim, or mutate anything; they read the local snapshot and degrade locally. Unrelated dirty files and unrelated local branch commits are never staged into a synchronization commit.

Canonical `record` operations run under a bounded local sync lock, reconcile before writing, then publish after writing. That lock protects atomic file/Git reconciliation only; it is not task ownership, a worker lease, or a second coordinator. `main`, `master`, `dev`, and `develop` are forbidden publication targets. If the dedicated `memory/live` mirror has been deleted, the writer recreates it from current `origin/main` and then merges the local bank before publishing, so branch cleanup does not permanently disable durable recording. A racing mirror update is fetched and retried without overwriting either side. If the local append succeeds but GitHub publication cannot be proven, the command fails visibly with an explicit `local memory was saved` message; do not append a duplicate. Any later canonical write/sync retries pending reconciliation.

A GitHub-only worker that needs the newest Vault memory should read `memory/memory-bank.jsonl` from `memory/live`; `main` is integration history and may lag the dedicated memory mirror. Before changing the bank through GitHub, preserve append-only history and use a named branch/PR rather than pushing a protected integration branch directly. The next canonical local reconciliation imports remote-only mirror entries automatically.

If a GitHub-only worker cannot prove the mirror is current, **do not replace or reconstruct the bank from GitHub**. Preserve new information as an append-only timestamped file under `memory/reports/` (or another explicitly pending append-only artifact), record which canonical memory it should join, and let the next local reconciliation merge it safely. A stale mirror is a durability gap, not permission to discard unseen local history and not a reason to stop the active task.

## Source relevance and recall budget

Recall is relevance-first. Source provenance weight may only reorder entries that already match the query, scope, or tags; it must never cause unrelated high-authority memories to surface.

Source classes are ranked in `sources.json`: current user instruction, live canonical policy, verified evidence, durable memory/personal context, historical context, then recovery-only material. Old seeds/backups remain searchable history but do not compete as current truth against canonical or verified sources.

Ordinary `search` is intentionally narrow: blank unscoped searches return no entries, the default is 5 results, and the hard maximum is 8. Explicit `search --history` may expand to at most 20 entries. Individual entries are bounded to 2000 text characters, 12 tags, 16 evidence pointers, and 16 supersession pointers. Broader context requires an explicit follow-up search rather than one accidental dump.

## Classification and normalization

Every bank/candidate record can be classified through the bounded deterministic taxonomy documented in [`docs/memory-normalization.md`](../docs/memory-normalization.md). The classifier derives semantic category, primary domain, project/role/entity labels, durability, sensitivity and review reasons without changing claim state or authority. Project/role inference uses descriptors only; a project name mentioned only in the body does not silently re-scope a record.

Ordinary recall excludes records classified as historical, ephemeral, expired or strongly sensitive, while explicit `search --history` preserves their evidence trail. `PROVISIONAL` remains explicit review work. New writes auto-fill `project` only when exactly one descriptor project can be inferred safely; explicit `--project` wins.

Classify one bank record incrementally with `python tools\memory_classification.py --bank memory\memory-bank.jsonl --id <memory-id>`. The completed #87 exhaustive normalization receipts remain preserved under `02 Evidence/` as historical acceptance evidence; current operation does not regenerate them.
