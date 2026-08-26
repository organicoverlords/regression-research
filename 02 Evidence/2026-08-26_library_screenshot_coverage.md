# ChatGPT Library screenshot coverage ? 2026-08-26

Issue #86. The screenshot corpus is now text-first: every indexed screenshot is one timestamped searchable occurrence. Exact duplicate pixels remain separate occurrences so recurrence frequency is preserved; semantic memory dedupe is a separate later layer and does not erase source occurrences.

## Proven local checkpoint

- `274` screenshot/image occurrences are now searchable together by `tools/library_screenshot_search.py`: the first 100 inventory-backed occurrences plus 117 in occurrence ledger `_001` and 57 in `_002`.
- The first `100` occurrences are fully joined to the stable-ID visual inventory in `2026-08-26_library_screenshot_shard_000.jsonl`: 62 conversation screenshots, 34 non-conversation images, and 4 byte-proven duplicate occurrences.
- A further `117` timestamped occurrences are recorded in `2026-08-26_library_screenshot_text_occurrences_001.jsonl`. All 117 are visually reviewed and joined one-to-one to stable Library file IDs: 31 conversation screenshots, 82 non-conversation images, and 4 byte-proven duplicate occurrences. No `PENDING_BACKFILL`, `PENDING_RECONCILIATION`, or pending visual-review rows remain in this ledger.
- A further `57` occurrences are recorded in `2026-08-27_library_screenshot_text_occurrences_002.jsonl`. All 57 are visually reviewed and joined one-to-one to stable Library file IDs: 35 conversation screenshots, 21 non-conversation images, and 1 byte-proven duplicate occurrence.
- Search proof: query `tool` currently reports `89` matching occurrences across `274` indexed occurrences and returns before/after temporal neighbors. `authorization` reports 4 occurrences; `provider retries exhausted` reports 83.
- Strict token-shaped secret scan over the indexed screenshot text reports zero live credential candidates. Two existing page-2 text files contain the literal `[REDACTED_CREDENTIAL]` marker; those markers remain searchable evidence without retaining the credential values.
- The classified 274-occurrence checkpoint is 128 conversation screenshots, 137 non-conversation images, and 9 exact duplicate occurrences. The new 57-row `_002` ledger is fully stable-ID joined and visually reviewed. Focused validation passes `28/28`; `git diff --check` passes.

## Duplicate evidence

Page-1 byte-proven pairs remain separate occurrence rows: `071425.png` / `071425(1).png` share SHA-256 `ee10a81eb3673a65262654728f292b8ede28a0f7efe118a8f046645ffb3ad256`; `073256.png` / `073256(1).png` share `fca0229ad66be2adcd1eef647cebb80d2dfe7d8fd2f11779129e554a78195352`; page-1 items 74/75 share `38eb23619fb889250f458c6c9ccea30da86df05e531d7e7e6a53f96ca0f13593`; items 83/84 share `cd12226468f9abbf0ad55c6fcbe28f8a997372478f2832a6d2ea5ad8515f135c`. The reconciled 117-row ledger adds four byte-proven duplicate occurrences: `190006(1)` -> `190006` (`7b7fefdf4232de8a505a13eb6d319579e881d850adc8184d6711dab86954f509`), `190014(1)` -> `190014` (`aa1216a8802d2059c36816544ea6a4aede9227d95a407cee6964433b8e36c152`), `190023(1)` -> `190023` (`3ba1412bd8a16f78ee6f7f7f89b7bb780d297995d6d2a36d5ce52dbd079a1990`), and `014950(1)` -> `014950` (`d2c8dde921c7f49081c64b1ea4313adc8b56e4f5f22d923460493597def92ce4`). Each remains a separate searchable occurrence. The 57-row `_002` ledger adds `N?ytt?kuva 2026-05-28 120606(1).png` -> `N?ytt?kuva 2026-05-28 120606.png`, both 60,974 bytes with SHA-256 `64d983e7df5d46625488ee9e2b8049a988adafb2fcb829b60d68a3e8dbadf23b`; the duplicate remains its own occurrence.

## Coverage boundary

Full accessible ChatGPT Library image exhaustion is still `NOT_PROVEN`. Library pagination recovered after an earlier `READ_QUERY_PAGE_RATE_LIMIT`, and bounded later slices have been enumerated, but later chronological windows still need to be walked until the Library reports no remaining images. Recursive Google Drive Library enumeration is separately unsupported by the current Files surface and is not included in any exhaustive-coverage claim.

Next step: continue chronological Library enumeration after the current 274 completed occurrences; do not rescan them. The exact next known Library item is `/40 ? Visual and 3D Assets/52186.jpg` (`file_00000000e3f071fd8baada2c6594183d`). Each newly encountered screenshot gets one timestamped searchable occurrence before any semantic clustering or memory synthesis.
