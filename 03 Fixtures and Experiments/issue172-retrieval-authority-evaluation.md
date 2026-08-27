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

After the canonical bank independently grew to 114 entries, the unchanged candidate retained Recall@5 73.3%, improved MRR to 0.552, exact Recall@1 100%, and abstention 100%; the legacy control remained Recall@5 40.0%.

This is a small, hand-authored challenge set rather than an independent blinded benchmark, so it is evidence for the preregistered promotion decision, not a claim of universal retrieval superiority. Future unseen-query evaluation remains desirable.

## Authority firewall

Retrieval relevance and behavioral authority are now independent. Behavioral authority is not a truth-confidence score. A current explicit user instruction applies immediately outside the bank and is not subject to a proof gate. For persisted memory, a `preference`, `decision`, or `correction` with direct `user-instruction:` provenance is `USER_EXPLICIT` regardless of `PROVEN`/`PROVISIONAL` claim state. Live canonical policy/spec entries are `CANONICAL_POLICY` only when `PROVEN`. A user-sourced `fact` or `lesson` remains evidence rather than policy.

`USER_EXPLICIT` has precedence 100, `CANONICAL_POLICY` 90. All other records are `ADVISORY_EVIDENCE`; rejected records are inactive. User provenance has `behavior_only` scope: it can establish what behavior/instruction to honor without converting an unverified external causal claim into proven truth.

The observed regression `mem-20260827-afce2baf` is an executable acceptance case. The old PROVISIONAL derived lesson is denied behavioral authority and is superseded; `mem-20260827-9a770b5b`, the explicit user-backed correction, is admitted as `USER_EXPLICIT`. Tests also cover PROVEN assistant-derived lessons, PROVISIONAL user-sourced interpretations, user-sourced factual records, canonical policy, supersession, and user-over-canonical precedence.

## Rollback and surface area

Default local Memory Bank search is hybrid. `MEMORY_RETRIEVAL_STRATEGY=legacy` restores the previous lexical ranking exactly; invalid strategy names fail closed. History semantics stay legacy. No LLM, embedding service, model download, network dependency, MCP tool, or MCP resource is added.
