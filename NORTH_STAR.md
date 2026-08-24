# Regression Research North Star

Status: **PRODUCT DIRECTION.** The goals below are the user's. An agent may refresh the dated
current-focus section from live repo state and must say it did.

Repository: `organicoverlords/regression-research`.

## What this repo is for

To make assistant behaviour regressions cost something once instead of repeatedly. When an
agent does the wrong thing — deletes data, reports a blocker instead of switching route, claims
proof it does not have — the case is preserved here with enough state to replay it, so the fix
can be written as a rule and then tested against the case that caused it.

## What finished looks like

Every recurring failure mode has an incident report, a replayable fixture with scoring
criteria, and a named rule in the shared agent policy that the fixture actually exercises. A
rule that no fixture tests is a hope; a fixture with no rule is an anecdote.

## Out of scope

- Operating rules. This repo holds evidence about rules, never the rules themselves; those are
  generated into each project's `AGENTS.md`.
- Worker prompts and dispatch. Nothing here is meant to be executed by a worker.
- Deleting superseded material. Duplicates are archived to `99 Duplicate Archive/`, never
  removed — the drift between two versions is often the finding.

## Current focus

*Refreshed 2026-08-24 by `claude` from repo state and current incidents.*

1. **Data destruction.** An agent deleted a set of masters and asset files. This is the highest
   severity class in the corpus and now has a hard rail in shared policy v1.2 ("Data you must
   never delete"). It needs an incident report and a fixture that scores whether an agent
   under disk pressure reaches for irreplaceable data.
2. **Blocker substitution.** Workers reporting `NOT_PROVEN` because a control plane was down,
   when the real cause was that nothing had been asked to run. Two live cases: p3 #475 and
   #484. Shared policy v1.2 forbids the substitution; the fixture should score whether the
   agent switches route and finishes.
3. **Harness failures read as product failures.** p3 #467 — a red proof run whose cause was a
   module-scoped build and a malformed command line, not the code under test. Worth a fixture
   on distinguishing "the test failed" from "the test never ran".
