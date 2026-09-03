import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
PY = [sys.executable, str(ROOT / "python" / "busy.py")]
RS = ROOT / "rust" / "target" / "release" / "busy-coordinator.exe"
RETIRED = {"enqueue", "ready", "next", "handoff", "block", "complete"}
CORE = {"list", "sweep", "snapshot", "recover", "inspect", "claim", "heartbeat", "release"}


def managed_actor(label: str) -> str:
    return f"ChatGPT-{label}"


def run(kind: str, store: pathlib.Path, *args: str) -> dict:
    cmd = PY if kind == "py" else [str(RS)]
    cp = subprocess.run([*cmd, "--store", str(store), *args], capture_output=True, text=True)
    if cp.returncode != 0:
        raise AssertionError(f"{kind} {' '.join(args)} failed: {cp.stderr or cp.stdout}")
    return json.loads(cp.stdout)


def raw(kind: str, store: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
    cmd = PY if kind == "py" else [str(RS)]
    return subprocess.run([*cmd, "--store", str(store), *args], capture_output=True, text=True)


def read(store: pathlib.Path) -> dict:
    return json.loads(store.read_text(encoding="utf-8"))


subprocess.run(["cargo", "build", "--release", "--manifest-path", str(ROOT / "rust" / "Cargo.toml")], check=True)
base = pathlib.Path(tempfile.mkdtemp(prefix="busy-ownership-parity-"))
try:
    # Both redundant implementations expose the same ownership-only surface.
    py_help = subprocess.run([*PY, "--help"], capture_output=True, text=True, check=True).stdout
    rs_missing = subprocess.run([str(RS)], capture_output=True, text=True)
    assert all(name in py_help for name in CORE)
    for retired in RETIRED:
        assert retired not in py_help
        assert raw("py", base / "retired-py.json", retired).returncode != 0
        assert raw("rs", base / "retired-rs.json", retired).returncode != 0

    store = base / "shared.json"
    actor = managed_actor("parity")
    claimed = run("py", store, "claim", actor, "repo#125", "--lease-seconds", "60", "--checkpoint", "working", "--operation-id", "claim-1")
    assert claimed["ok"] is True
    assert run("rs", store, "inspect", "repo#125")["claim"]["actor"] == actor
    heartbeat = run("rs", store, "heartbeat", actor, "repo#125", "--lease-seconds", "60", "--checkpoint", "still-working", "--operation-id", "heartbeat-1")
    assert heartbeat["ok"] is True
    snapshot_py = run("py", store, "snapshot", "--actor", actor, "--scope", "repo#125")
    snapshot_rs = run("rs", store, "snapshot", "--actor", actor, "--scope", "repo#125")
    assert snapshot_py == snapshot_rs
    assert snapshot_py["counts"] == {"active": 1, "checkpoints": 0, "claims": 1, "legacy_only_claims": 0}

    collision = run("py", store, "claim", managed_actor("other"), "repo#125", "--lease-seconds", "60")
    assert collision["ok"] is False and collision["reason"] == "scope_already_claimed"

    released = run("rs", store, "release", actor, "repo#125", "--checkpoint", "pending-finding", "--operation-id", "release-1")
    assert released["ok"] is True and released["checkpoint"] == "pending-finding"
    checkpoint_view = run("py", store, "snapshot", "--scope", "repo#125")
    assert checkpoint_view["counts"] == {"active": 0, "checkpoints": 1, "claims": 0, "legacy_only_claims": 0}
    assert checkpoint_view["focus"]["job"]["state"] == "checkpoint"
    assert "ready" not in checkpoint_view["counts"] and "blocked" not in checkpoint_view["counts"] and "completed" not in checkpoint_view["counts"]

    # Reclaim keeps the exact-scope checkpoint; ordinary release clears it.
    reclaimed = run("rs", store, "claim", actor, "repo#125", "--lease-seconds", "60")
    assert reclaimed["ok"] is True
    assert run("py", store, "inspect", "repo#125")["job"]["checkpoint"] == "pending-finding"
    assert run("py", store, "release", actor, "repo#125")["ok"] is True
    assert run("rs", store, "inspect", "repo#125")["job"] is None

    # Idempotency remains cross-language.
    idem_store = base / "idem.json"
    first = run("py", idem_store, "claim", actor, "idem", "--lease-seconds", "60", "--operation-id", "same-op")
    replay = run("rs", idem_store, "claim", actor, "idem", "--lease-seconds", "60", "--operation-id", "same-op")
    assert first == replay
    conflict = run("rs", idem_store, "claim", actor, "different", "--lease-seconds", "60", "--operation-id", "same-op")
    assert conflict["ok"] is False and conflict["reason"] == "idempotency_conflict"

    # Compare-and-swap recovery never manufactures ready work.
    for kind in ("py", "rs"):
        recovery = base / f"recover-{kind}.json"
        claim = {"actor": "legacy-owner", "scope": "legacy-scope", "timestamp": "2026-09-03T00:00:00.000Z"}
        recovery.write_text(json.dumps({"claims": [claim], "coordinator": {"version": 1, "jobs": {}, "operations": {}}}, indent=2)+"\n", encoding="utf-8")
        stale = run(kind, recovery, "recover", "legacy-owner", "legacy-scope", "--expected-claim-timestamp", "2026-09-02T23:59:59.000Z")
        assert stale["ok"] is False and stale["reason"] == "claim_changed"
        recovered = run(kind, recovery, "recover", "legacy-owner", "legacy-scope", "--expected-claim-timestamp", claim["timestamp"])
        assert recovered["ok"] is True
        snap = run(kind, recovery, "snapshot")
        assert snap["counts"] == {"active": 0, "checkpoints": 0, "claims": 0, "legacy_only_claims": 0}

    # Legacy queue records migrate to ownership/checkpoint metadata only.
    legacy = {
        "claims": [{"actor": actor, "scope": "claimed-old", "timestamp": "2026-09-03T00:00:00.000Z"}],
        "coordinator": {
            "version": 1,
            "jobs": {
                "claimed-old": {"job_id": "claimed-old", "scope": "claimed-old", "state": "ready", "owner": None, "checkpoint": "claim-context", "updated_at": "2026-09-01T00:00:00.000Z"},
                "ready-drop": {"job_id": "ready-drop", "scope": "ready-drop", "state": "ready", "owner": None, "updated_at": "2026-09-01T00:00:00.000Z"},
                "blocked-keep": {"job_id": "blocked-keep", "scope": "blocked-keep", "state": "blocked", "owner": None, "checkpoint": "waiting-note", "updated_at": "2026-09-01T00:00:00.000Z"},
                "completed-drop": {"job_id": "completed-drop", "scope": "completed-drop", "state": "completed", "owner": None, "updated_at": "2026-09-01T00:00:00.000Z"},
            },
            "operations": {},
        },
    }
    migrated = []
    for kind in ("py", "rs"):
        path = base / f"migrate-{kind}.json"
        path.write_text(json.dumps(legacy, indent=2)+"\n", encoding="utf-8")
        snap = run(kind, path, "snapshot")
        state = read(path)
        assert snap["counts"] == {"active": 1, "checkpoints": 1, "claims": 1, "legacy_only_claims": 0}
        assert set(state["coordinator"]["jobs"]) == {"claimed-old", "blocked-keep"}
        assert state["coordinator"]["jobs"]["claimed-old"]["state"] == "active"
        assert state["coordinator"]["jobs"]["blocked-keep"]["state"] == "checkpoint"
        migrated.append(state)
    assert migrated[0] == migrated[1]

    # Managed lease expiry releases ownership and preserves only an explicit checkpoint.
    expiry = base / "expiry.json"
    assert run("py", expiry, "claim", actor, "expiring", "--lease-seconds", "1", "--checkpoint", "resume-here")["ok"] is True
    time.sleep(1.2)
    swept = run("rs", expiry, "sweep")
    assert swept["expired"] and swept["expired"][0]["scope"] == "expiring"
    snap = run("py", expiry, "snapshot", "--scope", "expiring")
    assert snap["counts"] == {"active": 0, "checkpoints": 1, "claims": 0, "legacy_only_claims": 0}
    assert snap["focus"]["job"]["state"] == "checkpoint"

    print(json.dumps({"ok": True, "python_rust_redundancy": "preserved", "queue_semantics": "retired", "ownership_parity": True}))
finally:
    shutil.rmtree(base, ignore_errors=True)
