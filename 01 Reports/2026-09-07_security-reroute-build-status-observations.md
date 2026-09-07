# Security reroute / build-status observation log

Date: 2026-09-07
Status: OBSERVATION ONLY — not definitive evidence of causation

## Observed pattern

- The user reports that security/model reroutes appear unusually often while ChatGPT is checking build or process status.
- This appears to occur even when SSH is not involved, so SSH alone is unlikely to explain the pattern.
- Possible correlates seen in these moments include repeated process/service introspection, frequent polling, long-running tool sequences, and compound shell/PowerShell status commands.
- None of those correlates should be treated as a proven trigger without platform telemetry.

## Screenshot observation (~17:17 EEST)

A screenshot supplied in chat showed the UI banner:

> "Our systems are thinking a bit more about this request before responding. You can retry with a faster model..."

At the same time, the visible execution trace was dominated by status/monitoring actions such as:

- "Continued monitoring process output"
- "Monitored Raincoat quality measurement integration process completion"
- "Checked process status and output for continued work"
- "Monitored Ethereal asset replay and reporting process completion"

The surrounding work was Blender/Raincoat asset generation and validation rather than SSH administration.

Interpretation: this strengthens the observed correlation between reroute/thinking-more events and repeated build/process-output monitoring, but it does **not** establish that status checking caused the reroute.

## Competing explanations / confounders

- overall tool-call density or long-running task complexity
- repeated process introspection regardless of transport
- command complexity / shell nesting
- generic model-routing or platform load behavior unrelated to the commands
- other hidden safety/routing signals not visible in chat

## Suggested low-risk experiment

When monitoring builds, compare reroute frequency while using:

1. one minimal, single-purpose read-only status query per check;
2. lower polling frequency;
3. reuse of an existing process/read handle where supported;
4. no unrelated process enumeration or compound command wrappers.

Treat any change in reroute frequency as additional observational evidence only, not proof of mechanism.
