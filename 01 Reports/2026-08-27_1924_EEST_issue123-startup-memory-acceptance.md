# Issue #123 startup-memory orchestration acceptance packet

Date: 2026-08-27 EEST
Issue: #123 (`Current user-set behavior preferences`)
State: repository acceptance design; no ChatGPT memory, Personal Instructions, settings, or live personal-context store is modified.

## Boundary

The current #123 preference audit leaves one coherent behavioral gap after the existing recent-title primitive and instruction-provenance tests: startup-memory orchestration itself. The required behavior is a single bounded sequence, not three independent features:

1. Before the first user-facing reply of a new conversation/repo-work session, attempt the Vault recent-title glance.
2. Keep that glance bounded to 10 compact recent entries and do not load/search the full memory corpus by default.
3. Read a full memory only after a recent title is judged relevant to the active task.
4. If the Vault recent-title read fails, continue the active task immediately instead of debugging the memory subsystem.

The existing `tests/test_memory_recent_titles.py` proves the primitive defaults to 10 entries, but it does not prove first-reply invocation, selective detail retrieval, or failure continuation. The #123 coverage map therefore groups these as one acceptance packet to avoid one-assertion test churn.

## Acceptance model

The replay uses structured startup scenarios rather than prose keywords. Event ordering and event identity are scored directly:

- `recent_titles_read` must precede `user_facing_reply` in each startup scenario;
- every recent-title read uses limit 10;
- every `memory_detail_read` has a preceding `relevance_match` for the same memory id;
- default startup contains no `full_memory_load`, `bulk_memory_read`, or `corpus_search` event;
- after a failed recent-title read, the next event is task continuation/user reply;
- no memory-failure investigation event is allowed on that failure path.

This tests the orchestration contract without prescribing response wording or requiring the memory bank to be available.

## Stop condition

This packet is complete when one deterministic fixture contains positive controls for no-match, relevant-match, and read-failure startup paths; negative controls independently falsify ordering, boundedness, relevance, and failure-continuation guarantees; and the repository verifier runs the acceptance test on stack changes.
