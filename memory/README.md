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

The Vault is a shared knowledge surface, not a second coordinator. Orchestrators and workers read the same canonical memory and derived views concurrently. `recent`, `search`, and `context` remain direct local reads. The canonical multi-source `timeline` normally reads a periodically materialized local projection under `.state/timeline/`; the expensive aggregation runs once in a Vault-owned scheduled task, not once per bootstrap/worker. The materializer is a batch job with an atomic lock, not a daemon, scheduler, ownership service, or control plane. If a scheduled refresh overlaps an already-running manual/scheduled refresh, lock contention is an intentional successful no-op rather than a scheduler failure; the owning refresh remains the only writer. The existing external coordinator remains the ownership/control plane for work; timeline/context tools never replace it.

Inspect chronology directly:

```powershell
python tools\timeline_materializer.py refresh
# Explicit one-time horizon backfill only when needed:
python tools\timeline_materializer.py refresh --rebuild
python tools\timeline_materializer.py task-status
python tools\timeline_materializer.py install-task --minutes 5
python tools\memory_bank.py timeline --view general --days 7
python tools\memory_bank.py timeline --view project --project p3 --days 7
python tools\memory_bank.py timeline --view errors
# Explicit diagnostic escape hatch only; this rescans sources synchronously:
python tools\memory_bank.py timeline --live-rebuild --with-all --days 7
```

The timeline is the canonical derived continuity chronology, not another journal. The materializer performs a horizon backfill only when the store is missing or when an operator explicitly uses `refresh --rebuild`. Normal periodic refreshes are **incremental**: every source keeps a last-success watermark, collectors request only the watermark minus a 10-minute overlap, stable event IDs de-duplicate the overlap, and unchanged historical observations are retained from the local store rather than reread. A saturated/erroring delta source keeps its older watermark so the missed interval is retried without forcing unrelated sources to rescan. If the initial horizon backfill was saturated, that **historical coverage debt persists across later clean delta refreshes** until a later explicit backfill actually closes it; a clean five-minute delta must never erase the fact that older history was only a lower bound. In that state timeline/overview/bootstrap expose `HISTORICAL_INCOMPLETE` and `NO_MATCH_IS_NOT_PROOF_OF_ABSENCE`. The same non-absence rule applies whenever the materialization is `STALE` or a source has a pending delta retry, because recent unseen evidence may exist even when the older backfill was otherwise complete. Vault records retain meaning, state, evidence, supersession, and explicit incident/thread membership. The periodic materializer aggregates a deeper default 30-day corpus from all-branch Git commits/ref decorations for known repos, immutable timed/manual worker-report history and efficiency fields, Git-tracked Vault artifacts, local-only/untracked report/evidence/proof observations (explicitly lower-authority), GitHub issues/PRs/Actions metadata, local self-hosted runner diagnostics, and bounded MCP front-door/process-receipt metadata. Raw secret-bearing command/log bodies are not copied into the timeline store. Evidence form and event meaning remain separate: a preserved item may be a report, evidence file/log, screenshot, proof, fixture, contract, transcript, memory, commit, worker report, issue, PR, action run, runner diagnostic, or MCP observation, while its continuity case may independently carry incident, regression, slopwall, or security-incident traits plus RED severity. `provenance.json`, explicit incident IDs/threads, report/proof paths, and other strong anchors join observations into one continuity case; broad GitHub issue references corroborate but do not by themselves merge continuity cases. Local-only artifact observations remain `LOCAL_WIP_ARTIFACT_OBSERVATION` and are never silently promoted to durable Git evidence.

