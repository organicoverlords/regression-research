# MCP clone-a production quarantine — 2026-09-01 05:55 EEST

Current public route: `/clone-a -> 127.0.0.1:3041`.

Reason: plugin2 showed intermittent connector drops while `/clone-a` was routed to 3051. The already-running 3041 prefix-safe generation uses commit `ad45690` (`fix: preserve stable OAuth identity on replacements`), the stable `clone-a` OAuth store, and the shared process-receipt directory. Its backend `dist/index.js` hash matches the older routefront generation and differs from current main.

Safety action: changed only the Tailscale Funnel local target for `/clone-a`; public URL/OAuth identity were not changed. 3051 was left running and untouched as rollback evidence. 3011/3012 remain fallback/test generations. Do not restore 3051 to production without new end-to-end connector proof.

Verification after switch: multiple plugin2 `start_process` calls succeeded, and an asynchronous `start_process` + `read_output` receipt path completed successfully through server PID 20044 on port 3041 with HTTP 200 responses. Funnel status confirmed `/clone-a -> 3041`.

Repo documentation commit: `e2969f7 docs: quarantine unstable clone-a generation`.

This does not claim mathematical 100% reliability; it establishes the current safest verified route and preserves rollback evidence.
