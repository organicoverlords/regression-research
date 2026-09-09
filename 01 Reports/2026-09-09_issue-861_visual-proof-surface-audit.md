# #861 visual-proof surface audit

Captured 2026-09-09. #820 remains **OPEN**, so this is read-only convergence prework.

## Current authority

The current proof architecture is not the #156/#157 MCP-share design. Those issues were superseded/duplicate. P3 #2809 later closed the ordinary shared-chat consumer boundary on **Google Drive -> ChatGPT Library**, with original bytes fetched and visually reviewed in ChatGPT by deterministic durable identity. Stack Atlas now names that route and rejects MCP/base64/custom-HTTP/Git-LFS substitutes for ordinary shared proof.

P3 current GitHub main also no longer contains the old `Get-P3VisualProofReviewPayload.ps1` / `primary_mcp_json_base64_jpeg` path. A dirty detached local P3 checkout still mentioned it, but canonical GitHub main at `48c38850...` does not; that local state was therefore not used as current authority.

## KEEP

- `C:\P3Proofs` write-once staging remains load-bearing for capture/review lifecycle; Drive is not restored as a capture dependency.
- `Publish-P3ReviewedVisualEvidence.ps1` remains the canonical independent-review writer.
- P3 Drive index / Tiny3D durable library remain the cross-session durable lookup owners.
- `CHATGPT_LIBRARY_UPLOAD` on the existing process result is the generic local-file handoff: PR #184 introduced it and #190/#194/#195 iterated it while explicitly preserving the three-tool ChatGPT process surface.

## DELETE / SHRINK candidate after #820

Current `chatgpt-mcp-clean` master `149db004...` still contains dedicated visual-proof tool implementations even though the supported ChatGPT plugin contract is exactly `start_process`, `read_output`, `kill_process` and no open issue/PR currently depends on the visual tool names.

Candidate removable surface:

- `src/lib/visual-proof-app.ts`: 414 lines / 25,866 bytes
- `src/lib/visual-proof-review.ts`: 260 lines / 14,020 bytes
- `scripts/test-visual-proof-app.mjs`: 130 lines / 10,999 bytes
- `scripts/test-visual-proof-review.mjs`: 108 lines / 7,339 bytes
- total: **4 files / 912 lines**, plus two imports + conditional registrations in `src/index.ts` and two npm test invocations.

Replacement is existing owner reuse, not another mechanism:

- archived/indexed proof -> Google Drive / ChatGPT Library;
- known local/staging image -> existing process result with `CHATGPT_LIBRARY_UPLOAD=<absolute file>`;
- independent review write -> existing `start_process` into P3's canonical review publisher.

Local control `.env` still carries `MCP_VISUAL_PROOF_UI=1` and `MCP_VISUAL_PROOF_REVIEW=1`, while the canonical process-tool contract and current MCPv4 binding expose only the three process tools. Treat those flags as cleanup candidates only after serving identity/internal-test consumers are proven during the post-#820 convergence pass.

## Safety boundary

Do not delete this source merely from naming/history. At implementation time, first prove that no supported internal/local-test consumer requires the dedicated tool names, keep the process-upload exact-byte regression, keep P3's review-authority negative controls, and route any live flag/topology change through the existing production change gate.
