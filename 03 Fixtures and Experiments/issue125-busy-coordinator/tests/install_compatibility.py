import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install.ps1"

with tempfile.TemporaryDirectory(prefix="busy-install-compat-") as td:
    base = Path(td)
    destination = base / "installed"
    destination.mkdir()
    legacy = destination / "busy.py"
    legacy.write_text(
        "import json, pathlib, sys\n"
        "p=pathlib.Path(sys.argv[sys.argv.index('--store')+1])\n"
        "s=json.loads(p.read_text())\n"
        "p.write_text(json.dumps({'claims': s.get('claims', [])}))\n",
        encoding="utf-8",
    )

    installed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(INSTALLER), "-Destination", str(destination)],
        capture_output=True,
        text=True,
    )
    assert installed.returncode == 0, installed.stderr or installed.stdout
    current = destination / "python" / "busy.py"
    assert legacy.read_bytes() == current.read_bytes(), "installer left stale historical busy.py in place"

    store = base / "busy.json"
    store.write_text(json.dumps({
        "coordinator": {
            "version": 1,
            "jobs": {
                "scope-a": {
                    "job_id": "scope-a", "scope": "scope-a", "state": "active",
                    "owner": "actor-a", "checkpoint": "KEEP_ME",
                    "lease_expires_at": None, "claim_timestamp": "2026-08-27T00:00:00.000Z",
                    "updated_at": "2026-08-27T00:00:00.000Z",
                }
            },
            "operations": {},
        },
        "claims": [{"actor": "actor-a", "scope": "scope-a", "timestamp": "2026-08-27T00:00:00.000Z"}],
    }), encoding="utf-8")
    snapshot_args = ["--store", str(store), "snapshot", "--actor", "actor-a", "--scope", "scope-a"]
    py_snapshot = subprocess.run(
        [sys.executable, str(current), *snapshot_args], capture_output=True, text=True,
    )
    rs_snapshot = subprocess.run(
        [str(destination / "rust" / "busy-coordinator.exe"), *snapshot_args], capture_output=True, text=True,
    )
    assert py_snapshot.returncode == 0, py_snapshot.stderr or py_snapshot.stdout
    assert rs_snapshot.returncode == 0, rs_snapshot.stderr or rs_snapshot.stdout
    py_view = json.loads(py_snapshot.stdout)
    rs_view = json.loads(rs_snapshot.stdout)
    assert rs_view == py_view
    assert py_view["counts"] == {
        "active": 1, "ready": 0, "blocked": 0, "completed": 0,
        "claims": 1, "legacy_only_claims": 0,
    }
    assert py_view["focus"]["claim"]["actor"] == "actor-a"

    # Both installed wrappers expose the same versioned contract and audit sidecar
    # while retaining the current canonical core command surface (including recover).
    wrappers = {
        "py": destination / "busy-python.cmd",
        "rs": destination / "busy-rust.cmd",
    }
    contract_views = {}
    for kind, wrapper in wrappers.items():
        contract_run = subprocess.run(
            ["cmd.exe", "/d", "/c", str(wrapper), "contract"],
            capture_output=True, text=True,
        )
        assert contract_run.returncode == 0, contract_run.stderr or contract_run.stdout
        contract_views[kind] = json.loads(contract_run.stdout)
        assert contract_views[kind]["contract_version"] == 2
        assert contract_views[kind]["authority"] == "standalone_busy_coordinator"
        assert "recover" in contract_views[kind]["required_commands"]
        assert {"contract", "log", "audit"}.issubset(contract_views[kind]["required_commands"])
        help_run = subprocess.run(
            ["cmd.exe", "/d", "/c", str(wrapper), "--help"],
            capture_output=True, text=True,
        )
        assert help_run.returncode == 0, help_run.stderr or help_run.stdout
        for command in ("recover", "contract", "log", "audit"):
            assert command in help_run.stdout
    assert contract_views["py"]["required_commands"] == contract_views["rs"]["required_commands"]

    py_heartbeat = subprocess.run(
        ["cmd.exe", "/d", "/c", str(wrappers["py"]),
         "--store", str(store), "heartbeat", "actor-a", "scope-a",
         "--lease-seconds", "60", "--tool", "DesktopCommander",
         "--model", "GPT-5.6-Sol", "--input-tokens", "10", "--output-tokens", "5"],
        capture_output=True, text=True,
    )
    assert py_heartbeat.returncode == 0, py_heartbeat.stderr or py_heartbeat.stdout
    rs_heartbeat = subprocess.run(
        ["cmd.exe", "/d", "/c", str(wrappers["rs"]),
         "--store", str(store), "heartbeat", "actor-a", "scope-a",
         "--lease-seconds", "60", "--tool", "DesktopCommander",
         "--model", "GPT-5.6-Sol", "--total-tokens", "20"],
        capture_output=True, text=True,
    )
    assert rs_heartbeat.returncode == 0, rs_heartbeat.stderr or rs_heartbeat.stdout
    tool_log = subprocess.run(
        ["cmd.exe", "/d", "/c", str(wrappers["rs"]),
         "--store", str(store), "log", "actor-a", "scope-a",
         "--action", "build", "--target", "fixture", "--detail", "sidecar-proof",
         "--duration-ms", "12.5", "--tool", "DesktopCommander", "--model", "GPT-5.6-Sol"],
        capture_output=True, text=True,
    )
    assert tool_log.returncode == 0, tool_log.stderr or tool_log.stdout
    audit_run = subprocess.run(
        ["cmd.exe", "/d", "/c", str(wrappers["py"]),
         "--store", str(store), "audit", "--limit", "20", "--actor", "actor-a"],
        capture_output=True, text=True,
    )
    assert audit_run.returncode == 0, audit_run.stderr or audit_run.stdout
    audit = json.loads(audit_run.stdout)
    assert audit["malformed"] == 0
    command_events = [event for event in audit["events"] if event.get("event_type") == "coordinator_command"]
    assert any(event.get("command") == "heartbeat" and event.get("tool") == "DesktopCommander"
               and event.get("tokens", {}).get("input") == 10 for event in command_events)
    assert any(event.get("command") == "heartbeat" and event.get("tokens", {}).get("total") == 20
               for event in command_events)
    assert any(event.get("event_type") == "tool_event" and event.get("command") == "build"
               and event.get("detail") == "sidecar-proof" for event in audit["events"])

    # Canonical Windows .cmd wrappers must be able to carry the documented
    # maximum provenance payload and reject one character above the summary bound.
    for kind, wrapper in [
        ("py", wrappers["py"]),
        ("rs", wrappers["rs"]),
    ]:
        max_store = base / f"handoff-max-{kind}.json"
        max_handoff = subprocess.run(
            [
                "cmd.exe", "/d", "/c", str(wrapper),
                "--store", str(max_store),
                "handoff", "scout", "repo#194:parent",
                "--finding-id", f"max-{kind}",
                "--source", "s" * 2048,
                "--summary", "x" * 4096,
            ],
            capture_output=True,
            text=True,
        )
        assert max_handoff.returncode == 0, max_handoff.stderr or max_handoff.stdout
        max_state = json.loads(max_store.read_text(encoding="utf-8"))
        max_job = max_state["coordinator"]["jobs"][f"repo#194:parent::handoff:max-{kind}"]
        assert len(max_job["handoff"]["source"]) == 2048
        assert len(max_job["handoff"]["summary"]) == 4096

        over_store = base / f"handoff-over-{kind}.json"
        over_handoff = subprocess.run(
            [
                "cmd.exe", "/d", "/c", str(wrapper),
                "--store", str(over_store),
                "handoff", "scout", "repo#194:parent",
                "--finding-id", f"over-{kind}",
                "--source", "source:ok",
                "--summary", "x" * 4097,
            ],
            capture_output=True,
            text=True,
        )
        assert over_handoff.returncode == 1
        assert over_handoff.stderr.strip() == "summary exceeds 4096 characters"
        assert not over_store.exists(), "rejected wrapper handoff must not create coordinator state"

    released = subprocess.run(
        [sys.executable, str(legacy), "--store", str(store), "release", "actor-a", "scope-a"],
        capture_output=True,
        text=True,
    )
    assert released.returncode == 0, released.stderr or released.stdout
    after = json.loads(store.read_text(encoding="utf-8"))
    assert after["coordinator"]["jobs"]["scope-a"]["checkpoint"] == "KEEP_ME"
    assert after["claims"] == []

print(json.dumps({
    "result": "PASS",
    "legacy_entrypoint_overwritten": True,
    "coordinator_preserved": True,
    "snapshot_parity": True,
    "contract_wrapper_parity": True,
    "audit_sidecar": True,
    "cmd_handoff_bounds": True,
}))
