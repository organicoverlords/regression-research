# Recovery / guidance / work-sanity audit — 2026-09-13

Date: 2026-09-13
Scope: current stack recovery posture, shared guidance quality, recent work effectiveness, and the smallest useful sanity view. This is a bounded current-state audit, not a new authority or monitoring system.

## Executive verdict

**Sanity snapshot: 7/10 — recovering and materially improved, but not a good point for another broad stack-wide change.**

The important distinction is that the current stack is not broadly broken: MCP is live, the current serving route is explicit, rollback lanes exist, shared rules are coherent/current, and recent work has removed a large amount of obvious lifecycle slop. The remaining risk is concentrated rather than mysterious: historical/discovery freshness is not fully clean, continuation behavior still fragments too often, and machine headroom—especially disk—is under pressure.

**Nexus is explicitly out of scope for activation/deployment in this recovery phase.** Nexus #16/#23 being implementation/proof complete does not create a reason to deploy it. The user explicitly wants recovery and current-state understanding first, after the earlier period where too many stack changes interacted at once.

## Minimal sanity score

This score is only an audit shorthand. It is not product/runtime authority, must not replace the underlying evidence, and should never be optimized as a target.

| Axis | Score | Current evidence |
|---|---:|---|
| Live path + rollback safety | 2/2 | MCP live on the named current route; current topology is explicit; independent previous/secondary rollback generations exist; recovery policy is restore-first. |
| Shared guidance / guardrails | 2/2 | RULES/AGENTS coherent at v87, source freshness clean, restore-first/proof-before-claim/unified-discovery/shared-convergence rules are present. |
| Discovery + historical context | 1/2 | Exact gh-buffer identity hole found and repaired under #1127, but materialized history is stale during this audit and Timeline runtime graph reports drift that needs owner-level reconciliation. |
| Work behavior / convergence | 1/2 | Manual lifecycle anomaly diagnostic improved strongly, but go/continue fragmentation remains high and the last 24h still contains many regression/Slopwall cases. |
| Machine/resource headroom | 1/2 | Commit headroom is still healthy and MCP is live, but physical RAM is tight and C: is 90.2% used with ~18.9 GB free-space loss over ~23h. |

Interpretation: **7/10 = controlled enough for surgical work; not evidence for broad simultaneous changes.** Re-score only from current authoritative evidence; do not carry the number forward when its inputs are stale.

## Current recovery state

### MCP / serving path

Fresh bootstrap at ~09:55 EEST:
- MCP `available=true`, `status=LIVE`, fresh MCPv4 activity evidence, three live transport sources.
- Current GPT1 serving authority is `mcp-current-topology.v1`, currently `ChatGPT/GPT1 connector -> local HTTPS Caddy -> 127.0.0.1:3064`.
- The selected recovery target in `mcp-recovery-state.json` is recovery metadata only and is correctly kept separate from the live serving identity.
- Independent rollback/control generations remain available (3012 previous stable, 3022 secondary recovery, older rollback generations retained).
- Current recovery guidance is restore-first: preserve evidence/work, restore known-working behavior/topology before speculative fixes, and do not turn above-MCP/platform evidence into another MCP mutation without MCP-local causality.

Verdict: **the recovery model itself is currently good enough; adding another recovery coordinator/state machine is not justified.**

### Shared rules / guidance

Current shared agent contract is coherent at v87 and local canonical sources match their tracked main. Particularly useful rules now cover:
- bootstrap/live-swarm as bounded shared orientation;
- one unified `find` route before source-by-source archaeology;
- issue/task as a shared convergence identity, not a worker-owned lane;
- existing coherent WIP wins for the same logical mutation;
- next highest-value ready canonical contribution when one slice blocks;
- proof-before-claim for shared behavior corrections;
- restore-first production/MCP recovery and explicit live-vs-recovery authority separation.

The rules are substantially better than the behavior observed around the earlier failure period. The present problem is no longer mainly “missing prose”. Repeated incidents now more often indicate a concrete enforcement/discovery/runtime-freshness gap that should be repaired at its owner instead of adding another generic rule.

