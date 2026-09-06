# MCP security-reroute investigation correction — 2026-09-06 18:25 EEST

## Material correction
- `d6e2972` is NOT a true pre-regression / pre-Sep-5 baseline.
- It already contains substantial Sep 5 transport/runtime changes. Restoring it therefore did not test the architecture that worked before the Sep 5 regression window.
- User reports that 32 KB output behavior and the PowerShell/slopwall guards worked normally before the Sep 5 failures. They must not be treated as root-cause candidates merely because they correlate with later incidents.

## Verified consequence
- By 04:35 EEST on Sep 6, production had restored the original `d6e2972` compiled dist hash, but user-visible security reroutes continued.
- Therefore a successful `d6e2972` source/dist rollback does NOT prove restoration of the previously stable platform-facing MCP state.
- Investigation must compare against a genuinely pre-Sep-5 topology/state baseline, including ingress/public origin, edge/TLS path, WireGuard/portproxy, front-door routing, OAuth/client registration state, and connection/session state.

## Communication regression
- The assistant initially buried this high-value correction inside a long response.
- After the user requested less spam, the assistant overcorrected by becoming terse enough to suppress the important finding.
- Required behavior: verbosity reduction must remove repetition and low-value detail, never material findings. Put decisive corrections first, state their consequence directly, then stop.

## Investigation rule
Do not call `d6e2972` the pre-fuckup/pre-Sep-5 baseline. Establish and test the actual pre-Sep-5 working topology/state before attributing the regression to older features that were already working.
