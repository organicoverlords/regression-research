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
                }
            },
            "operations": {},
        },
        "claims": [{"actor": "actor-a", "scope": "scope-a", "timestamp": "2026-08-27T00:00:00.000Z"}],
    }), encoding="utf-8")
    released = subprocess.run(
        [sys.executable, str(legacy), "--store", str(store), "release", "actor-a", "scope-a"],
        capture_output=True,
        text=True,
    )
    assert released.returncode == 0, released.stderr or released.stdout
    after = json.loads(store.read_text(encoding="utf-8"))
    assert after["coordinator"]["jobs"]["scope-a"]["checkpoint"] == "KEEP_ME"
    assert after["claims"] == []

print(json.dumps({"result": "PASS", "legacy_entrypoint_overwritten": True, "coordinator_preserved": True}))