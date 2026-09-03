# P3 single-machine swarm policy recovery — 2026-09-01

## Finding

The current P3 operational contract was located at:
`C:\Users\Lauri\AppData\Local\Temp\chatgpt-p3-456-20260831\docs\SINGLE_MACHINE_SWARM.md`.

This is the specific policy governing the machine's physical resource topology:
source lanes, persistent hot-build capacity, one reusable editor/runtime lane,
disk-growth admission, cache-only recovery, and the single GitHub Actions integration cohort.

## Authoritative resource rules

1. Ordinary P3 workers use lightweight source lanes with LFS pointers. They do not
   own Unreal build products.
2. Build state is concentrated in the existing persistent hot-source pool and
   machine-wide build mutex. Source ownership does not imply another Unreal build copy.
3. Editor/runtime capacity is one reusable editor-class lane. It is the ordinary
   hydrated Content/PIE/capture lane.
4. Any disk-growing build, editor launch, or LFS hydration must reserve expected
   growth and retain 25 GB free. An unreadable disk probe refuses the growth operation.
5. Before refusing a growing operation, the existing cache-only sweep may reclaim
   only cold, gitignored Intermediate/Binaries from lanes with no attributed process.
   Content, Saved evidence, dirty work, assets, branches, and whole worktrees are protected.
6. Build pressure is resource contention, not task failure. Continue source edits,
   focused tests, review, and integration without allocating another Unreal workspace.
7. When work lands or stops, release the exact BusyCoordinator scope and recycle
   clean fully pushed source lanes; worker-owned runtimes remain receipt/deadline governed.
8. LowVRAM and Tiny3D fan into P3 through manifests, hashes, and one-time materialization;
   they do not create hydrated P3 checkouts or start P3 builds/editors.
9. GitHub Actions keeps one integration cohort through its existing concurrency group.
10. Preventing queue growth is not the same as restoring progress; queue/deadlock work
    must prove forward progress.

## Incident correction

During this session ChatGPT selected a new hydrated editor lane for #603 visual proof.
That violated the one-reusable-editor-lane rule because the existing editor/runtime
capacity must be reused before creating another hydrated P3 workspace.

The correction is behavioral and operational: resolve the current reusable editor lane
first, inspect ownership and live resource state, reserve disk growth before hydration,
and use the existing hot-build path. Do not solve resource contention by multiplying
Unreal workspaces.

## Documentation update

`docs/SINGLE_MACHINE_SWARM.md` was updated to state explicitly that it is the P3
single-machine resource-path authority and that queue/resource changes require
forward-progress evidence, not only admission protection.
