# Incident report - obsolete MCP recovery topology remained operational after topology correction

## Incident identity

- Incident ID: `INC-20260909-2028-EEST-MCP-RECOVERY-CONTRACT-AUTHORITY`
- Time: 2026-09-09 20:28 EEST (Europe/Helsinki)
- Tracking owner: `organicoverlords/agents#287`
- System: GPT1 MCPv4 home-direct recovery authority, Vault/Stack Atlas retrieval, historical MCP edge records.
- Incident class: recovery-authority / stale-operational-state recurrence.

## User correction

The user asked why the recovery files that caused the earlier topology drift were still present, then explicitly requested that this recurrence be preserved as both a lesson and an incident and that Vault, timeline, search, and Atlas be hardened so it does not recur.

## Executive finding

The previous topology correction in regression-research PR #915 was **necessary but insufficient**. It added a correct `mcp-current-topology.json` and labeled `mcp-recovery-state.json` as historical/recovery-only, but the body of `mcp-recovery-state.json` still encoded the obsolete VPS/WireGuard system as concrete machine-readable recovery state.

That meant the file still contained actionable-looking fields such as:

- `deployment.public_origin = https://5-61-91-127.sslip.io`;
- a deployment topology of `VPS Caddy HTTPS -> WireGuard 10.203.0.2:3011 -> ...`;
- `recovery_target.recovery_lanes.automatic_routing = WireGuard only`;
- a selected recovery topology pointing at the VPS/WireGuard route;
- topology-restore evidence and actions that explicitly restored WireGuard;
- old backend generation/deployment identifiers tied to 3011.

Stack Atlas also still exposed `mcp.regression_recovery` entrypoints containing `production-backend-3011` and `replace-wireguard-production.ps1`. A recovery-oriented search could therefore surface the obsolete edge path as a plausible operational next action even though `mcp.current_topology` correctly said GPT1 was local on 3022.

A warning at the top of a machine-readable recovery file did not neutralize the operational semantics inside it.

## Recurrence chain studied

### PR #545 - stale WireGuard edge topology was made canonical in Atlas

PR #545 (`Fix stale WireGuard MCP edge topology in Atlas`, merged 2026-09-05) intentionally encoded the then-verified VPS/WireGuard edge as current production topology. That was valid for that earlier architecture, but it created strong durable Atlas/recovery language around WireGuard and 3011.

### PR #867 - live serving identity was separated from recovery identity

PR #867 (`Fix bootstrap MCP live/recovery identity semantics`, merged 2026-09-09) fixed an important ambiguity: bootstrap stopped presenting the selected recovery deployment/generation as the live serving identity. However, it deliberately preserved the selected recovery target model and its recovery-state semantics.

### 15:34 wrong-WireGuard hardening incident

`01 Reports/2026-09-09_1534_EEST_wrong-wireguard-hardening_after-mcp-recovery_incident_report.md` documented the immediate architectural failure: after a one-off recovery used a WireGuard-named script, the assistant promoted that mechanism into new hardening work even though the intended architecture was simpler and the actual unresolved seam was elsewhere.

### PR #915 - current GPT1 topology was pinned, but the old recovery body survived

PR #915 (`Pin canonical GPT1 MCP topology contract`, merged 2026-09-09) correctly established:

`GPT1 -> https://91-159-12-133.sslip.io -> local Caddy -> 127.0.0.1:3022`

and explicitly excluded the VPS/WireGuard/Tailscale route from GPT1. It also changed bootstrap so current topology and recovery state were separate projections. But it only added warning/scope metadata to the existing v1 recovery document; it did **not** remove the obsolete recovery target from the operational file.

This incident is the proof that semantic separation alone was not enough. The obsolete target had to be structurally removed from operational recovery authority.

## Why existing memory did not prevent recurrence

Targeted memory retrieval before this repair already returned several correct lessons, including:

- `mem-20260909-d317b308`: stale recovery identity must not become live topology;
- `mem-20260909-63702a9a`: MCPv4 home-direct is independent of VPS/Funnel;
- `mem-20260909-90d5c1e0`: observer mismatch cannot authorize serving mutation;
- `mem-20260909-6309b2b5`: use the documented local MCP recovery path.

The problem was not absence of lessons. The problem was that durable operational structures still contradicted them. Search/timeline could retrieve both the correction and the obsolete operational recovery model, leaving future reasoning vulnerable to choosing the wrong authority.

## Root cause

Primary root cause: **obsolete topology was quarantined by prose rather than by data model**.

Contributing causes:

1. `mcp-recovery-state.v1` mixed historical deployment evidence, selected rollback target, routing policy, and recovery actions in one operational contract.
2. Bootstrap hid most dangerous fields, but deeper lookup still exposed the file as canonical recovery state.
3. Atlas `mcp.regression_recovery` retained old WireGuard replacement entrypoints.
4. Generic recovery/edge search terms could rank legacy edge-monitoring records near the current recovery result.
5. Durable memory had the right corrections, but older selected-target memories remained current and the operational contract contradicted the newer local topology.

## Corrective design

The recovery model is changed from "historical target with warning" to **current-local-only recovery authority**:

1. `04 Operating Contracts/mcp-recovery-state.json` becomes `mcp-recovery-state.v2` and contains only the current GPT1 local recovery contract.
2. The only automatic restore target is `current_serving_topology`:
   `https://91-159-12-133.sslip.io/mcp -> local Caddy -> 127.0.0.1:3022`.
3. `clone-a at 127.0.0.1:3011` is explicitly independent local control only, not the public GPT1 target.
4. `legacy_topology_restore_allowed` is `false`.
5. Returning GPT1 to VPS Caddy, WireGuard, reverse SSH, or Tailscale owner authorization is explicitly a new topology/control-plane design requiring separate user authorization, never ordinary recovery.
6. The former v1 document is preserved only under `02 Evidence/mcp-recovery-state-legacy-20260906.json`, wrapped as `mcp-recovery-history.v1`, `authority=historical_evidence_only`, `non_operational=true`.
7. Atlas recovery entrypoints no longer reference `replace-wireguard-production.ps1` or the old `production-backend-3011` scope.
8. Legacy VPS/Tailscale components remain discoverable for archaeology/separate infrastructure, but are explicitly labeled non-GPT1 recovery authorities.
9. Recovery-search triggers are biased toward the current local recovery contract; generic recovery wording must not elevate legacy edge monitoring.
10. A new durable memory lesson supersedes the old selected-recovery-target semantics for GPT1.

## Retrieval invariant

For queries such as:

- `MCP recovery stale recovery file wrong WireGuard GPT1 local 3022`
- `restore working MCP`
- `MCP recovery state`

Vault/Atlas must lead to the current local recovery contract. The old VPS/WireGuard record may be found only as historical evidence or when the query explicitly asks for that legacy edge.

## Acceptance

This incident is resolved only when all of the following are true:

- the operational recovery JSON contains no selectable legacy topology;
- the historical v1 snapshot is explicitly non-operational under `02 Evidence`;
- bootstrap recovery projection exposes current-local recovery semantics only;
- Atlas recovery search ranks the local recovery contract ahead of legacy edge monitoring for the failed query class;
- the three-tool GPT1 contract remains unchanged;
- the lesson is present in canonical memory search;
- the materialized timeline returns this incident/lesson for MCP recovery/WireGuard recurrence queries;
- provenance validation recognizes the new incident and the earlier 15:34 wrong-WireGuard report rather than leaving them as orphan reports.
