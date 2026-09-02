# MCP direct-clone topology recurrence study — 2026-09-02 19:41 EEST

## Executive finding

The repeated plugin2 tool-drop recovery took so long because several independent MCP failure classes were repeatedly collapsed into one incident, while a previously working **live ingress topology** was later overwritten by documentation and “canonicalization” commits. The decisive restored state is not a new design: it is the Aug-27 production rollback topology recovered from preserved dirty-worktree artifacts and transport logs.

For path-scoped process clones, the proven production shape is:

- root `/` may remain on the stable front door at port 3003;
- `/clone-a` is a direct Tailscale Funnel handler to the selected compatible clone-a listener;
- clone-a also requires three direct metadata handlers: `/.well-known/oauth-authorization-server/clone-a`, `/.well-known/oauth-protected-resource/clone-a/mcp`, and `/.well-known/openid-configuration/clone-a`;
- the same shape applies to another path-scoped clone when independently promoted and proven;
- 3003 static clone routing is optional bounded experiment/fallback infrastructure, not the production clone-continuity invariant.

This distinction matters because the user remembered that the system worked well until an authentication/reauthorization event. The preserved Aug-27 rollback script proves that the good direct-clone state included the OAuth/OpenID metadata handlers, not only `/clone-a`.

## Decisive chronology

### 1. Pre-existing no-arrival failure existed before the later regressions

On Aug 26–27, client-visible `Connection failed` events could occur with no corresponding request at the local listener. A controlled direct-port test also reproduced failures. That failure class is real and must remain separate from local backend/process defects.

### 2. Aug-27 front-door clone experiment failed and was rolled back

PR/commit lineage around `0591c2e` / PR #22 added optional clone forwarding through the stable front door. The live #125 experiment then observed a real clone-A connector error. The experiment was explicitly rolled back.

The preserved dirty-worktree artifact:

`ChatGPTMcpClean-routefront-20260827/.state/deploy-20260827/rollback-funnel.ps1`

restores exactly:

- root -> 3000;
- `/clone-a` -> 3011;
- `/clone-b` -> 3012;
- clone-specific OAuth authorization-server handlers;
- clone-specific OAuth protected-resource handlers;
- clone-specific OpenID configuration handlers.

This artifact is stronger than later prose because it is the executable rollback state retained from the actual experiment.

### 3. Good live period followed on the direct clone path

Clone-a PID `31388` started at 2026-08-27 21:18 EEST and, before replacement, handled approximately:

- 3,344 `start_process` calls;
- 3,628 `read_output` calls;
- about 7,300 MCP requests;
- 341 TCP connections;
- one recorded socket error.

The next clone-a PID handled more requests over proportionally far more connections and more socket errors, but the key topology fact is independent of that comparison: **the 3003 front-door request log contains no clone-a traffic during the Aug-27/28 good period.** The first `/clone-a` request in that front-door log is on Sep 1 at approximately 07:58 EEST.

Therefore the good period did not depend on clone traffic traversing 3003.

### 4. Process fast-path improvements landed before the receipt fix

`64b74d8` added the default ~750 ms `start_process` completion wait. `4e681bc` removed the rolling launch bucket and raised the live process cap to five. These reduced client round trips and were part of the good period, but they did not define ingress topology.

### 5. Receipt retention was fixed later

The durable receipt work (`45bb1d1` lineage) came after the good direct-route period. It fixed completed-process reassociation beyond >64 churn and the 30-minute window. The receipt fix must remain independent from ingress routing.

A later fallback/health branch (`2e2b47f`) mixed routing changes into the receipt-era lineage. The later known-good reconstruction deliberately avoided that hot-path health-preflight behavior.

### 6. Sep-1 “canonicalization” reversed the proven live ingress state

Commits `412c566` (“docs: restore single-front-door MCP topology”) and `8413054` (“fix: restore array-aware front-door static routing”) promoted a different rule: clone paths should fall through one root Funnel handler to 3003.

That rule was then reflected in README/CHANGELOG/Atlas language and became easier for later assistants to trust than the older dirty/runtime evidence. This is the concrete regression boundary: a failed Aug-27 experiment became the later documented “canonical” production model.

### 7. Authentication/binding events obscured the topology regression

Sep-1 evidence also records hosted connector/link/binding replacement behavior and reauthorization symptoms with no local arrival. Because hosted binding failures, local routing, OAuth identity, receipts, and backend generation were investigated together, later debugging repeatedly changed the wrong layer.

The missing clue was that the old direct topology included the three metadata handlers. Restoring only `/clone-a` can look healthy until a future authentication discovery/reauthorization path is exercised.

### 8. Sep-2 direct-route restoration produced the missing closure proof

The live clone-a production path was restored to direct `/clone-a -> 55578`, where `55578` is the compatible `clone-a-known-good-61b0d79` generation. Root `/` remained on 3003.

