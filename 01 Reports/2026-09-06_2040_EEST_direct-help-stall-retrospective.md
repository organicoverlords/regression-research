# Incident report — direct-help request turned into 25 minutes of non-helpful orchestration

Timestamp: 2026-09-06 EEST
Category: REGRESSION / SLOPWALL / ORCHESTRATION / RESPONSE-QUALITY / TOOL-CHURN

## User request that should have controlled the work

The user asked for immediate help with runaway command activity:

- `help`
- `powershell git gh everything please help`

The required outcome was narrow: identify the actively churning PowerShell/Git/GitHub process trees, stop only the offending transient work, preserve unrelated infrastructure and the five timed workers, verify the churn stopped, and return a concise result.

## What actually happened

The assistant initially found real shell/Git/GitHub churn, but then expanded a direct incident-response task into scheduler administration, policy repair, fleet archaeology, report archaeology, GitHub/PR bookkeeping, transport-history inspection, and repeated state verification.

The largest error was disabling recurring workers. Process churn and scheduler membership are separate control surfaces. The user did not authorize worker cancellation. Disabling Alder, Pine, and Hazel reduced the requested five-worker fleet and created a second incident while the original process problem was still being handled.

After the user corrected that error, the assistant kept spending the interaction on proving and documenting scheduler-disable behavior instead of returning to the direct-help objective. This converted useful evidence gathering into a slopwall: lots of internal activity, little additional user-relevant help.

## Where the ~25 minutes went

The time was not consumed by `bootstrap-glance`; current bootstrap is ~0.2 s internally and well under a second end-to-end. The delay came from assistant-selected follow-on work:

1. Process-tree inspection and cleanup — relevant.
2. Unauthorized scheduler mutation — harmful and created compensating work.
3. Re-enabling and repeatedly verifying workers — compensating work caused by step 2.
4. Reading recurring-worker reports and historical uptime incidents — useful only after immediate stabilization, not as the main response path.
5. Editing shared policy and recurring-worker contracts — broader than the immediate direct-help request.
6. GitHub PR/policy convergence and verification — not required to stop the active churn.
7. Transport-log archaeology around scheduler invocation times — diagnostic follow-up, not direct incident relief.
8. Repeated scheduler/worker/status reads — useful for evidence, but excessive relative to the user's immediate need.

The result was workflow amplification: one urgent local troubleshooting request became a multi-system orchestration exercise.

## Root causes

### 1. Interactive help was incorrectly treated like an orchestration/worker-control task

The assistant inherited global machinery intended for durable engineering work and applied it to an urgent local troubleshooting request. Reporting, policy, fleet supervision, issue/PR convergence, and historical investigation displaced the immediate operational objective.

### 2. The assistant confused process ownership with scheduler membership

The observed churn was MCP-spawned shell/Git/GitHub activity. The correct control surface was the offending process tree or its spawning workflow. Disabling timed workers was an escalation across a different control plane without authorization.

### 3. Evidence collection became a substitute for resolution

Once the active churn had been cleared, the assistant continued gathering evidence about worker disable recurrence and policy history. That evidence is useful for a separate follow-up, but it did not materially improve the user's immediate state quickly enough.

### 4. Self-generated remediation created more work than the original incident

Disabling workers forced restoration, scheduler verification, policy changes, historical comparison, and new incident documentation. The assistant created a larger recovery workload than the initial process cleanup required.

### 5. The response-quality failure was a slopwall, not merely verbosity

The failure was low substance relative to the user's goal. The assistant produced a large amount of process and meta-work while the user was asking for direct operational help. Even technically valid diagnostics were low-value at that moment because they displaced the requested result.

## Concrete evidence

- Current `bootstrap-glance` measured 215.6 ms internally and completed normally; bootstrap itself is not the source of multi-minute delay.
- MCP is currently live.
- The canonical timed fleet is currently 5/5 enabled: Alder, Pine, Maple, Aspen, Hazel.
- Historical evidence already showed workers could become disabled after scheduler invocations, so disabling more workers during process troubleshooting was especially unsafe.
- Existing incident evidence: `01 Reports/2026-09-06_2021_EEST_worker-fleet-disable-and-assistant-cancellation-regression.md`.
- Existing uptime evidence: `worker-reports/observations/2026-09-04-worker-uptime-loop.md`.
- Existing peer-recovery evidence: `02 Evidence/recurring-worker-peer-recovery-2026-09-06.md`.

## Correct direct-help path

For a future request equivalent to `powershell git gh everything please help`:

1. Identify the exact currently churning process trees and their parent/spawner.
2. Kill only the offending transient process trees.
3. Do not mutate recurring-worker schedules, enabled state, prompts, names, or fleet membership unless the user explicitly asks for that scheduler change.
4. Check once that the offending process pattern is no longer respawning.
5. If it respawns, repair or stop the exact spawning workflow; do not fan out into unrelated policy/history work first.
6. Return the concrete result immediately. Preserve deeper forensic/policy follow-up separately and only when it materially prevents recurrence.

## Recurrence-prevention invariant

Urgent direct-help requests must optimize for **time-to-user-relief**. Internal evidence, reporting, policy, PRs, worker supervision, and historical archaeology are secondary. They may follow stabilization, but they must not become the primary work while the user's requested operational outcome remains unresolved.

## Status

The process-churn incident was stabilized and the five timed workers are restored. The main failure documented here is the assistant's unnecessary 25-minute expansion of a direct-help request into orchestration and policy work.
