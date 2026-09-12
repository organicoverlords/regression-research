from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "stack-atlas.runtime-deployment-graph.v1"
AUTHORITY = "DERIVED_DEPLOYMENT_NAVIGATION_WITH_EXACT_LOCAL_TASK_AND_FILE_OBSERVATIONS"
_ENV_RE = re.compile(r"%([A-Za-z_][A-Za-z0-9_]*)%")
_WIN_PATH_RE = re.compile(r'"([A-Za-z]:\\[^"\r\n]+?\.(?:py|ps1|cmd|bat|exe))"|(?<!\S)([A-Za-z]:\\[^\s"\r\n]+?\.(?:py|ps1|cmd|bat|exe))', re.I)
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$", re.I)
_GENERIC = {"runtime","deployment","deploy","deployed","graph","dependency","dependencies","scheduler","scheduled","task","script","scripts","copy","copies","drift","live"}

SURFACES: dict[str, dict[str, Any]] = {
    "vault.bootstrap_snapshot": {
        "label": "Vault persistent bootstrap snapshot runtime",
        "components": ["bootstrap_snapshot", "stack_atlas", "vault_checkout_sync"],
        "aliases": ["bootstrap", "bootstrap snapshot", "persistent bootstrap", "VaultBootstrapSnapshot", "VaultBootstrapSnapshotWatchdog", "bootstrap_read_loop", "runtime stack atlas", "AppData stack_atlas copy", "bootstrap producer", "bootstrap alias"],
        "tasks": ["VaultBootstrapSnapshot", "VaultBootstrapSnapshotWatchdog"],
        "pairs": [
            ("producer", "tools/bootstrap_read_loop.py", r"%LOCALAPPDATA%\VaultBootstrapSnapshot\bootstrap_read_loop.py", "refs/remotes/origin/main"),
            ("memory_helper", "tools/memory_recent_projection.py", r"%LOCALAPPDATA%\VaultBootstrapSnapshot\memory_recent_projection.py", "refs/remotes/origin/main"),
            ("atlas", "tools/stack_atlas.py", r"%LOCALAPPDATA%\VaultBootstrapSnapshot\stack_atlas.py", "refs/remotes/origin/main"),
        ],
        "sources": [("installer", "tools/install_bootstrap_snapshot_task.ps1")],
        "outputs": [("latest", ".state/bootstrap/latest.json"), ("producer_status", ".state/bootstrap/producer-status.json")],
        "consumers": [("bootstrap_alias", "MCP persistent process_id=bootstrap")],
        "edges": [
            ("source:installer","task:VaultBootstrapSnapshot","INSTALLS"),
            ("source:installer","task:VaultBootstrapSnapshotWatchdog","INSTALLS"),
            ("source:producer","runtime:producer","PRODUCER_BUNDLE_SYNCS_FROM_CACHED_ORIGIN_MAIN"),
            ("source:memory_helper","runtime:memory_helper","PRODUCER_BUNDLE_SYNCS_FROM_CACHED_ORIGIN_MAIN"),
            ("source:atlas","runtime:atlas","PRODUCER_BUNDLE_SYNCS_FROM_CACHED_ORIGIN_MAIN"),
            ("task:VaultBootstrapSnapshot","runtime:producer","EXECUTES"),
            ("task:VaultBootstrapSnapshotWatchdog","runtime:producer","EXECUTES"),
            ("runtime:producer","runtime:memory_helper","IMPORTS"),
            ("runtime:producer","runtime:atlas","SPAWNS_FOR_FULL_REFRESH"),
            ("runtime:producer","output:latest","WRITES"),
            ("runtime:producer","output:producer_status","WRITES"),
            ("output:latest","consumer:bootstrap_alias","EXPOSED_AS"),
        ],
        "recovery": ["keep exact VaultCheckoutSync active so cached origin/main remains fresh without mutating foreign WIP", "reinstall with tools/install_bootstrap_snapshot_task.ps1 after validating source", "preserve %LOCALAPPDATA%/VaultBootstrapSnapshot rollback copies before replacing a live runtime file"],
    },
    "vault.checkout_sync": {
        "label": "Vault canonical serving checkout remote-ref/convergence owner",
        "components": ["vault_checkout_sync", "stack_atlas", "bootstrap_snapshot"],
        "aliases": ["VaultCheckoutSync", "vault checkout sync", "serving checkout", "canonical vault checkout", "origin/main refresh", "cached origin main", "vault main sync"],
        "tasks": ["VaultCheckoutSync"],
        "pairs": [],
        "sources": [
            ("sync", "tools/Sync-VaultCheckout.ps1"),
            ("installer", "tools/Install-VaultCheckoutSyncTask.ps1"),
        ],
        "outputs": [],
        "consumers": [
            ("origin_main", "cached refs/remotes/origin/main authority"),
            ("serving_checkout", r"C:\Users\Lauri\Desktop\vault canonical serving/read checkout"),
            ("bootstrap_runtime", "VaultBootstrapSnapshot committed deployment source"),
        ],
        "edges": [
            ("source:installer", "task:VaultCheckoutSync", "INSTALLS"),
            ("task:VaultCheckoutSync", "source:sync", "EXECUTES"),
            ("task:VaultCheckoutSync", "consumer:origin_main", "REFRESHES_CACHED_REF"),
            ("consumer:origin_main", "consumer:serving_checkout", "FAST_FORWARD_SOURCE_FOR"),
            ("consumer:origin_main", "consumer:bootstrap_runtime", "SUPPLIES_COMMITTED_SOURCE_TO"),
        ],
        "recovery": [
            "install the hidden exact VaultCheckoutSync task only after production/change-gate review",
            "default sync is fail-closed for dirty/ahead/diverged/wrong-branch worktrees; -Repair preserves exact WIP before convergence",
        ],
    },
    "vault.timeline_materializer": {
        "label": "Vault materialized Timeline scheduled runtime",
        "components": ["timeline_materializer", "memory_bank", "stack_atlas"],
        "aliases": ["timeline", "Vault Timeline Materializer", "materialized timeline", "timeline runtime", "timeline_materializer", "VaultTimeline", "query index", "timeline store"],
        "tasks": ["Vault Timeline Materializer"],
        "pairs": [
            ("entry", "tools/timeline_materializer.py", "$TASK:Vault Timeline Materializer:timeline_materializer.py", "pinned"),
            ("memory_bank", "tools/memory_bank.py", "$SIBLING:entry:memory_bank.py", "pinned"),
            ("memory_sync", "tools/memory_git_sync.py", "$SIBLING:entry:memory_git_sync.py", "pinned"),
            ("memory_timeline", "tools/memory_timeline.py", "$SIBLING:entry:memory_timeline.py", "pinned"),
            ("repo_timeline", "tools/repo_timeline.py", "$SIBLING:entry:repo_timeline.py", "pinned"),
            ("worker_history", "tools/worker_report_history.py", "$SIBLING:entry:worker_report_history.py", "pinned"),
        ],
        "sources": [],
        "outputs": [("store", r"%LOCALAPPDATA%\VaultTimeline\timeline-store.json"), ("index", r"%LOCALAPPDATA%\VaultTimeline\timeline-query-index.pkl"), ("status", r"%LOCALAPPDATA%\VaultTimeline\status.json")],
        "consumers": [("find", "stack_atlas.py find unified discovery"), ("memory", "memory_bank.py context/timeline drill-down")],
        "edges": [
            ("source:entry","task:Vault Timeline Materializer","INSTALLS_SELF_AS_TASK"),
            ("source:entry","runtime:entry","DEPLOYS_TO_PINNED_RUNTIME"),
            ("task:Vault Timeline Materializer","runtime:entry","EXECUTES"),
            ("source:memory_bank","runtime:memory_bank","DEPLOYS_WITH"),
            ("source:memory_sync","runtime:memory_sync","DEPLOYS_WITH"),
            ("source:memory_timeline","runtime:memory_timeline","DEPLOYS_WITH"),
            ("source:repo_timeline","runtime:repo_timeline","DEPLOYS_WITH"),
            ("source:worker_history","runtime:worker_history","DEPLOYS_WITH"),
            ("runtime:entry","runtime:memory_bank","IMPORTS"),
            ("runtime:entry","runtime:memory_sync","IMPORTS"),
            ("runtime:entry","runtime:memory_timeline","IMPORTS"),
            ("runtime:entry","runtime:repo_timeline","IMPORTS"),
            ("runtime:entry","runtime:worker_history","IMPORTS"),
            ("runtime:entry","output:store","WRITES"),
            ("runtime:entry","output:index","WRITES"),
            ("runtime:entry","output:status","WRITES"),
            ("output:index","consumer:find","READ_BY"),
            ("output:store","consumer:memory","READ_BY"),
        ],
        "recovery": ["reinstall through the validated commit-addressed Timeline runtime install-task path", "Timeline state is derived and rebuildable; preserve canonical source/history"],
    },
}


