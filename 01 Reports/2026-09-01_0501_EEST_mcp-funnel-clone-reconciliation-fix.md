# SUPERSEDED 05:14 EEST
This report's 3011/3012 production preference is superseded by 2026-09-01_0514_EEST_receipt-only-clone-route-restoration.md.

# MCP Funnel clone reconciliation fix — 2026-09-01 05:01 EEST

## Incident
Production Funnel clone paths had been switched from canonical `/clone-a -> 3011` and `/clone-b -> 3012` to experimental listeners `3051` and `3052`. Canonical listeners remained alive, so the failure was route ownership/drift rather than backend loss.

## Root cause
Commit `39f205a` introduced a supervisor ownership regression around static clone routing. The production front-door supervisor could leave public Funnel state unreconciled while experimental/test route state existed. Later state had partially removed the original early-return, but clone-path reconciliation itself was still absent.

## Fix
MCP commit `83578cc` adds explicit production reconciliation in `keepalive.ps1`: `/clone-a` is restored to `3011` and `/clone-b` to `3012` when the corresponding local `/health` endpoint is healthy. Root `/` remains `3003`. Experimental ports `3051/3052` are not production targets.

## Verification
The actual `keepalive.ps1 -Role FrontDoor -Port 3003` supervisor was restarted with the patch. A forced drift changed `/clone-b` to `3052`; the supervisor restored it automatically to `3012` after 7 seconds. PowerShell parsing and `git diff --check` passed before commit.

## Durable rule
Production Funnel ownership is explicit: root `3003`, clone-a `3011`, clone-b `3012`. Test/prefixsafe listeners may exist locally but must not persist as production Funnel handlers. Reconciliation must operate on each owned path without rewriting unrelated handlers.
