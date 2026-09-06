# Operator cleanup convergence

Use one bounded operator invocation instead of repeated manual "go" cleanup passes:

`python tools\cleanup_converger.py --apply --operator-ack`

The converger loops until it observes the configured number of stable rounds or reaches its hard round bound. It may remove only secondary P3/Vault worktrees that are clean, branch-attached, exact-ref anchored, absent from recent MCP CWD activity, and absent from external process command lines. Removal is non-force and branch-preserving.

For an inactive secondary **P3** worktree that must otherwise be preserved, the same invocation may reclaim only standard Unreal `Binaries`, `Intermediate`, and `DerivedDataCache` directories when Git itself proves each directory ignored immediately before deletion. Git-locked lanes, recent MCP-CWD lanes, and externally process-targeted lanes are excluded. Reparse-point directories are skipped. `Content`, `Saved`, proof/evidence, source, and every non-ignored path are outside this cleanup surface.

If Windows detaches worktree metadata but cannot delete the directory, the tool may finish only that residue when the same exact branch anchor remains, `.git`/registration are absent, and fresh CWD plus external-process guards are clear. Locked or active residues remain blocked for a later round.

Git cleanliness probes are individually time-bounded. A timeout is **unknown state**, not clean state: the worktree is preserved with `cleanliness_probe_timeout`, so one pathological dirty/LFS-heavy lane cannot wedge the entire convergence operation.

This is an operator tool. Recurring workers must not invoke it to administer themselves or sibling lanes. Dirty, detached lanes without an exact durable ref at HEAD, ref-mismatched, active, or otherwise ambiguous lanes are preserved. A clean detached lane may be removed only when a local branch, tag, or non-symbolic remote-tracking ref points exactly at its HEAD before and after removal. The tool never fetches, resets, rebases, deletes branches, changes permissions, kills processes, or treats cleanup as product/acceptance authority.