## What the existing sanity machinery says—and does not say

There is already a `manual-worker-sanity` projection. It intentionally **does not emit an authoritative truth score**: `headline_eligible=false`, `truth_score_status=UNAVAILABLE_MCP_GITHUB_EVAL_NOT_CALIBRATED`, `direction=UNAVAILABLE_TRUTH_SCORE`. This is correct because worker reports are auxiliary metadata, not execution or acceptance truth.

Its historical diagnostics are still useful:
- self-reported lifecycle anomaly rate: **16.67% baseline -> 1.04% current**, descriptive operational delta +93.8;
- reporting overhead also fell materially, but report size/shape is explicitly non-scoring;
- identified go/continue runs remain fragmented: **36.51% <5 min** and **20.11% <2 min**, versus 0%/0% in the small historical continuation baseline.

So the useful conclusion is not “sanity improved 93.8 points”. The grounded conclusion is: **some lifecycle hygiene clearly improved, while continuation/convergence still deserves targeted audit.**

## Recent incident/regression pressure

Bootstrap memory overview currently shows, for the last 24h:
- 13 material cases;
- 9 Slopwall cases;
- 2 incidents;
- 8 regressions.

Recent durable corrections include:
- Slopwall semantics must come from preserved incident/replay authority before shared-rule mutation;
- worker-health reviews should return the bounded verdict before telemetry detail;
- CI recovery should act on a proven runner outage before narrating history.

This supports the user's observation that today has contained useful surgical repair work, but it also means “lots of fixes landed” must not be mistaken for “recovery is finished”. The right question is whether the same failure classes are shrinking under current authoritative evidence.

## Current concrete gaps / watch items

### 1. Stack Atlas exact GitHub identity discovery — repaired under #1127

During this audit, `stack_atlas.py find` could search the existing local gh-buffer SQLite cache but could not surface an exact issue/PR that had never been fetched through the buffer. That directly hid Nexus #16/#23 during historical reconstruction.

Root cause: `find` treated gh-buffer as cache-only. A cold exact identity was invisible until a separate `gh issue view` populated/retrieved it.

#1127 changes this narrowly:
- a strong exact `#number` plus a resolved repo identity may perform a bounded exact lookup through the existing `gh-buffer-proxy`;
- max two repo hints / three numbers;
- no issue/PR listing and no broad GitHub fanout;
- generic semantic queries remain cache-only;
- exact hits rank as exact identity rather than depending on body/title keyword overlap.

End-to-end proof during this audit: `find "organicoverlords/regression-research#1127"` performed one bounded proxy lookup and returned `organicoverlords/regression-research#1127` as an exact `github_cache_hit` with score 100.

### 2. Timeline/history freshness is not clean

During this audit, Stack Atlas reported the materialized Timeline/history index stale/invalid for discovery. The exact scheduled task exists, is enabled, and most recently reported result 0, but the deployment graph also flags drift for parts of the pinned Timeline runtime.

Important: scheduler success is not proof that the current query index is fresh/coherent. Conversely, a derived drift label is not enough to mutate the runtime. This needs one owner-level reconciliation of scheduled runtime bytes, publication/read-state pointer, and current query-index generation.

Until that is reconciled, **absence from `find` history is not proof that an event did not happen.**

### 3. Continuation/convergence remains weaker than lifecycle hygiene

The existing manual diagnostics show much less explicit lifecycle slop but significantly more short/micro go/continue runs than the old bounded baseline. This is a good candidate for the next behavioral audit because #55/#178 already define the desired semantics: a blocked slice should not end the turn when another useful canonical contribution exists.

Do not add duration incentives or force workers to “stay busy”. The audit should classify actual short continuation endings against stop reason + MCP execution + repo/GitHub convergence evidence and fix only a proven recurring cause.

### 4. Disk pressure is a near-term operational constraint

Current KONE C: state: about **46.8 GB free, 90.2% used**, with about **18.9 GB lost over ~23h**. Physical RAM is also tight (~0.8 GB free) although commit headroom remains ~15.8 GB, so this is not commit exhaustion.