Every general/project timeline report also contains cumulative **24h / 3d / 7d snapshots** over the same merged event stream. The 24h snapshot gets the richest highlights; 3d highlights come only from the 24h-72h slice and 7d highlights from the 72h-168h slice so startup does not repeat the same newest events three times. The narrative hierarchy is explicit and machine-readable: **continuity cases first, work graph second, evidence/observation density third, context-only corroboration last**. Raw event and signal-observation counts describe evidence density, not incident count. Broad GitHub issue/PR anchors are labeled `CONTEXT_ONLY` when they are not strong case anchors; consumers must not call such an anchor “the case” or “the thread,” even when many sources mention it. Snapshots retain stronger unique continuity-case counts and concrete case examples ahead of raw volume. A legacy label fallback exists only for genuinely unstructured old records that predate canonical tags/provenance and is marked as inferred; canonical assistant-recorded memories, worker reports with structured finding tags, structured non-incident artifact types, generic evidence filenames, repository names such as `Regression Research`, and incidental/negated prose are not eligible to create a signal case from words alone. Memory `semantic_category` is retrieval/content taxonomy rather than continuity-case authority: explicit signal tags/provenance (or the narrow legacy case fallback) own case promotion. The `errors` view remains a broader forensic-recall lane for genuinely unstructured old memory notes and may retrieve descriptive historical text without turning that retrieval match into a continuity case. Case-level provenance distinguishes `STRUCTURED`, `MIXED`, and `LEGACY_DEPENDENT`: a case is legacy-dependent only when one of its reported semantics (for example RED severity or a case trait) has no structured supporting observation. Merely containing an older legacy-derived observation makes the case `MIXED`, not legacy-dependent. Source diversity and shared broad anchors are corroboration evidence only: they are not independent-witness proof, current-state authority, case identity, or causal inference. Bounded repo/artifact collectors expose saturation/coverage so a capped count is treated as a lower bound rather than an exhaustive claim. Malformed external event timestamps are skipped and counted instead of breaking the whole chronology.

Worker events remain lagging self-report evidence, not current-state/liveness authority; `--no-workers` suppresses them when needed. Git commits and artifact changes are never automatically promoted into memory or interpreted as fixes/causes merely because titles or filenames contain words such as `fix`, `error`, or `incident`. The materialized **work graph** is separate from the incident/continuity-case graph: stable Git patch IDs identify exact equivalent changes across branches/rebases, while normalized-title fallback is allowed only for nearby branch/main activity or shared explicit work anchors. Worker reports, memories, proofs, PRs, Actions, MCP receipts, and runner evidence attach to work nodes through explicit SHA/PR/proof evidence. Worker duration/utilization and CI conclusions may be summarized per work node, but those metrics remain historical execution evidence rather than present worker liveness or causal proof.

New durable/event writes may optionally supply `--event-at <ISO-8601-with-offset>` when the event occurred earlier than it was recorded and `--thread <stable-id>` when an explicit cross-scope relationship is known. Otherwise chronology falls back to the record timestamp and conservative specific-scope grouping. Broad scopes do not imply one incident. A single unambiguous GitHub issue/PR or `INC-...` evidence anchor may also join incident chronology automatically; multiple conflicting anchors deliberately abstain rather than guessing.

`overview` exposes bounded `incident_rollups` **and reads the same materialized timeline orientation used by bootstrap**, so `overview`, `timeline <query>`, and `bootstrap-glance` share freshness, coverage, and absence semantics instead of presenting competing Vault views. Targeted timeline queries scope work-graph groups and similar-commit suggestions to the query/project/thread and return compact group details; the global graph totals remain separately labelled as store totals rather than masquerading as query matches. The materializer writes compact 24h/3d/7d snapshots plus a work-graph summary into `.state/timeline/bootstrap-memory-overview.json`. `bootstrap-glance` **only reads that small projection**; it never scans Git/GitHub, worker archives, reports, MCP logs, runner logs, or artifact history to rebuild the timeline. Freshness is explicit: the normal 5-minute materialization cadence becomes `STALE` after 15 minutes (three missed refresh windows), and missing/error state is surfaced rather than triggering a hidden rebuild. Bootstrap also surfaces stale materialization, historical coverage debt, or a delta retry as notable orientation conditions without falsely degrading otherwise healthy live components. The startup memory budget remains **3,800 compact JSON bytes**. Full history stays in `.state/timeline/timeline-store.json` for cheap filtered drill-down, while the startup projection retains richer 24h evidence plus bounded 3d/7d context. Rollups, snapshots, work-graph links, and efficiency summaries remain historical evidence only and never become current runtime truth or behavior authority through repetition; current diagnosis and mutation still require the owning live repo/runtime/scheduler/coordinator evidence.

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
