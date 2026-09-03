# Retired ChatGPT bootstrap distribution

The ChatGPT behavior-bootstrap pipeline is retired. Normal ChatGPT continuity now comes from the current conversation and ChatGPT Memory.

The former `memory_bank.py bootstrap` command and `/Agent Bootstrap/chatgpt-bootstrap.json` / `agents.md` behavior artifacts are retired historical names; the command is no longer exposed and the artifacts are not published as current behavior authority. They must not override current conversation, ChatGPT Memory, Stack Atlas, shared policy, or live evidence.

The Stack Atlas remains an operational map and may still be published independently at `/Agent Bootstrap/stack-atlas.json`. For stack/infra work, consult it before reasoning about dependencies or blast radius, then verify current state through the live proof routes it names.

The Vault remains searchable history/notebook/evidence. `memory_bank.py search`, `context`, `history`, `timeline`, and related read-only views may be used on demand when relevant; none is a startup prerequisite.
