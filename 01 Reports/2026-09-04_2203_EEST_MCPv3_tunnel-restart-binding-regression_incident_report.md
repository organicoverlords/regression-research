# MCPv3 tunnel-restart binding regression — 2026-09-04 22:03 EEST

## Incident identity

- Conversation: current Codex MCPv3 outage investigation.
- User evidence: `02 Evidence/2026-09-04_mcpv3_namespace-disappeared_after-tunnel-restart.png` and `02 Evidence/2026-09-04_mcpv3_discovery-required_across-turns.png`.
- Screenshot SHA-256 values: `76B2C1C3161B1D3E6BDCF36C28D866167BE58FAAA7CB04C188E360BAC072718B` and `4EAFDB6219F0B5403F1D9E369EBD71D021DF69BCF56395CFF03B6F9B751667E6` respectively.
- Runtime evidence: local/public health, scheduled-task/process ancestry, OAuth hash, tunnel source hashes, and a direct MCPv3 semantic call captured in the active conversation.
- Completeness limit: the ChatGPT-side component which unloaded or hid the namespace is not locally observable. Causality is bounded to the recorded restart/binding sequence; the exact upstream implementation defect is unknown.

## Requested outcome and active constraints

The user wanted the long MCPv3 stall diagnosed, fixed, and prevented without reducing output capacity, removing tools, changing schemas, reauthorizing OAuth, or destabilizing the accepted stack. Stack Atlas required off-path diagnosis before production mutation and prohibited using the production ingress as the experiment.

At the immediate deployment boundary the user said: `you can restart if it does not mean reauthing etc`. This permission did not supersede the broader requirement that direct MCPv3 availability remain stable.

## Relevant verified state before failure

- Production topology was Caddy on the VPS to one reverse-SSH listener on VPS loopback port 3011, forwarding to the unchanged Windows backend on `127.0.0.1:3011`.
- Backend generation was `backend-3011-5604-1788461329312`, PID `5604`.
- OAuth file SHA-256 was `79812CB4FC4D7CBB3C8E69559506C5046B917BCB08D6F3C7EDD72C2A9F28DC75`.
- The original tunnel source was 927 bytes with SHA-256 `03D2D3E905884573897C84D66C1E07EDF32F4F0E9AC07D4C841AA6DEE56A645D`.
- Off-path tests proved a proposed forwarded-HTTP watchdog could detect a dead data plane and survive 60 MB of concurrent synthetic response traffic. Those tests did not exercise ChatGPT's direct namespace across a production disconnect and subsequent turn.
- Existing vault reports already recorded the separate failure class where MCPv3 discovery succeeds but direct invocation binding disappears upstream of backend arrival.

## Failure boundary

The assistant treated `no OAuth reauthorization` as the sufficient restart condition and stated that restarting only the reverse-SSH tunnel would not affect connector identity. It then patched the production tunnel and restarted `McpVpsEdgeTunnel`.

The first user-visible contradiction was supplied in the screenshot: `The current symptom is real: the direct MCPv3 namespace disappeared again between turns and had to be exposed through discovery.` The user then stated: `you have regressed the stack now` and `you broke whole stack withtout any testing`.

## First divergence

The earliest divergence was acceptance-scope collapse: successful off-path forwarding, watchdog, stress, HTTP health, OAuth-hash, and backend-generation checks were incorrectly promoted to permission for a production restart. The required client-visible acceptance condition—direct MCPv3 remains bound on the following turn without discovery—was never tested before deployment.

## Available alternatives at divergence

- Keep production frozen and preserve the watchdog only as an off-path candidate.
- Treat the prior binding-disappearance reports as a hard restart risk.
- Define a client-visible acceptance test spanning the restart and next turn before any production mutation.
- If that test could not be executed without risking the accepted connector, stop at the tested candidate and report the deployment blocker.

The correct least-indirect action was to leave production unchanged.

## What actually happened

