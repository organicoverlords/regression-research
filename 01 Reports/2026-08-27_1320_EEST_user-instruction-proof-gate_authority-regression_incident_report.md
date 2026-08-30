# Incident: user instruction was incorrectly put behind a proof gate

Date: 2026-08-27 13:20 EEST
Scope: Memory Bank / issue #172 authority firewall

## What happened

While fixing the earlier failure where an unproven assistant interpretation could silently influence behavior, the assistant proposed and implemented an authority rule requiring a stored behavior-changing memory to be `PROVEN`. The user immediately corrected this: the user does not have to prove an instruction in order to change assistant behavior.

The proposed rule was wrong because it conflated two independent dimensions:

- **Instruction authority:** what behavior the assistant must follow. A current explicit user instruction applies immediately. A faithfully persisted direct user preference/decision/correction remains behavior-authoritative because it is a user instruction, not because an external fact was proven.
- **Claim confidence:** whether a factual or causal claim about the world is PROVEN, PROVISIONAL, or REJECTED. This can constrain what the assistant asserts as fact, but it cannot veto a user instruction.

## Why the assistant made the mistake

The immediate design goal was to stop relevant but unverified memories from silently becoming policy. The assistant over-generalized the epistemic safeguard and reused the bank's factual `state` field as an authorization gate. That was an attractive implementation shortcut because `PROVEN` already existed and had clear semantics, but those semantics belonged to evidence confidence, not command authority.

This also reproduced the user's larger complaint in reverse: the system was willing to derive behavioral policy from assistant interpretation, yet attempted to demand evidentiary proof from the user before honoring a direct correction.

## Correct rule

1. Current explicit user instruction has highest behavioral authority and is not subject to a factual proof gate.
2. In persisted memory, direct user `preference`, `decision`, or `correction` records with explicit `user-instruction:` provenance may change behavior regardless of whether their attached factual claim state is PROVEN or PROVISIONAL.
3. A user-sourced `fact` or `lesson` is evidence, not automatically policy.
4. Assistant-derived lessons, incident interpretations, historical material, screenshots, and other retrieved evidence do not gain behavioral authority from relevance or from being `PROVEN`.
5. Hidden external causality remains independently uncertain. Honoring the user's instruction or accepting the user's account of their own action/intent does not prove an external platform mechanism.
6. A newer PROVEN assistant-derived lesson must never override a direct user correction merely because the direct correction is marked PROVISIONAL.

## Regression proof

Issue #172 now contains an executable regression test named `test_proven_derived_lesson_cannot_override_provisional_direct_user_instruction`. The authority test suite also checks that user-sourced facts remain evidence rather than policy and that direct user corrections have behavior authority without claiming external causal truth.

This incident must remain distinct from the earlier `mem-20260827-afce2baf` security-warning/cross-contamination incident. The earlier incident exposed silent policy synthesis from ambiguous evidence; this incident exposed the opposite authority error introduced while repairing it.
