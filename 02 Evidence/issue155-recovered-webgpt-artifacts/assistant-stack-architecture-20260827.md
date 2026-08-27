# WebGPT-led Assistant Stack Architecture — 2026-08-27

Status vocabulary:

- **PROVEN** — observed directly in current live/config/repository evidence.
- **INTENDED** — explicitly required by user or current policy, but not fully proven end-to-end in the observed state.
- **UNKNOWN** — the current state was not observable from the available evidence. It must not be inferred from another surface.

```mermaid
flowchart TB
    U["User<br/>creative/product decisions + genuine external authority"]
    W["WebGPT<br/>continuity / orchestration surface"]

    PI["Personal instructions<br/>private source; contents not reproduced"]
    MEM["ChatGPT memory context<br/>private/advisory; contents not reproduced"]
    HIST["Conversation history<br/>surface-local continuity evidence"]
    VAULT["Vault corpus / memory bank<br/>external evidence store"]

    SCH["WebGPT task scheduler"]
    S1["P3 Asset Sprint 1<br/>hourly :36 — PAUSED"]
    S2["P3 Asset Sprint 2<br/>hourly :48 — PAUSED"]
    S3["P3 Asset Sprint 3<br/>hourly :36 — ENABLED"]
    S4["P3 Asset Sprint 4<br/>hourly :48 — PAUSED"]
    S5["P3 Asset Sprint 5<br/>hourly :00 — PAUSED"]

    C["Codex<br/>separate execution surface"]
    O["Other execution workers<br/>OpenCode / Traycer / Command-Code / others"]

    ACCT["MCP0 account configuration<br/>current state UNKNOWN"]
    WBIND["WebGPT conversation binding<br/>tool injection"]
    CBIND["Codex conversation binding<br/>current state UNKNOWN"]
    CALL["MCP0 tool callability<br/>conversation-scoped"]
    FD["MCP0 stable front door<br/>127.0.0.1:3003/mcp"]
    B1["replaceable backend A<br/>loopback :3001"]
    B2["replaceable backend B<br/>loopback :3002"]
    MCPTOOLS["Exact worker contract<br/>view_image · start_process · read_output · kill_process<br/>busy_list · busy_claim · busy_release"]
    BUSY["MCP0 BUSY state<br/>single live ownership authority"]
    MACHINE["Local machine / shell / processes"]

    POLICY["Canonical shared policy v1.18<br/>local source + GitHub mirror"]
    RAG["Repo AGENTS.md"]
    NORTH["Repo NORTH_STAR.md"]
    ISS["GitHub issues<br/>durable backlog / task anchors"]
    GIT["branches / commits / PRs"]
    CI["CI / build / test evidence"]
    RT["runtime / rendered proof"]
    REPORT["concise reporting / durable evidence"]

    U -->|"INTENDED: one clear request; user owns only real product/external decisions"| W

    PI -->|"PROVEN: current WebGPT receives user-authored instructions"| W
    MEM -->|"PROVEN: advisory memory context is available; not authority"| W
    HIST -->|"PROVEN: conversation-local history is available"| W
    VAULT -.->|"INTENDED: external evidence/continuity read path; current shell access unavailable"| W

    W -->|"PROVEN: scheduler records exist"| SCH
    SCH -->|"PROVEN current metadata"| S1
    SCH -->|"PROVEN current metadata"| S2
    SCH -->|"PROVEN current metadata"| S3
    SCH -->|"PROVEN current metadata"| S4
    SCH -->|"PROVEN current metadata"| S5

    W -->|"INTENDED: dispatch/convergence according to live authority"| S1
    W -->|"INTENDED: dispatch/convergence according to live authority"| S2
    W -->|"INTENDED: dispatch/convergence according to live authority"| S3
    W -->|"INTENDED: dispatch/convergence according to live authority"| S4
    W -->|"INTENDED: dispatch/convergence according to live authority"| S5

    W -.->|"PROVEN: MCP0 seven-tool surface was injected/discovered in this conversation"| WBIND
    C -.->|"UNKNOWN current binding; historical Codex availability is recorded in issue #155"| CBIND
    ACCT -.->|"UNKNOWN: account configuration is not equivalent to conversation injection"| WBIND
    ACCT -.->|"UNKNOWN"| CBIND

    WBIND -->|"PROVEN: initially callable; later Resource-not-found after surface switch/rediscovery"| CALL
    CALL -.->|"UNKNOWN current backend health: failed callability is not backend-health proof"| FD
    CBIND -.->|"UNKNOWN current callability"| FD

    FD -->|"PROVEN configured topology"| B1
    FD -->|"PROVEN configured topology"| B2
    B1 -->|"PROVEN configured contract"| MCPTOOLS
    B2 -->|"PROVEN configured contract"| MCPTOOLS
    MCPTOOLS -->|"PROVEN contract"| BUSY
    MCPTOOLS -->|"PROVEN contract"| MACHINE

    POLICY -->|"PROVEN: generated shared block inherited"| RAG
    NORTH -->|"PROVEN: product direction / current focus"| W
    RAG -->|"PROVEN: repo-local work rules"| W
    ISS -->|"PROVEN: durable task state/evidence"| W

    W -->|"INTENDED normal flow"| ISS
    ISS -->|"INTENDED normal flow"| GIT
    GIT -->|"PROVEN normal validation surfaces exist"| CI
    CI -->|"INTENDED: supporting evidence, not player-visible acceptance alone"| RT
    RT -->|"PROVEN policy + current P3 PR practice: rendered proof gates visible claims"| GIT
    GIT -->|"PROVEN: durable result / publication surface"| REPORT
    REPORT -->|"INTENDED: concise result, complexity absorbed internally"| U

    BUSY -->|"PROVEN shared policy: exact live mutation ownership"| W
    BUSY -->|"INTENDED when callable"| S1
    BUSY -->|"INTENDED when callable"| S2
    BUSY -->|"INTENDED when callable"| S3
    BUSY -->|"INTENDED when callable"| S4
    BUSY -->|"INTENDED when callable"| S5
    BUSY -->|"INTENDED when callable"| C
    BUSY -->|"INTENDED when callable"| O

    S1 -->|"INTENDED implementation / Git / CI / proof"| GIT
    S2 -->|"INTENDED implementation / Git / CI / proof"| GIT
    S3 -->|"INTENDED implementation / Git / CI / proof"| GIT
    S4 -->|"INTENDED implementation / Git / CI / proof"| GIT
    S5 -->|"INTENDED implementation / Git / CI / proof"| GIT
    C -->|"INTENDED bounded execution when explicitly/scheduled-authorized"| GIT
    O -->|"INTENDED bounded execution when explicitly/scheduled-authorized"| GIT
```