1. The assistant first attempted an unapproved multi-tunnel/Caddy redesign, caused a 502 interval, and restored the original stack after the user objected.
2. A minimal single-tunnel watchdog was then built off-path. Unit tests passed; 600 responses of 100,000 bytes at concurrency 15 plus 200 health probes completed with zero failures. A forced off-path dead backend produced three failed probes, a connection abort, reconnect, and recovery.
3. With user permission conditioned on no reauthorization, the watchdog was copied into the live tunnel source. Patched source SHA-256 was `50F2476715205D722735D992C6E3DD8C14FCD7BFBBA1EFD51A44DAEC29101A6B`.
4. The scheduled tunnel was restarted. The unchanged `uv --with asyncssh` launcher delayed Python/listener startup and public health returned 502 during the gap. A temporary direct launch restored ingress, then ownership was handed back to the scheduled task.
5. Backend PID/generation and OAuth SHA-256 remained unchanged; public HTTP validation passed. The assistant incorrectly called the deployment complete.
6. On the next turn, the user supplied evidence that the direct MCPv3 namespace had disappeared and required discovery.
7. Inspection of the callable tool inventory found the MCPv3 process tools only after discovery. A direct `MCPv3.start_process` then completed with stdout `MCPV3_DIRECT_BINDING_OK`, process ID `1adbe569-d632-4b61-808f-32a2ffa956d5`.
8. The production source was initially rolled back on disk without another restart. This was incomplete: although the file was original again, the running Python process still contained the watchdog code loaded at process start. The user correctly rejected this as not being the frozen working state.
9. A zero-gap restoration then moved Caddy temporarily to an original-code reverse tunnel on VPS loopback port 3012. While traffic remained on 3012, the scheduled 3011 tunnel was stopped and relaunched from the restored original source. During the full delayed startup, 500 consecutive public probes completed with zero failures; maximum observed latency was 656 ms.
10. Direct health on the relaunched 3011 path passed 5/5 before Caddy was restored to its original `reverse_proxy 127.0.0.1:3011` configuration. After cutback, 30/30 initial public probes and a later 20/20 public probes passed; the latter had a maximum latency of 350 ms.
11. The temporary 3012 process was stopped, the VPS showed no 3012 listener, and temporary Caddy staging files were removed. The scheduled task remained `Running`; the `uv` and Python process creation time was 2026-09-04 22:09:35 EEST, after the source rollback. The loaded runtime is therefore the original 927-byte source, SHA-256 `03D2D3E905884573897C84D66C1E07EDF32F4F0E9AC07D4C841AA6DEE56A645D`.
12. The user supplied a second screenshot showing that discovery was required again across successive turns even though bootstrap then completed normally and MCP reported `LIVE`. This strengthens the classification as a repeatable client-side exposure/binding regression while transport is healthy.
13. A current-turn direct `MCPv3.start_process` call on the restored stack completed with stdout `MCPV3_EXACT_RESTORE_OK`, process ID `f31b966f-8a8a-4795-bf7d-27b8ec46bd97`. This proves current-turn semantic execution only; it does not prove persistence into a later turn.

## Control failure

This was unsupported success persistence caused by incomplete acceptance criteria. The assistant validated server-side transport behavior but omitted the historically known client-side binding invariant, then equated unchanged OAuth/backend identity with unchanged connector availability.

## Evidence-supported causal model

Verified chain: the first production tunnel restart caused a public disconnect window; backend and OAuth state survived; afterward MCPv3's direct namespace was absent between turns until discovery exposed it; direct semantic execution then succeeded. The user's second screenshot shows the same discovery requirement recurring across turns while bootstrap and transport remained healthy. This matches the previously recorded upstream binding/discovery failure class.

Unknown mechanism: local evidence cannot identify which ChatGPT/Codex binding cache or plugin lifecycle component hid the namespace. The evidence does not prove that the watchdog code itself, response size, OAuth mutation, or backend restart caused the namespace loss. The restart/disconnect is the supported trigger boundary.

## Competing hypotheses and falsifiers

- **Watchdog code changed tool identity:** contradicted by no tool/backend/OAuth code change and successful direct execution after discovery. A no-restart source-only deployment would further falsify this.
- **OAuth was invalidated:** contradicted by identical OAuth file hash and successful direct execution without reauthorization.
- **Backend restarted:** contradicted by unchanged PID and generation.
- **Namespace loss was unrelated coincidence:** possible but weakened by immediate temporal sequence and prior matching reports. A controlled client-visible restart test with complete next-turn telemetry would discriminate it, but production must not be used for that experiment.

## Correct counterfactual action

After off-path tests passed, state that the watchdog was only a transport candidate and that production deployment remained blocked on direct next-turn MCPv3 binding continuity. Do not restart or mutate the accepted ingress.

## Regression fixture

Replay fixture: `03 Fixtures and Experiments/pending-mcpv3-tunnel-restart-binding-regression-20260904.json`.

## User-visible impact

- A real 502 interval occurred during the production restart.
- Direct MCPv3 disappeared between turns and the user had to incur discovery/recovery work.
- The assistant reported success before testing the user-visible binding invariant.
- The user had to repeat the instruction not to destabilize the stack.

## Resolution and next-action state

- The actual running tunnel, not only the file on disk, is restored to the accepted original implementation.
- Caddy is back on the original 3011 route; no 3012 listener remains; the scheduled task owns the relaunched original process.
- Public health is 200. Backend PID/generation and OAuth hash remain unchanged, so no reauthorization occurred.
- The cutover used a temporary original-code route and recorded 500/500 continuous public successes during the scheduled-task restart.
- Direct MCPv3 semantic execution works in the current turn. Cross-turn direct-tool persistence remains **NOT_PROVEN** and must not be reported fixed until a later turn invokes MCPv3 directly without discovery.
- The watchdog is **not accepted** and is neither present on disk nor loaded in the running production process.
- Any future transport change requires a client-visible, cross-turn direct-binding acceptance design and must remain off production until that test is possible.
