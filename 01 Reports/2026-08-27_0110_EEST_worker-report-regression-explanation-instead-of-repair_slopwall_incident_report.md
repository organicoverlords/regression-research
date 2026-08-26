# Incident report — worker-report regression answered with explanation instead of repair

Timestamp: 2026-08-27 01:10 EEST
Scope: response-quality / worker-report-format / shared-policy
Trigger: `slopwall`

## Incident
The user asked why current workers had lost the established worker-report presentation and were now emitting PROVEN-heavy status text. The assistant inspected shared policy and correctly found that `PROVEN / NOT_PROVEN / REJECTED` is globally present in the shared proof rules and propagated into generated repo `AGENTS.md` blocks. It also found a 23:55 memory-scope policy change that increased the salience of `PROVEN`.

The response still failed. It delivered a long causal explanation and stopped, even though an immediately preceding 01:00 incident had already identified this exact failure mode: explaining the formatting regression instead of restoring the worker-report format. The user then issued `slopwall`.

## What was wrong
The answer over-attributed the regression to the 23:55 memory-scope change. The proof taxonomy itself was already in the shared policy from at least Aug 25, so that commit can only be treated as an amplifier, not the origin of the worker-report style. The answer also failed to separate three surfaces cleanly: the canonical shared-policy source, dirty/generated local `AGENTS.md` copies workers are currently reading, and the separate response-style seed that already says no canned templates and no bullets.

Most importantly, the answer did not finish the live task. It identified the mechanism but did not bound or apply the corrective policy change that preserves epistemic proof states while restoring the established worker report presentation, including worker/branch identity, concrete status, percentage/progress bar, compact evidence, and normal prose.
## What drove the poor answer
The main driver was task misclassification: the assistant treated “why” as a request for retrospective explanation rather than as a continuation of the active report-format repair. Tool use then widened into policy archaeology. Because the assistant searched for causal provenance before checking the newest directly matching incident, it rediscovered evidence the Vault had already summarized and reproduced the same explanation-first behavior.

A second driver was salience bias from the shared proof vocabulary. Once `PROVEN` was found in several policy surfaces, it became the organizing concept of the diagnosis even though the user's complaint was specifically that this vocabulary had displaced the report UX. A third driver was premature causal closure: the recent 23:55 commit looked temporally attractive, so the answer framed it as the key cause despite older policy evidence showing the taxonomy predated it.

## Corrective lesson
Evidence states must continue to constrain claims and actions, but they must not define worker-report presentation. A worker report should preserve the established compact status/progress format; evidence labels appear only where a particular uncertainty needs to be surfaced. When a live shared-policy regression is identified and the correction is bounded, the assistant must repair the governing source and propagate/verify it rather than stop after explaining the mechanism.

Evidence: current conversation screenshot and user corrections; `C:\Users\Lauri\.agents\SHARED-AGENT-POLICY.md`; generated `p3\AGENTS.md` and Tiny3D `AGENTS.md`; `01 Reports/2026-08-27_0100_EEST_worker-report-format-proven-spam_slopwall_incident_report.md`; `.agents` history including `cd55ae6`.