def _env(value: str) -> str:
    return _ENV_RE.sub(lambda m: os.environ.get(m.group(1), m.group(0)), value)


def _hash(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""):
                h.update(block)
        return h.hexdigest()
    except OSError:
        return None


def _file(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"resolved": False, "exists": False}
    try:
        st = path.stat()
    except OSError:
        return {"resolved": True, "path": str(path), "exists": False}
    out = {"resolved": True, "path": str(path), "exists": True, "size_bytes": st.st_size, "mtime_ns": st.st_mtime_ns}
    if path.is_file():
        out["sha256"] = _hash(path)
    return out

def _git_blob_oid(root: Path, ref: str, relpath: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", f"{ref}:{relpath.replace(os.sep, '/') }"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = proc.stdout.strip()
    return value if proc.returncode == 0 and re.fullmatch(r"[0-9a-f]{40,64}", value, re.I) else None


def _file_git_blob_oid(
    root: Path, relpath: str, path: Path | None, *, apply_filters: bool = True
) -> str | None:
    if path is None or not path.is_file():
        return None
    command = ["git", "-C", str(root), "hash-object"]
    if apply_filters:
        command.append(f"--path={relpath.replace(os.sep, '/')}")
    else:
        command.append("--no-filters")
    command.append(str(path))
    try:
        proc = subprocess.run(
            command,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = proc.stdout.strip()
    return value if proc.returncode == 0 and re.fullmatch(r"[0-9a-f]{40,64}", value, re.I) else None


def _arg_paths(arguments: str) -> list[str]:
    out: list[str] = []
    for match in _WIN_PATH_RE.finditer(str(arguments or "")):
        value = match.group(1) or match.group(2)
        if value and value not in out:
            out.append(value)
    return out


def probe_tasks(names: Iterable[str]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Read only named Task Scheduler definitions via schtasks XML; never enumerate the scheduler."""
    names = list(dict.fromkeys(str(n) for n in names if str(n).strip()))
    coverage: dict[str, Any] = {
        "authority": "EXACT_LOCAL_WINDOWS_TASK_DEFINITION",
        "task_names": names,
        "broad_enumeration": False,
        "observation_mode": "SCHTASKS_XML_EXACT_NAME",
    }
    if not names:
        return {}, {**coverage, "status": "NO_TASKS_REQUESTED"}
    if os.name != "nt":
        return {}, {**coverage, "status": "UNAVAILABLE_NON_WINDOWS"}
    started = time.perf_counter()
    result: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    for name in names:
        try:
            proc = subprocess.run(
                ["schtasks.exe", "/Query", "/TN", name, "/XML"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            result[name] = {"TaskName": name, "Exists": False, "Actions": []}
            errors.append({"task": name, "error": str(exc)})
            continue
        if proc.returncode != 0:
            result[name] = {"TaskName": name, "Exists": False, "Actions": []}
            continue
        try:
            root = ET.fromstring(proc.stdout.lstrip("\ufeff"))
        except ET.ParseError as exc:
            result[name] = {"TaskName": name, "Exists": True, "Actions": []}
            errors.append({"task": name, "error": f"invalid task XML: {exc}"})
            continue
        actions: list[dict[str, Any]] = []
        for exec_node in root.findall(".//{*}Exec"):
            def text(child: str) -> str | None:
                node = exec_node.find(f"{{*}}{child}")
                return node.text if node is not None and node.text else None
            actions.append({
                "Execute": text("Command"),
                "Arguments": text("Arguments"),
                "WorkingDirectory": text("WorkingDirectory"),
            })
        result[name] = {"TaskName": name, "Exists": True, "Actions": actions, "ObservationMode": "SCHTASKS_XML_EXACT_NAME"}
    status = "OK" if not errors else "PARTIAL"
    return result, {
        **coverage, "status": status, "returned_tasks": len(result), "errors": errors,
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
    }


def _task_paths(row: dict[str, Any] | None) -> list[str]:
    if not isinstance(row, dict):
        return []
    out: list[str] = []
    for action in row.get("Actions") or []:
        if not isinstance(action, dict):
            continue
        exe = str(action.get("Execute") or "")
        if exe and exe not in out:
            out.append(exe)
        for value in _arg_paths(str(action.get("Arguments") or "")):
            if value not in out:
                out.append(value)
    return out


def _compact_task(row: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {"observed": False}
    actions = []
    for action in row.get("Actions") or []:
        if isinstance(action, dict):
            actions.append({"execute": action.get("Execute"), "arguments": action.get("Arguments"), "working_directory": action.get("WorkingDirectory"), "paths": _task_paths({"Actions":[action]})})
    return {"observed": True, "exists": bool(row.get("Exists")), "state": row.get("State"), "last_task_result": row.get("LastTaskResult"), "last_run_time": row.get("LastRunTime"), "next_run_time": row.get("NextRunTime"), "actions": actions}


def _runtime_path(raw: str, *, root: Path, task_rows: dict[str, dict[str, Any]], resolved: dict[str, Path | None]) -> Path | None:
    if raw.startswith("$TASK:"):
        _, task_name, basename = raw.split(":", 2)
        for value in _task_paths(task_rows.get(task_name)):
            candidate = Path(value)
            if candidate.name.casefold() == basename.casefold():
                return candidate
        return None
    if raw.startswith("$SIBLING:"):
        _, sibling, basename = raw.split(":", 2)
        base = resolved.get(sibling)
        return base.with_name(basename) if base else None
    return Path(_env(raw)).expanduser()


def _pin_from_path(path: Path | None) -> str | None:
    if path:
        for part in reversed(path.parts):
            if _SHA_RE.fullmatch(part):
                return part
    return None


def _comparison(root: Path, source_rel: str, runtime: Path | None, tracking: str) -> dict[str, Any]:
    source = (root / source_rel).resolve()
    runtime_hash, source_hash = _hash(runtime), _hash(source)
    runtime_exact_blob = _file_git_blob_oid(root, source_rel, runtime, apply_filters=False)
    runtime_clean_blob = _file_git_blob_oid(root, source_rel, runtime, apply_filters=True)
    source_blob = _file_git_blob_oid(root, source_rel, source, apply_filters=True)
    out: dict[str, Any] = {
        "runtime_sha256": runtime_hash,
        "worktree_source_sha256": source_hash,
        "runtime_exact_blob": runtime_exact_blob,
        "runtime_clean_blob": runtime_clean_blob,
        "worktree_source_clean_blob": source_blob,
        "matches_worktree_source": bool(runtime_clean_blob and source_blob and runtime_clean_blob == source_blob),
    }
    if runtime is None:
        return {**out, "status": "UNRESOLVED_RUNTIME_PATH", "comparison_basis": "NONE"}
    if runtime_hash is None:
        return {**out, "status": "MISSING_RUNTIME", "comparison_basis": "RUNTIME_PATH"}

    if tracking == "pinned":
        pin = _pin_from_path(runtime)
        out["pinned_commit"] = pin
        desired_blob = _git_blob_oid(root, pin, source_rel) if pin else None
        basis = f"PINNED_GIT_COMMIT:{pin}:{source_rel}" if pin else "PINNED_PATH_COMMIT_UNRESOLVED"
        out["deployment_mechanism"] = "COMMIT_ADDRESSED_RUNTIME"
    elif tracking == "worktree_copy":
        head_blob = _git_blob_oid(root, "HEAD", source_rel)
        out["git_head_clean_blob"] = head_blob
        out["worktree_source_dirty_vs_head"] = bool(source_blob and head_blob and source_blob != head_blob)
        desired_blob = source_blob
        basis = f"CURRENT_WORKTREE_INSTALL_SOURCE:{source_rel}"
        out.update({
            "deployment_mechanism": "INSTALLER_COPY_FROM_WORKTREE",
            "install_identity_persisted": False,
            "drift_semantics": (
                "runtime differs from the source bytes the installer would copy now; "
                "the installer does not persist the historical install-time source identity"
            ),
        })
    else:
        desired_blob = _git_blob_oid(root, tracking, source_rel)
        if tracking == "HEAD":
            out["git_head_clean_blob"] = desired_blob
            out["worktree_source_dirty_vs_head"] = bool(source_blob and desired_blob and source_blob != desired_blob)
        basis = f"GIT_REF:{tracking}:{source_rel}"
        out["desired_ref"] = tracking
        if tracking == "refs/remotes/origin/main":
            out["deployment_mechanism"] = "PRODUCER_BUNDLE_SYNC_FROM_CACHED_ORIGIN_MAIN"
        elif tracking == "HEAD":
            out["deployment_mechanism"] = "PRODUCER_SYNC_FROM_GIT_HEAD"
        else:
            out["deployment_mechanism"] = "GIT_REF_TRACKED_RUNTIME"

    if tracking == "worktree_copy":
        comparison_runtime_blob = runtime_clean_blob
        comparison_mode = "GIT_CLEAN_FILTERED_RUNTIME_VS_WORKTREE_SOURCE"
    else:
        comparison_runtime_blob = runtime_exact_blob
        comparison_mode = "EXACT_RUNTIME_BYTES_VS_GIT_BLOB"
    out.update({
        "desired_clean_blob": desired_blob,
        "comparison_basis": basis,
        "comparison_mode": comparison_mode,
        "runtime_comparison_blob": comparison_runtime_blob,
    })
    if desired_blob is None or comparison_runtime_blob is None:
        out["status"] = "UNKNOWN"
    elif comparison_runtime_blob == desired_blob:
        out["status"] = "MATCH"
    elif tracking == "worktree_copy":
        out["status"] = "DRIFT_FROM_CURRENT_INSTALL_SOURCE"
    else:
        out["status"] = "DRIFT"
    return out


def build_surface(surface_id: str, *, root: Path, task_rows: dict[str, dict[str, Any]] | None = None, task_coverage: dict[str, Any] | None = None, probe_live: bool = True) -> dict[str, Any]:
    spec = SURFACES[surface_id]
    root = Path(root).resolve()
    if task_rows is None:
        if probe_live:
            task_rows, task_coverage = probe_tasks(spec["tasks"])
        else:
            task_rows, task_coverage = {}, {"status":"NOT_PROBED","broad_enumeration":False}
    task_rows = task_rows or {}
    task_coverage = task_coverage or {"status":"INJECTED","broad_enumeration":False}

    nodes: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    resolved_runtime: dict[str, Path | None] = {}

    def add(key: str, kind: str, **values: Any) -> dict[str, Any]:
        row = {"id": f"{surface_id}:{key}", "key": key, "kind": kind, **values}
        nodes.append(row); by_key[key] = row
        return row

    for name, rel in spec.get("sources", []):
        p = (root / rel).resolve()
        add(f"source:{name}", "source_artifact", label=name.replace("_"," "), resolved_path=str(p), observation=_file(p))

    for name, source_rel, _, _ in spec["pairs"]:
        p = (root / source_rel).resolve()
        add(f"source:{name}", "source_artifact", label=f"{name.replace('_',' ')} source", resolved_path=str(p), observation=_file(p))

    for task_name in spec["tasks"]:
        add(f"task:{task_name}", "scheduled_task", label=task_name, task_name=task_name, observation=_compact_task(task_rows.get(task_name)))

    for name, source_rel, raw_runtime, tracking in spec["pairs"]:
        p = _runtime_path(raw_runtime, root=root, task_rows=task_rows, resolved=resolved_runtime)
        resolved_runtime[name] = p
        add(
            f"runtime:{name}", "runtime_artifact", label=f"{name.replace('_',' ')} runtime",
            resolved_path=str(p) if p else None, observation=_file(p),
            deployment=_comparison(root, source_rel, p, tracking),
        )

    for name, raw in spec.get("outputs", []):
        p = (root / raw).resolve() if not raw.startswith("%") else Path(_env(raw)).expanduser()
        add(f"output:{name}", "output_artifact", label=name.replace("_"," "), resolved_path=str(p), observation=_file(p))
    for name, label in spec.get("consumers", []):
        add(f"consumer:{name}", "consumer", label=label)

    edges: list[dict[str, Any]] = []
    for a, b, relation in spec["edges"]:
        if a not in by_key or b not in by_key:
            continue
        edge = {
            "from": by_key[a]["id"],
            "to": by_key[b]["id"],
            "relation": relation,
            "provenance": {
                "evidence_class": "DECLARED",
                "authority": "RUNTIME_SURFACE_SPEC",
                "source": f"SURFACES:{surface_id}",
                "semantics": "declared topology; not current observation",
            },
        }
        deployment = by_key[b].get("deployment") if by_key[b]["kind"] == "runtime_artifact" else None
        if isinstance(deployment, dict):
            edge["verification"] = {
                "evidence_class": "DERIVED",
                "authority": "RUNTIME_DEPLOYMENT_COMPARISON",
                "status": deployment.get("status"),
                "source": deployment.get("comparison_basis"),
                "comparison_mode": deployment.get("comparison_mode"),
            }
        if by_key[a]["kind"] == "scheduled_task" and by_key[b].get("resolved_path"):
            task_name = str(by_key[a].get("task_name") or "")
            task_row = task_rows.get(task_name)
            observed = {x.casefold() for x in _task_paths(task_row)}
            matched = str(by_key[b]["resolved_path"]).casefold() in observed
            edge["observed_action_match"] = matched
            if not isinstance(task_row, dict):
                verification_status = "UNKNOWN"
            elif not bool(task_row.get("Exists")):
                verification_status = "MISSING_TASK"
            else:
                verification_status = "MATCH" if matched else "MISMATCH"
            edge["verification"] = {
                "evidence_class": "OBSERVED",
                "authority": "EXACT_LOCAL_WINDOWS_TASK_DEFINITION",
                "status": verification_status,
                "source": f"TaskScheduler:{task_name}:Actions",
            }
        edges.append(edge)

    known_paths = {str(n.get("resolved_path")).casefold() for n in nodes if n.get("resolved_path")}
    for task_name in spec["tasks"]:
        task_node = by_key[f"task:{task_name}"]
        for index, raw in enumerate(_task_paths(task_rows.get(task_name))):
            candidate = Path(raw)
            if candidate.suffix.casefold() not in {".py",".ps1",".cmd",".bat"} or raw.casefold() in known_paths:
                continue
            node = add(f"observed:{task_name}:{index}", "observed_runtime_entrypoint", label=f"observed task action target {candidate.name}", resolved_path=str(candidate), observation=_file(candidate))
            edges.append({
                "from": task_node["id"],
                "to": node["id"],
                "relation": "EXECUTES_OBSERVED",
                "provenance": {
                    "evidence_class": "OBSERVED",
                    "authority": "EXACT_LOCAL_WINDOWS_TASK_DEFINITION",
                    "source": f"TaskScheduler:{task_name}:Actions",
                    "semantics": "exact task action target observed outside the declared topology",
                },
            })

    edges.sort(key=lambda row: (str(row.get("from")), str(row.get("to")), str(row.get("relation"))))
    drift = [n for n in nodes if (n.get("deployment") or {}).get("status") in {"DRIFT","DRIFT_FROM_CURRENT_INSTALL_SOURCE","MISSING_RUNTIME"}]
    missing_tasks = [n for n in nodes if n["kind"] == "scheduled_task" and n["observation"].get("observed") and not n["observation"].get("exists")]
    if drift:
        status = "DRIFT"
    elif missing_tasks:
        status = "DEGRADED"
    elif probe_live and task_coverage.get("status") not in {"OK","INJECTED"}:
        status = "UNKNOWN"
    else:
        status = "OK"
    return {
        "schema": SCHEMA, "surface_id": surface_id, "label": spec["label"], "components": list(spec["components"]),
        "aliases": list(spec["aliases"]), "authority": AUTHORITY, "status": status, "nodes": nodes, "edges": edges,
        "recovery": list(spec.get("recovery") or []),
        "coverage": {"task_scheduler": task_coverage, "repo_root": str(root), "network_fanout": False, "broad_task_enumeration": False},
        "boundary": "Deployment graph is navigation plus exact local file/task observation. It does not replace the owning source/runtime authority or prove process liveness unless a node explicitly carries that evidence.",
    }


def _tokens(value: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9åäö]+", str(value).casefold()) if len(t) > 1]


def _search_text(surface_id: str, spec: dict[str, Any]) -> str:
    fields = [surface_id, spec["label"], *spec["components"], *spec["aliases"], *spec["tasks"]]
    for name, source, runtime, _ in spec["pairs"]:
        fields.extend((name, source, runtime))
    for name, path in spec.get("sources", []): fields.extend((name,path))
    for name, path in spec.get("outputs", []): fields.extend((name,path))
    for _, label in spec.get("consumers", []): fields.append(label)
    for a,b,r in spec["edges"]: fields.extend((a,b,r))
    return " ".join(fields).casefold()


def _rank(query: str, surface_id: str, spec: dict[str, Any]) -> tuple[float, list[str]] | None:
    terms = _tokens(query)
    if not terms: return None
    text = _search_text(surface_id, spec); hay = set(_tokens(text))
    matched = [t for t in terms if t in hay or t in text]
    meaningful = [t for t in terms if t not in _GENERIC]
    meaningful_matches = [t for t in matched if t not in _GENERIC]
    if meaningful and len(set(meaningful_matches)) < (1 if len(set(meaningful)) <= 1 else 2): return None
    if not meaningful and not matched: return None
    score = 4.0*len(set(matched)) + 2.0*len(set(meaningful_matches))
    normalized = " ".join(terms)
    if normalized in text: score += 20.0
    q = query.casefold()
    if any(alias.casefold() in q or q in alias.casefold() for alias in spec["aliases"]): score += 12.0
    return score, sorted(set(matched))


def search_runtime_dependency_graph(query: str, *, root: Path, limit: int = 3, task_rows: dict[str, dict[str, Any]] | None = None, probe_live: bool = True) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    started = time.perf_counter(); ranked = []
    for sid, spec in SURFACES.items():
        row = _rank(query, sid, spec)
        if row: ranked.append((row[0], sid, row[1]))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    normalized_query = query.casefold()
    alias_exact = [
        row for row in ranked
        if any(alias.casefold() in normalized_query for alias in SURFACES[row[1]]["aliases"] if len(alias.strip()) >= 6)
    ]
    selected = (alias_exact or ranked)[:max(1,min(8,int(limit)))]
    if not selected:
        return [], {"status":"OK","authority":AUTHORITY,"surface_count":len(SURFACES),"matched_surfaces":0,"network_fanout":False,"broad_task_enumeration":False,"latency_ms":round((time.perf_counter()-started)*1000,1)}
    if task_rows is None and probe_live:
        names = [name for _, sid, _ in selected for name in SURFACES[sid]["tasks"]]
        task_rows, task_cov = probe_tasks(names)
    else:
        task_rows = task_rows or {}; task_cov = {"status":"INJECTED" if task_rows else "NOT_PROBED","broad_enumeration":False}
    hits = []
    for score, sid, matched in selected:
        surface = build_surface(sid, root=root, task_rows=task_rows, task_coverage=task_cov, probe_live=probe_live)
        surface["score"] = round(score,3); surface["matched_terms"] = matched; hits.append(surface)
    return hits, {"status":"OK","authority":AUTHORITY,"surface_count":len(SURFACES),"matched_surfaces":len(hits),"task_scheduler":task_cov,"network_fanout":False,"broad_task_enumeration":False,"latency_ms":round((time.perf_counter()-started)*1000,1)}


def runtime_graph_for_components(component_ids: Iterable[str], *, root: Path, task_rows: dict[str, dict[str, Any]] | None = None, probe_live: bool = True) -> dict[str, Any]:
    wanted = {str(x) for x in component_ids if str(x).strip()}
    ids = [sid for sid,spec in SURFACES.items() if wanted & set(spec["components"])]
    if not ids:
        return {"schema":SCHEMA,"authority":AUTHORITY,"components":sorted(wanted),"surfaces":[],"coverage":{"status":"NO_MATCHING_RUNTIME_SURFACE","network_fanout":False,"broad_task_enumeration":False}}
    if task_rows is None and probe_live:
        names = [name for sid in ids for name in SURFACES[sid]["tasks"]]
        task_rows, task_cov = probe_tasks(names)
    else:
        task_rows = task_rows or {}; task_cov = {"status":"INJECTED" if task_rows else "NOT_PROBED","broad_enumeration":False}
    surfaces = [build_surface(sid, root=root, task_rows=task_rows, task_coverage=task_cov, probe_live=probe_live) for sid in ids]
    return {"schema":SCHEMA,"authority":AUTHORITY,"components":sorted(wanted),"surfaces":surfaces,"coverage":{"status":"OK","task_scheduler":task_cov,"network_fanout":False,"broad_task_enumeration":False},"boundary":"Bounded graph slice for the resolved owner; exact returned source/runtime/task observations must be reconciled before mutation or liveness claims."}


def _navigation_surfaces(
    *,
    root: Path,
    surface_id: str | None = None,
    task_rows: dict[str, dict[str, Any]] | None = None,
    probe_live: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ids = [surface_id] if surface_id else sorted(SURFACES)
    unknown = [sid for sid in ids if sid not in SURFACES]
    if unknown:
        return [], {
            "status": "UNKNOWN_SURFACE",
            "surface_ids": unknown,
            "authority": AUTHORITY,
            "network_fanout": False,
            "broad_task_enumeration": False,
        }
    if task_rows is None and probe_live:
        task_names = sorted({name for sid in ids for name in SURFACES[sid]["tasks"]})
        task_rows, task_cov = probe_tasks(task_names)
    else:
        task_rows = task_rows or {}
        task_cov = {
            "status": "INJECTED" if task_rows else "NOT_PROBED",
            "broad_enumeration": False,
            "task_names": sorted(task_rows),
        }
    surfaces = [
        build_surface(
            sid,
            root=root,
            task_rows=task_rows,
            task_coverage=task_cov,
            probe_live=probe_live,
        )
        for sid in ids
    ]
    return surfaces, {
        "status": "OK",
        "authority": AUTHORITY,
        "surface_ids": ids,
        "task_scheduler": task_cov,
        "network_fanout": False,
        "broad_task_enumeration": False,
    }


def _node_summary(node: dict[str, Any], surface_id: str) -> dict[str, Any]:
    return {
        "id": node.get("id"),
        "surface_id": surface_id,
        "key": node.get("key"),
        "kind": node.get("kind"),
        "label": node.get("label"),
        "resolved_path": node.get("resolved_path"),
        "task_name": node.get("task_name"),
    }


def _navigation_nodes(surfaces: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for surface in surfaces:
        sid = str(surface.get("surface_id") or "")
        for node in surface.get("nodes") or []:
            if isinstance(node, dict):
                rows.append(_node_summary(node, sid))
    return sorted(rows, key=lambda row: str(row.get("id") or ""))


def _resolve_navigation_node(term: str, surfaces: Iterable[dict[str, Any]]) -> dict[str, Any]:
    query = str(term or "").strip()
    if not query:
        return {"status": "EMPTY_QUERY", "query": query, "candidates": []}
    q = query.casefold()
    nodes = _navigation_nodes(surfaces)

    def candidates(predicate) -> list[dict[str, Any]]:
        return [row for row in nodes if predicate(row)]

    exact_id = candidates(lambda row: str(row.get("id") or "").casefold() == q)
    if exact_id:
        return {"status": "OK", "query": query, "match_mode": "EXACT_NODE_ID", "node": exact_id[0]}

    exact_key = candidates(lambda row: str(row.get("key") or "").casefold() == q)
    if len(exact_key) == 1:
        return {"status": "OK", "query": query, "match_mode": "EXACT_KEY", "node": exact_key[0]}
    if len(exact_key) > 1:
        return {"status": "AMBIGUOUS", "query": query, "match_mode": "EXACT_KEY", "candidates": exact_key}

    exact_label = candidates(lambda row: str(row.get("label") or "").casefold() == q)
    if len(exact_label) == 1:
        return {"status": "OK", "query": query, "match_mode": "EXACT_LABEL", "node": exact_label[0]}
    if len(exact_label) > 1:
        return {"status": "AMBIGUOUS", "query": query, "match_mode": "EXACT_LABEL", "candidates": exact_label}

    exact_task = candidates(lambda row: str(row.get("task_name") or "").casefold() == q)
    if len(exact_task) == 1:
        return {"status": "OK", "query": query, "match_mode": "EXACT_TASK_NAME", "node": exact_task[0]}
    if len(exact_task) > 1:
        return {"status": "AMBIGUOUS", "query": query, "match_mode": "EXACT_TASK_NAME", "candidates": exact_task}

    terms = _tokens(query)
    fuzzy = []
    for row in nodes:
        haystack = " ".join(
            str(row.get(name) or "")
            for name in ("id", "key", "kind", "label", "resolved_path", "task_name")
        ).casefold()
        if terms and all(term in haystack for term in terms):
            fuzzy.append(row)
    if len(fuzzy) == 1:
        return {"status": "OK", "query": query, "match_mode": "UNIQUE_TOKEN_MATCH", "node": fuzzy[0]}
    if fuzzy:
        return {"status": "AMBIGUOUS", "query": query, "match_mode": "TOKEN_MATCH", "candidates": fuzzy}
    return {"status": "NOT_FOUND", "query": query, "candidates": []}


def _all_navigation_edges(surfaces: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    edges = [
        dict(edge)
        for surface in surfaces
        for edge in (surface.get("edges") or [])
        if isinstance(edge, dict)
    ]
    return sorted(edges, key=lambda row: (str(row.get("from")), str(row.get("to")), str(row.get("relation"))))


def explain_runtime_dependency_node(
    term: str,
    *,
    root: Path,
    surface_id: str | None = None,
    task_rows: dict[str, dict[str, Any]] | None = None,
    probe_live: bool = True,
) -> dict[str, Any]:
    surfaces, coverage = _navigation_surfaces(
        root=root, surface_id=surface_id, task_rows=task_rows, probe_live=probe_live
    )
    if coverage.get("status") != "OK":
        return {
            "schema": "stack-atlas.runtime-explain.v1",
            "status": coverage.get("status"),
            "query": term,
            "coverage": coverage,
        }
    resolution = _resolve_navigation_node(term, surfaces)
    if resolution.get("status") != "OK":
        return {
            "schema": "stack-atlas.runtime-explain.v1",
            "status": resolution.get("status"),
            "query": term,
            "resolution": resolution,
            "coverage": coverage,
            "boundary": "Ambiguous runtime terms are never silently resolved; use an exact returned node id.",
        }
    node = resolution["node"]
    node_id = str(node["id"])
    full_node = next(
        dict(candidate)
        for surface in surfaces
        for candidate in (surface.get("nodes") or [])
        if isinstance(candidate, dict) and candidate.get("id") == node_id
    )
    edges = _all_navigation_edges(surfaces)
    incoming = [edge for edge in edges if edge.get("to") == node_id]
    outgoing = [edge for edge in edges if edge.get("from") == node_id]
    return {
        "schema": "stack-atlas.runtime-explain.v1",
        "status": "OK",
        "query": term,
        "resolution": resolution,
        "node": full_node,
        "incoming": incoming,
        "outgoing": outgoing,
        "coverage": coverage,
        "boundary": "Edge provenance states why a relationship is present; verification states whether named live/source evidence corroborates it. Neither implies process liveness unless explicitly observed.",
    }


def runtime_dependency_path(
    source_term: str,
    target_term: str,
    *,
    root: Path,
    surface_id: str | None = None,
    task_rows: dict[str, dict[str, Any]] | None = None,
    probe_live: bool = True,
) -> dict[str, Any]:
    surfaces, coverage = _navigation_surfaces(
        root=root, surface_id=surface_id, task_rows=task_rows, probe_live=probe_live
    )
    base = {
        "schema": "stack-atlas.runtime-path.v1",
        "source_query": source_term,
        "target_query": target_term,
        "coverage": coverage,
    }
    if coverage.get("status") != "OK":
        return {**base, "status": coverage.get("status")}
    source = _resolve_navigation_node(source_term, surfaces)
    target = _resolve_navigation_node(target_term, surfaces)
    if source.get("status") != "OK" or target.get("status") != "OK":
        status = "AMBIGUOUS" if "AMBIGUOUS" in {source.get("status"), target.get("status")} else "NOT_FOUND"
        return {
            **base,
            "status": status,
            "source_resolution": source,
            "target_resolution": target,
            "boundary": "Ambiguous runtime terms are never silently resolved; use exact returned node ids.",
        }

    source_id = str(source["node"]["id"])
    target_id = str(target["node"]["id"])
    if source_id == target_id:
        return {
            **base,
            "status": "OK",
            "source_resolution": source,
            "target_resolution": target,
            "distance": 0,
            "nodes": [source["node"]],
            "hops": [],
        }

    edges = _all_navigation_edges(surfaces)
    adjacency: dict[str, list[dict[str, Any]]] = {}
    for edge in edges:
        adjacency.setdefault(str(edge.get("from")), []).append(edge)
    for rows in adjacency.values():
        rows.sort(key=lambda row: (str(row.get("relation")), str(row.get("to"))))

    previous: dict[str, tuple[str, dict[str, Any]] | None] = {source_id: None}
    queue = [source_id]
    cursor = 0
    while cursor < len(queue) and target_id not in previous:
        current = queue[cursor]
        cursor += 1
        for edge in adjacency.get(current, []):
            nxt = str(edge.get("to"))
            if nxt in previous:
                continue
            previous[nxt] = (current, edge)
            queue.append(nxt)
            if nxt == target_id:
                break

    if target_id not in previous:
        return {
            **base,
            "status": "NO_PATH",
            "source_resolution": source,
            "target_resolution": target,
            "distance": None,
            "nodes": [],
            "hops": [],
        }

    hops: list[dict[str, Any]] = []
    current = target_id
    while current != source_id:
        prior = previous[current]
        if prior is None:
            raise RuntimeError("runtime path predecessor chain terminated unexpectedly")
        parent, edge = prior
        hops.append(edge)
        current = parent
    hops.reverse()
    node_map = {row["id"]: row for row in _navigation_nodes(surfaces)}
    node_ids = [source_id] + [str(hop["to"]) for hop in hops]
    return {
        **base,
        "status": "OK",
        "source_resolution": source,
        "target_resolution": target,
        "distance": len(hops),
        "nodes": [node_map[node_id] for node_id in node_ids],
        "hops": hops,
        "boundary": "Directed path over the bounded declared/observed deployment graph; edge provenance and verification remain distinct from liveness authority.",
    }
