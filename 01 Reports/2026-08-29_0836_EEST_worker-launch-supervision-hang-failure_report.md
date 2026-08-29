# Worker-launch supervision hang failure report

**Date:** 2026-08-29
**Scope:** fresh recurring worker generation / supervising ChatGPT run
**Disposition:** confirmed orchestration and user-experience failure; launch contract corrected

## What happened

The worker-launch flow left the supervising chat visibly "working" for minutes while the UI showed repeated opaque tool calls and a continuously increasing timer. The user received no useful status boundary while the assistant was inspecting state and creating workers. After creating `Portfolio Worker 1E`, the worker prompt required `@plugin2` as its first actual action, yet the resulting worker response was `RESET_REQUIRED: TOOLS` without an actual `@plugin2` attempt in that worker turn.

The screenshot therefore exposed two distinct failures:

- **silent supervision:** the parent chat behaved as if "remaining active" meant it could simply hang around in tool work while the user watched a timer;
- **unsupported launch failure:** Worker 1E emitted a tool-reset conclusion without first executing the required tool route.

The surrounding parent-chat evidence also showed that local tool calls had been working immediately before the scheduled task was created. That made the unsupported `RESET_REQUIRED: TOOLS` especially clear: it was not evidence of a proven transport outage.

## Why the "hang around and wait" method does not work

Keeping the supervising chat alive solely to wait for a timer is the wrong control model.

1. **It provides no useful user-visible state.** A growing timer and generic "Called tool" rows do not tell the user whether the assistant is progressing, blocked, polling, or stuck.
2. **It turns waiting into the mission.** The assistant starts spending its execution budget observing scheduler state instead of advancing repositories.
3. **It encourages low-information polling.** Repeated timer/task checks add noise but do not improve acceptance evidence until the launch window has actually elapsed.
4. **It blurs setup and acceptance.** Creating/enabling a scheduled task can begin to feel like progress even though the only meaningful acceptance event is the worker's real first execution.
5. **It makes failures easier to fabricate from expectation.** In this incident Worker 1E jumped to `RESET_REQUIRED: TOOLS` without the required first tool attempt.
6. **It wastes the five-task topology.** A separate verifier/wakeup timer competes with the same scheduler capacity that should be used for the five actual workers.
7. **It is fragile across long turns and interruptions.** A supervising chat that is merely waiting can accumulate stale assumptions and opaque state instead of performing checkable work.

The correct supervision model is not "stay open and wait." It is **arm, report, work, verify, repair if necessary, and keep working**.

## Correct five-worker launch sequence

1. Retire poisoned/stale workers that are being replaced.
2. Create and enable **all five** fresh recurring workers in one bounded setup pass.
3. Schedule **Worker 1 to launch immediately/as soon as the scheduler permits**. Workers 2-5 may be staggered, but they are already armed.
4. **Immediately tell the user the five-worker fleet is armed and Worker 1 has been given the immediate launch.** This is a setup report, not a health claim.
5. **Immediately begin substantive repository work in the supervising chat.** Do not wait on the scheduler and do not create a separate verifier timer.
6. When Worker 1's expected launch window has elapsed, reach a natural repo-work boundary and verify its actual first run:
   - the scheduled run fired;
   - `@plugin2` was actually invoked;
   - local `git` succeeded and recorded repo/branch/HEAD/origin;
   - local `gh` succeeded;
   - standalone BusyCoordinator ownership was checked;
   - a concrete safe scope was selected;
   - substantive engineering work began;
   - the proof record was written only after those facts were true.
7. If Worker 1 is healthy, **continue the supervising chat's repository work until the current bounded work is done**. The recurring five-worker fleet continues independently.
8. If Worker 1 is not healthy, **replace the failed Worker 1 immediately, schedule the replacement immediately, report the repair, return to repo work, and verify again after the new launch window**. Repeat this cycle until Worker 1 is proven healthy. Do not use Workers 2-5 as substitute proof and do not tear them down unless evidence shows a shared defect.

## Reporting contract

The supervising chat has three useful user-facing transitions:

- **armed:** all five workers exist/enabled and Worker 1 has an immediate launch scheduled;
- **repaired:** a failed Worker 1 was replaced and the immediate launch cycle restarted;
- **accepted:** Worker 1 produced real local-tool/repo/ownership/substantive-work proof.

Between those transitions the assistant should be doing repository work, not filling the UI with timer-watching chatter. If the repository work is long, normal compact progress reporting still applies after meaningful work or a direction change.

## Regression rule

The old four-worker / "keep the supervising run active while waiting" rule is superseded. The required invariant is now:

> **Arm all five, launch Worker 1 immediately, report the arm, work on repositories, verify Worker 1 after its launch window, and repair-and-repeat while continuing useful work until Worker 1 is proven healthy. Never use silent waiting as supervision.**

Schedule state remains setup evidence only. First-run execution remains acceptance evidence.