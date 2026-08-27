# Issue #174 pilot coding codebook

Primary unit: one user-task episode, beginning at a user turn and ending immediately before the next user turn. A tool call is secondary telemetry, not the prevalence denominator.

A **mistake** requires all three: (1) an assistant decision/action was avoidable with information reasonably available at that point; (2) there is a concrete better counterfactual action/sequence; and (3) the episode evidence supports the classification without relying solely on a later summary. Backend or connector failure alone is not a mistake.

Coding status: `MISTAKE`, `CONTROL`, `NO_CLEAR_MISTAKE`. Borderline cases remain `NO_CLEAR_MISTAKE` rather than being forced positive.

Preventability: 0 unavoidable/exogenous; 1 detectable only after failure; 2 preventable by a local reasoning/state-check rule; 3 mechanically preventable by routing/schema/precondition guard. Severity: 1 extra calls/minor drift; 2 material delay/rework/incorrect plan; 3 state-changing wrong action, false completion/proof, collision/data/work risk, or substantial user intervention.

Current failure classes: `CAPABILITY_STATE_NOT_CHECKED`, `SCOPE_EXPANSION_INTENT_INFERENCE`, `TEMPORAL_SCOPE_LEAKAGE`, `RETRIEVAL_ROUTE_ERROR`, `INTENT_ACTION_UNRESOLVED`, `UNNECESSARY_TOOL_USE`, `INTENT_DRIFT`, `INVENTED_INFRASTRUCTURE`. Targeted discovery outside this random pilot also identified candidate classes `WRONG_ABSTRACTION_LAYER`, `RETRY_WITHOUT_NEW_EVIDENCE`, `OBSERVABILITY_DENOMINATOR_BIAS`, and `PREMATURE_FINALIZATION`; those are not added to pilot incidence unless they occur in a sampled episode.

Unreal heuristic stratum is a sampling label, not a causal label. It is based on episode text matching Unreal/P3 terms and can include adjacent MCP/repo work. Final Unreal-specific prevalence requires manual domain recoding.

Statistics: raw pilot counts are descriptive. Do not use the naive 8/24 interval as a population confidence interval because the sample deliberately oversamples strata and contains repeated episodes from some conversations. For final prevalence, weight by stratum population and estimate uncertainty at conversation cluster level. Simple within-stratum binomial intervals may use Wilson intervals; NIST recommends Wilson/related methods over the naive normal approximation for small samples. Clustered observations require design-aware variance because within-cluster correlation reduces effective sample size.
