# ChatGPT bootstrap distribution

The canonical ChatGPT behavioral semantics live in the Vault memory authority layer and are compiled by `build_behavior_bootstrap()`. Library is a distribution transport only. It must never become an independently edited behavior constitution.

The generated distribution artifact is `/Agent Bootstrap/chatgpt-bootstrap.json`. Its producer is `python tools/chatgpt_bootstrap_artifact.py render`. The artifact contains the complete current behavior bootstrap payload plus byte count and SHA-256 provenance for the canonical behavior bank and authority registry. It deliberately contains no recent incidents, project history, conversation archive, repo history, or live status.

Publication is two-phase. Render the artifact from the intended Vault revision, publish those exact bytes to the Library path, then obtain the published copy and run `python tools/chatgpt_bootstrap_artifact.py verify <copy>`. Do not replace a previously verified Library snapshot until byte-for-byte verification returns `PROVEN`. A publisher or deployment adapter may automate the transport, but it must not rewrite, normalize, summarize, or otherwise synthesize the payload.

Fresh ChatGPT sessions prefer a compatible local execution route to `python C:\Users\Lauri\Desktop\vault\tools\memory_bank.py bootstrap`. The generated Library artifact is the fallback when local execution is unavailable or the exact command still fails after its bounded retry. A Library consumer accepts the fallback only when the complete generated artifact is returned and `payload.contract.complete_behavior_semantics` is true, then uses `payload` exactly as the bootstrap result.

The artifact is not live orientation. After bootstrap, `fresh_session_startup` still requires the bounded relevant live-state scan before the first substantive fresh-chat response. Current user instruction and verified current state remain stronger than historical or distributed context.

If both local bootstrap and the generated Library fallback fail, continue from current instructions, applicable already-present policy, and verified live state. Persistent-context loss is a continuity degradation, not a task-level stop condition and not permission to debug the memory system instead of the inherited task.

Legacy `/Agent Bootstrap/agents.md`, `/Agent Bootstrap/chatgpt-memory-seed.md`, tracked old seed files, built-in ChatGPT Memory, and cached/paraphrased copies are historical/recovery evidence only. They are not fallback behavioral authorities for this contract.
