# Fresh-chat startup orientation

The generated Vault bootstrap is the executable startup authority. This document explains its `fresh_session_startup` instructions; it is not a second behavioral authority.

Fresh normal-chat sequence: **complete behavior bootstrap → consume mandatory stack-map glance → consume bounded 20-item recent-memory glance → acquire bounded live status → respond**. The map is descriptive, the memory glance is historical orientation, and current user direction plus verified live state win.

The mandatory `stack_map_glance` keeps one compact operating model in every fresh chat: **user → ChatGPT → work → proof → result**, with the assistant internally responsible for **KNOW → COORDINATE → EXECUTE → RECOVER → PROVE**. This is intentionally small enough to live in the bootstrap payload.

The maintained human map is `docs/assistant-stack-human-map.md`. The detailed capability/authority map for assistants is `docs/assistant-stack-capability-map.md`, backed by `docs/assistant-stack-capability-map.json`. Normal chats consume the compact bootstrap map; full-map reading becomes mandatory before stack/architecture/control-plane design or mutation.

Before proposing a new cross-stack mechanism, inspect the full assistant map and the current owner of the requested capability. If an existing authority already owns it, reuse it, make the smallest evidence-backed owner-local change, or do nothing. Do not recreate #271-style capability invisibility as another subsystem.

Map freshness is enforced during repository verification. Changes to declared stack-defining files must refresh both the human map and machine-readable map in the same change. The guard is `tools/stack_map_guard.py`; its watched paths are intentionally narrow so ordinary feature work does not cause documentation churn.

A fresh-chat bootstrap is not task completion and is not live orientation. The first user message may be a greeting, a project name, `go`, `continue`, another established shorthand, a status question, or an underspecified wake-up message. That first message triggers the startup sweep; it never bypasses it. Resolve what is already known from the Vault and current live state instead of asking the operator to restate established context.

Immediately after the map and memory glances, and before the first substantive response of every fresh normal chat, perform one bounded live orientation for the relevant scope. For repository/project work, inspect current repo identity and dirty state, meaningful recent commits, open or near-ready PRs and CI/check results, current coordinator ownership/claims, scheduled-worker state and recent runs, and material runtime or machine alerts. Broaden from one project to the wider fleet only when the task, active alerts, or observed symptoms make that necessary.

The assistant owns closing the live-status gap. `bootstrap` deliberately contains behavior, the compact map, and bounded historical orientation rather than current live status. `live_status_included: false` is therefore an outstanding obligation, not permission to answer from memory.

If the orientation is clean, stay quiet about the sweep and answer normally. If it exposes a material abnormality, lead the first substantive response with that abnormality and any safe repair or containment already performed. Do not turn repair into new orchestration architecture, timer churn, or a replacement mission.

After startup, re-check relevant live sources before any later answer whose correctness depends on current repo/coordinator/worker/CI/runtime state. A previously acquired snapshot is timestamped evidence, not permanent authority.

For a user-facing worker-status question, inspect the current execution surface immediately before answering. Only a currently running automation/run/session/process or in-flight tool/command tied to that worker/scope can prove `working now`. Claims, leases, heartbeats, checkpoints, schedules, branches, PRs, commits, reports, and prior snapshots have zero positive weight for liveness and must never make the answer look healthy or complete. If no current execution is observed, answer `not working now`; if the execution surface itself cannot be inspected, answer `unverified`.

When the user asks about progress or whether useful work happened, measure concrete output during the relevant work window: completed commands/tools/tests, created commits, written artifacts, PR updates, or other direct work products. Claim timestamps may delimit that measurement window, but claim existence itself adds zero evidence. Reconcile collision-control state separately and never substitute it for the live-work answer.

For long execution, continue automatically with the highest-value safe inherited or project work after any necessary abnormality report. Do not dump the orientation transcript, map internals, or facts the operator already knows. A context-loaded message, status dump, plan, or orientation summary is never a successful end state while useful work remains.

Post-compaction rehydration is different. Re-running `bootstrap` after a genuine new continuity-loss event restores governing behavior; it does not repeat the fresh-session sweep merely because the same summary or compacted context remains visible. A genuinely new fresh session still requires the map glance and new pre-response live orientation.
