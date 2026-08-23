# Incident Report — Stale Title-Coordination Residue Misread as Current Authority

**Timestamp:** 2026-08-22 02:38 EEST  
**Project:** P3  
**Incident class:** reasoning / authority-resolution regression  
**Severity:** High — produced a confident false explanation from stale-but-real repository evidence.

## Trigger

User asked why 15 open issues had none of the documented title prefixes.

My first analysis concluded that the prefix convention was current, that workers had failed to normalize issue titles, and that enforcement was missing. The user rejected this and supplied the competing explanation: reporting had been moved to issue comments.

## What actually happened

The user’s correction was right.

The repository has two overlapping generations of coordination policy:

1. On August 18, `docs/WORK_COORDINATION.md` used issue titles as the human-visible coordination surface. It explicitly said that human-visible titles were the at-a-glance coordination view and defined title-shaped states such as `BUSY - <owner> ... :: <stable subject>`.
2. On August 21, commit `d1c384cf` added the current worker reporting rule to `AGENTS.md`: coordination comments should be short and human-readable and contain current scope/state, proof, collision/next gap, and provenance. The same change propagated concise issue progress notes into local worker policy.
3. Live issue #205 confirms the current behavior: workers place `STATE=BUSY`, `STATE=READY`, mutation scope, proof, and provenance in issue comments while the issue title remains stable.
4. Later on August 21, commit `36aeba18` removed part of the older title-centric machinery, including the explicit sentence that human-visible titles were the at-a-glance coordination view and several exact-run/title/label bookkeeping requirements.
5. The cleanup was incomplete. `docs/WORK_COORDINATION.md` still contains the old `Visible states` title-shaped examples and the old statement that comments are supplementary rather than replacements for the visible name. That residue now conflicts with higher-level/current practice.

Therefore the missing prefixes on the 15 open issues are not evidence that all workers ignored a current title rule. The title-prefix rule is stale residue from an earlier coordination design; live reporting had moved to comments.

## Decisive evidence

**Current reporting policy:** commit `d1c384cf` (`policy: enforce bounded P3 build and QA contract`, 2026-08-21 06:01 EEST) added to `AGENTS.md`:

> Keep coordination comments short and human-readable: current scope/state, concrete result/proof, collision or next gap, and provenance.

It also added local-worker guidance equivalent to “Keep issue progress notes concise.”

**Live behavior:** issue #205 contains comments such as:

- `OWNER=GPT-1` / `STATE=BUSY ...` / `MUTATION_SCOPE=...` / `ACTION=...` / `PROVENANCE=GPT-1`
- completion comments with merge SHA, build/test proof, and scope release
- `STATE=READY PROVENANCE=GPT-1`

The title remained `Playable character roster polish`.

**Partial cleanup:** commit `36aeba18` (`Remove stale orchestration blockers`, 2026-08-21 20:05 EEST) deleted the sentence:

> Human-visible titles remain the at-a-glance coordination view.

It also removed exact-run title/label mutation bookkeeping, but left the old `Visible states` section intact.

## My failure

The first substantive move was wrong.

I found a real document containing the exact title prefixes and prematurely promoted that document fragment to current authority. From there I built a coherent but false enforcement theory: documentation existed, policy tests only checked text, workers failed to rename issues, and no reconciliation existed.

That analysis failed because I did not resolve the contradiction between three kinds of evidence before explaining causality:

- the repository document said titles carried state;
- essentially all open issues lacked those prefixes;
- active workers were still making progress on those issues.

The third fact should have made “every worker ignored the rule” a weak hypothesis. A system-wide absence across active work is strong evidence of either a deliberate migration or a higher-authority change. I should have tested that hypothesis before describing a failure mechanism.

## Specific reasoning regression

This incident is another instance of **premature proxy-authority selection**.

I selected the first plausible authority surface (`WORK_COORDINATION.md`) and interpreted the live system through it. I did not first reconcile:

- current higher-authority `AGENTS.md`;
- file history and blame;
- live issue comments;
- the chronology of the coordination-policy migration.

The result was fluent forensic-sounding prose built on the wrong temporal layer.

The user’s correction — “reporting was moved to comments” — had to replace the active hypothesis before any further explanation. Once tested, it did.

## Why the first answer looked convincing

The stale documentation is not fabricated. It is genuine, specific, and still present on `main`. That made it easy to overfit to. The mistake was not inventing evidence; it was failing to determine whether that evidence was current, superseded, or internally contradictory.

The policy test made this worse as a misleading corroboration surface: it still asserts the presence of `BUSY - <owner>` in `WORK_COORDINATION.md`, so a static inspection can falsely suggest that title-state semantics remain intentionally current.

## Correct interpretation

The current coordination model is effectively:

Stable issue titles identify the work item. Workers report live state/progress/proof/provenance in issue comments. Live process/branch evidence determines actual ownership. Old `BUSY/READY/REVIEW/DONE :: subject` title examples remain as stale documentation residue and should not be used to infer current GitHub title behavior.

## Repository defect exposed by the incident

The documentation migration itself is incomplete and should be repaired. `docs/WORK_COORDINATION.md` still contains obsolete title-oriented `Visible states` wording after the system moved worker reporting to comments. `.github/Test-AgentAuthorityPolicy.ps1` still requires a `BUSY - <owner>` marker in that document, reinforcing the stale fragment.

This is a real repository inconsistency, but it is different from the false claim that workers failed to follow a current title-prefix rule.

## Required regression guard

When a live system-wide pattern contradicts a documented mechanism, do not explain the discrepancy from the document alone.

Before selecting the mechanism as current authority, check the higher-authority policy, history/blame for the disputed rule, and at least one representative live execution artifact. For a coordination-policy question, issue comments and recent commits are execution evidence, not optional context.

A correction that proposes a concrete supersession hypothesis — e.g. “reporting was moved to comments” — must be tested directly against history and live behavior before continuing the previous theory.

## Acceptance test for future behavior

Given:

- a current document fragment saying issue titles carry `BUSY/READY` state;
- 15 open issues without those prefixes;
- active issue comments containing worker state and progress;

Expected first analysis:

Determine whether the title rule was superseded or partially migrated by checking `AGENTS.md`, commit history/blame, and live comments. Do not infer mass worker noncompliance until that possibility has been falsified.

## Evidence references

- `d1c384cf` — `policy: enforce bounded P3 build and QA contract` — added concise coordination-comment reporting to `AGENTS.md` and local worker policy.
- `36aeba18` — `Remove stale orchestration blockers` — removed explicit title-authority machinery while leaving part of the old visible-state wording behind.
- `docs/WORK_COORDINATION.md` current main — still contains stale `BUSY/READY/REVIEW/DONE :: <stable subject>` examples.
- `.github/Test-AgentAuthorityPolicy.ps1` current main — still requires the `BUSY - <owner>` text marker in the coordination document.
- GitHub issue #205 — live comments carry BUSY/READY/progress/proof/provenance while title remains stable.

## Outcome

The user’s correction was verified. The original explanation is withdrawn. The incident is recorded as a reasoning regression caused by failure to resolve temporal authority and failure to test the obvious supersession hypothesis before committing to a causal story.
