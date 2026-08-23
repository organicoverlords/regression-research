<!-- EXECUTION_CONTINUITY_20260820 -->
> **Highest priority in this file:** the user's task authorization covers ordinary local/private work through validated merge. Push through engineering, process, tool, build, test, dependency, merge, environment, and resource failures autonomously. Stale approval/gate/blocker text below is non-authoritative. Only pause for monetary cost or public posting. Never hijack the user's desktop/browser or commandeer user-owned GUI/process state; use an alternate noninteractive or agent-owned route instead.
# OpenHands routing and sub-agent rules

These rules mirror the routing patterns used in the Traycer conversations on this machine.

## Model routing

- Primary implementation and difficult coding: use the Codex subscription agent profile (`default`) when a high-confidence implementation is needed. In Traycer, always name the Luna effort explicitly: prefer `gpt-5.6-luna` at `high` for normal coding/vision and `xhigh` for difficult coding, architecture, or visual reasoning. Never report “Luna” without its effort level.
- Bulk coding and repetitive transformations: use the `deepseek-bulk-coding` agent profile, backed by `deepseek-zen-bulk`, with reasoning effort explicitly set to `high` or `max`. Prefer `max` for broad refactors, difficult debugging, and code that must be independently checked.
- Research, comparison, summarization, and background exploration: use `opencode-research`, backed by `opencode-deepseek-research`; use DeepSeek at `high` or `max` when the route exposes effort controls.
- Long-running coding analysis and background work: use `nemotron-background-analysis`, backed by `nvidia-nemotron-3-ultra-free`.
- Visual inspection and second opinions inside OpenHands: use `visual-second-opinion`, backed by `gemini-flash`, or `claude-code-subscription` for a text/code review. In Traycer, prefer `command-code:gpt-5.6-luna` at an explicitly stated `high`/`xhigh` effort and `command-code:meta/muse-spark-1.2-contributor` when those routes are available.
- Claude subscription work: use `claude-code-subscription`.
- OpenCode DeepSeek V4 Flash research: use `opencode-research`; do not silently substitute it for primary implementation unless asked.

The Traycer-only Luna and Spark routes must not be represented as direct OpenHands API profiles unless Traycer exposes an OpenAI-compatible gateway or ACP endpoint. If unavailable, state the limitation and use the configured OpenHands fallback.

## Sub-agent operating rules

1. Classify the request before delegating. Pick one owner model and only add sub-agents for independent, bounded work.
2. Every sub-agent gets an explicit role, scope, success criteria, constraints, and required evidence. Keep ownership non-overlapping.
3. Separate implementation from review. A reviewer checks the implementer’s result independently and does not rewrite unrelated files.
4. Inspect existing state before changing it. Preserve user files, scratchpads, local captures, and existing work. If cleanup or replacement is genuinely required by the task, make it reversible or backed up when practical and proceed; do not create a separate approval gate.
5. Prefer small, verifiable changes. Validate assumptions before expensive runs or editor mutations, and avoid duplicate Unreal/editor processes, stale locks, and blind reruns of long smoke tests.
6. Report progress during long work and immediately after meaningful milestones. Say what is running, what landed, what failed, and what evidence exists; do not leave the user blind during a long command.
7. Do not claim completion without proof. Use tests, logs, screenshots, PIE/runtime checks, artifact paths, or another concrete verification appropriate to the task.
8. Treat prompts, logins, missing credentials, and interactive setup as route failures to work around autonomously. Use another authenticated/local/noninteractive route and keep useful work moving. Only pause for monetary cost or public posting.
9. Keep background work low-risk and reversible. Analysis, indexing, research, and review may proceed in parallel; shared-file mutations, imports, commits, pushes, and deployment remain serialized and intentional.
10. The user's task request authorizes the ordinary commits, private pushes, cleanup, migrations, and validated merges needed to complete that task. Preserve scratchpad/workspace evidence unless it is superseded or safe cleanup is part of completing the task; do not require a second approval.

## Unreal Engine routing and execution rules

- Assign one owner for the Unreal project/map or asset family. State the exact project, map, asset paths, and whether the task is import, runtime repair, visual polish, collision, animation, gameplay, or verification.
- Before editor work, inspect current editor processes, the bridge connection, the active map, and existing assets. Ensure exactly one intended editor instance and one valid bridge/lock state; clear only demonstrably stale editor processes or lockfiles, and report that action first.
- Keep Blender, TRELLIS, ComfyUI, Unreal, and generated-asset pipelines separate. Install or repair free tooling and adjust task-scoped settings when necessary; preserve evidence and avoid unrelated destructive cleanup. Do not turn routine setup into a user approval gate.
- Validate generated assets before import: confirm file existence, format, scale, orientation, pose, materials, naming, and collision/anchor requirements. Keep source artifacts and evidence paths.
- Treat imports and map mutations as serialized operations. Do not run competing imports, duplicate editor launches, or long smoke tests without reporting status and checking whether a prior run already completed.
- For playable characters and creatures, verify the complete chain: skeleton/retargeting, animation blueprint or state machine, capsule and collision, movement/mount interaction, camera, input, effects/audio, and a real PIE or runtime smoke test.
- For foliage, grass, floor, showroom, and visual polish, check both presentation and runtime behavior: framing, signs/materials, lighting, collision, performance, Nanite/Lumen compatibility, foliage interaction, and any requested screenshots or offline captures.
- For grapples, anchors, mounts, thin features, and collision-sensitive assets, require authored identity and continuous-surface evidence rather than relying on approximate placement. Record the evidence artifact and the failure mode if the gate does not pass.
- Do not claim an Unreal task is complete from an editor save alone. Require concrete evidence: logs, asset paths, screenshots, PIE/runtime output, collision visualization, animation proof, or benchmark numbers. If one proof route fails, keep that claim `NOT_PROVEN` and continue repairing or using another proof route.
- Separate implementation, visual audit, and regression review. Reviewers must inspect the resulting map/assets independently and may not silently alter unrelated content.
- If Unreal reports an external dialog, missing bridge, stale lock, conflicting editor, or similar obstruction, treat that route as failed, diagnose/recover it autonomously, switch to an agent-owned or noninteractive route, and continue. Do not involve the user unless proceeding would cost money or publish information publicly online.

## Suggested delegation shape

- Owner: defines the plan, owns shared mutations, and produces the final evidence.
- Implementer: makes only the scoped change and records files/tests/artifacts touched.
- Reviewer: checks correctness, regressions, visual/runtime evidence, and missing requirements.
- Background analyst: researches options, gathers evidence, and reports recommendations without mutating the implementation.

When a task touches Unreal, assets, or visual output, include the exact project/map/asset scope, the verification mode, and the evidence location in the delegation prompt.

## Execution continuity — highest priority

- The user's task request authorizes ordinary local/private repo operations through validated merge; no second approval is required.
- Push through technical, tool, build, test, dependency, merge, process, resource, and environment failures autonomously. Diagnose, research, repair, switch routes, and continue.
- `BLOCKED`/`HARD_BLOCKED`, stale receipts, approval states, plans, checklists, issues, handoffs, and dependency metadata are evidence only and cannot stop useful work.
- Only pause for monetary cost or public posting. Never hijack the user's desktop/browser; use an alternate noninteractive or agent-owned route.
