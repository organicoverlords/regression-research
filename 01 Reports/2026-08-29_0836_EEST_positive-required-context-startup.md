# Positive control — required-context startup succeeded

Date: 2026-08-29 EEST
Status: POSITIVE CONTROL

Before the user tested whether the assistant knew the shared-agent-policy and RED ALERT history, the assistant had already performed the required Vault startup and had read the relevant live governing context: the Vault `AGENTS.md`, `NORTH_STAR.md`, the canonical `SHARED-AGENT-POLICY.md`, and the August 28 stale-BUSY / RED ALERT recurrence report.

That prior context load materially changed behavior. When the user said to stop and write a RED ALERT only if that information had not already been read, the assistant could truthfully determine that the condition was false instead of guessing, asking the user to restate policy, or fabricating an incident.

Useful positive control: fresh-session Vault bootstrap plus targeted governing-context reads succeeded before substantive mutation and were actually available at the decision point. Preserve and regression-test that behavior across Codex, Claude, and other local coding harnesses.
