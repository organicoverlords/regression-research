# Canonical Vault serving checkout

`C:\Users\Lauri\Desktop\vault` is the canonical local serving/read checkout for Vault orchestration. It is not a worker WIP surface. Workers that change `organicoverlords/regression-research` use a separate branch/worktree based on current `origin/main`.

`tools\Sync-VaultCheckout.ps1` is the supported convergence entrypoint. Its default path fetches `origin/main`, fast-forwards only a clean behind `main`, and fails closed on dirty, ahead, diverged, wrong-branch, unmerged, or error states. It never discards foreign work on the default path.

When explicit serving convergence is required and collision/attribution checks permit it, `-Repair` preserves the exact index/worktree tree on a local `preserve/vault-live-*` branch before resetting the serving checkout to fetched `origin/main`. The preservation branch is the recovery anchor; do not replace this with an unpreserved hard reset or clean.

`tools\Install-VaultCheckoutSyncTask.ps1` defines the hidden one-minute `VaultCheckoutSync` task. Installing or changing the live scheduled task is a production/control-plane mutation and is separate from source merge: use the repository's production-change gate and required authorization before activation.

Bootstrap never fetches or converges Git. `bootstrap-glance.vault.checkout` is observation only and reports coherence against the locally cached `origin/main`; the sync task is the owner that refreshes that cache. An incoherent Vault checkout makes Vault bootstrap health degraded so stale orchestration source is not silently treated as current.
