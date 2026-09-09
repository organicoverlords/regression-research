# Swarm routing cohort

Status: canonical machine-admission owner for the ChatGPT swarm.

## Objective

Make one machine-routing decision for a stable work identity and reuse it across workers. This eliminates worker-local machine selection and makes the Linux OMEN the default execution machine without duplicating repository-owned queues or build/proof gates.

## Routing invariant

- `lowvram` and `windows-only`: Windows.
- `portable`, `heavy`, and `p3-runtime`: OMEN first.
- `portable-light`: OMEN first. The `p3-vps-light` runner may take overflow only for a caller that explicitly opts in with `--allow-vps` and owns a supported execution adapter. Generic routing and `swarm_exec.py` do not opt in, so they fall back to Windows rather than emit an unexecutable VPS assignment.
- Windows is the general fallback only after the cohort has fresh evidence that OMEN is unavailable or saturated for the requested class.
- A valid assignment is sticky for its `work-id`. Another worker joining the same work reuses it rather than choosing a machine independently.
- Physical/session ownership is stronger than fungible compute fallback. For work that belongs to an exact machine or its visible desktop/session, pass `--owner-node-id <node-id>`. An explicit owner never falls back to another node when its transport is unavailable; it stays owner-bound and fails closed. An explicit owner correction supersedes a stale sticky decision for that work ID.
- Laptop-desktop/UI work (for example an editor already open on the laptop desktop) must use `--owner-node-id omen-linux-laptop`; never substitute KONE merely because the OMEN SSH probe is unavailable. KONE remains `kone-gpu-desktop`.
- Release the assignment when the work leaves that machine. Expiry is a crash/stale-worker backstop, not a normal handoff mechanism.

The cohort is machine admission only. It does not own task priority, GitHub issues, repository ownership, BusyCoordinator claims, heavy-flight identity, CI acceptance, merge authority, or proof semantics.

## Execution-node identity invariant

Route labels are not machine identities. The canonical node registry is `execution-node-topology.json`. Every fresh machine probe and new routing assignment must carry `node_id`, `node_name`, `node_alias`, `machine_class`, `observed_hostname`, and `node_identity_status` in addition to the compatibility `route`/`route_label`.

- `kone-gpu-desktop` = **KONE GPU desktop** = user-facing **GPU machine**: Windows HP Pavilion Gaming Desktop TG01-2xxx with NVIDIA GeForce GTX 1660 SUPER. Compatibility route label: `windows`.
- `omen-linux-laptop` = **OMEN Linux laptop** = user-facing **laptop**: Linux HP OMEN Laptop 15-dc0xxx with NVIDIA GeForce GTX 1070 Max-Q. Compatibility route label: `omen`.
- These are physically distinct machines. Never describe a KONE/`windows` hardware sample as the laptop or an OMEN/`omen` sample as the GPU desktop. Both machines have NVIDIA GPUs, so the word `GPU` alone is not sufficient evidence of node identity.
- A hostname mismatch or missing hostname must not borrow the expected physical node identity. Emit `node_id: null`, preserve `expected_node_id`, and mark the identity status unverified/mismatched.
- The `p3-vps-light` runner is a separate logical execution node with compatibility route label `vps`.

## Entrypoint

```powershell
python C:\Users\Lauri\Desktop\vault\tools\swarm_route.py route --work-id <stable-task-id> --kind <lowvram|windows-only|portable|portable-light|heavy|p3-runtime>
# Exact physical/session ownership; never cross-node fallback:
python C:\Users\Lauri\Desktop\vault\tools\swarm_route.py route --work-id <stable-task-id> --kind <work-kind> --owner-node-id omen-linux-laptop
python C:\Users\Lauri\Desktop\vault\tools\swarm_route.py release --work-id <stable-task-id>
python C:\Users\Lauri\Desktop\vault\tools\swarm_route.py status
python C:\\Users\\Lauri\\Desktop\\vault\\tools\\swarm_exec.py --work-id <stable-task-id> --kind portable --repo-root <repo> -- python -m pytest <tests>
# Adapter owners only; do not use for generic swarm_exec work:
python C:\\Users\\Lauri\\Desktop\\vault\\tools\\swarm_route.py route --work-id <stable-task-id> --kind portable-light --allow-vps
```

State is atomically stored under `%LOCALAPPDATA%\SwarmRouting\cohort-v1.json` behind a cross-process lock. One capacity probe is shared for 45 seconds so distinct worker invocations do not independently open fresh OMEN SSH sessions. `route` and `status` expose `probe_cache_reused`, `probe_age_seconds`, and `probe_cache_ttl_seconds` so callers can prove whether the warm path avoided remote probing. `--refresh-probe` intentionally bypasses that cache; the standalone `probe` command is likewise a fresh diagnostic and should not be used as the routine warm routing path.

## OMEN saturation and scratch recovery

The cohort reads live OMEN RAM, both root (`/`) and NVMe (`/mnt/ue`) free space, CPU load, build-lane activity, and existing cohort assignments. `disk_free_gb` remains the NVMe-compatible field; `root_disk_free_gb` and `nvme_disk_free_gb` make the storage tier explicit. Runtime admission checks both tiers while the hot runtime still has root-resident state; portable and heavy scratch admission uses NVMe headroom. **Assignments are observability/stickiness, not utilization authority**: an OMEN lease may be waiting in a repo-owned queue or may have outlived active compute, so lease count never makes the machine `full` by itself. Actual RAM/disk/load and repository-owned lane locks/queues govern execution concurrency.

OMEN is a dedicated hot development node. Its NVMe is expected to carry rebuildable Unreal scratch close to useful capacity rather than preserve a large permanently-empty fraction. Router hard floors are deliberately modest (`heavy` 16 GiB, `p3-runtime` 12 GiB, `portable` 10 GiB, `portable-light` 8 GiB). When a new assignment would miss a disk floor, the router performs **one** bounded call to `/home/aatuska/ue-work/reclaim-p3-linux-scratch.sh`, which may remove only inactive P3 lane-generated overlay/build/cache state, then re-probes OMEN and continues there when recovered. Active lane locks/processes, source snapshots, engine base, Content/assets, Saved/proof/evidence, and user data are preserved. If safe scratch reclaim cannot recover the hard floor, normal fallback remains explicit.

Heavy/runtime single-flight remains repository-owned. The router does not duplicate that queue and does not use sticky lease counts as a substitute for it.

Routing policy carries an explicit epoch. Assignments from an older epoch remain sticky only until their already-issued expiry; reuse does **not** extend them. This drains pre-change Windows/VPS fallbacks without moving an in-flight job, after which the next request is admitted again under the current OMEN-first policy. Current-epoch assignments keep normal sticky-TTL renewal.

## VPS role

The VPS remains the persistent edge/coordination machine. Its compute surface is the repo-scoped `p3-vps-light` GitHub runner. Because generic `swarm_exec.py` has no GitHub-Runner execution adapter, VPS assignment is capability-gated and disabled by default. Only a caller that owns a supported runner handoff may pass `--allow-vps`; the router still checks that runner is online and idle before such an assignment. No heavy Unreal workload is routed to the VPS.

## Windows role

Windows remains MCP/control transport, LowVRAM owner, GitHub-authenticated coordination host, and Windows-specific validation host. It is not the default general execution machine while OMEN has capacity. Generic Linux-compatible source/test work must use `swarm_exec.py` when no repository-specific OMEN entrypoint exists; the helper snapshots the current non-ignored Git working copy to `/mnt/ue/worker-workspaces/<work-id>` and executes it there in one SSH session. A non-OMEN cohort assignment is returned explicitly rather than being silently executed on Windows.
