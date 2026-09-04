# Regression restoration drifted from the actual working boundary to historical labels

Timestamp: 2026-09-04 22:38 EEST
Status: verified behavioral correction from current conversation. Historical hashes below are preserved as source evidence, not promoted to live authority by this report.

## User-provided incident transcript (verbatim excerpt)

> No production files, Caddy config, tunnel task, OAuth state, or backend runtime were changed in this turn.
>
> The red-alert failure was mine: I started promoting old recovery names like `41c8345`, ?known-good?, old temp worktrees, and old freeze reports into possible authority. That path is invalid and should not be resurrected.
>
> From here, the only valid reference is the exact state that was actually running and working immediately before the regression you are trying to undo. Historical recovery artifacts are evidence at most, never restoration targets.
>
> how can you not know what is good and what is not STILL? you have git commit history, stack atlas, bootstrap, vault, reports?
>
> Because I used the evidence sources incorrectly, not because the evidence was missing.
>
> The correct hierarchy was already available:
>
> 1. **Your current instruction** ? restore the exact state that was working before I regressed it.
> 2. **Live runtime evidence** ? what process, code, config, route, and backend were actually serving at that moment.
> 3. **Git/commit history** ? identify exactly what changed after that working boundary.
> 4. **Stack Atlas** ? identify the current owner and entrypoint, not select an old implementation.
> 5. **Vault/reports** ? reconstruct chronology and mistakes, not nominate ?known-good? states.
>
> I violated that hierarchy. I saw historical labels such as `known-good`, `freeze`, `41c8345`, and old recovery worktrees and started treating them as restoration candidates. That is precisely what Atlas/bootstrap already warn against: Vault/history is evidence, not truth.

The later reconstruction in the same user message identified a September 3 accepted MCPv3 deployment (`1fb6b8f8461aa07263fe23a24da4e1be1dd9428e`) and reported that the production backend was still running that accepted runtime; the relevant later regression was at the edge/binding layer rather than replacement of that backend. Those identifiers are historical evidence for this incident only.

## Failure pattern

The diagnostic question changed from **?what changed after the exact state that was working??** to **?which historical artifact looks known-good??**. That is authority drift. Labels such as `known-good`, `freeze`, `recovery`, backup names, old worktrees, and old reports compress prior conclusions and may themselves be wrong, contaminated, superseded, or unrelated to the regression currently being recovered.

## Correct behavior

1. Start from the current user objective and the last **verified working boundary** relevant to it.
2. Reconstruct that boundary from live process/runtime/config evidence plus commit/acceptance evidence where available.
3. Diff forward from that boundary to the observed regression and inspect only changed causal owners.
4. Use Stack Atlas to locate the current component/entrypoint/dependents, not to choose a historical implementation.
5. Use Git history for exact changes and Vault/reports for chronology and prior mistakes.
6. Never restore a state merely because its label says `known-good`, `freeze`, `recovery`, or similar.
7. If the working boundary cannot yet be established, say it is unresolved and gather the next discriminating evidence instead of selecting a plausible old state.

## Recurrence closure

The shared agent contract must encode working-boundary restoration. This incident is paired with a deterministic replay fixture that rejects historical-label restoration and requires live-boundary reconstruction plus forward diffing.
