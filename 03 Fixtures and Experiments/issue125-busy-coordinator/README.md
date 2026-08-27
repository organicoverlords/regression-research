# #125 standalone BUSY coordinator trial

Purpose: prove that BUSY ownership can leave the MCP tool schema without adding any GPT-facing tool or changing the user's work method.

Two intentionally small implementations are kept for comparison:

- `python/busy.py`
- `rust/` (`busy-coordinator.exe` after build)

Both operate on the same existing JSON store and `.lock` file. They implement only `list`, `claim`, and `release` in this first parity stage. The default store remains `%LOCALAPPDATA%\ChatGPTMcpClean\.state\busy-claims.json` so the trial can prove cross-visibility with the current MCP BUSY tools before cutover.

The intended invocation is through the existing `start_process` capability. Neither implementation is an MCP/GPT tool.

The automation layer described in regression-research #125 is the next stage after parity: admission dedupe, renewable ownership, blocked checkpoint/release, automatic cleanup, and bounded next-work redirection. Do not turn this trial into a dashboard, dispatcher, scoring system, or second ownership authority.

Run isolated contention proof:

```powershell
cargo build --release --manifest-path .\rust\Cargo.toml
python .\tests\mixed_contention.py
```
