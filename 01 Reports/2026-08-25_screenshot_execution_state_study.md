# Screenshot study — execution-state persistence vs turn-local collapse

Date: 2026-08-25
Issue: #69
Status: evidence capture / causal diagnosis still NOT_PROVEN

## Why these screenshots matter

The user reports that conversation screenshots are selective: they are normally captured only when a conversation is special, unusually good, unusually bad, or otherwise worth preserving. Therefore this screenshot set is not a random sample of ChatGPT usage. It is a high-value incident/control corpus and must not be interpreted as prevalence data.

The screenshots are valuable because they preserve visible transition behavior that tool/server logs cannot show by themselves: whether a worker resumes after `go`/`continue`, whether an ordinary tool error changes only the local action or collapses the whole execution state, whether an incidental chat turn displaces the task, and whether the assistant hands executable work back to the user.

## Main observed phenotype

The strongest current description is **active execution-state persistence**, not merely "tool context".

Healthy workers preserve a hierarchy like:

`program/project objective -> current lane -> current issue -> current operation -> individual tool call`

When a lower level succeeds, fails, pauses, or changes route, the higher-level objective remains active. The next admissible action is normally executed without requiring the user to restate the task or re-authorize ordinary work.Bad workers can retain semantic task knowledge while losing the binding between **"this is the next action"** and **"invoke the tool now"**. The visible pattern becomes:

`execute -> identify next action -> response boundary -> describe next action -> response boundary -> ask/expect another go`

This is not ordinary forgetting. In the clearest bad screenshots the worker still knows the repo, tools, plan, and unfinished acceptance target. What disappears is execution momentum/authorization at the turn boundary.

## Strong positive controls

Several Instant workers on 2026-08-25 show the sane phenotype across difficult boundaries: long runs, many tool calls, ordinary parameter errors, subprocess hangs, route switches, pauses, `sup`, `go`, `continue`, completed subtasks, and security-review delays.

Especially strong controls:

- P3 #456 worker: preserved the exact runtime-proof objective through build success, a frozen offscreen editor, kill of only its owned runtime, route change, pause, "what were you doing?", and later `go`/`continue`.
- Regression-research worker: `sup` did not displace the active lane; the following `go` immediately resumed tool execution.
- Memory worker: after a bounded issue reached 100%, a one-word `go` advanced the higher-level program into the next legitimate issue rather than treating the completed issue as the whole task.
- Cleanup worker: reclaimed safe caches, then stopped destructive deletion when `git stash -u` itself hung; it preserved objective, ownership, completed effects, unresolved effects, and safety constraints.
## Strong negative control

The cleanest bad sequence begins with both GitHub and Remote Desktop Commander available. The worker successfully locates `C:\Users\Lauri\Desktop\regression-research`, reads `AGENTS.md`, understands the North Star, and produces an explicit five-step next plan. On subsequent `go` turns it stops consuming that plan and instead says what it *would* inspect next, says the next step *requires* Desktop Commander, and later acknowledges that both connectors are available without invoking them.

This sequence is important because there is no visible route outage, safety block, machine-pressure event, or ambiguity to explain the stop. The worker repeatedly regenerates a next-step representation instead of executing it.

A second negative example is the MCP memory-bank incident: after already using MCP, an ordinary command/CLI problem is followed by the claim that MCP is not actually available as an invokable tool and the command is handed back to the user. The strongest sane contrast is another worker that receives a mundane MCP output-limit error, corrects the parameter, and continues.

## Exclusion classes

Do not count every interruption as execution-state collapse. Separate at least these classes:

- genuine execution-surface outage or authentication failure;
- safety/security block before execution;
- machine saturation or build/runtime resource pressure;
- correct safety stop protecting unrestorable dirty data;
- delivery-context failure where work happened but the requested visible artifact was not surfaced;
- visual-proof misinterpretation;
- execution-state collapse where a usable route and unfinished task remain but the worker reverts to plans/prose/manual handoff.
## What the evidence supports

PROVEN at the behavioral level:

- Instant workers can sustain long multi-tool execution; the mode itself does not imply short or turn-local behavior.
- Security-review/thinking delays can coexist with intact tool execution.
- Ordinary tool errors do not inherently destroy execution context.
- Good workers preserve unresolved acceptance criteria across route changes and completed lower-level units.
- Bad workers can retain excellent semantic recall while failing to execute the next known action.

NOT_PROVEN:

- the internal mechanism causing some runs to enter/retain the sane state;
- whether project memory, recent-memory glance, prompt wording, retrieved context density, or another initialization variable is causal;
- whether semantic deduplication/context compression is the primary cause of the broader regression;
- prevalence of either phenotype, because screenshots are intentionally selective.

Current working hypothesis: bootstrap/context quality may affect the probability that a run establishes a durable task-level execution state, but memory alone is neither necessary nor sufficient. Once established, the sane state can survive conditions that bad workers incorrectly treat as terminal boundaries.

See `02 Evidence/2026-08-25_screenshot_execution_state_index.json` for the searchable rated evidence index.
## Search

Use `python tools/screenshot_evidence.py <term> [--min-rating 1..5]`. Search covers ids, tags, filenames, polarity, phenotype, observations and contrasts. Example: `python tools/screenshot_evidence.py plan_loop --min-rating 5` returns the strongest bad cold-baseline sequence.