Before heavy builds, broad parallel experiments, or another stack-wide rollout, identify the live owner of disk growth and reclaim only owner-proven regeneratable output. Do not turn this into generic cleanup.

### 5. Regression-research CI is intentionally fail-closed during #1120

PR #1131 exposed a current required-check queue: the existing workflow still requests `[self-hosted, Windows, X64, regression-research]`, while live RR-KONE-02 is online/idle with only `self-hosted, Windows, X64, kone-ci-light`.

This is **not an accidental runner outage**. Existing issue #1120 owns the transition. Its current evidence says the generic `regression-research` label was deliberately removed from KONE after a substantive verify job was accepted there, because the user direction now permits KONE only for extremely-light mandatory Windows CI. The intended substantive runner is OMEN, but its regression-research runner is still staged/unregistered. Therefore generic verify jobs are intentionally queuing rather than violating the execution-node policy.

This is a good recovery property—fail closed rather than silently spill work—but it is also a real current integration gate. #1131 must not bypass it; after #1120 lands, #1131 should reconcile/rebase onto the new workflow and rerun the exact-head required proof.

## Why this event chain was unnecessarily hard to reconstruct

The reconstruction started from remembered terms such as `intent`, `epoch`, “yhteinen suunta”, Ponytail and YAGNI. The actual behavior evolved across multiple owners and dates rather than one named feature:

1. regression-research #675 — full task picture / lessons / peers / WIP / next nonduplicative action;
2. Agents PR #132 — executable contribution boundaries;
3. Agents PR #178 / #55 — issue is shared convergence identity, not a worker lane;
4. #861 + Agents #238/#239 — Ponytail/minimal sufficient fix rules;
5. Agents #315/#316 — small bootstrap/swarm-first orientation + durable decision provenance;
6. Agents #375/#376 — proof before claiming shared swarm behavior changed;
7. Nexus #16/#23 — shared operator cockpit implemented/proven but explicitly not deployed;
8. today's #1122/#1123 — preserved the Ponytail/swarm/Nexus discussion without pretending those discussion ideas were new implementation.

The search difficulty had three distinct causes:
- remembered vocabulary did not match the durable owner names;
- the relevant concept is intentionally distributed across existing owners rather than represented by one new “shared understanding” service;
- exact Nexus issue identities were cold in gh-buffer, while `find` only searched the existing cache. #1127 repairs this last technical gap.

A fourth temporary complication is current Timeline staleness: history search can be incomplete even when live/current owner evidence is healthy.

## Ponytail/YAGNI conclusion: what is actually missing?

**No new orchestrator, truth store, Nexus deployment, scheduler, “sanity service”, or global recovery engine is justified by this audit.**

The smallest missing operational practice is a **bounded sanity snapshot** like this report, built from existing authorities:
1. live route/recovery status;
2. rule/contract coherence;
3. history/discovery freshness;
4. authoritative execution/convergence plus carefully labelled diagnostics;
5. resource headroom;
6. exact unresolved decisions/gaps.

For now this can remain an on-demand Vault report. If repeated audits prove that manually assembling the same five facts is itself causing errors or wasted work, then a tiny read-only projection may be justified later. Do not build it pre-emptively.

## Recommended next order

1. Land #1127 and keep `find` exact-identity discovery bounded.
2. Reconcile the Timeline scheduled runtime/read-state staleness/drift at its existing owner; do not redesign Timeline.
3. Identify the current disk-growth owner before heavy/broad work.
4. Audit short go/continue endings using MCP + repo/GitHub evidence; repair only a recurring proven cause.
5. Re-run this five-axis sanity snapshot before any materially broad stack/control-plane change.
6. Keep Nexus deployment out of scope until the recovery/current-state decision is explicitly revisited by the user.

## Reusable snapshot rule

When this audit is repeated, record only:
- score `/10` with the same five 0–2 axes;
- exact evidence timestamp;
- what improved;
- what regressed/unknown;
- the smallest next owner/action;
- explicit “do not widen” decisions.

Never use the score itself as authority, worker KPI, or automatic deployment gate.
