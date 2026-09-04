# P3 #803 exact-SHA ground/runtime proof — 2026-09-04 15:59 EEST

Historical evidence record only. Current product truth remains the live P3 repo/runtime and issue #803.

## Resolved topology

- PR #876 merge SHA: `5fb1b84150a82d95fe041498b935c25120de3568`.
- The warm proof branch had advanced to `67cab9494cb6d73fa31bcdac47675f4d54f14d25`; `5fb1b841` is its ancestor, so the previous `git --ff-only` refusal was correct because moving the branch to the merge SHA would be a rewind.
- No history was rewritten. Exact proof used a detached checkout at `5fb1b841`, then restored the warm proof branch to `67cab949`.
- Candidate `c33e68fc6218152b49955a2610d0e371a1deab22` and merge `5fb1b841` both resolve to tree `1a36dcbd4b01c2a5d7f65da69791ca856ef60c34`.
- Preserved `UnrealEditor-p3.dll`: 2,616,320 bytes, mtime 2026-09-04 07:41:44 EEST; this falls after candidate commit 07:32:23 and before merge 07:43:27. No rebuild was run for the recapture.

## Exact runtime evidence

- Worker-owned offscreen Unreal runtime, `/Game/V2/Maps/Lvl_V2ProductionWorld`.
- PIE configured for 2 clients, `ListenServer`, one process.
- Both pawns resolved to `/Script/P3Gameplay.P3CharacterBase`.
- Pawn Z values: `90.274999356947944` and `90.274996415163542`.

## Canonical capture evidence

Screenshot:
- Manifest commit: `5fb1b84150a82d95fe041498b935c25120de3568`.
- Pixel gate: PASS (`pixel-content-pass`).
- 1280x720, 2,244,875 bytes.
- SHA-256: `a8fc3c7f584e27a1818942d9041d335c0798d78052ddf6882445ad5a3e6ada0e`.
- Shared path: `C:\P3Proofs\issue803-exact-5fb1b841-20260904-125121-screenshot`.

Video:
- Manifest commit: `5fb1b84150a82d95fe041498b935c25120de3568`.
- H.264 1280x720, 15 fps, 60 frames, 4.000 seconds, 680,730 bytes.
- SHA-256: `723da2c010b8877dc1c45df3e9c5d25485a020aa1005a0afe015ea9dd7add570`.
- Independent `ffmpeg` decode: exit 0.
- Independent `ffprobe`: H.264, 1280x720, 15/1 fps, 4.000000 s, 60 frames, exit 0.
- Shared path: `C:\P3Proofs\issue803-exact-5fb1b841-20260904-125121-video`.

Both new capture manifests remain `PENDING_REVIEW`; this record proves exact-state binding, runtime stability, canonical capture generation, and video decode, not independent visual-review approval.

## Shutdown and preservation

- PIE stopped through the live MCP bridge.
- The worker-owned editor exited gracefully via Unreal Python `unreal.SystemLibrary.quit_editor()`; shutdown log reached `LogExit: Exiting`, removed the MCP port lockfile, and the canonical launcher returned exit code 0.
- Existing `visual-polish-artifacts/` were preserved.
- GitHub issue #803 updated at issue comment `#issuecomment-5540776753` with the same exact evidence.