Same-chat test after direct cutover:

- 10/10 `start_process` calls succeeded;
- 10/10 reads of the original IDs succeeded;
- zero network/tool drops;
- zero retries;
- front-door clone-a arrivals after cutover: zero.

Fresh-chat closure supplied by the user:

- 5/5 starts succeeded with `wait_ms=0`;
- 5/5 reads succeeded using each original returned process ID exactly once;
- zero start/network drops;
- zero read/tool drops;
- zero retries.

The three historical clone-a OAuth/OpenID metadata handlers were then restored to 55578. Public checks returned HTTP 200 for `/clone-a/health` and all three metadata endpoints.

## Why restoration took too long

1. **Failure-class collapse.** Pre-arrival hosted/ingress drops, response-loss-after-HTTP-200, health-preflight oscillation, receipt eviction, TCP churn, stale schema/binding, auth events, and supervisor Funnel rewrites were discussed as “MCP dropping.” Fixing one class repeatedly created false closure for the others.

2. **Documentation was treated as stronger than live provenance.** Sep-1 README/CHANGELOG/Atlas language called single-front-door clone routing “re-proved,” so later work repeatedly returned to 3003 even though the original Aug-27 experiment had been rolled back.

3. **History search began too close to `master`.** The decisive state survived in all-ref history, reflog/worktrees, `.state/deploy-20260827`, long-lived transport logs, and Vault/GitHub issue comments. These surfaces were not searched together early enough.

4. **Dirty working state was underweighted.** The user explicitly remembered an unsaved switch. The surviving rollback script was the exact executable proof, but it was only examined late.

5. **Server-side smoke was overvalued.** Local health, public health, authenticated smoke, and HTTP 200 responses cannot pass a client-visible closure test when failures can occur before listener arrival or after a response leaves the server.

6. **Ingress promotion lacked a client-visible gate.** A topology could be declared canonical after local/public smoke without repeated fresh-chat process calls and arrival correlation.

7. **OAuth metadata routing was not treated as part of ingress topology.** This allowed a partial direct-route restoration to look correct while leaving the next authentication transition vulnerable.

8. **Later fixes were allowed to carry adjacent topology changes.** Receipt, health, TCP reuse, OAuth identity, process contract, and ingress should have been independently testable axes. Mixing them made rollback lineage ambiguous.

9. **No regression guard encoded the direct-route shape.** A prose claim could override the live-known-good layout because there was no helper/test stating “four direct clone handlers; root untouched; no Funnel reset.”

## Durable prevention contract

1. The live MCP repository owns the routing rule. Path-scoped production clones use direct Tailscale path handlers to a compatible clone listener, including the three OAuth/OpenID metadata handlers. Root may remain on 3003.

2. `scripts/set-direct-clone-funnel.ps1` is the supported bounded promotion/verification helper. It must never run `tailscale funnel reset` and must never rewrite the root handler.

3. A clone ingress promotion is accepted only after:
   - helper verification of all four direct paths;
   - exact process contract compatibility;
   - fresh-chat 5-start/5-read closure with no hidden retries;
   - timestamp-to-listener-arrival correlation for any failure.

4. A no-arrival failure does not authorize backend, receipt, OAuth-store, port, or health-policy churn.

5. Receipt retention, five-live-process admission, 750 ms default wait, 32 KB reads, exact tool contract, stable OAuth identity, no hot-path health preflight, and backend TCP reuse remain separate invariants. Do not “restore MCP” by reverting one to repair another.

6. When the user says a regression was already solved, reconstruct the last known-good state **before proposing a new fix** using: all Git refs -> reflog/stashes -> surviving worktrees/dirty state -> README/CHANGELOG at that time -> Vault indexed timeline -> linked reports/evidence -> preserved raw transcript only as needed -> client-visible proof.

7. Never label a topology canonical from configuration or smoke alone. The highest-value proof for this class is real ChatGPT connector calls plus local arrival correlation.

## Updated durable surfaces

- chatgpt-mcp-clean GitHub issue #37: recurrence ledger and proof.
- chatgpt-mcp-clean AGENTS/README/CHANGELOG: direct clone production invariant.
- chatgpt-mcp-clean `scripts/set-direct-clone-funnel.ps1`: bounded apply/verify helper.
- chatgpt-mcp-clean `scripts/test-direct-clone-funnel.mjs`: four-route/root-untouched/no-reset regression.
- Vault Stack Atlas source + rendered document: front door is root transport; minimal clone production ingress is direct.
- This report + machine-readable evidence timeline.

## Closure boundary

The specific restored direct-route closure is proven by the same-chat 20-call clean run and the user-supplied fresh-chat 10-call clean run. This does **not** erase the historical existence of hosted/pre-arrival failures in other configurations. Future failures must still be classified by client timestamp and listener arrival before any repair is chosen.
