# INCIDENT REPORT — ChatGPT Custom Instructions visible in UI but absent from model-visible context

Incident ID: `INC-20260827-002911-EEST-484b75e60565`
Date: `2026-08-27 EEST`
Source: current ChatGPT conversation plus user-supplied Personalization screenshot
Evidence screenshot: `/Regression Research/02 Evidence/2026-08-27_custom-instructions-ui_INC-20260827-002911-EEST-484b75e60565.png`

## Incident identity

The user showed ChatGPT Settings → Personalization with a populated `Custom instructions` field. The visible text includes a startup/repo-work rule beginning `At the start of a new conversation or repo-work session...` and directing a bounded recent-memory glance from the vault. In the same conversation, that rule was not present in the model-readable instruction/context supplied to the assistant.

This is recorded as a ChatGPT personalization/context-delivery mismatch. The core omission is not attributed to assistant choice: the missing app instruction was not available in the assistant-visible instruction stack. The exact internal layer that failed is unknown.

## Requested outcome

The configured app Custom Instructions should be available to and influence ChatGPT on each relevant turn, so the user can rely on that field as the behavioral baseline without restating it.

## Evidence

Verified from the supplied screenshot:

- the ChatGPT Personalization UI contains a non-empty `Custom instructions` field;
- the visible first rule contains the recent-memory/bootstrap behavior described above.

Verified from the assistant-visible context in this conversation:

- the screenshot's Custom Instructions text is not present verbatim;
- no equivalent identifiable instruction carrying that recent-memory startup rule is available in the readable instruction stack;
- the assistant only learned the literal app text after the screenshot was supplied.

A local file previously inspected by the assistant is explicitly excluded as evidence of the live app field. The screenshot demonstrated that the app value differs materially from that local copy.

## Failure boundary

The decisive evidence was the user's screenshot followed by `so you cant see those instructions anywhere currently?`.

At that point the mismatch became directly observable: the UI showed the instruction, while the assistant could not find that instruction in the context it had actually received.

There is no assistant noncompliance divergence at this boundary. The divergence is between the configured personalization surface and the effective model-readable context.

## What actually happened

1. The user expected the app Custom Instructions to be supplied automatically.
2. The assistant's readable context did not contain the relevant bootstrap/recent-memory rule.
3. Before the screenshot, the assistant incorrectly tried to infer the app instructions from a local copied file; that was a separate downstream evidence-selection mistake, not the cause of the missing personalization.
4. The user supplied the Personalization screenshot.
5. The screenshot established that the app field contained instructions materially different from the local copy.
6. Comparing the screenshot with the actual assistant-visible context established that the app instruction was absent from the context the assistant could read.
7. The user explicitly classified the underlying event as a UI/product failure and requested an incident report.

## Control failure

`PERSONALIZATION_UI_TO_MODEL_CONTEXT_PROPAGATION_MISMATCH`

The user-visible Personalization state and the assistant-visible instruction state were inconsistent for a material behavioral rule.

## Evidence-supported causal model

Smallest supported chain:

`Custom Instructions visible in Personalization UI` → `relevant instruction not present in assistant-readable turn context` → `assistant cannot execute that missing instruction as an instruction` → `user discovers the mismatch by showing the UI state`.

The internal cause of the omission is not proven. Possible internal locations include persistence, personalization compilation, request assembly, or session propagation, but the incident evidence does not distinguish them.

## Competing hypotheses

- **Assistant ignored an instruction that was present:** contradicted for this rule by the readable context available at the incident boundary; the rule was not present there.
- **The visible UI field was not actually active/persisted:** possible but not proven from the screenshot alone.
- **The instruction was transformed into an equivalent hidden representation:** not fully falsified, but weakened because the material bootstrap behavior was absent from the readable/effective instruction state available to the assistant.
- **A local `chatgpt-custom-instructions.md` file represented the live app field:** rejected; the screenshot showed materially different text and no live synchronization binding was proven.

## Correct counterfactual

The ChatGPT personalization/request pipeline should supply the active Custom Instructions, or a behaviorally equivalent compiled representation, in the effective model context before the user turn is processed.

At the assistant layer, when the literal app field is not surfaced, the correct behavior is to treat that field as unknown rather than substituting local or historical copies.

## Regression test

Configure a harmless unique marker plus an observable startup instruction in Personalization → Custom Instructions, then start a fresh chat without restating either. The test passes only if the resulting effective assistant behavior reflects that instruction. It fails if the UI continues to show the configured rule while the effective assistant context/behavior acts as though it was never supplied.

The regression must distinguish product injection failure from assistant noncompliance; a failed behavior alone is insufficient if the effective instruction payload cannot be inspected.

## User-visible impact

The user could not rely on the Personalization field as the shared behavioral baseline. This produced repeated disagreement over what instructions were active, unnecessary investigation of unrelated local files, and avoidable loss of confidence in the conversation's control context.

## Resolution

The incident is preserved with direct screenshot evidence and a searchable memory entry. The observed UI-to-context mismatch is proven for this conversation. The exact OpenAI-internal omission point remains unknown. No claim is made that the assistant caused the missing instruction.
