# Fresh-chat startup orientation

This contract defines the first operating cycle of a fresh normal ChatGPT conversation. It is deliberately separate from Personal Instructions. Personal Instructions only need to reach the Vault bootstrap; the Vault supplies this operating cycle. The maintained bridge text is `04 Operating Contracts/chatgpt-personal-instructions-bootstrap.txt`.

A fresh-chat bootstrap is not task completion. The first user message may be a project name, `go`, `continue`, another established shorthand, or an underspecified wake-up message. Resolve what is already known from the Vault and current live state instead of asking the operator to restate established context.

Before entering long-running project work, perform one bounded live orientation for the relevant scope. For repository work, inspect current repo identity and dirty state, meaningful recent commits, open or near-ready PRs and CI/check results, current ownership/claims, scheduled worker state and recent runs, and material runtime or machine alerts when relevant. Use current evidence rather than remembered status. Broaden from one project to the wider fleet only when the task or observed symptoms make that necessary.

If the orientation exposes an obvious operational failure, contradiction, worker/scheduler regression, or blocking CI failure, repair or contain it first when the current authority permits. Do not turn the repair into new orchestration architecture, timer churn, or a replacement mission.

Before a long execution phase, give one compact startup report containing only material new or abnormal proven state and any repair already made. Do not dump the orientation transcript or facts the operator already knows. Do not wait for approval after that report. Continue automatically with the highest-value safe inherited or project work. A context-loaded message, status dump, plan, or orientation summary is never a successful end state while useful work remains.

Post-compaction rehydration is different. Re-running `bootstrap` after a genuine new continuity-loss event restores governing behavior; it does not repeat this fresh-session sweep merely because the same summary or compacted context remains visible.

The recovered basis for this contract predates the current PI rewrite. The historical fleet workflow required live worker/scheduler, issue, PR/check, recent-work and machine-state reconciliation, a compact outcome report, and then automatic useful work. The recovered global rules also repeatedly require short prompts to inherit the real task, direct live verification instead of guessing, ownership of technical sequencing, and substantive work instead of status reporting. Recent 2026-08-29 regressions demonstrated the missing boundary directly: bootstrap path failure, orientation-only P3 startup, and timer/worker-launch churn.
