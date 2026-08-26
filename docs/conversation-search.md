# Downloaded conversation search

`tools/conversation_search.py` searches a local SQLite FTS5 index over preserved ChatGPT conversation exports. The raw downloads remain unchanged and outside Git; the canonical index is `C:\Users\Lauri\Desktop\vault\.state\conversation-search\conversations.sqlite3`.

## Full refresh

```powershell
python tools\conversation_search_refresh.py
```

This is the preferred corpus-ingestion path. It includes the known `Downloads\ChatPortEvidence` and `Downloads\ChatGPTLocalExporter` roots, ChatGPT/export-named download directories, plus a bounded depth-3 metadata walk that finds nested `conversations.json` folders and opaque ZIPs whose central directory contains conversation JSON signatures. This catches archive-organized downloads without performing an unbounded profile scan or treating generic JSONL archives as conversation exports.

The same-machine validation workflow refreshes this canonical derived index while validating the search implementation. Because the database is derived and ignored by Git, retaining it gives workers an immediately usable search surface without changing or replacing any source download.

## Narrow discovery/index

```powershell
python tools\conversation_search.py discover
python tools\conversation_search.py index
```

The narrow path covers the known roots and top-level candidates. Use repeated `--root PATH` arguments to index an explicit protected source set. `--force` re-reads known source items without changing the originals.

Unchanged source items are skipped by path/size/mtime. Changed items are re-read and their source-to-message mappings are reconciled. Exact repeated messages from multiple captures share one search row while every retained source locator remains attached as provenance.

## Search full turns

```powershell
python tools\conversation_search.py search "slopwall"
python tools\conversation_search.py search "exact phrase from old conversation" --literal
```

Results are bounded (maximum 20) and contain conversation ID/title/timestamps, role, matching turn text, one neighboring turn on each side, and every indexed source locator that contains that exact message version. Ordinary search uses FTS token matching; `--literal` searches the full message text as a phrase substring.

## Coverage

```powershell
python tools\conversation_search.py coverage
```

Coverage reports indexed source counts, ignored non-conversation JSON, unresolved sources, deduplicated conversations/messages, role counts, and indexed message-time range. The privacy-safe corpus validator additionally proves that an old-ChatPort-only phrase and a newer-download-only phrase can both be retrieved without printing the phrases themselves; newer-source evidence uses source acquisition time rather than assuming every exporter preserves wall-clock message timestamps.

## Safety boundary

The SQLite database is a disposable derived index, not a replacement for the downloads. Indexing a source never authorizes deleting, moving, renaming, overwriting, or deduplicating the original export. A search hit must remain traceable to its source locator.
