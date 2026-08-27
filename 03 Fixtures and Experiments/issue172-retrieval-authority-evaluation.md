# Issue #172 retrieval and authority evaluation

Date: 2026-08-27

## Frozen retrieval experiment

The evaluation fixture and legacy baseline were committed before the candidate implementation. Candidate weights and admission thresholds were posted to issue #172 before the first candidate run and were not tuned after seeing eval-v1 results. Canonical `memory/memory-bank.jsonl` was not rewritten by the retrieval candidate.

Frozen bank: 112 entries. Paraphrase cohort: 15 cases; exact lexical controls: 6; unrelated abstention controls: 4.

| Metric | Legacy baseline | Candidate 1 |
| --- | ---: | ---: |
| Paraphrase Recall@1 | 13.3% | 40.0% |
| Paraphrase Recall@3 | 33.3% | 60.0% |
| Paraphrase Recall@5 | 40.0% | 73.3% |
| Paraphrase MRR | 0.250 | 0.519 |
| Exact-control Recall@1 | 83.3% | 100.0% |
| Exact-control Recall@5 | 100.0% | 100.0% |
| Unrelated-query abstention | 75.0% | 100.0% |

At Recall@5, five paraphrase cases changed from miss to hit and zero changed from hit to miss. A one-sided exact paired sign/binomial test over the five discordant cases gives p=0.03125 under an equal win/loss null. The first candidate output and an immediate repeat were byte-identical (SHA-256 `8B62231EF0485ED91516D263DCC2F2A11B83C32401F36B09B2628492CE5938D3`).

The same frozen candidate was then rerun unchanged as the canonical bank independently grew. At 116 entries, paraphrase Recall@5 remained above the preregistered gate at 66.7% versus the legacy control's 40.0%; MRR was 0.539 versus 0.236, exact Recall@1 was 100% versus 83.3%, and abstention was 100% versus 75%. Two consecutive hybrid runs on that 116-entry bank were byte-identical (SHA-256 `fc8f79d627075166493bcc756d42b290c92be23f6302c8881531d09f9f3a4eb5`).

This is a small, hand-authored challenge set rather than an independent blinded benchmark, so it is evidence for the preregistered promotion decision, not a claim of universal retrieval superiority. Future unseen-query evaluation remains desirable.

## Authority firewall

Retrieval relevance and behavioral authority are now independent. Behavioral authority is not a truth-confidence score. A current explicit user instruction applies immediately outside the bank and is not subject to a proof gate. For persisted memory, a `preference`, `decision`, or `correction` with direct `user-instruction:` provenance is `USER_EXPLICIT` regardless of `PROVEN`/`PROVISIONAL` claim state. Live canonical policy/spec entries are `CANONICAL_POLICY` only when `PROVEN`. A user-sourced `fact` or `lesson` remains evidence rather than policy.

`USER_EXPLICIT` has precedence 100, `CANONICAL_POLICY` 90. All other records are `ADVISORY_EVIDENCE`; rejected records are inactive. User provenance has `behavior_only` scope: it can establish what behavior/instruction to honor without converting an unverified external causal claim into proven truth.

The observed regression `mem-20260827-afce2baf` is an executable acceptance case. The old PROVISIONAL derived lesson is denied behavioral authority and is superseded; `mem-20260827-9a770b5b`, the explicit user-backed correction, is admitted as `USER_EXPLICIT`. Tests also cover PROVEN assistant-derived lessons, PROVISIONAL direct user corrections, user-sourced factual records, canonical policy, supersession, and user-over-canonical precedence. The separate 13:20 EEST incident report records the design regression where the first firewall draft wrongly required user instructions themselves to be PROVEN; the regression test now requires a PROVISIONAL direct user correction to outrank a newer PROVEN assistant-derived lesson.

## Rollback and surface area

Default local Memory Bank search is hybrid. `MEMORY_RETRIEVAL_STRATEGY=legacy` restores the previous lexical ranking exactly; invalid strategy names fail closed. History semantics stay legacy. No LLM, embedding service, model download, network dependency, MCP tool, or MCP resource is added. MCP0 discovery returned 7 exposed tools at the start of #172 and 7 again after implementation. The branch changes no MCP server/schema file.

## Test status

The #172-focused retrieval/authority suite passes 34/34. The broader `test_memory_*.py` suite passes 111/112; its sole failure is `test_memory_report.MemoryReportTests.test_status_is_validated_and_receipt_is_deterministic`, which was separately reproduced on a clean `origin/main` worktree before promotion and is therefore a pre-existing baseline failure rather than a #172 regression.
