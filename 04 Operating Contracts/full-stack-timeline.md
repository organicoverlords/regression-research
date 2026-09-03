# Full Stack Timeline

Use this when a worker needs whole-stack/project history rather than one issue or one checkout.

Run from the current Vault source tree:

`python tools/full_stack_timeline.py --vault-root C:\Users\Lauri\Desktop\vault --output <path>`

Add an optional search term such as `mcp`, `worker`, `tailscale`, `p3`, `tiny3d`, or `lowvram` to filter the event stream.

The output is a read-only projection. It does not create a queue, database, ownership system, scheduler, or current-state authority.

It combines durable documents, memory records as historical evidence, worker-report history, reachable Git commits, refs, branches, tags, stashes, worktrees, reflogs, repository snapshots, and optional live runtime observations.

It also projects source-presence coverage for the six assistant-history surfaces named by the North Star: ChatGPT, OpenCode, Claude, Codex, Traycer, and Command-Code. Concrete locations come from the existing `memory/sources.json` registry and are checked on the local filesystem. `SOURCE_PRESENT` proves only that the configured source root exists now, not that its contents are complete or current. `SOURCE_MISSING`, `UNRESOLVED_LOCATION`, and `REGISTRY_MISSING` are explicit coverage gaps and never evidence that a behavior did not occur.

OpenCode additionally contributes metadata-only `OPENCODE_SESSION` events from the primary local `opencode.db` `session` table when that registered source is present. The adapter reads only session identifiers/timestamps, project/workspace/parent IDs, directory, version, agent, normalized model metadata, and archive state. It intentionally does not read titles, metadata payloads, prompts, messages, parts, todos, summaries, or credentials. Missing/unreadable session metadata remains an explicit coverage gap/error rather than evidence about behavior.

Codex additionally contributes metadata-only `CODEX_THREAD` events from the primary local `.codex/state_5.sqlite` `threads` table when that registered source is present. The adapter reads identifiers, timestamps, source type, cwd, Git metadata, model metadata, and archive state; it intentionally does not read titles, prompts, previews, item bodies, or transcript content. Missing/unreadable thread metadata is surfaced as a coverage error and never as evidence that behavior did not occur.

Claude additionally contributes session-level `CLAUDE_SESSION` events from the primary local `.claude/history.jsonl` history index when that registered source is present. Entries are aggregated by `sessionId` into earliest/latest timestamps, project scope, and entry count. Text-bearing `display` and `pastedContents` values are discarded and never emitted into the timeline. Missing/malformed history remains an explicit coverage gap/error rather than evidence about behavior.

Stash and reflog metadata are also emitted as queryable `OBSERVED_FACT` events so recoverable Git history can be found by subject, SHA, ref/selector, project, or repository path. Their messages are metadata only and never prove the intent, effect, or correctness of the referenced changes.

Every event also carries an explicit epistemic class. `OBSERVED_FACT` means source metadata or runtime state was directly observed. `REPRODUCED_FACT` and `INFERENCE` are reserved for producers that explicitly justify those stronger meanings; the timeline never infers them from filenames, commit messages, proximity, or a `PROVEN` label. Documents, memory records, and worker self-reports remain `HISTORICAL_CLAIM` by default.

Stronger historical findings enter through `02 Evidence/timeline-events/*.json` using schema `full-stack-timeline-events.v1`. Each event must explicitly declare its epistemic class, basis, timestamp, title, ID, and non-empty evidence references. `OBSERVED_FACT`, `REPRODUCED_FACT`, and `INFERENCE` require at least one existing Vault-relative evidence file; `git:`, `github:`, and HTTP references may supplement but cannot replace that local proof. Invalid or malformed events are excluded and surfaced in `structured_evidence_errors`; the timeline never upgrades ordinary prose or state labels into reproduced facts or inferences.

Explicit `supersedes` and `contradicts` links are projected as relationships and reverse `superseded_by` / `contradicted_by` references when both records are present. No contradiction or causal edge is synthesized from chronology or text similarity. Historical documents and reports never become current truth merely because they appear in the timeline.

For mutation, inspect the repository's `mutation_admission`. `DIRECT_OK` means the checkout is a clean named worker/convergence branch. `main`, `master`, `dev`, and `develop` are protected human/integration branches and are never worker mutation targets. `ISOLATE_REQUIRED` means preserve that checkout and use or claim a clean named work branch/already-owned safe lane.

For current runtime claims, verify the smallest named live source from Stack Atlas. The timeline is evidence and navigation, not proof of present liveness.
