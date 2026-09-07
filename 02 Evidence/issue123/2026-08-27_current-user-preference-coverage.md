# Issue #123 current user-preference coverage map

Original audit date: 2026-08-27 EEST
Current reconciliation: 2026-09-07 EEST
Source: GitHub issue #123 plus the merged 2026-09-03 current Vault-history boundary.
Scope: repository regression/audit coverage only. This document does **not** edit or claim control over ChatGPT memory, Personal Instructions, settings, or other live personal-context surfaces.

## Why this exists

Issue #123 is an external audit of the user's current behavior preferences. Those preferences are not all the same kind of requirement, and treating every sentence as a lexical hard gate would recreate the overfitting/canned-response problem the corpus already documents. This map separates deterministic executable coverage from partial evidence and policy-only guidance so future work can close real gaps without manufacturing test churn.

**Supersession note:** the Aug-27 mandatory startup `memory_bank.py recent` preference is preserved as historical evidence only. The current explicit boundary, merged on 2026-09-03, is: ordinary startup proceeds from current conversation + ChatGPT Memory without a Vault bootstrap/recent-title read; Vault is optional targeted history/evidence only when a specific past fact, decision, incident, or prior work materially helps.

## Coverage

| Preference / boundary from #123 | Current repository coverage | Status | Notes |
| --- | --- | --- | --- |
| Preferred name is Joonas | #123 issue body and audit comment preserve the user-authored fact with provenance. | EXTERNAL_ONLY | No behavior test is appropriate merely to force name usage. |
| Prefer concise, information-dense answers | `NORTH_STAR.md` keeps tool chatter/process dumps out of the user experience; `tests/test_durable_memory_adapter.py` has a durable-memory preference example. | POLICY_ONLY | There is no deterministic answer-length/style acceptance test, intentionally avoiding brittle lexical formatting gates. |
| Run the Vault recent-memory glance before the first user-facing reply of a new conversation/repo-work session | Superseded by `03 Fixtures and Experiments/issue123-current-vault-history-boundary.json` and `tests/test_issue123_current_vault_history_boundary.py`. | HISTORICAL_SUPERSEDED | The old startup glance is now a negative control: ordinary startup must not perform it by default. |
| Inspect only the 10 newest compact entries | `tests/test_memory_recent_titles.py::test_newest_first_default_is_ten_and_hard_cap_is_twenty` still proves the historical primitive. | HISTORICAL_PRIMITIVE | The 10-entry bound remains valid if that primitive is explicitly used, but it is no longer a startup requirement. |
| Do not load full memories/search the corpus by default | `issue123-current-vault-history-boundary` directly requires ordinary startup without Vault retrieval and allows only targeted history after a specific past-fact need. | DETERMINISTIC_CURRENT | Current orchestration boundary is replayed without turning Vault into behavior/current-state authority. |
| Retrieve Vault history only when a specific past fact materially helps | `issue123-current-vault-history-boundary` requires a `specific_past_fact_need` before `vault_history_read`. | DETERMINISTIC_CURRENT | This supersedes title-driven startup retrieval; targeted history remains allowed. |
| If the old mandatory startup memory command fails, continue immediately rather than investigating | Superseded together with the mandatory startup command. | HISTORICAL_SUPERSEDED | Current startup does not invoke Vault by default, so there is no startup Vault failure to make into a prerequisite. |
| Current user instructions and live repo/runtime state outrank memory | `AGENTS.md` precedence plus `tests/test_instruction_provenance.py::test_current_turn_beats_current_personal_instructions` and `::test_current_personal_instructions_beat_repo_durable_and_historical_context`. | DETERMINISTIC | Covers current-turn and current-PI authority over lower/stale context. |
| Do the necessary analysis/retrieval/falsification/tool work/verification before answering | Evidence/proof rules exist in `AGENTS.md`/`NORTH_STAR.md`; many domain fixtures require direct evidence before acceptance. | POLICY_ONLY | Not reduced to a generic "use N tools" metric because that would reward churn. |
| Compress presentation, not underlying work | `NORTH_STAR.md` explicitly keeps tool chatter out unless it changes decision/risk/result. | POLICY_ONLY | Intentionally not enforced by fixed answer template or token count. |
| Report only information that materially changes understanding/confidence/decision/action | `AGENTS.md` and `NORTH_STAR.md` encode materiality-based reporting. | POLICY_ONLY | No lexical hard gate. |
| Avoid canned templates and worker/project conventions in ordinary conversation | `tests/fixtures/issue123-small-response-shape.json` + `tests/test_issue123_response_shape.py` replay the preserved Aug-29 tiny-status slopwall incident. | DETERMINISTIC_SMALL_REPLY | For unstructured yes/no, status, and small-clarification replies, the regression rejects headings/lists/arrows/multi-paragraph scaffolding. Explicitly requested structure and genuinely complex tasks remain exempt, avoiding a universal canned template. |
| Finish the bounded requested outcome without absorbing adjacent discovered work | `tests/test_issue122_acceptance_boundary_replay.py` requires task-local acceptance and rejects unrelated activity becoming a completion obligation. The #123 correction-integration replay also rejects open-ended investigation. | DETERMINISTIC_CORE | Core stop/scope boundary is replayed; arbitrary semantic adjacency is intentionally not regex-gated. |
| Do not replace thinking with narration; prioritize doing work and useful conclusions | `NORTH_STAR.md` user-experience clauses and tool-chatter rule. | POLICY_ONLY | This is a process invariant, not a narration keyword ban. |
| Distinguish user-authored instructions/preferences from other sources | `tests/test_instruction_provenance.py` covers current user, current PI, repo policy, retrieved content, unknown provenance, and false behavior attribution. | DETERMINISTIC | Direct coverage. |
| Preserve and execute the allowed part of a mixed request | `tests/test_instruction_provenance.py::test_mixed_request_preserves_allowed_user_authored_part` and `tests/test_stack_acceptance.py::test_mixed_request_keeps_allowed_user_owned_part`. | DETERMINISTIC | Whole-stack positive control exists. |
| Keep tool/status narration minimal unless materially helpful | `NORTH_STAR.md`: tool chatter stays out unless it materially changes decision/risk/result. | POLICY_ONLY | Deliberately not a fixed response-shape test. |

## Current actionable gaps

There is **no remaining startup-memory orchestration gap** under the current authority boundary. The merged Sept-3 fixture proves the opposite of the Aug-27 packet: ordinary startup performs no Vault retrieval, and targeted Vault history is permitted only after a specific historical need. Future #123 work should not resurrect the superseded startup-glance packet.

The preserved Aug-29 incident now supplies one discriminating structural replay: small yes/no, status, and clarification replies default to one cohesive paragraph without headings, lists, arrows, or flow scaffolding unless structure is requested or genuinely required. Broader style/reporting preferences remain outcome/materiality based rather than fixed lexical templates or universal length gates.

## Conclusion

#123 is substantially covered on precedence, mixed-request preservation, bounded completion, the current targeted-history boundary, and the narrow small-response anti-slopwall shape boundary. The old startup-memory orchestration packet is historical/superseded and must not be reopened as a current gap. Broader style/reporting preferences remain outcome/materiality based unless a future discriminating failure justifies another non-brittle replay.
