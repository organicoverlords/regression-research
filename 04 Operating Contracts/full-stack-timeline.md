# Full Stack Timeline

Use this when a worker needs whole-stack/project history rather than one issue or one checkout.

Run from the current Vault source tree:

`python tools/full_stack_timeline.py --vault-root C:\Users\Lauri\Desktop\vault --output <path>`

Add an optional search term such as `mcp`, `worker`, `tailscale`, `p3`, `tiny3d`, or `lowvram` to filter the event stream.

The output is a read-only projection. It does not create a queue, database, ownership system, scheduler, or current-state authority.

It combines durable documents, memory records as historical evidence, worker-report history, reachable Git commits, refs, branches, tags, stashes, worktrees, reflogs, repository snapshots, and optional live runtime observations.

Every source keeps its provenance/authority class. Historical documents and reports never become current truth merely because they appear in the timeline.

For mutation, inspect the repository's `mutation_admission`. `DIRECT_OK` means the checkout is clean and at current `origin/main`. `ISOLATE_REQUIRED` means preserve that checkout and use an admitted isolated worktree or already-owned safe lane.

For current runtime claims, verify the smallest named live source from Stack Atlas. The timeline is evidence and navigation, not proof of present liveness.

At low disk, use `tools/build_admission.py`. A denied disk-growing build/worktree does not stop the worker while `non_disk_work_admitted=true`; continue bounded source, test, review, integration, CI, or convergence work that does not materially grow disk.
