# Pending canonical memory handoff - SW-V2-20260913-005

Event: `SW-V2-20260913-005`
Source report: `01 Reports/SW-V2-20260913-005_incident.md`
Replay: `03 Fixtures and Experiments/SW-V2-20260913-005_replay.json`
Visible evidence: `02 Evidence/SW-V2-20260913-005_visible-context.json`

Kind: correction
Scope: assistant-orchestration/recurring-worker-topology
Tags: slopwall, regression, recurring-workers, topology, authority-selection, fleet-watch

Title: Scheduled worker fleet is 5 per subscription, 10 total; manual swarm is separate

Text: The recurring scheduled fleet consists of five workers in S1 and five in S2, ten scheduled workers total. Manual/on-demand swarm is separate. For actual enabled membership use the owning live scheduler; slot registry/fleet-watch is mutable coordination/recovery evidence and must be reconciled against exact scheduler state before mutation.

Interpretation: The failure was an unsupported global-cap assumption plus authority selection: scheduler truth was conflated with slot-registry projection. No new shared rule is required.
Confidence: 99
Confidence reason: Direct user correction plus canonical topology, live slot-registry output, and fresh S1 fleet-watch all agree on the five-per-partition model and guarded peer recovery semantics.

State: PENDING_CANONICAL_MEMORY - this file is a handoff/index candidate, not a canonical memory-bank entry and not closure proof.
