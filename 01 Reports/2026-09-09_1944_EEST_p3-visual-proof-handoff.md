# P3 visual-proof handoff: camera readability, opponent label orientation, and review routing

Date: 2026-09-09 EEST
Status: CURRENT_CHECKPOINT_NOT_AUTHORITY
Keywords: P3, #2441, #2855, #2875, visual proof, third person camera, opponent health label, TextRender, native image review, OMEN

## Authority boundary

This report is recovery/history context only. Current P3 issue/PR state comes from `organicoverlords/p3`; current runtime/proof state comes from the exact runtime/proof receipts and media. Do not use this Vault record as a live-status substitute.

## Parent acceptance

`organicoverlords/p3#2441` — **[GAMEPLAY] First/third-person spell and hit readability pass** — remained OPEN at the 2026-09-09 19:44 EEST refresh.

Broad #2441 acceptance is not complete merely because the camera and one world-space label defect are repaired. First-/third-person integrated play, HUD/spell/hit/material presentation, and compatible-head composition remain separate acceptance scope.

## #2855 third-person restart camera

PR: `organicoverlords/p3#2855`

Exact head: `3c07d6b88aa51ebd87efe2db28b288b2b57029b6`

Current GitHub state at the 19:44 EEST refresh:

- OPEN
- MERGEABLE / CLEAN
- `p3 contract-gate`: SUCCESS, completed `2026-09-09T16:41:53Z`

Exact runtime evidence already established on OMEN:

- untouched fresh PIE held player-camera pitch `-12`, yaw `180`, FOV `90` for 24/24 samples from about 278 ms through 5.6 s;
- earlier exact heads stayed at `-45`, so this is a real runtime behavior change, not only a source assertion;
- canonical capture run: `sol-2855-thirdperson-pawntick-verified-20260909`;
- published PNG SHA-256: `1ba2c47498d6ad16962c2d2100998834fd7793767316e342839812d24ed497ba`;
- direct image review showed the steep top-down camera failure was gone and the avatar/world composition was a normal readable third-person view;
- the same frame exposed a separate mirrored opponent-health label defect.

At the 19:44 EEST filesystem check, this canonical run did **not** contain `reviewed.json`. Do not infer durable review-record completion from the camera/runtime evidence alone.

## #2875 opponent health/damage TextRender orientation

PR: `organicoverlords/p3#2875`

Exact head: `e7f660732ee6b26f1566865459786d7519ab7e83`

Current GitHub state at the 19:44 EEST refresh:

- OPEN
- MERGEABLE / CLEAN
- `p3 contract-gate`: SUCCESS, completed `2026-09-09T16:36:37Z`

Repair:

- TextRender readable face is `-X`; the old billboard calculation pointed component `+X` at the viewer, producing horizontally reversed text;
- the fix reverses the billboard look vector with `return (LabelLocation - ViewLocation).Rotation();`;
- the same correction is used for `P3CombatHealthText` and transient damage-feedback text.

Validation:

- focused presentation suites: 14/14 PASS;
- OMEN hot refresh: PASS;
- OMEN runtime preflight: PASS;
- exact runtime PID: `534331`;
- 12/12 live samples: component `+X` dot direction-to-camera = `-1.0`, therefore TextRender readable `-X` face dot direction-to-camera = `+1.0`;
- canonical run: `sol-2875-health-label-readable-20260909`;
- published PNG SHA-256: `01c78f9edeeb53e1e37422b4b5f24c77d2c4331b593291f34f3306e493690914`;
- pixel-content gate: PASS.

At the 19:44 EEST filesystem check, this run did **not** contain `reviewed.json`. Runtime orientation is proven; final visual acceptance still requires direct inspection of the exact PNG/video pixels.

## Visual-review routing correction

Canonical shared agent policy was corrected in `organicoverlords/agents` commit `066ca6cd2be8a8bab51854a0cba8d2dce59db9ca`.

The prior P3 documentation forced ordinary chat-visible review through Google Drive -> ChatGPT Library and treated absence of that connector as a review blocker. That routing was removed.

Current rule:

- when exact media is already exposed to the model/session, use the platform-native image/video inspection surface directly;
- do **not** shuttle already-available media through MCP, PowerShell/base64, OCR, Drive/Library, custom HTTP, or file materialization merely to make pixels visible;
- transport/retrieval is only for media that is genuinely not otherwise available;
- hashes, paths, telemetry, and pixel-content gates never substitute for visual inspection.

Regression guard: `Test-VisualProofReviewRule.ps1` passes and rejects reintroduction of the forced Drive/Library acceptance dependency.

## Recovery sequence

1. Re-read live GitHub/runtime state before acting; this report is historical context.
2. For #2875, inspect the exact canonical PNG through the native image surface when exposed; do not base64/PowerShell shuttle it just for review.
3. Record the visual verdict against the exact media identity and write the repo-owned durable review record only if the proof workflow requires it.
4. Keep #2855 camera acceptance and #2875 label acceptance narrow; neither closes broad #2441 by itself.
5. Continue broader #2441 through the existing two-player/integrated proof owners rather than creating duplicate gameplay implementations.