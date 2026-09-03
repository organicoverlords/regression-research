# MCP Aug 27–29 restore + 32KB recovery — 2026-09-03 03:42 EEST

## Requested recovery

Restore the last user-identified successful MCP lineage and make only the 32KB `read_output` change. Do not treat any later September repair as recovery authority.

Historical base chain:

- `64b74d8` — automatic ~750 ms `start_process` wait.
- `4e681bc` — remove launch bucket; allow 5 live processes.
- `45bb1d1` — retain completed process receipts for the full 30-minute window, including after >64 newer processes.
- `9c2aae5` — pin the exact process `tools/list` contract and reject incompatible descriptions/schemas.
- `ad45690` — preserve OAuth identity across replacement.
- `41c8345` — reuse backend TCP connections.

32KB overlay only:

- runtime read window from `268cb53`.
- advertised `read_output.max_chars.maximum = 32000` from `3b28997`.

## Restored source state

Canonical checkout `C:\Users\Lauri\AppData\Local\ChatGPTMcpClean` was rewritten to the exact `41c8345` tracked tree, then only these five validated 32KB-overlay files were applied:

- `config/process-server.sha256`
- `config/process-tool-contract.json`
- `scripts/test-read-window.mjs`
- `src/lib/process-manager.ts`
- `src/server.ts`

A mechanical file-by-file SHA-256 comparison against an independently materialized `41c8345 + 32KB` expected tree reported:

`EXPECTED_FILES=60 MISMATCHES=0`

Runtime contract after restore:

- exactly `start_process`, `read_output`, `kill_process` for process profile.
- process contract hash `7c2fd4be29b79146935cbc4a9af8dfe9c431407d31f14cc6fcecd4255e2565a5`.
- `read_output` runtime maximum 32,000 characters.
- `read_output.max_chars.maximum` schema maximum 32,000.
- automatic start wait 750 ms.
- maximum 5 live processes per caller.
- no rolling launch/token bucket.
- historical receipt/OAuth/replacement/connection-reuse behavior retained from the Aug 27–29 chain.

## Runtime topology restored

The later Aug28 clone launchers on 3011/3012 were replaced with the validated `41c8345 + 32KB` process-profile build while preserving the stable clone OAuth stores and shared process receipts.

Startup guard evidence:

- clone-a 3011: `PASS process_contract_guard ... server_sha256=7c2fd4be...`
- clone-b 3012: same contract hash and exact three-tool process profile.

The historical public topology was restored:

- Tailscale Funnel has only root `/ -> http://127.0.0.1:3003`.
- no clone-specific Funnel handlers remain.
- front-door static routes continue to send clone-a to 3011 and clone-b to 3012.
- local `3003/clone-a/health` resolved to restored clone-a listener PID 948 during verification.

The existing 3003 front-door process was elevated and could not be terminated from the current connector (`Access denied`). It remains in memory as a transparent proxy. No privilege workaround or new supervisor mechanism was introduced.

## Validation

Canonical rebuild / focused tests:

- TypeScript build: PASS.
- exact process contract guard: PASS.
- 32KB read-window regression: `whole=24026 truncated=32000` PASS.
- two-clone cross-client/cross-clone reassociation, completed read, live read, live kill, clone survival: PASS.
- `git diff --check`: PASS.

Client-visible closure through restored path:

- 5/5 `start_process(wait_ms=0)` calls succeeded with distinct process IDs.
- 5/5 original process IDs were read exactly once.
- all five reads returned the expected output and exit code 0.
- zero retries and zero drops in that closure.

A live 8,000-character `start_process` result was returned successfully, proving the active process transport is no longer constrained to 6,000 output characters.

Authenticated public MCP `tools/list` against `https://kone.tailbf0440.ts.net/clone-a` using the preserved existing ChatGPT OAuth client returned:

`{"tools":["kill_process","read_output","start_process"],"max_chars_maximum":32000,"description_has_32000":true}`

## Remaining UI/binding discrepancy

After the server and public route were verified at 32KB, this already-open ChatGPT conversation's callable `plugin2.read_output` binding still displayed:

`max_chars: minimum 1, maximum 6000`

That value is inconsistent with the authenticated public `tools/list`, canonical source, built `dist`, pinned process contract, and observed >6KB output behavior. Therefore this specific conversation's loaded connector/tool snapshot is stale. It is not evidence that the restored public MCP server still serves the 6KB schema.

A fresh ChatGPT tool refresh/rebinding after this recovery should be used to confirm the conversation-visible schema becomes 32000.

## Do not regress

For this recovery baseline, do not fold in later September topology/reconciliation changes merely because they were documented as successful. The user explicitly identifies the Aug 27–29 chain as the last successful baseline. Any future change starts from this restored baseline and must be separately justified and tested.
