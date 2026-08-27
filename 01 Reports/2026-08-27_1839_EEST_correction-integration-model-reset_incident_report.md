# Correction integration regression: local correction erased the working model

Date: 2026-08-27 18:39 EEST
Issue: #123
State: PROVEN for the observed response pattern; root cause UNKNOWN.

## Boundary

The user had restored substantially richer recent-conversation context and asked for help with a current assistant regression. The assistant repeatedly treated each user correction as if it invalidated the whole working model instead of changing only the proposition actually corrected.

Observed sequence:

- User: `this was never a problem efore`
- Assistant correctly narrowed the historical-prevalence claim, but then over-weighted a same-day shared-policy rewrite.
- User: `i mean im not meant to deny everything why are you so lobotomized`
- Assistant recognized that corrections should constrain rather than erase prior evidence.
- Later, assistant proposed rolling back a Personal Instructions paragraph as the strongest candidate.
- User: `that was added because you thought 57 second test was proof of stability on a known crashing server` and then `but it's gone`
- Assistant discarded that candidate, but immediately widened the rollback target to the full Personal Instructions + memory-context combination.
- User: `we are not rolling back`

## Failure

The failure was not ordinary disagreement. The assistant used a destructive update rule for its own reasoning: a new correction caused the prior model to be replaced wholesale. Valid observations, still-live hypotheses, and already-falsified hypotheses were not kept separate. This produced oscillation and premature configuration-change recommendations.

The user should not need to deny every over-broad inference individually to keep the assistant on course.

## Correct behavior

Apply corrections incrementally:

1. Preserve observations and supplied facts that the correction does not contradict.
2. Mark only the corrected proposition as narrowed, rejected, or unknown.
3. Keep remaining live hypotheses explicitly live rather than rebuilding the theory from zero.
4. Do not recommend rollback or configuration mutation merely because one explanatory branch changed.
5. Continue the original task unless a new fact makes that task impossible or the user changes it.

This is a reasoning/replay rule, not authorization to mutate ChatGPT memory, Personal Instructions, settings, or the Vault memory bank.

## Acceptance

A replay passes when a user correction changes only the affected claim, preserves the original task and unaffected evidence, and does not trigger an unrelated rollback/configuration recommendation.
