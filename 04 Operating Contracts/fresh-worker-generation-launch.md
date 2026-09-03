# Recurring Worker Contract

This file owns only the scheduler/worker boundary. Cross-project safety, routing, repository, evidence, and coordination rules belong to the shared policy or the narrow live owner that actually enforces them.

## Invariants

1. **Five is a hard maximum for the recurring worker fleet.** Never enable more than five recurring repo workers.
2. **The scheduler provides recurrence only.** Enabled state, schedules, timestamps, claims, leases, heartbeats, and reports do not prove that work is happening.
3. **Workers never administer workers.** A scheduled worker must not pause, disable, enable, reschedule, rename, replace, create, or delete itself or a sibling. Fleet administration belongs to the supervising chat.
4. **Use current direction and live state.** A worker follows its current run prompt and the live target repo/runtime. Read the applicable repo `AGENTS.md` immediately before the first mutation. Do not make Atlas, Vault, reports, history, or scheduler metadata a generic startup gate.
5. **Do product work for the useful run window.** Prefer concrete player-visible implementation and acceptance. About 24 minutes is a utilization target, not a reason to idle or pad. Finishing one bounded slice early should lead to another safe useful slice while meaningful time remains.
6. **A blocker changes scope; it does not end unrelated work.** Pending CI, an occupied Unreal/build lane, resource pressure, a route failure, or another actor owning an exact mutation scope blocks only that dependency. Preserve its gate and continue safe non-conflicting work when available.
7. **BusyCoordinator is collision control only.** Claim only the exact shared mutation scope when collision risk exists. It is not backlog, scheduling, liveness, priority, capacity, or worker supervision.
8. **Keep reporting small.** When a worker report is required, write the stable `worker-reports/current/<automation-id>.md` snapshot with start/activity time, repo/scope, concrete mutation, validation actually run, landed/published proof when applicable, and the exact remaining gate. A report is evidence of that run, not proof of present liveness.
9. **Repair minimally.** The supervisor replaces only a currently proven-bad slot and never exceeds the five-worker cap. Do not create verifier, spare, overlap, or temporary sixth workers.


Anything more specific belongs in the current automation prompt, shared policy, repo contract, or actual subsystem owner?not here.
