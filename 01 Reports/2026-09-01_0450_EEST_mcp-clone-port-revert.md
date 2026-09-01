# MCP clone port revert — 2026-09-01 04:50 EEST

User direction: the newest MCP switch to the alternate clone ports performed worse; restore the previous working clone ports and make that state explicit in docs/history.

Live state before change: Tailscale Funnel root `/` -> `127.0.0.1:3003`; `/clone-a` -> `127.0.0.1:3051`; `/clone-b` -> `127.0.0.1:3052`. All four clone listeners 3011/3012/3051/3052 existed locally, so listener existence alone did not establish which public route was preferred.

Change: only the two public clone Funnel handlers were reverted. `/clone-a` now targets `127.0.0.1:3011`; `/clone-b` now targets `127.0.0.1:3012`. Root `/` remained on `127.0.0.1:3003`. No OAuth, credentials, worker, scheduler, Unreal, or project state was changed.

Verification: `tailscale funnel status` showed root 3003, clone-a 3011, clone-b 3012 after the mutation. A fresh plugin2 `start_process` then completed successfully and returned a real MCP receipt at 2026-09-01T04:50:33+03:00. A later connector network error remains possible and is not evidence that the local listeners stopped; route performance should be judged from fresh command receipts rather than configured state alone.

Durable rule: 3011/3012 are the preferred public clone targets. 3051/3052 are experimental prefixsafe/test listeners and must not replace the public clone routes unless explicitly requested for a bounded test. Root remains 3003.
