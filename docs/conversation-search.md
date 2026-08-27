# Unified memory corpus

The Vault has one recall system with two source classes:

- `memory/memory-bank.jsonl`: compact, manually curated future memories added when the user explicitly asks.
- `memory/conversations/`: the preserved historical full-conversation corpus used for behavioral/regression analysis.

`memory/conversations/` is private local data, ignored by Git, and is the canonical owner of the historical transcript bytes. Downloads and legacy tool directories are preservation sources only; workers must not depend on those paths after migration.

The rebuildable SQLite FTS5 index is `C:\Users\Lauri\Desktop\vault\.state\conversation-search\conversations.sqlite3`. It is disposable and may always be rebuilt from `memory/conversations/`.

## Search

Ordinary memory recall automatically includes matching historical turns:

```powershell
python tools\memory_bank.py search "MCP routing failure"
```

Manual memory hits and bounded full-conversation hits are returned together. Startup `recent` remains lightweight and reads only curated memory titles.

Direct transcript analysis is also available when corpus-wide counts or explicit literal matching are needed:

```powershell
python tools\conversation_search.py search "slopwall"
python tools\conversation_search.py search "exact historical phrase" --literal
```

`discover` is a read-only inventory command for locating preservation sources under a Downloads directory. It does not index those paths:

```powershell
python tools\conversation_search.py discover --downloads C:\Users\Lauri\Downloads
```

`index` accepts repeatable explicit `--root` values, or uses the canonical Vault corpus when no root is supplied. It has no Downloads shortcut. For the normal canonical rebuild, use `conversation_search_refresh.py` as documented below.

## Preservation and recovery

`tools\conversation_corpus.py` performs explicit one-time preservation operations. It never runs a download queue and never continuously ingests ChatGPT history.

The migration preserves source bytes before deriving anything. The current historical set includes the surviving ChatPort raw corpus, the remaining LocalExporter slice, the legacy regression SQLite itself, and self-contained conversation JSON recovered from that SQLite so conversations survive even if the old database path disappears.

Verify the canonical corpus with hashes:

```powershell
python tools\conversation_corpus.py verify
```

Create a separately checksummed backup with:

```powershell
python tools\conversation_corpus.py backup
```

Rebuild search only from the canonical Vault corpus:

```powershell
python tools\conversation_search_refresh.py
```

Original source files are never deleted, moved, renamed, overwritten, or treated as disposable. The private corpus itself is also never committed to Git.
