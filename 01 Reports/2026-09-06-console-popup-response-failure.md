# Incident Report — Console Popup Help Request Failure

Date: 2026-09-06
Scope: User request to stop recurring visible console windows (`gh.exe`, `git.exe`, Python/PowerShell-related windows) appearing on a roughly five-minute cadence.

## Executive summary

The response failed because I did not prioritize immediate symptom containment and strict process attribution. Instead, I broadened the investigation into multiple subsystems, created GitHub issues and PRs, ran repeated validation loops, and modified both the Vault timeline materializer path and the MCP launcher path before proving which process tree was actually creating the visible windows.

The direct user goal was simple: stop the popups. The correct first move was to temporarily disable the five-minute `Vault Timeline Materializer` scheduled task, confirm the popups stopped, then investigate its child-process behavior offline. I did not do that. This caused a long sequence of work that consumed time without reliably removing the user-visible symptom.

## What was known early

The first screenshot showed a console tied to the UV-managed Python installation. Live Task Scheduler inspection then found `Vault Timeline Materializer`, repeating every five minutes, originally launching the timeline materializer through that Python installation.

The scheduled task was changed from `python.exe` to `pythonw.exe`. That removed the parent Python console window but did not guarantee that child console applications such as `git.exe` and `gh.exe` would remain hidden.

The timeline materializer source was later confirmed to launch many `git` and `gh` subprocesses during each refresh. That five-minute task cadence matched the user's report closely and should have remained the primary suspect until disproved.

## Where the response went wrong

### 1. Immediate containment was skipped

Instead of temporarily disabling the five-minute task to stop the visible disruption first, I tried to preserve full operation while diagnosing. That was the wrong priority for an active user-facing nuisance.

A temporary disable would have provided a clean binary test:
- popups stop -> task/process tree is the source;
- popups continue -> investigate another five-minute task.

That would have reduced the problem space immediately.

### 2. I broadened scope too early

I investigated `ChatGPTMcpClean` and its process launcher because MCP-launched commands also use PowerShell and can execute `gh.exe`. I found a legitimate hidden-window regression there and opened issue #137 / PR #138.

That work was technically related to console-window suppression, but it was not yet proven to be the source of the user's five-minute popup storm. Spending time there delayed direct resolution of the scheduled-task symptom.

### 3. I treated incomplete evidence as proof

The first timeline-materializer fix centralized subprocess execution behind `CREATE_NO_WINDOW` and tests passed. A manual scheduled run also showed many `git.exe` and `gh.exe` processes with `MainWindowHandle = 0` at sampled moments.

I then reported the problem as fixed. That conclusion was too strong.

Later, stricter attribution using the direct `pythonw.exe` parent PID plus Win32 `IsWindowVisible` showed the first fix was incomplete: several direct `git.exe` children still had visible windows, while `gh.exe` children were hidden.

This means the earlier verification method was insufficient for transient console windows. A zero handle at one sample did not prove a process never displayed a window.

### 4. Too much process was added around a small operational fix

The response created or used:
- GitHub issues,
- branches,
- worktrees,
- PRs,
- BusyCoordinator claims,
- repeated test runs,
- multiple scheduled/manual verification runs,
- MCP launcher investigation,
- production-change considerations.

Some of those are appropriate for durable engineering work, but they were excessive before the immediate user symptom had been contained.

### 5. Verification loops became the work instead of serving the work

Several tool calls were spent re-checking state that had already been established, waiting on long-running process probes, or correcting command/quoting mistakes. That extended the interaction while the user still had the original problem.

Examples included:
- repeated bootstrap/state checks,
- repeated Task Scheduler checks,
- GitHub CLI quoting failures,
- repeated process-handle sampling,
- a PowerShell parser error during visibility probing,
- a long-running visibility probe,
- re-checking MCP repo state after the primary five-minute task was already known.

## Technical findings

### Vault Timeline Materializer

Observed scheduled-task behavior:
- task name: `Vault Timeline Materializer`
- cadence: every five minutes (`PT5M`)
- action after first change: `pythonw.exe ...\timeline_materializer.py refresh --quiet`
- timeline materializer launches many `git.exe` and `gh.exe` child processes per refresh.

First durable fix:
- wrapped six direct `subprocess.run(...)` sites with a helper using Windows `CREATE_NO_WINDOW`.
- tests passed.
- PR #655 merged in `organicoverlords/regression-research`.

Later direct visibility proof showed this was insufficient for Git for Windows:
- `gh.exe` children were observed hidden;
- multiple direct `git.exe` children were observed with visible top-level windows.

A second change was started in an isolated worktree to add Windows `STARTUPINFO`, `STARTF_USESHOWWINDOW`, and `SW_HIDE` in addition to `CREATE_NO_WINDOW`.

That second change passed the focused unit test and the full timeline materializer test file, but live end-to-end verification was not completed before the user stopped the tool work.

### MCP launcher

A separate real defect was found in `ChatGPTMcpClean`:
- Node used `windowsHide: true`;
- the PowerShell launcher omitted explicit `-WindowStyle Hidden`;
- an existing regression test expected it.

That fix was implemented and PR #138 merged. However, this was not proven to be the cause of the user's five-minute popup storm and should not have been allowed to distract from the scheduled timeline task.

## Important state anomaly

During later verification, `Vault Timeline Materializer` was found in `Disabled` state.

The exact actor or command that disabled it was not established from the evidence gathered. I should not attribute that disable to any specific process or user without proof.

Because the task was disabled, subsequent scheduled-run verification became inconsistent and should have been treated as a separate state change requiring attribution before more testing.

## Why roughly 25 minutes were spent without delivering the requested outcome

The time was consumed by a combination of:
- preserving operation instead of stopping the noisy task first;
- investigating an unproven secondary subsystem;
- converting the incident into durable repo/PR work before containment;
- relying on weak process-window sampling and then having to re-open the diagnosis;
- repeated verification and command-correction loops;
- trying to prove a polished permanent fix while the immediate requirement was simply to stop the popups.

The main failure was prioritization, not lack of technical activity. A large amount of work was performed, but too little of it was aligned with the user's immediate need.

## What should have happened

1. Identify the five-minute scheduled task.
2. Temporarily disable `Vault Timeline Materializer` immediately after user authorization.
3. Wait through at least one expected trigger boundary to verify the popup storm stops.
4. If it stops, reproduce the task manually from a controlled parent process.
5. Attribute every visible window to its exact parent/command line.
6. Fix only that child-launch path.
7. Prove no attributed child window becomes visible using Win32 visibility checks, not a single `MainWindowHandle` snapshot.
8. Re-enable the task only after the proof passes.
9. Then create/merge the durable repo change.

That sequence would have minimized disruption and avoided unrelated investigation.

## Current status at the point tools were stopped

- The original five-minute task was found disabled.
- The first `CREATE_NO_WINDOW` timeline-materializer fix was merged but later shown incomplete for some `git.exe` children.
- A stronger `STARTUPINFO` / `SW_HIDE` change existed in an isolated worktree and passed unit tests, but live proof had not completed.
- The separate MCP hidden-window fix was merged, but it was secondary to the five-minute timeline-task problem.
- Therefore the console-popup incident should not be considered conclusively resolved based on the work completed in this interaction.

## Corrective process rule

For an active repetitive desktop disruption, containment must come before durable engineering cleanup. Do not broaden to adjacent subsystems until the visible process has been attributed by parent PID and command line. Do not report success from a transient handle snapshot; require direct visibility proof across the full reproduced process run.