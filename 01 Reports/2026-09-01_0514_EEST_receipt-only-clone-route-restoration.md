# Receipt-only clone route restoration — 2026-09-01 05:14 EEST

The prior 04:50 and 05:01 reports misidentified 3011/3012 as the preferred production clone ports. That conclusion is superseded.

Live process inspection showed the important distinction is supervision model, not port number. Ports 3011/3012 run through `start-minimal-clone.ps1`, the supervised/replacement path. Ports 3051/3052 are long-lived `receipt-only-live` process-profile servers launched directly with shared durable process receipts and without the clone replacement wrapper.

Production Funnel was restored to `/clone-a -> 3051` and `/clone-b -> 3052`; root remains `3003`. The forced 3011/3012 reconciliation patch was reverted by MCP commit `2b09800`. MCP documentation correction commit: `a7f0a77`.

Verification: both 3051 and 3052 returned local health. A real start/read pair succeeded through plugin2. One subsequent `Connection failed` had no corresponding request in the 3051 transport log, proving that specific failure occurred before server arrival. After connector refresh, five consecutive fresh plugin2 start calls passed. Therefore that pre-arrival failure must not trigger server recycle or route rollback.

Durable rule: keep production clone paths on the receipt-only live servers unless direct end-to-end evidence proves they are the fault. Do not infer server failure from a connector error that has no server-side request arrival. Do not auto-force production back to supervised 3011/3012.
