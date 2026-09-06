# Regression Research #125 - timeline convergence research

Date: 2026-09-06 EEST
Scope: read-only serving evidence plus isolated current origin/main. No active-owner implementation file or serving checkout was modified.

## Isolation and owner boundary

- Bootstrap was run first from the live Vault checkout.
- Serving checkout was inspected read-only at ffb68e1ecf929116f7300b13baf5ba0e5827761d and was 76 commits behind origin/main during the audit.
- Research worktree baseline was origin/main 54d5c759e357103e801e9be4f36333c350efec31.
- Active implementation owner reported on #125: vault-125-timeline-ingest-graph-20260906, owning dirty memory_bank.py, memory_timeline.py, repo_timeline.py, stack_atlas.py, plus timeline_materializer.py and its test. None were modified here.

## Measured bootstrap and collector cost

Live startup bootstrap internal elapsed in this run: 2257.3 ms.

Forced-cache-miss independent stage samples on current-main code:

| Stage | Wall time | Count evidence |
| --- | ---: | --- |
| PC telemetry | 31.41 ms | local memory/disk/GPU probes |
| Worker status | 94.36 ms | 16 historical worker IDs; 107 manual-current files; bounded scan 64 |
| MCP status | 52.93 ms | 1,887 JSONL rows / 786,432 B; 12 sessions observed |
| Memory/timeline overview | 2,154.14 ms | 203 eligible entries; 3 snapshot windows |
| Vault status | 41.36 ms | 1 Git subprocess; memory bank 466,926 B |
| GitHub status | 446.80 ms | 1 bounded gh api rate_limit call |
| MCP freeze record | 0.33 ms | 1 JSON record |

Cold parallel bootstrap profile: 2275.08 ms total; memory/timeline stage 2268.56 ms, so it set the critical path in that sample. Concurrent stage times must not be summed.

Independent timeline measurements:

- Memory bank parse: 8.74 ms, 339 entries, 466,926 B in isolated current-main. Live bank: 352 entries / 492,708 B in 8.81 ms.
- Repo discovery: 1.26 ms, four repos: lowvram, tiny3d, p3, vault.
- Repo history at 100 events/repo: 797.21 ms, 400 events, 12 Git subprocesses, 781.79 ms summed Git wall, 59,107 stdout B / 408 lines.
- Seven-day repo repeats: 788.37 / 942.53 / 843.41 ms, 398 events each.
- Artifact history without a date bound at a 240-event cap: 3208.98 ms. The path-filtered Vault git log --all --date-order --max-count=240 --name-status was 3121.58 ms alone.
- Seven-day artifact repeats: 357.90 / 380.29 / 348.15 ms, 240 events each.
- Timeline linking/snapshot assembly over 339 memory + 398 repo + 240 artifact events: 419.85 ms, 977 matching events.
- Timed worker archive from live read-only evidence: 229 JSON / 1,236,598 B -> 217 events; metadata load 40.47 ms; event projection 40.21 ms.
- Manual worker archive: 156 JSON / 847,404 B -> 154 events; metadata load 22.64 ms; event projection 29.52 ms.

Actual seven-day timeline cost ordering: repo Git history > artifact Git history > timeline assembly. Worker archive parsing and memory-bank parsing are not leading costs at current cardinality.

A parallel #125 research run posted at 05:28 EEST independently measured repo history 710.1 ms, artifacts 385.3 ms, timeline assembly 359.8 ms, and about 59 ms total worker archive parsing. Absolute walls differ with cache/I/O state, but the cost ordering agrees.

Important input-location edge: the isolated source checkout contains no immutable worker-history JSON corpus. Clean-tree collection therefore yields zero worker events unless pointed at the live read-only archive roots or a materialized copy. This is an input-location fact, not a liveness statement.

## Safe materialization / invalidation identities

These are requirements for the materializer already owned by the active implementation branch, not a new cache/control system.

### Repo history

Current collector uses git log --all, so HEAD alone is unsafe. Source identity should cover:

- collector/schema version;
- repo identity;
- HEAD OID, including detached HEAD;
- digest of sorted all refs as (refname, OID);
- origin URL, because event anchors depend on it;
- shallow/graft/replace state where present;
- resolved since/limit only if caching a bounded view rather than a reusable source stream.

Ref creation, deletion, or force-push can change --all history with HEAD unchanged. Working-tree dirtiness is not an input to the current Git-history collector.

### Worker archives

Timed and manual populations need separate keys. Safe incremental identity is directory membership plus JSON content identity. Filename alone is insufficient because it addresses report identity while derived metadata affects chronology and manual run_id dedupe.

Efficient safe check: manifest (name, size, mtime_ns) to find add/remove/change candidates, then content-hash only new or changed JSON. Any removal/change invalidates the population.

### Tracked artifacts

Safe key = Vault repo-history identity above + provenance content hash + artifact roots + collector/schema. Git refs may stay unchanged while provenance changes incident ID, title, evidence type, or anchors.

### Memory

Robust key = collector/classification schema + bank content hash. Safe incremental form is retained prefix hash + prior byte length + parsed suffix; shrink or prefix mismatch forces full rebuild. Newest timestamp/ID alone is unsafe because later supersede/reject records can change active counts while preserving prior evidence.

Memory parsing is only about 9 ms at current size, so correctness dominates optimization here.

## Query-quality acceptance corpus

The expected links below are historical evidence, not current-state authority.

### P3 RAM / paging pressure

Question family: P3 RAM paging pressure pagefile runners

