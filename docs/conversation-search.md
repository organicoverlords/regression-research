# Downloaded conversation search

`tools/conversation_search.py` builds a local SQLite FTS5 index over preserved ChatGPT conversation exports. The raw downloads remain unchanged and outside Git; the index defaults to `.state/conversation-search/conversations.sqlite3`.

## Discover sources

```powershell
python tools\conversation_search.py discover
```

Discovery includes the known `Downloads\ChatPortEvidence` and `Downloads\ChatGPTLocalExporter` roots, top-level download directories whose names indicate ChatGPT/export data, and opaque top-level ZIPs whose central directory contains conversation JSON signatures. Discovery does not extract, move, rename, or delete sources.

## Incremental index

```powershell
python tools\conversation_search.py index
```

Unchanged source items are skipped by path/size/mtime. Changed items are re-read and their source-to-message mappings are reconciled. Exact repeated messages from multiple captures share one search row while every retained source locator remains attached as provenance.

Use repeated `--root PATH` arguments to index an explicit protected source set. `--force` re-reads known source items without changing the originals.

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

Coverage reports indexed source counts, ignored non-conversation JSON, unresolved sources, deduplicated conversations/messages, role counts, and indexed message-time range.

## Safety boundary

The SQLite database is a disposable derived index, not a replacement for the downloads. Indexing a source never authorizes deleting, moving, renaming, overwriting, or deduplicating the original export. A search hit must remain traceable to its source locator.
