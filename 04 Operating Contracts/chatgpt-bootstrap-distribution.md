# ChatGPT behavior distribution

The canonical ChatGPT behavioral semantics live in the Vault memory authority layer and are compiled by `build_behavior_bootstrap()`. Fresh chats load that canonical Vault behavior first through `python C:\Users\Lauri\Desktop\vault\tools\memory_bank.py bootstrap`. The generated Library artifact is a complete transport fallback cache, not a second behavioral authority.

The generated behavior artifact is `/Agent Bootstrap/chatgpt-bootstrap.json`; the generated on-demand operational Atlas is `/Agent Bootstrap/stack-atlas.json`. Its producer is `python tools/chatgpt_bootstrap_artifact.py render`; `python tools/chatgpt_bootstrap_artifact.py publication-plan` reports the exact bytes/SHA/source digests a Library publisher must expose. The behavior artifact is a compact compiled projection capped at 15,000 bytes: it keeps every active behavior and canonical-policy text, removes redundant per-rule metadata already owned by Vault, keeps the startup and `stack_atlas_glance` semantics in compact form, and embeds only the newest recent-memory title as emergency fallback. The full Vault records and the normal live `recent-titles --limit 20` refresh remain canonical; the compact Library copy is delivery, not a second policy store.

Fresh normal-chat delivery order is: **Vault behavior bootstrap -> compact Stack Atlas -> relevant context -> response**. If the exact Vault bootstrap command fails, retry it once through a compatible local execution route. If local execution is unavailable or that retry still fails, load `/Agent Bootstrap/chatgpt-bootstrap.json` as the complete generated behavior fallback. The Library copy is transport fallback only; Vault remains canonical. The compact Atlas is universal startup context. Recent-memory and live-state reads are conditional on the actual task.

## Library publisher worker contract

This is a publication job, not a second authority, scheduler, database, or hand-authored constitution. Whenever the job is run after a relevant landed Vault change, it must:

1. use the landed `origin/main` Vault revision;
2. run `python tools/chatgpt_bootstrap_artifact.py publication-plan`; render the exact behavior bytes and the exact Atlas bytes reported in its `stack_atlas` plan with `python tools/stack_atlas.py library-render --output <copy>`;
3. obtain both current Library copies (`chatgpt-bootstrap.json` and `stack-atlas.json`) and compare each byte-for-byte;
4. if already equal, report current and make no mutation;
5. if different, preserve restorable previous copies, publish only rendered bytes, retrieve both new Library copies, require bootstrap `verify <copy>` to return `PROVEN`, and require `python tools/stack_atlas.py library-verify <copy>` to return `PROVEN`;
6. on mismatch or invalid publication, restore the previous Library bytes and leave publication unaccepted.

The publisher must never rewrite, normalize, summarize, or hand-edit behavior. It changes only the generated Library artifacts. It does not edit Personal Instructions, built-in ChatGPT Memory, scheduler state, coordinator authority, or Vault behavior while publishing.

A behavior/policy/startup change is not fully **distributed** until both generated Library artifacts verify against the current landed Vault render. Repository merge and Library distribution are distinct states; a green repository check must not be described as proof that the external Library surface is current.

Personal Instructions are a stable delivery bridge rather than a copy of the behavior rules. They point fresh chats to the exact Vault bootstrap first and the generated Library cache only as fallback, so ordinary behavior-rule changes still require Library republishing for continuity fallback but do not require repeated Personal-Instructions edits. If the delivery protocol itself changes, the saved ChatGPT Personal Instructions are a separate live configuration surface and require explicit update/verification.

The embedded Stack Atlas entrypoint is not live authority, but it is universal orientation context: use it before stack/infra reasoning or changes to identify relevant components and possible blast radius, then fetch current status from the named live sources. Recent-memory and other live-state reads remain conditional. Current user instruction and verified current state remain stronger than historical/distributed context.

Legacy `/Agent Bootstrap/agents.md`, `/Agent Bootstrap/chatgpt-memory-seed.md`, tracked old seed files, built-in ChatGPT Memory, and cached/paraphrased copies are historical/recovery evidence only. They are not behavior delivery sources for this contract.
