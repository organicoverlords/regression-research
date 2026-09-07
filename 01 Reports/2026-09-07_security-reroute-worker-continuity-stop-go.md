# Security reroute: worker continuity, stop/go recovery, and child-process overlap

Date: 2026-09-07
Status: OBSERVED BEHAVIOR + BOUNDED HYPOTHESIS; internal platform cause unknown
Lineage: `thread:mcp-security-reroute-causality`

## What was observed

During the Owl rigging workstream (`caller_e89dd7b969dd`, `session_e89dd7b969dd`, worktree `tiny3d-10-eagle-stretch-20260907`), the visible ChatGPT UI repeatedly showed the systems-thinking/reroute banner while the same logical worker continued issuing fresh MCP calls underneath it.

The strongest observed sequence was:

- `22:09:54.075 EEST`: process `231e5941-42ea-4034-8517-b908447284db` started.
- From `22:09:57` through `22:11:32`: repeated new `read_output` / process-wait calls were issued while the visible reroute was already present.
- `22:11:35.851`: process `231e5941...` finished successfully.
- `22:11:41.313`: final read of that completed process returned HTTP 200.
- After that final read, there were no new MCP calls and no live child processes for the affected caller until `22:13:34.679`.
- The resulting machine-side silent interval was about 113 seconds.
- The user then stopped the visibly rerouted turn and sent `go`. Fresh substantive work resumed under the same logical `caller_id` and `session_id` rather than a new logical session.
- `22:13:34.679`: fresh MCP work resumed and process `bee76a43-7ceb-4db7-9f20-9fdb13b60f46` started.
- `22:14:10`: additional processes were launched, including `24ecba3c-7417-47ea-8404-d44b4c1993d4` and `b9486459-7bee-402e-8265-2fdca44a4dae` nearly concurrently on different connection IDs while retaining the same caller/session.
- The UI reroute banner reappeared immediately after `go`, but the worker continued making new MCP calls and running Blender experiments underneath it.
- `22:14:18`: process `86afdf23-92b0-489a-861e-108e124bbe5a` started and completed successfully at `22:14:49.136`.
- Additional fresh work continued through `22:17:01.575`, when process `00bf3ca2-3ade-4611-a56f-b97cd884510c` exited successfully. At the subsequent check there were no live processes owned by the affected caller.

## Log signature

The observed reroute pattern is therefore not simply "reroute = no work". It has at least two phases that can be distinguished in local MCP evidence:

1. **Visible reroute while work is still active:** the same logical caller/session continues to launch processes and issue repeated `read_output` calls.
2. **Visible reroute after the active work has ended:** after a final process exit/read, MCP activity can go completely silent with no live child process. In this capture that silent interval lasted about 113 seconds. A user stop -> `go` was followed by fresh MCP work under the same logical caller/session.

This makes a useful operational detector for future incidents:

`active MCP traffic during visible reroute -> final process exit/read -> long zero-MCP/no-child interval while reroute remains visible -> user stop/go -> same caller/session resumes fresh MCP work`

Connection-ID changes are not sufficient on their own to identify a reroute; they occurred during otherwise healthy activity as well.

## Child-process overlap finding

A separate but related Owl incident showed that asynchronous children can outlive the model's immediate active tool-call sequence and continue affecting shared state. An older PowerShell process, Windows PID `25764`, remained alive with Blender child PID `4064` and repeatedly copied/tuned `src/tiny3d/workers/avian_rigging.py` while newer work in the same logical session was already evaluating the same worktree. A newer Blender run then observed code written by the older process, demonstrating a real concurrent-writer race.

The stop/go recovery capture also showed multiple child processes active close together under the same logical caller/session, including simultaneous process launches on different MCP connection IDs.

## Hypothesis to test

The user's hypothesis is plausible and should be tested explicitly: **spawning multiple asynchronous child processes may allow work to continue after the model/turn is no longer actively issuing calls, and overlapping children may create hidden progress or state races during reroute periods.**

What is supported now:

- background OS child processes can continue independently after launch;
- more than one child can be active under the same logical caller/session;
- an older child can continue mutating the shared worktree while newer work is active;
- visible reroute can coexist with ongoing MCP activity;
- visible reroute can later persist after all MCP activity and child processes have stopped;
- stop -> `go` can resume fresh work under the same logical caller/session.

What is **not** established:

- that spawning multiple children causes the platform reroute;
- that a second backend model worker necessarily exists when multiple children overlap;
- that every reroute contains an orphaned child;
- that the 113-second silent interval was caused by child-process management.

The child-process hypothesis currently explains hidden continuation and shared-state contamination better than it explains the reroute trigger itself. Future captures should record, at each user-visible reroute boundary, the count of live children, their parent PIDs/process IDs, start times, final reads, and whether any remain alive after the affected caller stops issuing MCP calls.
