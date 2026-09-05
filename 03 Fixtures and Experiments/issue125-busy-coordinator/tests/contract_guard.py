import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "coordinator-contract.json"
PY_SOURCE = ROOT / "python" / "busy.py"
RS_SOURCE = ROOT / "rust" / "src" / "main.rs"
WRAPPER_SOURCE = ROOT / "python" / "audit_wrapper.py"


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_command_help(text: str) -> set[str]:
    match = re.search(r"\{([^}]+)\}", text)
    if not match:
        raise RuntimeError("cannot parse command surface")
    return {item.strip() for item in match.group(1).split(",") if item.strip()}


def parse_python_commands() -> set[str]:
    cp = subprocess.run([sys.executable, str(PY_SOURCE), "--help"], capture_output=True, text=True, check=False)
    if cp.returncode != 0:
        raise RuntimeError(f"python help failed: {cp.stderr.strip()}")
    return parse_command_help(cp.stdout)


def parse_rust_commands() -> set[str]:
    text = RS_SOURCE.read_text(encoding="utf-8")
    matches = re.findall(r"<((?:list\|sweep\|snapshot\|)[^>]+)>", text)
    if not matches:
        raise RuntimeError("cannot parse Rust command surface")
    return {item.strip() for item in matches[-1].split("|") if item.strip()}


