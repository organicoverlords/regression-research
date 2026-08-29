# Incident Report ? Fresh-worker reset policy conflict

**Time:** 2026-08-29 10:14 EEST  
**Severity:** HIGH ? orchestration policy regression caused repeated wrong scheduler mutations  
**Status:** FIXED LOCALLY; regression test added

## Trigger

The user asked to arm five workers. The current worker fleet was bugged and fresh replacement was justified. After an initial incorrect orchestration pass, the assistant then over-corrected in the opposite direction and claimed fresh replacement had not been justified, re-enabled an old worker, and disabled the fresh generation.

Relevant user corrections, verbatim:

- `verified enabled? also that is not the procedure at all`
- `fresh replacement WAS justified all the workers are bugged omg this is not ok`
- `the policy is failing fix this and write a report`

The opening task was `@plugin2 arm the 5 workers please`.

## What failed

This was not a lack-of-policy incident. The canonical fresh-generation contract already said poisoned/buggy workers must be replaced rather than re-armed. The failure came from conflicting discoverable policy artifacts and insufficient regression coverage around the mode decision.

Three policy surfaces disagreed:

1. `04 Operating Contracts/fresh-worker-generation-launch.md` correctly required replacement of stale/buggy workers and a five-worker generation.
2. `templates/P3-V2-SWARM-TEMPLATE.md` was stale: it still described a **four-worker** generation, held Workers 2-4 behind Worker 1 acceptance, and recreated a fresh **four-worker** generation after shared poisoning.
3. `01 Reports/2026-08-29_armworkers-orchestration-fiasco-root-cause_report.md` strongly prescribed an explicit `REARM_EXISTING` / `FRESH_GENERATION` classification and said the earlier `armworkers` request had drifted into fresh replacement without sufficient proof. That report was historical evidence, but its wording was easy to misapply as current launch authority.

The assistant searched these artifacts, let the historical rearm warning outweigh the current fact that the fleet was bugged, and reversed a justified fresh reset. That violated the core precedence rule: current user instruction and current live condition outrank historical reports and older templates.

## Specific decision error

The wrong decision chain was:

1. Observe that only one old worker was enabled and several generations had failed.
2. Create five fresh workers.
3. User says the procedure was wrong.
4. Search historical policy.
5. Find the old rearm-vs-fresh warning.
6. Infer that fresh replacement itself was unjustified.
7. Disable the fresh workers and re-enable an old bugged worker.

Step 6 was the regression. The user's current statement that all workers were bugged is itself sufficient evidence that this is a fresh-replacement case. No additional rearm classification should override that fact.

## Policy correction

### Canonical launch contract

`04 Operating Contracts/fresh-worker-generation-launch.md` now makes the mode gate explicit:

- bugged / poisoned / stale / contaminated / missing-tool fleet => `FRESH_GENERATION`;
- that current statement/evidence is sufficient justification for replacement;
- `REARM_EXISTING` is only valid for workers currently known healthy and merely paused/disabled;
- historical reports/templates/memory cannot override the current mode;
- creating/enabling Workers 1-5 is one setup pass, so a per-worker one-mutation-per-proof rule must not split the five-worker arm operation.

### Canonical swarm template

`templates/P3-V2-SWARM-TEMPLATE.md` was updated from the stale four-worker topology to the current five-worker topology:

- exactly five workers;
- Workers 2-5 are armed in the same setup pass as Worker 1;
- they may be staggered, but are not held until Worker 1 acceptance;
- failed Worker 1 is replaced while Workers 2-5 are preserved unless a shared defect is evidenced;
- shared poisoning recreates five workers, not four.

### Historical report containment

The older armworkers root-cause report was not deleted or rewritten. A supersession banner was added at its top so future searches cannot reasonably treat its rearm-classification language as current launch authority.

## Regression coverage

`tests/test_memory_bootstrap.py` now verifies all of the following:

- the current fresh launch contract exposes the explicit bugged/poisoned/stale/contaminated => fresh replacement rule;
- the contract says the current evidence is sufficient justification;
- all five workers are one setup pass;
- the canonical swarm template says five workers, not four;
- Workers 2-5 are armed with Worker 1 rather than held;
- the stale phrases `Exactly four recurring workers per fresh generation` and `fresh four-worker generation` are absent.

This closes the exact gap that allowed the assistant to retrieve correct five-worker policy while still being steered by stale four-worker/rearm artifacts.

## Scheduler impact from this incident

The assistant made two bad scheduler transitions before this policy repair:

- it first created a fresh `Portfolio Worker 1G?5G` generation;
- then, after misreading the historical rearm rule, it disabled `1G?5G` and re-enabled the old `Portfolio Worker 2E`.

Those scheduler changes are operational fallout, not the policy fix itself. The correct next fleet action is a fresh five-worker replacement because the user explicitly states the workers are bugged. The bugged old worker must not be treated as a healthy rearm target.

## Acceptance criteria

The policy repair is accepted only if:

1. the regression test passes;
2. bootstrap behavior retains the current five-worker launch rule and excludes the superseded four-worker rule;
3. the canonical template contains no four-worker fresh-generation topology;
4. a future `arm five` request in the presence of a current bugged/poisoned fleet cannot resolve to `REARM_EXISTING`;
5. enabled/scheduled state is never described as execution proof.

## Root cause

**Primary:** stale/conflicting policy artifacts remained discoverable without a strong enough current-mode guard.  
**Secondary:** regression tests checked the five-worker launch contract but did not check the canonical swarm template or the bugged=>fresh decision boundary.  
**Execution error:** the assistant treated a historical incident report as decision authority and reversed a justified fresh reset.

## Prevention rule

When current user/live evidence says a worker fleet is bugged, poisoned, contaminated, stale, or missing required tool sessions, the orchestration mode is already `FRESH_GENERATION`. Replace the affected workers. Do not re-enable them as a corrective move. Do not let historical rearm warnings overrule the current defect state.
