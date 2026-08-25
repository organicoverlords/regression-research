# Five-day control-plane correlation â€” 2026-08-21..25

Status: **PARTIAL / NOT_PROVEN for causation**. The dataset is reproducible for live MCP telemetry on Aug 23-25 and PR activity across P3, Tiny3D, LowVRAM, and Regression Research. MCP telemetry for Aug 21-22 is absent, so five-day causal claims are not supported.

## Measured result

Live telemetry contains 5,219 MCP calls on Aug 23, 14,960 on Aug 24, and 4,579 on Aug 25 at capture time. Slow `read_output` calls >=9s are 0, 4, and 107 respectively. The outcome snapshot records 95/49/6 merges and 224/98/23 default-branch commits for those dates, corresponding to 18.227, 3.275, and 1.497 merges per 1,000 MCP calls.

This is a real negative association in this three-day slice between MCP-call volume/shape and merge yield, but it is not a causal estimate. Aug 25 is partial, observability changed across versions, the worker population changed, and commits/merges are imperfect proxies for accepted user-visible work.

## Hypothesis challenge

The strong thesis â€œmore parallel work directly caused the control-plane regressionâ€ is **materially weakened**. Aug 23 had substantial activity and the highest measured merge yield, while Aug 25 had far fewer MCP calls than Aug 24 but the worst measured merge yield and by far the most >=9s reads. Raw concurrency alone therefore does not explain the failure shape.

A narrower hypothesis survives: coordination/transport shape matters. After foreground command removal, traffic shifted toward process lifecycle and polling; on Aug 25, bounded-output transport coincided with 107 long reads. This is compatible with polling amplification or queue pressure, but remains **PROVISIONAL** until caller-level events are joined to corrections and accepted outcomes.

## Version boundaries

The dataset records the Aug 23 removal of foreground `execute_command`, followed on Aug 25 by the 6,000-character `read_output` cap, full receipt preservation, truncation accounting, and per-response byte telemetry. These are treated as observability/transport boundaries, not proof that any one revision caused model drift.

## Worst preserved incident

The Aug 23 PRIMARY shows the clearest directly preserved control-plane failure: four repeated zero-yield grep calls, then a successful bounded parser, followed immediately by unrelated Git/project-throughput queries. That sequence demonstrates both failed-route persistence and acceptance-condition displacement without requiring a private-reasoning reconstruction.

## Counterexamples and limits

High activity was not uniformly dysfunctional: Aug 23 combines thousands of MCP calls with the highest measured merge yield in the available slice. Conversely, Aug 25 shows fewer calls than Aug 24 but much heavier long-poll pressure. These counterexamples reject a simple call-count or agent-count threshold model.

The current join does not yet provide exact token counts, correction-turn counts, per-caller accepted outcomes, or user-visible proof attribution. Aug 21-22 MCP telemetry is missing. PR collection is capped per repository and commit/merge counts are snapshot-derived. These gaps prevent a defensible five-day causal coefficient.

## External challenge to the simple overload thesis

External evidence also argues against treating additional agents or scaffolding as inherently harmful. MARCO, a 2025 primary study of a specialized multi-agent code-optimization loop, reports a 14.6% average runtime reduction versus Claude 3.5 Sonnet alone on its evaluated workload (https://arxiv.org/abs/2505.03906). That result does not transfer directly to this workstation or prove our orchestration is efficient, but it is a concrete counterexample to the strong claim that adding agent roles necessarily reduces useful engineering yield. The relevant question here is therefore not agent count alone, but whether decomposition, feedback, transport, and coordination overhead remain cheaper than the work they enable.
## Concrete changes supported by evidence

Keep output bounded, but also bound polling frequency and repeated same-route retrievals; after two contradictory retrievals, switch route. Keep admission/resource blockers first-class so they are diagnosed before downstream work. Measure useful outcomes separately from tool-call volume, and retain caller/process receipts so long-poll pressure can be attributed instead of inferred.

## Reproduction

Run `python tools/five_day_correlation.py`. Canonical outputs are `02 Evidence/five-day-control-plane-20260821-25/five-day-correlation-dataset.json` and `.csv`. The JSON embeds source status, version boundaries, PR joins, outcome joins, and a checksum.
