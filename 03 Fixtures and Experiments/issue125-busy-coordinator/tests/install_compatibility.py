import json
import os
import pathlib
import shutil
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "coordinator-contract.json").read_text(encoding="utf-8"))


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
    assert run_wrapper(wrappers["python"], store, "snapshot")["counts"]["checkpoints"] == 1
    print(json.dumps({"ok": True, "installed_python_and_rust": True, "contract_version": CONTRACT["contract_version"]}))
finally:
    shutil.rmtree(base, ignore_errors=True)
