# Bootstrap, Vault, timeline and workflow audit — 2026-09-06

Work identity: regression-research #125. Observation window began 15:48 UTC.
This report records evidence and recommendations, not operating policy or current truth.

## Result and implemented fixes

The basic architecture is sound: bounded live bootstrap, targeted owner lookup, materialized history, exact mutation coordination, and separation of scheduler membership, activity and archival evidence. The largest problems found are inconsistent filtering, verification omissions, contradictory instructions and divergence between merged code and the serving checkout.

1. **Timeline graph filters were incomplete.** In the fetched main revision 872cb92, event filtering honored thread/date/errors/worker exclusion, but commit and similarity groups could come from the entire stored horizon. Continuity cases also ignored date and worker-exclusion filters. An unknown thread returned zero events alongside unrelated work groups. Five regression scenarios failed before the fix; all pass afterward. The reader now gates graph membership on events eligible under explicit filters, using project-qualified commit identities and attachment IDs. Topical matching still works afterward; an unfiltered overview remains available.
2. **The canonical verifier omitted timeline coverage.** tools/verify.py did not select an area for tools/timeline_materializer.py or its test module, and even its full memory suite did not execute those tests. Added the materializer to compilation/change selection and both timeline suites to execution, with verifier regressions for selection and actual inclusion.
3. **Obsolete skill removal was attempted, not completed account-wide.** The user explicitly requested removal of orchestration-reorientation and no further skill use. The seven tracked skill files were removed and committed locally, but the skill service rejected persistence with HTTP 422; a subsequent state check showed the original server-materialized revision and files restored. No account-wide removal is claimed. No skill was applied after the correction.

Validation: six focused filter tests (five red before implementation), all 28 combined timeline tests green, and the canonical repository verifier ended REPOSITORY_VERIFY_PASS. Its memory suite reported 147 passed plus three subtests; verifier and stack suites also passed. Validation was fixture-only and did not rebuild the live corpus.

The fix is isolated from the serving Vault tree. The two inspected existing query worktrees and the serving source contained foreign changes. Those changes were preserved. This report does not imply live activation.

## Priorities for smoother operation

### 1. Make serving convergence an explicit completion check

The live Vault root was on chatgpt/125-timeline-workgraph-sha-index-20260906 at 026676e, with dirty Stack Atlas and timeline files. The fetched main included the ranked reader while the live source still used its prior matching path. Issue #125 comments independently described the merged-versus-serving mismatch.

Use the existing issue and integration route to record: intended commit, actually serving code identity (include dirty-file hashes), and one live acceptance query. A Git HEAD alone cannot identify serving Python code when files are modified. Avoid another registry or worker. Keep the active owner's changes intact.

### 2. Resolve instruction contradictions, then shorten the canonical text

- The current user profile says workers never administer siblings. The live worker contract invariant 3 explicitly permits bounded sibling re-enable; commits d253bd8 and 87bc01f deliberately added that behavior on this date. This is a real contradiction between instruction surfaces, not evidence that those commits were accidental. I did not silently reverse a recently introduced policy.
- The manual contract requires a report immediately before the first tool call and archival immediately after the last tool call. Both operations themselves require tools. It also competes with bootstrap-first ordering. Replace the literal timing requirement with creation in the first permitted reporting action after bootstrap, and finalization in the final tool batch; describe timestamp precision honestly.
- The worker contract mandates rediscovery/retry before fallback when a route fails, while shared RULES permits another attempt only when changed evidence makes it discriminating. Keep one canonical retry rule and have the worker contract point to it.
- Shared AGENTS/RULES repeat task identity, dirty-work preservation, nonblocking continuation and stop conditions. Consolidate repeated wording without weakening protections. Keep incident-specific mechanics with their owners.

Do not change the explicitly retained timed >=80% guard merely because elapsed time is an imperfect productivity metric. Pair existing utilization evidence with accepted outcomes and rework; preserve the current guard unless the user changes that policy.

### 3. Bound retrieval by bytes as well as row counts

The live targeted command memory_bank.py timeline "bootstrap timeline" returned roughly 50 KB of timeline JSON (the combined receipt was 55,787 stdout characters). It required multiple 32,000-character transport pages. --limit defaults to 20, but repeated snapshots, graph details and event prose can still expand the response.

Improve the existing query command with a compact default and explicit expansion/continuation. Preserve freshness, coverage, case identity, matched-versus-returned counts and exact evidence pointers. A byte cap must report omissions and preserve access to omitted evidence; silently dropping history is not a fix. Caller-side broad output contributed to this audit's own unnecessary paging.

### 4. Treat coverage debt separately from refresh failure

Initial bootstrap completed in 764.5 ms internally. History was labeled FRESH and HISTORICAL_INCOMPLETE with repos/runner_logs coverage debt. A later status.json showed a successful incremental refresh starting 15:50:02 UTC, taking 57,093.4 ms, processing 159 delta events, with no saturated incremental sources or retries and the same backfill debt.

That is evidence of successful refresh, not a stalled materializer. Decide whether a missing historical interval matters to a concrete retrieval question before requesting backfill. Keep current freshness and historical completeness separate.

### 5. Retire obsolete instruction surfaces at their source

The skill surfaced as available and was read before the user's correction despite being obsolete for this workflow. Removing or disabling the source registration is stronger than relying on every future assistant to ignore it. The current session's injected catalog is not proof of desired configuration. Account deletion remains unresolved because the supported persistence path rejected the change.

## Limits and source pointers

Read live shared .agents/AGENTS.md and RULES.md, the worker contract, Stack Atlas bootstrap, targeted timeline history, the relevant implementation/tests, git status/history, exact Busy scopes, and issue #125's recent coordination comments. Did not enumerate scheduler automations or claim the current fleet count. Recent MCP callers are not worker identities. Did not change scheduler state, worker prompts, shared policy, live MCP, or the serving Vault source.

Key replay sources:
- tools/timeline_materializer.py query_materialized
- tools/verify.py select_areas / verify_memory
- tests/test_timeline_query_filters.py
- tests/test_verify.py
- 04 Operating Contracts/fresh-worker-generation-launch.md
- Live .state/timeline/status.json as inspected above
- MCP process receipts 2cecdd51-58ff-4366-9f92-55a7597a24ae (five failing scenarios), 2bbdedd3-7eb7-426b-9772-1d21a99d6f7b (28 passing tests), 6867c720-8bde-4ca1-82ff-b8c07e76f4ec (canonical verifier pass)
