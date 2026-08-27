# Issue #176 unseen holdout evaluation

Date: 2026-08-27

## Purpose

This evaluation was created after #172 merged. Its selection protocol and constants were posted to issue #176 before outcomes were inspected. The merged hybrid ranker and authority rules were not changed during the holdout.

## Frozen population

Source bank: 117 entries at commit recorded in `tests/fixtures/memory-holdout-v1.json`.

After mechanically excluding every #172 evaluation/sentinel memory, the bank contained only six eligible current correction/supersession pairs and eight eligible negative-control facts/lessons. The preregistered maximums were 20 each, so the holdout uses the entire eligible correction population and the entire eligible negative population available under the protocol.

Queries were generated mechanically from each superseded entry's title plus its first 160 normalized text characters. No hand-written paraphrases or post-result synonyms were added.

## Retrieval result

| Metric | Legacy | Merged hybrid |
| --- | ---: | ---: |
| Recall@1 | 33.3% (2/6) | 33.3% (2/6) |
| Recall@3 | 33.3% (2/6) | 33.3% (2/6) |
| Recall@5 | 33.3% (2/6) | 50.0% (3/6) |
| MRR | 0.333 | 0.394 |
| Superseded-memory leaks | 0 | 0 |

At Recall@5, one case improved from miss to hit and zero regressed. With only one discordant case, a one-sided exact sign/binomial test is p=0.5. For reciprocal-rank direction, two cases improved and zero regressed, giving p=0.25 over the two discordant cases. These are not strong statistical results. The holdout supports a directional improvement, not a claim of broad or universal retrieval superiority.

The two hybrid-only rank improvements were one correction reaching rank 5 and one reaching rank 6. Three of six corrections still failed to appear in the top eight. Those misses are preserved in the machine-readable result and were not used to tune #172.

Two consecutive runs were byte-identical; SHA-256 of the result was `911a867f20726b330a21eb34c7c33985725eca7179bec3919d7bbc7d30f7baeb`.

## Authority result

The authority firewall had zero failures across the unseen population:

- 0/6 superseded entries entered `behavioral_context`;
- 0/8 negative-control facts/lessons gained behavioral authority;
- all six sampled corrections were classified according to the merged rules without promoting the stale entries.

This is useful independent evidence that supersession and the advisory/behavioral separation generalize beyond the #172 sentinel incident.

## Important limitation: direct user authority

The deterministic correction-pair sample contained zero corrections with `user-instruction:` provenance. A population audit found only five current user-backed behavior records in the entire bank: two #172 corrections plus three older records. The three non-#172 records are all `PROVEN`; there is no naturally occurring non-#172 `PROVISIONAL` direct-user preference/decision/correction available for an independent holdout of the exact proof-gate failure.

Therefore this holdout does **not** independently prove the `PROVISIONAL direct user instruction > PROVEN derived lesson` branch. That branch remains covered by the executable #172 regression test and the real #172 sentinel correction. The absence of an independent natural case is an evidence gap, not a reason to fabricate one.

## Interpretation

#172's strongest generalization is the authority firewall, not the retrieval uplift. The unseen bank population produced zero stale/advisory authority failures. Hybrid retrieval remained better than legacy on this holdout, but only modestly and with insufficient sample size for a strong significance claim.

No retrieval weights, authority precedence, evidence prefixes, MCP tools/resources, canonical memory entries, or conversation-index behavior were changed by #176.
