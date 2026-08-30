# Issue #123 current user-preference coverage map

Date: 2026-08-27 EEST
Source: GitHub issue #123, `Current user-set behavior preferences`, read from live GitHub during this work pass.
Scope: repository regression/audit coverage only. This document does **not** edit or claim control over ChatGPT memory, Personal Instructions, settings, or other live personal-context surfaces.

## Why this exists

Issue #123 is an external audit of the user's current behavior preferences. Those preferences are not all the same kind of requirement, and treating every sentence as a lexical hard gate would recreate the overfitting/canned-response problem the corpus already documents. This map separates deterministic executable coverage from partial evidence and policy-only guidance so future work can close real gaps without manufacturing test churn.

## Coverage

| Preference / boundary from #123 | Current repository coverage | Status | Notes |
| --- | --- | --- | --- |
| Preferred name is Joonas | #123 issue body and audit comment preserve the user-authored fact with provenance. | EXTERNAL_ONLY | No behavior test is appropriate merely to force name usage. |
| Prefer concise, information-dense answers | `NORTH_STAR.md` keeps tool chatter/process dumps out of the user experience; `tests/test_durable_memory_adapter.py` has a durable-memory preference example. | POLICY_ONLY | There is no deterministic answer-length/style acceptance test, intentionally avoiding brittle lexical formatting gates. |
| Run the Vault recent-memory glance before the first user-facing reply of a new conversation/repo-work session | Historical incident/experiment evidence exists, but current `origin/main` has no replay fixture that proves first-reply invocation. | GAP | `tests/test_memory_recent_titles.py` proves the read primitive, not that the assistant invokes it at the correct boundary. |
| Inspect only the 10 newest compact entries | `tests/test_memory_recent_titles.py::test_newest_first_default_is_ten_and_hard_cap_is_twenty`. | DETERMINISTIC | Default is exactly 10; hard cap is 20. |
| Do not load full memories/search the corpus by default | The recent-title API is bounded, but no whole-stack test proves that a fresh assistant stops at titles unless relevance requires retrieval. | PARTIAL | Primitive is safe; orchestration boundary is not yet directly replayed. |
| Retrieve a memory only when a recent title is clearly relevant | Memory ranking/recall machinery is tested elsewhere, but no first-turn title-to-selective-retrieval acceptance exists for #123. | PARTIAL | Keep separate from general retrieval quality. |
| If the memory bank/command fails, continue immediately rather than investigating | Optional/missing-memory behavior exists in memory adapters, but there is no direct #123 startup-failure replay. | PARTIAL | A route/read failure must not become the task; this still needs a first-turn-specific acceptance if promoted. |
| Current user instructions and live repo/runtime state outrank memory | `AGENTS.md` precedence plus `tests/test_instruction_provenance.py::test_current_turn_beats_current_personal_instructions` and `::test_current_personal_instructions_beat_repo_durable_and_historical_context`. | DETERMINISTIC | Covers current-turn and current-PI authority over lower/stale context. |
| Do the necessary analysis/retrieval/falsification/tool work/verification before answering | Evidence/proof rules exist in `AGENTS.md`/`NORTH_STAR.md`; many domain fixtures require direct evidence before acceptance. | POLICY_ONLY | Not reduced to a generic "use N tools" metric because that would reward churn. |
| Compress presentation, not underlying work | `NORTH_STAR.md` explicitly keeps tool chatter out unless it changes decision/risk/result. | POLICY_ONLY | Intentionally not enforced by fixed answer template or token count. |
| Report only information that materially changes understanding/confidence/decision/action | `AGENTS.md` and `NORTH_STAR.md` encode materiality-based reporting. | POLICY_ONLY | No lexical hard gate. |
| Avoid canned templates and worker/project conventions in ordinary conversation | Corpus evidence and slopwall promotion/review records preserve canned-template regressions. | PARTIAL | Evidence exists; a universal formatting test would risk becoming the canned behavior itself. |
| Finish the bounded requested outcome without absorbing adjacent discovered work | `tests/test_issue122_acceptance_boundary_replay.py` requires task-local acceptance and rejects unrelated activity becoming a completion obligation. The #123 correction-integration replay also rejects open-ended investigation. | DETERMINISTIC_CORE | Core stop/scope boundary is replayed; arbitrary semantic adjacency is intentionally not regex-gated. |
| Do not replace thinking with narration; prioritize doing work and useful conclusions | `NORTH_STAR.md` user-experience clauses and tool-chatter rule. | POLICY_ONLY | This is a process invariant, not a narration keyword ban. |
| Distinguish user-authored instructions/preferences from other sources | `tests/test_instruction_provenance.py` covers current user, current PI, repo policy, retrieved content, unknown provenance, and false behavior attribution. | DETERMINISTIC | Direct coverage. |
| Preserve and execute the allowed part of a mixed request | `tests/test_instruction_provenance.py::test_mixed_request_preserves_allowed_user_authored_part` and `tests/test_stack_acceptance.py::test_mixed_request_keeps_allowed_user_owned_part`. | DETERMINISTIC | Whole-stack positive control exists. |
| Keep tool/status narration minimal unless materially helpful | `NORTH_STAR.md`: tool chatter stays out unless it materially changes decision/risk/result. | POLICY_ONLY | Deliberately not a fixed response-shape test. |

## Current actionable gaps

There are three related orchestration gaps around the startup memory rule: proving the first-reply invocation boundary, proving selective retrieval rather than automatic full-memory loading, and proving immediate continuation when the Vault read fails. They should be handled as one bounded startup-memory acceptance packet if work is opened, not as three serial micro-PRs.

The style/reporting preferences are intentionally **not** converted into fixed lexical templates. Existing evidence shows that over-formalizing response shape can itself become a regression. Their enforcement should remain outcome/materiality based unless a future failure yields a discriminating replay that can be tested without prescribing canned prose.

## Conclusion

#123 is substantially covered on precedence, mixed-request preservation, bounded completion, and the recent-title primitive. The main concrete behavioral hole is the startup-memory orchestration boundary. This map is the stop point for the audit pass; it identifies the next coherent packet instead of continuing to manufacture one-assertion follow-ups.
