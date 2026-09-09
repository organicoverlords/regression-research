# #861 BusyCoordinator dual-runtime YAGNI audit

Captured: 2026-09-09  
Boundary: #820 remains **OPEN**, so this is read-only/prework. No Busy source, install, claims-store, scheduler, or serving configuration was changed.

## Current owner trace

Busy still has one real authority: `%LOCALAPPDATA%\ChatGPTMcpClean\.state\busy-claims.json`. Current rules and serving navigation consistently route normal ownership operations through `%LOCALAPPDATA%\BusyCoordinator\busy-python.cmd`:

- `.agents/AGENTS.md` uses `busy-python.cmd` for exact-scope recovery.
- Stack Atlas sets `BUSY_CMD` to `busy-python.cmd` and its navigation/manual outputs point to Python.
- `cleanup_converger.py` points to Python.
- the current navigation manual and assistant-stack atlas list Python as the live status/recovery entrypoint.

Rust remains installed and contractually feature-equivalent, but I found no current canonical runbook that selects it for normal ownership or recovery. A bounded GitHub/report search found no evidence of `busy-rust.cmd` being used as a fallback when Python failed. Current process/scheduled-task inspection found no Rust Busy consumer other than this audit probe. This is negative bounded evidence, not proof that Rust has never been invoked.

## This is real duplicated maintenance

On current `origin/main` (`6f840a48c0683696618713d3bc26dc3dac65ab6f`):

| Surface | Size |
|---|---:|
| Python core `python/busy.py` | 630 lines / 24,977 B |
| Rust core `rust/src/main.rs` | 1,176 lines / 39,676 B |
| Rust Cargo manifest + lock | 413 lines / 10,968 B |
| shared audit wrapper | 499 lines / 19,193 B |
| five Busy test files | 652 lines / 32,132 B |

The history discriminator is stronger than LOC: the Python core has **19** commits on current main; the Rust core has **19**; the commit sets are identical (**19 shared, 0 Python-only, 0 Rust-only**). Every core change has therefore been implemented in both languages.

The contract makes that duplication mandatory: `coordinator-contract.json` still requires “python and rust cores expose the same required ownership commands,” and the README says the two implementations are deliberately retained for redundancy/parity. `verify_busy()` also runs `cargo test --release` plus install compatibility whenever the Busy area is selected, while dedicated parity/mixed-contention tests keep cross-language behavior aligned.

## Live safety control

I ran `snapshot --limit 32` through both installed wrappers against the same canonical store. Both returned `ok=true`, and a recursive structural comparison produced **0 semantic differences**. The installed Python, Rust, and contract files match current `origin/main` modulo Windows CRLF, so this was not a stale binary/source comparison.

This proves current equivalence for the read projection; it does **not** by itself authorize deleting one implementation.

## Disk footprint (do not overstate it)

The installed Rust tree is currently ~102.2 MB / 288 files, but **~101.5 MB is Cargo `target/` build cache**. That build cache is not required runtime payload and must not be advertised as architectural savings. Excluding `target/`, the Rust executable/source/manifest payload is ~767 KB; the executable itself is ~674 KB. Python's installed subtree is ~156 KB.

## #861 classification

**SHRINK / DELETE CANDIDATE — dual runtime, not the Busy authority itself.**

Keep the single canonical store and all load-bearing semantics: exact-scope collision ownership, CAS stale recovery, leases/checkpoints, safe temp sweep, actor validation, and path-alias rejection.

After #820 clears, the minimal candidate is:

`one canonical Busy store -> one Python Busy implementation -> existing callers`

and remove the second implementation layer: Rust core/wrapper, Cargo build/install requirement, and parity-only contract/tests. Do **not** replace Rust with another daemon/service/fallback abstraction.

However, #400 explicitly preserved dual Python/Rust implementations on 2026-09-03. Therefore deletion should not happen merely from low observed Rust use. Before mutation, resolve that recent acceptance decision and run one Python-only safety replay covering claim/heartbeat/release/recover/sweep plus Windows reader/contention behavior. If a real independent Rust failover consumer is discovered, this candidate becomes KEEP instead.

## Result

This is the first Busy-specific #861 surface with a measured maintenance multiplier: **19/19 core changes duplicated across two languages** while current serving/navigation selects one language. It is a stronger YAGNI target than removing Busy safety semantics, but remains a post-#820 candidate pending explicit recovery-consumer validation.
