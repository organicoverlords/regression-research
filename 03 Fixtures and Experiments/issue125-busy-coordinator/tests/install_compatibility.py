import json
import os
import pathlib
import shutil
import subprocess
import tempfile
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "coordinator-contract.json").read_text(encoding="utf-8"))
assert CONTRACT["limits"]["default_lease_seconds"] == 240
assert CONTRACT["limits"]["max_lease_seconds"] == 240


def run_wrapper(wrapper: pathlib.Path, store: pathlib.Path, *args: str) -> dict:
    env = os.environ.copy()
    env["BUSY_STORE_PATH"] = str(store)
    cp = subprocess.run([os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(wrapper), *args], env=env, capture_output=True, text=True)
    if cp.returncode != 0:
        raise AssertionError(cp.stderr or cp.stdout)
    return json.loads(cp.stdout)


base = pathlib.Path(tempfile.mkdtemp(prefix="busy-install-compat-"))
try:
    destination = base / "BusyCoordinator"
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "install.ps1"), "-Destination", str(destination)], check=True)
    wrappers = {kind: destination / f"busy-{kind}.cmd" for kind in ("python", "rust")}
    guards = {kind: destination / f"busy-run-{kind}.cmd" for kind in ("python", "rust")}
    assert (destination / "python" / "lease_guard.py").exists()
    for kind, guard in guards.items():
        assert guard.exists(), kind
        guard_help = subprocess.run(
            [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(guard), "--help"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert "short renewable Busy lease" in guard_help.stdout
    for kind, wrapper in wrappers.items():
        assert wrapper.exists(), kind
        help_cp = subprocess.run([os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(wrapper), "--help"], capture_output=True, text=True, check=True)
        for command in CONTRACT["required_commands"]:
            assert command in help_cp.stdout
        for retired in CONTRACT["retired_queue_commands"]:
            assert retired not in help_cp.stdout
        contract = subprocess.run([os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(wrapper), "contract"], capture_output=True, text=True, check=True)
        view = json.loads(contract.stdout)
        assert view["contract_version"] == CONTRACT["contract_version"]
        assert view["implementation"] == kind

    store = base / "state.json"
    actor = "ChatGPT-install-test"
    assert run_wrapper(wrappers["python"], store, "claim", actor, "scope", "--lease-seconds", "60", "--checkpoint", "ctx")["ok"] is True
    py = run_wrapper(wrappers["python"], store, "snapshot", "--scope", "scope")
    rs = run_wrapper(wrappers["rust"], store, "snapshot", "--scope", "scope")
    assert py == rs
    assert run_wrapper(wrappers["rust"], store, "release", actor, "scope", "--checkpoint", "pending")["ok"] is True
    assert run_wrapper(wrappers["python"], store, "snapshot")["counts"]["active"] == 0
    assert run_wrapper(wrappers["python"], store, "inspect", "scope")["job"] is None

    # Installed guard wrappers execute under both interchangeable cores and
    # release their short lease immediately on normal child completion.
    for kind, guard in guards.items():
        guard_store = base / f"guard-{kind}.json"
        marker = base / f"guard-{kind}.marker"
        cp = subprocess.run(
            [
                os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(guard),
                "--store", str(guard_store),
                "--lease-seconds", "3",
                "--heartbeat-seconds", "0.5",
                f"ChatGPT-install-guard-{kind}", f"install:guard:{kind}",
                "--", os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c",
                f"echo ok>{marker}",
            ],
            capture_output=True,
            text=True,
        )
        assert cp.returncode == 0, (kind, cp.stdout, cp.stderr)
        assert marker.exists(), kind
        assert run_wrapper(wrappers[kind], guard_store, "snapshot")["counts"]["active"] == 0

    # T22: equivalent absolute filesystem spellings are one collision boundary
    # across the installed Python/Rust implementations. Arbitrary logical scopes
    # remain opaque; known repository aliases are normalized separately below.
    alias_dir = base / "BusyAliasFixture"
    alias_dir.mkdir()
    alias_file = alias_dir / "scope.txt"
    alias_file.write_text("fixture", encoding="utf-8")
    alias_plain = str(alias_file)
    alias_dotted = str(alias_file.parent) + "\\.\\" + alias_file.name
    alias_slash_case = alias_plain.replace("\\", "/").lower()
    alias_store = base / "alias-state.json"
    alias_owner = "ChatGPT-install-alias-owner"
    alias_other = "ChatGPT-install-alias-other"
    assert run_wrapper(wrappers["python"], alias_store, "claim", alias_owner, alias_plain)["ok"] is True
    conflict = run_wrapper(wrappers["rust"], alias_store, "claim", alias_other, alias_dotted)
    assert conflict["ok"] is False
    assert conflict["reason"] == "scope_already_claimed"
    assert conflict["claim"]["actor"] == alias_owner
    assert run_wrapper(wrappers["python"], alias_store, "inspect", alias_slash_case)["claim"]["actor"] == alias_owner
    assert run_wrapper(wrappers["rust"], alias_store, "release", alias_owner, alias_slash_case)["ok"] is True
    assert run_wrapper(wrappers["python"], alias_store, "snapshot")["counts"]["active"] == 0

    # T23: short and owner-qualified spellings of known repository scopes share
    # one installed Python/Rust collision boundary.
    for index, (short_scope, full_scope) in enumerate((
        ("regression-research:git-ref:refs/heads/install-topic", "organicoverlords/regression-research:git-ref:refs/heads/install-topic"),
        ("agents:file:RULES.md", "organicoverlords/agents:file:RULES.md"),
    )):
        repo_store = base / f"repo-alias-{index}.json"
        repo_owner = f"ChatGPT-install-repo-alias-{index}"
        repo_other = f"ChatGPT-install-repo-other-{index}"
        assert run_wrapper(wrappers["python"], repo_store, "claim", repo_owner, short_scope, "--lease-seconds", "3600")["ok"] is True
        repo_view = run_wrapper(wrappers["rust"], repo_store, "inspect", full_scope)
        assert repo_view["claim"]["scope"] == short_scope
        assert repo_view["claim"]["actor"] == repo_owner
        claim_at = datetime.fromisoformat(repo_view["claim"]["timestamp"].replace("Z", "+00:00"))
        lease_at = datetime.fromisoformat(repo_view["job"]["lease_expires_at"].replace("Z", "+00:00"))
        assert 0 < (lease_at - claim_at).total_seconds() <= 241
        repo_conflict = run_wrapper(wrappers["rust"], repo_store, "claim", repo_other, full_scope)
        assert repo_conflict["ok"] is False and repo_conflict["reason"] == "scope_already_claimed"
        assert run_wrapper(wrappers["rust"], repo_store, "heartbeat", repo_owner, full_scope, "--lease-seconds", "3600")["ok"] is True
        assert run_wrapper(wrappers["python"], repo_store, "release", repo_owner, full_scope)["ok"] is True
        assert run_wrapper(wrappers["rust"], repo_store, "inspect", short_scope)["claim"] is None

    # Observability is non-authoritative: core ownership must keep working even if
    # audit_wrapper.py is missing or broken. Only contract/log/audit depend on it.
    audit_wrapper = destination / "audit_wrapper.py"
    disabled_audit_wrapper = destination / "audit_wrapper.py.disabled"
    audit_wrapper.replace(disabled_audit_wrapper)
    try:
        for kind, wrapper in wrappers.items():
            isolated = base / f"state-no-audit-{kind}.json"
            direct_actor = f"ChatGPT-install-direct-{kind}"
            assert run_wrapper(wrapper, isolated, "list") == {"claims": []}
            assert run_wrapper(wrapper, isolated, "claim", direct_actor, "scope")["ok"] is True
            direct_snapshot = run_wrapper(wrapper, isolated, "snapshot", "--scope", "scope")
            assert direct_snapshot["counts"]["active"] == 1
            assert run_wrapper(wrapper, isolated, "release", direct_actor, "scope")["ok"] is True
    finally:
        disabled_audit_wrapper.replace(audit_wrapper)

    print(json.dumps({"ok": True, "installed_python_and_rust": True, "contract_version": CONTRACT["contract_version"], "core_independent_of_audit_wrapper": True}))
finally:
    shutil.rmtree(base, ignore_errors=True)
