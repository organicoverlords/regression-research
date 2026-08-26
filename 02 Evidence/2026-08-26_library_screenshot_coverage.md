# ChatGPT Library screenshot coverage ? 2026-08-26

Issue #86. The screenshot corpus is now text-first: every indexed screenshot is one timestamped searchable occurrence. Exact duplicate pixels remain separate occurrences so recurrence frequency is preserved; semantic memory dedupe is a separate later layer and does not erase source occurrences.

## Proven local checkpoint

- `217` screenshot/image text occurrences are present under `02 Evidence/library_screenshot_text/` and are searched together by `tools/library_screenshot_search.py`.
- The first `100` occurrences are fully joined to the stable-ID visual inventory in `2026-08-26_library_screenshot_shard_000.jsonl`: 62 conversation screenshots, 34 non-conversation images, and 4 byte-proven duplicate occurrences.
- A further `117` timestamped text occurrences are recorded in `2026-08-26_library_screenshot_text_occurrences_001.jsonl`. Of these, 100 correspond to the already completed second visual-review pass; 17 are explicitly `TEXT_EXTRACTED_PENDING_VISUAL_REVIEW`. Stable Library file-ID and final classification backfill for these 117 remains `PENDING_BACKFILL` / `PENDING_RECONCILIATION`.
- Search proof: query `tool` currently reports `70` matching occurrences across `217` indexed occurrences and returns before/after temporal neighbors.
- Secret scan over all 217 text files reports zero live credential candidates. Two text files contain the literal `[REDACTED_CREDENTIAL]` marker; one credential-like value was removed during the new ingestion pass.
- Focused screenshot inventory/search tests pass `11/11`; `git diff --check` passes.

## Duplicate evidence

Page-1 byte-proven pairs remain separate occurrence rows: `071425.png` / `071425(1).png` share SHA-256 `ee10a81eb3673a65262654728f292b8ede28a0f7efe118a8f046645ffb3ad256`; `073256.png` / `073256(1).png` share `fca0229ad66be2adcd1eef647cebb80d2dfe7d8fd2f11779129e554a78195352`; page-1 items 74/75 share `38eb23619fb889250f458c6c9ccea30da86df05e531d7e7e6a53f96ca0f13593`; items 83/84 share `cd12226468f9abbf0ad55c6fcbe28f8a997372478f2832a6d2ea5ad8515f135c`. Later duplicate-looking screenshots are likewise retained as separate timestamped occurrences even when their extracted text is identical.

## Coverage boundary

Full accessible ChatGPT Library image exhaustion is still `NOT_PROVEN`. Library pagination recovered after an earlier `READ_QUERY_PAGE_RATE_LIMIT`, and bounded later slices have been enumerated, but later chronological windows still need to be walked until the Library reports no remaining images. Recursive Google Drive Library enumeration is separately unsupported by the current Files surface and is not included in any exhaustive-coverage claim.

Next reconciliation step: visually review the 17 pending occurrences, backfill stable Library file IDs and final classifications for the 117 text-first rows, then continue chronological Library enumeration without rescanning the 217 completed text occurrences.
