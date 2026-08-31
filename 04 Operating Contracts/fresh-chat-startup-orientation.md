# ChatGPT session continuity

Normal ChatGPT continuity comes from the current conversation and ChatGPT Memory. There is no Vault behavior bootstrap or mandatory Vault startup read.

Short or elliptical turns inherit the active task and established context. The current user message updates that context; explicit current facts override conflicting remembered or historical material.

For stack/infra work, consult the Stack Atlas before deciding relevance or blast radius, then check the relevant live sources. For non-stack work, do not perform an unrelated stack sweep.

When recurring execution workers are active, read their current reports directly from `C:\Users\Lauri\Desktop\vault\worker-reports\*.md` on normal ChatGPT turns. Surface and reconcile new substantive results, `BLOCKED` reports, stale `RUNNING` reports, or missing current report evidence without waiting for the user to relay worker output. DevProgressBoard/operator-live, scheduler, claim, lease, heartbeat, or enabled state may display context but never sits in the supervision path or substitutes for direct execution/report evidence; this compact direct check is supervision, not a broad stack sweep.

Current-state answers require current evidence. Vault history, memory, schedules, BUSY metadata, old reports, and prior snapshots may provide context but do not prove current state.

Vault search/context/history is optional notebook-style enrichment. Use it only when relevant history would materially improve the answer or avoid rediscovery.