## State separation that must not be collapsed

| State | Current observation | Classification |
|---|---|---|
| MCP0 account configuration | Not directly observable from this work session | **UNKNOWN** |
| MCP0 injected/discoverable in this WebGPT conversation | Exact seven-tool surface was discovered | **PROVEN** |
| MCP0 callable in this WebGPT conversation | `busy_list` succeeded earlier; after switching connector surfaces, rediscovery still listed tools but direct calls returned `Resource not found` | **PROVEN observed transition** |
| MCP0 backend/front-door health at the later failure | No matching server telemetry was inspected; callability failure alone cannot establish health | **UNKNOWN** |
| Current Codex conversation binding | Not inspected from Codex itself | **UNKNOWN** |
| Historical Codex MCP0 availability during the #155 triggering incident | Recorded by #155 | **PROVEN historical evidence** |

## Five timed worker records

The scheduler currently contains exactly these five named P3 Asset Sprint records. “Five timed workers” does **not** currently mean five simultaneously active workers.

| Worker | Effective hourly minute | Current state | Current scope |
|---|---:|---|---|
| P3 Asset Sprint 1 | :36 | Paused | Convergence-first asset placement: finish/prove/merge already-implemented placement work before adding more |
| P3 Asset Sprint 2 | :48 | Paused | Same convergence-first scope as Sprint 1 |
| P3 Asset Sprint 3 | :36 | Enabled | Bounded production-map asset-placement increment using existing P3/Tiny3D assets and normal proof path |
| P3 Asset Sprint 4 | :48 | Paused | Same bounded asset-placement scope as Sprint 3 |
| P3 Asset Sprint 5 | :00 | Paused | Same bounded asset-placement scope as Sprint 3 |

Recent scheduler metadata proves last-run timestamps but does not expose attributable outcome artifacts for these five records. A current GitHub PR with `PROVENANCE=chatgpt` is therefore **not** enough to attribute it to a specific Sprint worker without a run/automation identity.

## Current architecture findings

1. **P3 ownership contradiction — PROVEN.** The shared v1.18 block says MCP0 BUSY is the sole live ownership authority and GitHub BUSY titles are projections only. P3’s repo-local “Go work on p3” loop later says the GitHub title “is the claim” and MCP `busy_*` is only a mirror. Both cannot be authoritative simultaneously.
2. **LowVRAM ownership contradiction — PROVEN.** The shared block says MCP0 BUSY is sole live ownership authority; the LowVRAM repo-local section separately names a Traycer production-lanes YAML as the live lane/ownership authority.
3. **Five-worker naming vs live capacity — PROVEN.** Five named scheduler records exist, but only Sprint 3 is enabled at this observation.
4. **Worker-result attribution gap — PROVEN.** The live scheduler exposes worker metadata/last-run time, while current GitHub evidence commonly uses generic `PROVENANCE=chatgpt`; no reliable Sprint-1…5 outcome linkage was observed.
5. **Conversation binding can fail independently of backend health — PROVEN.** This WebGPT conversation first called MCP0 successfully, then after switching connector surfaces could still rediscover the seven tools while direct calls returned `Resource not found`. Current backend health remained unobserved.

Related hardening umbrella: [regression-research #125](https://github.com/organicoverlords/regression-research/issues/125).