Expected linked events:
- mem-20260825-7e943f4c: 92% CPU / 86% physical RAM with nine runners/P3 build trees.
- mem-20260826-a24f548c: 2.5 GB holds/moderate paging did not reproduce MCP failure.
- Current #296 paging/build-pressure work, including worker c083a440... and P3 commits 3189384e and b214a021.

Acceptance guard: pressure observed must not become pressure proven causal.

Observed current-query failure from the parallel audit: 415 matches; mem-...7e943f4c ranked 412; mem-...a24f548c missed; generic recent P3 commits dominate false positives.

### CI / proof capture

Question family: CI proof capture screenshot reviewed visual

Expected linked events:
- mem-20260904-1bfc720f: unified pictures/videos/captures and avoidance of wrong screenshots/build-queue churn.
- mem-20260827-f9d7a1f5: rendered-frame acceptance.
- Canonical L3 proof commit 5e9eb364... / P3 #1863 plus related proof worker evidence.
- Current proof-stack history should distinguish imported animation fidelity, live playback advancement, rendered temporal motion, and independent reviewed-evidence CI acceptance.

Observed failure: 348 matches; #1863 ranked 1; mem-...f9d7a1f5 ranked 159; mem-...1bfc720f missed. Generic live-proof/timeline-taxonomy records are obvious noise.

### MCP regression history

Question family: MCP regression reconnect token reroute

Expected linked events:
- mem-20260904-0b8acbf6 plus the 03:07 reconnect/token-burst report from the logs/anomalies debugging history.
- mem-20260902-da39b1b0: runtime-contract regression.
- mem-20260906-ccece36a: batching-policy RED correction.
- Later restore-first/known-good evidence only when the query asks for recurrence/recovery.

Acceptance guard: a platform reroute observed with no MCP request in flight must not be promoted into a new MCP-local fault without MCP-local evidence.

Observed failure: 595 matches; relevant memories ranked roughly 224 / 289 / 22 while generic Vault timeline commits appeared near the top.

### Cross-branch worker convergence

Question family: branch worker convergence worktree merge main

Expected linked events:
- mem-20260904-33a24173 and mem-20260904-cb38ce61: agent work must converge / branches do not just stack up, with cross-repo Git anchors.
- mem-20260825-p3-convergence.

Observed failure: 438 matches; expected memories ranked about 300 / 301 / 436. Ordinary merge commits and generic current worker reports dominate false positives.

Two evidenced miss mechanisms: important terms can live in memory body/source-message fields that are not query surfaces, and broad token-OR matching lets high-frequency terms such as p3, merge, worker, and mcp swamp the intended lineage.

## Dirty serving Vault classification vs origin/main

No reset, rebase, clean, overwrite, or serving mutation was performed.

### Already upstream / no semantic delta

- memory/README.md
- tests/test_memory_git_sync.py
- tests/test_memory_recent_titles.py
- tests/test_memory_timeline.py
- tests/test_repo_timeline.py
- tools/memory_bank.py
- tools/memory_git_sync.py
- tools/memory_timeline.py
- tools/repo_timeline.py
- tests/test_memory_worker_findings.py

These should not be transplanted during convergence.

### Unique and must preserve

- memory/memory-bank.jsonl: live append-only records beyond current main; parallel audit verified the extra records are mirrored on origin/memory/live.
- 02 Evidence/mcp-security-routing-events.jsonl: current-main baseline plus unique live events; preserve the live-only tail.
- 01 Reports/2026-09-06_0204_EEST_MCP_log_retention_regression.md
- 01 Reports/2026-09-06_0346_EEST_RED_ALERT_unproven_MCP_batching_ban_regression.md

### Mixed

- 04 Operating Contracts/fresh-worker-generation-launch.md: preserve/review the one local-only route-recovery invariant: refresh/re-discover bindings; route failure is not capability/task failure; never administer workers because of route failure. The rest is stale against current-main and must not be copied wholesale.

### Obsolete against current main

- docs/assistant-stack-operational-atlas.md
- tools/stack_atlas.py
- tests/test_stack_atlas.py
- tools/worker_report_history.py
- tests/test_worker_report_history.py
- untracked tests/test_bootstrap_health.py
- untracked 04 Operating Contracts/mcp-known-good-freeze.json

These contain older or contradictory semantics already superseded upstream and should not be preserved as units.

### Unknown; preserve until isolated review

- tests/test_memory_bootstrap.py: local-only worker/collision assertions with no direct current-main matching strings.
- Saved/Verification/P3VerificationTooling.json: unique generated Python-route receipt; no current-main consumer/reference established by the bounded audit.

## Convergence plan only

1. Leave the serving checkout frozen.
2. In a separate current-main reconciliation worktree, reconcile only the unique set, the exact mixed route-recovery hunk, and the two unknowns for provenance review.
3. Do not copy already-upstream or obsolete files.
4. Validate unknown provenance and durably preserve unique evidence first.
5. Only after preservation is proven should the serving checkout be advanced/replaced through the existing production-change boundary.

No daemon, sync scheduler, second policy store, or new timeline/control system is justified by this evidence.

## Exact handoff to active timeline owner

Keep ownership of the existing timeline_materializer.py implementation. Smallest next slice:

1. Add source-fingerprint/invalidation coverage for repo, artifacts, timed/manual worker archives, and memory using the identities above.
2. Skip unchanged source ingestion without changing canonical timeline semantics.
3. Run the four acceptance queries above against the materialized reader and record expected links/noise before changing ranking behavior.
4. Do not absorb serving-checkout convergence, contract cleanup, or new policy into that implementation slice.

The comprehensive parallel findings are already on regression-research #125, comment 5556355741. This file persists the handoff in Vault and adds independent profiling from this run.
