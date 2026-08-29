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

    # Canonical Windows .cmd wrappers must be able to carry the documented
    # maximum provenance payload and reject one character above the summary bound.
    for kind, wrapper in [
        ("py", destination / "busy-python.cmd"),
        ("rs", destination / "busy-rust.cmd"),
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
    "cmd_handoff_bounds": True,
}))
