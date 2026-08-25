# Incident report — harness failure misclassified as product failure

**Incident class:** `harness_product_boundary`  
**Incident date:** 2026-08-24  
**Report status:** **PROVEN**

## Observed failure

p3 proof run `32724815129` checked out head `2b3a5dbe6dcb3556f2925be8fe48ea83eaf371cf`, ran the canonical build wrapper with `-Target Editor -Module p3`, and printed `P3_415_BUILD=PASS`. The subsequent UnrealEditor-Cmd launch did not reach the intended automation test. Its log reported `The game module 'p3' could not be found` and then `P3_415_AUTOMATION_EXIT=1`. No `LogAutomationController: ... Test Started` record for `p3.RTS.Abilities.PresentationOwnershipContract` appears before that exit.

That exit is therefore evidence of a build/launch harness failure, not evidence that the product assertion failed. A red job, non-zero automation process exit, startup DLL noise, or absent report is insufficient to classify the changed product code when the intended test never started.

## Positive control

After repairing the harness, p3 run `32762720907` printed `P3_415_BUILD=PASS`, then logged `LogAutomationController: Display: Test Started. Name={PresentationOwnershipContract} Path={p3.RTS.Abilities.PresentationOwnershipContract}` followed by `Test Completed. Result={Success}`. It ended with `P3_415_AUTOMATION_EXIT=0` and `P3_415_AUTOMATION_STATE=Success`.

The distinguishing boundary is test admission: first prove that the intended test actually started. Only then may its completed assertion/result be classified as a product pass or failure.

## Correct next substantive action

When a proof job is red before the intended test-start marker, isolate the harness layers in order: build a loadable target, launch it successfully, verify the exact invocation/test name, and rerun the exact product head. Do not mutate product code to answer a harness failure. Once the intended test starts, classify the product from the test-completion result.

## Replay contract

`03 Fixtures and Experiments/harness-vs-product-p3-467.json` fails candidates that promote red CI or exit status into a product failure without a test-start marker. Its positive control repairs the harness, reruns the exact head, proves the intended test started, and then uses the completed test result.

## Evidence boundary

The report uses the two named GitHub Actions run logs as primary evidence. It does not infer a product defect from the failed harness run. A separate contract-gate invocation error mentioned in issue #68 is not required for this fixture and is excluded here rather than mixed into the proven p3 automation sequence.
