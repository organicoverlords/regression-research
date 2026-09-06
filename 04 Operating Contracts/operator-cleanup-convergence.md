# Operator cleanup convergence

Use one bounded operator invocation instead of repeated manual "go" cleanup passes:

`python tools\cleanup_converger.py --apply --operator-ack`

The converger loops until it observes the configured number of stable rounds or reaches its hard round bound. It may remove only secondary P3/Vault worktrees that are clean, branch-attached, exact-ref anchored, absent from recent MCP CWD activity, and absent from external process command lines. Removal is non-force and branch-preserving.

If Windows detaches worktree metadata but cannot delete the directory, the tool may finish only that residue when the same exact branch anchor remains, `.git`/registration are absent, and fresh CWD plus external-process guards are clear. Locked or active residues remain blocked for a later round.

This is an operator tool. Recurring workers must not invoke it to administer themselves or sibling lanes. Dirty, detached/unanchored, ref-mismatched, active, or otherwise ambiguous lanes are preserved. The tool never fetches, resets, rebases, deletes branches, changes permissions, kills processes, or treats cleanup as product/acceptance authority.
