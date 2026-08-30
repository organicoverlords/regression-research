# ChatGPT behavior distribution

The canonical ChatGPT behavioral semantics live in the Vault memory authority layer and are compiled by `build_behavior_bootstrap()`. The generated Library artifact is the **primary fresh-chat behavior delivery surface**. This deliberately keeps core behavior independent of MCP/local-process availability while keeping Vault as the only canonical behavior/policy source.

The generated artifact is `/Agent Bootstrap/chatgpt-bootstrap.json`. Its producer is `python tools/chatgpt_bootstrap_artifact.py render`; `python tools/chatgpt_bootstrap_artifact.py publication-plan` reports the exact bytes/SHA/source descriptors a Library publisher must expose. The artifact contains the complete current behavior bootstrap plus a bounded `recent_memory_glance` of at most 20 eligible non-superseded Vault entries. The embedded glance is a fallback orientation snapshot, not live authority and not a replacement for a fresh Vault memory read when that route is available.

Fresh normal-chat delivery order is: **Library behavior -> Vault recent-memory refresh -> live orientation -> response**. If the Library artifact is unavailable or incomplete, `python C:\Users\Lauri\Desktop\vault\tools\memory_bank.py bootstrap` is the behavior-delivery fallback. MCP/local execution is therefore optional for core behavior, while Vault remains the canonical source and the preferred source for the current recent-memory glance.

## Library publisher worker contract

This is a publication job, not a second authority, scheduler, database, or hand-authored constitution. Whenever the job is run after a relevant landed Vault change, it must:

1. use the landed `origin/main` Vault revision;
2. run `python tools/chatgpt_bootstrap_artifact.py publication-plan` and render those exact bytes;
3. obtain the current `/Agent Bootstrap/chatgpt-bootstrap.json` Library copy and compare it byte-for-byte;
4. if already equal, report current and make no mutation;
5. if different, preserve a restorable previous Library copy, publish only the rendered artifact bytes, retrieve the new Library copy, and require `python tools/chatgpt_bootstrap_artifact.py verify <copy>` to return `PROVEN`;
6. on mismatch or invalid publication, restore the previous Library bytes and leave publication unaccepted.

The publisher must never rewrite, normalize, summarize, or hand-edit behavior. It changes only the generated Library artifact. It does not edit Personal Instructions, built-in ChatGPT Memory, scheduler state, coordinator authority, or Vault behavior while publishing.

A behavior/policy/startup change is not fully **distributed** until the current Library bytes verify against the current landed Vault render. Repository merge and Library distribution are distinct states; a green repository check must not be described as proof that the external Library surface is current.

Personal Instructions are a stable delivery bridge rather than a copy of the behavior rules. They point fresh chats to Library first and Vault fallback second, so ordinary behavior-rule changes require Library republishing but do not require repeated Personal-Instructions edits. If the delivery protocol itself changes, the saved ChatGPT Personal Instructions are a separate live configuration surface and require explicit update/verification.

The artifact is not live orientation. After behavior delivery, attempt the bounded live Vault `recent-titles --limit 20` refresh; if unavailable, the embedded Library glance may be used as bounded historical fallback. Then perform the `fresh_session_startup` live-state scan. Current user instruction and verified current state remain stronger than historical/distributed context.

Legacy `/Agent Bootstrap/agents.md`, `/Agent Bootstrap/chatgpt-memory-seed.md`, tracked old seed files, built-in ChatGPT Memory, and cached/paraphrased copies are historical/recovery evidence only. They are not behavior delivery sources for this contract.