def wrapper_extra_commands() -> set[str]:
    spec = importlib.util.spec_from_file_location("busy_audit_wrapper", WRAPPER_SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load wrapper source")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return set(module.EXTRA_COMMANDS)


def validate_store(state: object, contract: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(state, dict):
        return ["store_root_not_object"]
    claims = state.get("claims")
    if not isinstance(claims, list):
        return ["claims_not_list"]
    claim_by_scope: dict[str, dict] = {}
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            errors.append(f"claim_{index}_not_object")
            continue
        if not all(isinstance(claim.get(key), str) and claim.get(key) for key in ("actor", "scope", "timestamp")):
            errors.append(f"claim_{index}_invalid_shape")
            continue
        scope = claim["scope"]
        if scope in claim_by_scope:
            errors.append(f"duplicate_claim_scope:{scope}")
        claim_by_scope[scope] = claim

    coordinator = state.get(contract["canonical_store"]["coordinator_key"])
    if not isinstance(coordinator, dict):
        return errors + ["coordinator_not_object"]
    expected_version = contract["canonical_store"]["coordinator_schema_version"]
    if coordinator.get("version") != expected_version:
        errors.append(f"coordinator_version:{coordinator.get('version')}!=expected:{expected_version}")
    jobs = coordinator.get("jobs")
    operations = coordinator.get("operations")
    if not isinstance(jobs, dict):
        errors.append("jobs_not_object")
        jobs = {}
    if not isinstance(operations, dict):
        errors.append("operations_not_object")
        operations = {}
    if len(operations) > int(contract["limits"]["max_operations"]):
        errors.append("operations_unbounded")

    allowed_states = set(contract["scope_metadata_states"])
    for scope, job in jobs.items():
        if not isinstance(job, dict):
            errors.append(f"job_not_object:{scope}")
            continue
        if job.get("scope") != scope or job.get("job_id") != scope:
            errors.append(f"job_identity_mismatch:{scope}")
        state_name = job.get("state")
        if state_name not in allowed_states:
            errors.append(f"invalid_scope_metadata_state:{scope}:{state_name}")
            continue
        claim = claim_by_scope.get(scope)
        owner = job.get("owner")
        if claim is None:
            errors.append(f"active_metadata_missing_claim:{scope}")
        elif owner != claim.get("actor"):
            errors.append(f"active_metadata_owner_mismatch:{scope}")

    return errors


def live_root() -> pathlib.Path:
    local = pathlib.Path(os.environ.get("LOCALAPPDATA", pathlib.Path.home() / "AppData" / "Local"))
    return local / "BusyCoordinator"


def run_cmd_wrapper(wrapper: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
    if os.name == "nt":
        command = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(wrapper), *args]
    else:
        command = [str(wrapper), *args]
    return subprocess.run(command, capture_output=True, text=True, check=False)


def live_command_surface(wrapper: pathlib.Path) -> set[str]:
    cp = run_cmd_wrapper(wrapper, "--help")
    if cp.returncode != 0:
        raise RuntimeError(f"help failed: {cp.stderr.strip()}")
    return parse_command_help(cp.stdout)


def live_contract(wrapper: pathlib.Path) -> dict:
    cp = run_cmd_wrapper(wrapper, "contract")
    if cp.returncode != 0:
        raise RuntimeError(f"contract failed: {cp.stderr.strip() or cp.stdout.strip()}")
    return json.loads(cp.stdout)


def check_sync(errors: list[str], warnings: list[str], strict: bool, label: str,
               deployed: pathlib.Path, source: pathlib.Path, result: dict) -> None:
    if not deployed.exists():
        (errors if strict else warnings).append(f"deployed_source_missing:{label}")
        return
    deployed_hash = sha256(deployed)
    source_hash = sha256(source)
    result[label] = {"deployed_sha256": deployed_hash, "source_sha256": source_hash, "synced": deployed_hash == source_hash}
    if deployed_hash != source_hash:
        (errors if strict else warnings).append(f"deployed_source_drift:{label}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only BusyCoordinator ownership-contract inspector")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--strict-source-sync", action="store_true")
    args = parser.parse_args()

    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8-sig"))
    core_required = set(contract["core_required_commands"])
    required = set(contract["required_commands"])
    retired = set(contract["retired_queue_commands"])
    errors: list[str] = []
    warnings: list[str] = []
    py_commands = parse_python_commands()
    rs_commands = parse_rust_commands()
    extras = wrapper_extra_commands()
    if required != core_required | extras:
        errors.append("manifest_required_commands_do_not_match_core_plus_wrapper_extensions")
    if core_required & retired:
        errors.append("retired_queue_commands_still_required")
    for label, commands in (("python", py_commands), ("rust", rs_commands)):
        if commands != core_required:
            errors.append(f"{label}_core_surface_mismatch:{','.join(sorted(commands))}")
        leaked = commands & retired
        if leaked:
            errors.append(f"{label}_retired_queue_surface:{','.join(sorted(leaked))}")

    result: dict = {
        "ok": False,
        "contract_version": contract["contract_version"],
        "authority": contract["authority"],
        "core_required_commands": sorted(core_required),
        "retired_queue_commands": sorted(retired),
        "source": {
            "python_commands": sorted(py_commands),
            "rust_commands": sorted(rs_commands),
            "wrapper_extensions": sorted(extras),
            "python_sha256": sha256(PY_SOURCE),
            "rust_sha256": sha256(RS_SOURCE),
        },
        "errors": errors,
        "warnings": warnings,
    }

    if args.live:
        install = live_root()
        store = pathlib.Path(os.environ.get("BUSY_STORE_PATH") or os.environ.get("MCP_BUSY_STORE_PATH") or
                             (install.parent / "ChatGPTMcpClean" / ".state" / "busy-claims.json"))
        live_info: dict = {"root": str(install), "store": str(store), "wrappers": {}, "source_sync": {}}
        for implementation in ("python", "rust"):
            wrapper = install / f"busy-{implementation}.cmd"
            if not wrapper.exists():
                errors.append(f"live_wrapper_missing:{implementation}")
                continue
            try:
                commands = live_command_surface(wrapper)
                if commands != required:
                    errors.append(f"live_{implementation}_surface_mismatch")
                contract_view = live_contract(wrapper)
                if contract_view.get("contract_version") != contract["contract_version"]:
                    errors.append(f"live_{implementation}_contract_version_mismatch")
                live_info["wrappers"][implementation] = {"commands": sorted(commands), "contract": contract_view}
            except Exception as exc:
                errors.append(f"live_{implementation}_probe_error:{exc}")
        check_sync(errors, warnings, args.strict_source_sync, "python_core", install / "python" / "busy.py", PY_SOURCE, live_info["source_sync"])
        check_sync(errors, warnings, args.strict_source_sync, "legacy_python_entry", install / "busy.py", PY_SOURCE, live_info["source_sync"])
        check_sync(errors, warnings, args.strict_source_sync, "rust_source", install / "rust" / "src" / "main.rs", RS_SOURCE, live_info["source_sync"])
        check_sync(errors, warnings, args.strict_source_sync, "audit_wrapper", install / "audit_wrapper.py", WRAPPER_SOURCE, live_info["source_sync"])
        check_sync(errors, warnings, args.strict_source_sync, "contract_manifest", install / "coordinator-contract.json", CONTRACT_PATH, live_info["source_sync"])
        if store.exists():
            try:
                state = json.loads(store.read_text(encoding="utf-8"))
                state_errors = validate_store(state, contract)
                errors.extend(f"live_store:{item}" for item in state_errors)
                live_info["store_invariants_ok"] = not state_errors
                live_info["claim_count"] = len(state.get("claims", [])) if isinstance(state, dict) else None
            except Exception as exc:
                errors.append(f"live_store_read_error:{exc}")
        result["live"] = live_info

    result["ok"] = not errors
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
