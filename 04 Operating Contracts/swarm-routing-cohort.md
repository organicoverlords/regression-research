# Swarm routing cohort

Status: canonical machine-admission owner for the ChatGPT swarm.

## Objective

Make one machine-routing decision for a stable work identity and reuse it across workers. This eliminates worker-local machine selection and makes the Linux OMEN the default execution machine without duplicating repository-owned queues or build/proof gates.

## Routing invariant

- `lowvram` and `windows-only`: Windows.
- `portable`, `heavy`, and `p3-runtime`: OMEN first.
- `portable-light`: OMEN first; the existing `p3-vps-light` runner may take overflow when it is freshly proven online and idle.
- Windows is the general fallback only after the cohort has fresh evidence that OMEN is unavailable or saturated for the requested class.
- A valid assignment is sticky for its `work-id`. Another worker joining the same work reuses it rather than choosing a machine independently.
- Release the assignment when the work leaves that machine. Expiry is a crash/stale-worker backstop, not a normal handoff mechanism.

The cohort is machine admission only. It does not own task priority, GitHub issues, repository ownership, BusyCoordinator claims, heavy-flight identity, CI acceptance, merge authority, or proof semantics.

## Entrypoint

```powershell
python C:\Users\Lauri\Desktop\vault\tools\swarm_route.py route --work-id <stable-task-id> --kind <lowvram|windows-only|portable|portable-light|heavy|p3-runtime>
python C:\Users\Lauri\Desktop\vault\tools\swarm_route.py release --work-id <stable-task-id>
python C:\Users\Lauri\Desktop\vault\tools\swarm_route.py status
```

State is atomically stored under `%LOCALAPPDATA%\SwarmRouting\cohort-v1.json` behind a cross-process lock. One capacity probe is shared for 45 seconds so the swarm does not independently probe the same machines.

## OMEN saturation

The cohort reads live OMEN RAM, `/mnt/ue` free space, CPU load, build-lane activity, and existing cohort assignments. Heavy work admits only one heavy cohort assignment at a time and refuses when lane/resource floors are crossed. Portable work can continue beside a heavy job while actual headroom remains. A lane-1 runtime refresh temporarily makes the P3 runtime route fall back rather than racing the build.

These thresholds are admission safeguards, not cleanup authorization.

## VPS role

The VPS remains the persistent edge/coordination machine. Its current supported swarm compute surface is the `p3-vps-light` GitHub runner; the router checks that runner is online and idle before assigning portable-light overflow. No heavy Unreal workload is routed to the VPS.

## Windows role

Windows remains MCP/control transport, LowVRAM owner, and Windows-specific validation host. It is not the default general execution machine while OMEN has capacity.
