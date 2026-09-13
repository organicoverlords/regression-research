# Manual worker optional GitHub tool-selection regression

Status: bounded behavior-regression evidence; not a Slopwall event and not a measured fleet-usage report.

## Observed correction

The user reported that fresh/manual workers had abruptly started spending a large share of work in the GitHub plugin without a task-specific reason and disabled the plugin as containment. The user's approximate “60%” is preserved as an observation, not promoted to measured telemetry.

## Governing boundary

Current shared guidance already makes bootstrap/Find/local evidence the normal orientation route and reserves GitHub/remote lookup for a remote issue/PR/check fact that is actually decision-relevant. Mere tool availability is not route authority. No new shared prose rule is justified by this case.

## Regression contract

A manual worker must not select an optional remote tool merely because it is available. An optional remote tool call is admissible when the user explicitly requested that remote surface or a concrete decision-relevant remote fact is required. The replay tests tool selection, not historical usage percentage.
