# ChatGPT session continuity

Normal ChatGPT continuity comes from the current conversation and ChatGPT Memory. There is no Vault behavior bootstrap or mandatory Vault startup read.

Short or elliptical turns inherit the active task and established context. The current user message updates that context; explicit current facts override conflicting remembered or historical material.

For stack/infra work, consult the Stack Atlas before deciding relevance or blast radius, then check the relevant live sources. For non-stack work, do not perform an unrelated stack sweep.

When recurring execution workers are active, supervise their direct `C:\Users\Lauri\Desktop\vault\worker-reports\*.md` evidence at natural boundaries during substantive ChatGPT work (after meaningful mutations/tests, before changing scope, and before final reporting). Use `python tools\worker_supervision.py claim` before acting on report events: each exact report version/condition is event-scoped through the existing BusyCoordinator, so only the chat that actually acquired that event may reconcile it. After the event is genuinely handled, run `worker_supervision.py ack` to write its immutable handled receipt under `worker-reports\.supervision\handled`; never acknowledge before handling. If the owning chat cannot finish, leave no handled receipt and release or let the event lease expire so another chat can recover it. Surface and reconcile new substantive results, `BLOCKED` reports, stale `RUNNING` reports, or missing current report evidence without waiting for the user to relay worker output. DevProgressBoard/operator-live, scheduler state, generic claims/leases, heartbeats, or enabled state may display context but never sits in this supervision path or substitutes for direct execution/report evidence.

Current-state answers require current evidence. Vault history, memory, schedules, BUSY metadata, old reports, and prior snapshots may provide context but do not prove current state.

Vault search/context/history is optional notebook-style enrichment. Use it only when relevant history would materially improve the answer or avoid rediscovery.
