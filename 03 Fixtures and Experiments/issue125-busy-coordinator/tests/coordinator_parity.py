import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone

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
    assert snapshot_py["counts"] == {"active": 1, "claims": 1, "legacy_only_claims": 0}

    collision = run("py", store, "claim", managed_actor("other"), "repo#125", "--lease-seconds", "60")
    assert collision["ok"] is False and collision["reason"] == "scope_already_claimed"

    released = run("rs", store, "release", actor, "repo#125", "--checkpoint", "pending-finding", "--operation-id", "release-1")
    assert released["ok"] is True and released["checkpoint"] == "pending-finding"
    checkpoint_view = run("py", store, "snapshot", "--scope", "repo#125")
    assert checkpoint_view["counts"] == {"active": 0, "claims": 0, "legacy_only_claims": 0}
    assert checkpoint_view["focus"]["job"] is None
    assert "ready" not in checkpoint_view["counts"] and "blocked" not in checkpoint_view["counts"] and "completed" not in checkpoint_view["counts"]

    # Reclaim starts clean because released checkpoint text is not retained in BUSY.
    reclaimed = run("rs", store, "claim", actor, "repo#125", "--lease-seconds", "60")
    assert reclaimed["ok"] is True
    assert run("py", store, "inspect", "repo#125")["job"]["checkpoint"] is None
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
        fresh_timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        claim = {"actor": "legacy-owner", "scope": "legacy-scope", "timestamp": fresh_timestamp}
        recovery.write_text(json.dumps({"claims": [claim], "coordinator": {"version": 1, "jobs": {}, "operations": {}}}, indent=2)+"\n", encoding="utf-8")
        stale = run(kind, recovery, "recover", "legacy-owner", "legacy-scope", "--expected-claim-timestamp", "2026-09-02T23:59:59.000Z")
        assert stale["ok"] is False and stale["reason"] == "claim_changed"
        recovered = run(kind, recovery, "recover", "legacy-owner", "legacy-scope", "--expected-claim-timestamp", claim["timestamp"])
        assert recovered["ok"] is True
        snap = run(kind, recovery, "snapshot")
        assert snap["counts"] == {"active": 0, "claims": 0, "legacy_only_claims": 0}

    # Legacy queue/checkpoint records migrate to live ownership metadata only.
    legacy = {
        "claims": [{"actor": actor, "scope": "claimed-old", "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")}],
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
        assert snap["counts"] == {"active": 1, "claims": 1, "legacy_only_claims": 0}
        assert set(state["coordinator"]["jobs"]) == {"claimed-old"}
        assert state["coordinator"]["jobs"]["claimed-old"]["state"] == "active"
        migrated.append(state)
    assert migrated[0] == migrated[1]

    # Bare repo-relative path spellings are ambiguous collision identities. Both
    # cores reject new path-like claims unless they are absolute or namespaced.
    for kind in ("py", "rs"):
        path_scope_store = base / f"path-scope-{kind}.json"
        path_actor = managed_actor(f"path-scope-{kind}")
        rejected = run(kind, path_scope_store, "claim", path_actor, "scripts/ci/job.py")
        assert rejected["ok"] is False
        assert rejected["reason"] == "ambiguous_relative_path_scope"
        accepted = run(kind, path_scope_store, "claim", path_actor, "p3:file:scripts/ci/job.py")
        assert accepted["ok"] is True
        assert run(kind, path_scope_store, "release", path_actor, "p3:file:scripts/ci/job.py")["ok"] is True


    # Known repository aliases are one exact collision identity across both cores.
    repo_aliases = [
        (
            "regression-research:git-ref:refs/heads/topic",
            "organicoverlords/regression-research:git-ref:refs/heads/topic",
        ),
        ("agents:file:RULES.md", "organicoverlords/agents:file:RULES.md"),
    ]
    for index, (short_scope, full_scope) in enumerate(repo_aliases):
        for first, second in (("py", "rs"), ("rs", "py")):
            alias_store = base / f"repo-alias-{index}-{first}-{second}.json"
            alias_owner = managed_actor(f"alias-{index}-{first}")
            alias_other = managed_actor(f"alias-other-{index}-{second}")
            claimed = run(first, alias_store, "claim", alias_owner, short_scope, "--lease-seconds", "3600")
            assert claimed["ok"] is True
            view = run(second, alias_store, "inspect", full_scope)
            assert view["claim"]["actor"] == alias_owner
            assert view["claim"]["scope"] == short_scope
            claim_at = datetime.fromisoformat(view["claim"]["timestamp"].replace("Z", "+00:00"))
            lease_at = datetime.fromisoformat(view["job"]["lease_expires_at"].replace("Z", "+00:00"))
            assert 0 < (lease_at - claim_at).total_seconds() <= 241
            collision = run(second, alias_store, "claim", alias_other, full_scope)
            assert collision["ok"] is False and collision["reason"] == "scope_already_claimed"
            heartbeat = run(second, alias_store, "heartbeat", alias_owner, full_scope, "--lease-seconds", "3600")
            assert heartbeat["ok"] is True
            assert run(first, alias_store, "inspect", short_scope)["claim"]["timestamp"] == heartbeat["claim"]["timestamp"]
            assert run(first, alias_store, "release", alias_owner, full_scope)["ok"] is True
            assert run(second, alias_store, "inspect", short_scope)["claim"] is None

    # Existing same-owner alias records converge to one canonical claim. Different
    # owners for aliases of the same exact scope fail closed instead of picking one.
    alias_short = "regression-research:git-ref:refs/heads/stored-topic"
    alias_full = "organicoverlords/regression-research:git-ref:refs/heads/stored-topic"
    first_at = datetime.now(timezone.utc)
    second_at = first_at + timedelta(seconds=1)
    first_stamp = first_at.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    second_stamp = second_at.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    migrated_alias_states = []
    for kind in ("py", "rs"):
        alias_path = base / f"stored-alias-{kind}.json"
        alias_path.write_text(
            json.dumps(
                {
                    "claims": [
                        {"actor": actor, "scope": alias_short, "timestamp": first_stamp},
                        {"actor": actor, "scope": alias_full, "timestamp": second_stamp},
                    ],
                    "coordinator": {
                        "version": 1,
                        "jobs": {
                            alias_short: {"job_id": alias_short, "scope": alias_short, "state": "active", "owner": actor, "checkpoint": "short-context", "updated_at": first_stamp},
                            alias_full: {"job_id": alias_full, "scope": alias_full, "state": "active", "owner": actor, "checkpoint": "full-context", "updated_at": second_stamp},
                        },
                        "operations": {},
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        snap = run(kind, alias_path, "snapshot", "--scope", alias_full)
        state = read(alias_path)
        assert snap["counts"] == {"active": 1, "claims": 1, "legacy_only_claims": 0}
        assert state["claims"] == [{"actor": actor, "scope": alias_short, "timestamp": second_stamp}]
        assert set(state["coordinator"]["jobs"]) == {alias_short}
        migrated_alias_states.append(state)
    assert migrated_alias_states[0] == migrated_alias_states[1]

    for kind in ("py", "rs"):
        conflict_path = base / f"stored-alias-conflict-{kind}.json"
        conflict_path.write_text(
            json.dumps(
                {
                    "claims": [
                        {"actor": managed_actor("stored-a"), "scope": alias_short, "timestamp": first_stamp},
                        {"actor": managed_actor("stored-b"), "scope": alias_full, "timestamp": second_stamp},
                    ],
                    "coordinator": {"version": 1, "jobs": {}, "operations": {}},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        failed = raw(kind, conflict_path, "snapshot", "--scope", alias_short)
        assert failed.returncode != 0
        assert "conflicting BUSY claims canonicalize to one scope" in (failed.stderr + failed.stdout)


    # Windows readers can hold the canonical file without delete sharing. Writers
    # must still be able to claim/release instead of wedging on rename forever.
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        reader_store = base / "reader-held.json"
        reader_actor = managed_actor("reader-held")
        assert run("py", reader_store, "claim", reader_actor, "reader-held-scope", "--lease-seconds", "60")["ok"] is True
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel32.CreateFileW.restype = wintypes.HANDLE
        handle = kernel32.CreateFileW(str(reader_store), 0x80000000, 0x1 | 0x2, None, 3, 0x80, None)
        invalid = wintypes.HANDLE(-1).value
        if handle == invalid:
            raise OSError(ctypes.get_last_error(), "CreateFileW reader fixture failed")
        try:
            assert run("py", reader_store, "heartbeat", reader_actor, "reader-held-scope", "--lease-seconds", "60")["ok"] is True
            assert run("rs", reader_store, "release", reader_actor, "reader-held-scope")["ok"] is True
            assert read(reader_store)["claims"] == []
        finally:
            kernel32.CloseHandle(handle)

    # Explicit sweep removes only stale exact-store temps whose encoded writer PID is proven dead.
    def exited_pid() -> int:
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait(timeout=10)
        return proc.pid

    temp_sweep_results = []
    for kind in ("py", "rs"):
        temp_store = base / f"temp-sweep-{kind}.json"
        temp_store.write_text(json.dumps({"claims": [], "coordinator": {"version": 1, "jobs": {}, "operations": {}}}) + "\n", encoding="utf-8")
        stale_dead_pid = exited_pid()
        fresh_dead_pid = exited_pid()
        stale_dead = pathlib.Path(str(temp_store) + f".{stale_dead_pid}.tmp")
        fresh_dead = pathlib.Path(str(temp_store) + f".{fresh_dead_pid}.tmp")
        live_old = pathlib.Path(str(temp_store) + f".{os.getpid()}.tmp")
        malformed = pathlib.Path(str(temp_store) + ".not-a-pid.tmp")
        sibling = base / f"other-store.{stale_dead_pid}.tmp"
        for path in (stale_dead, fresh_dead, live_old, malformed, sibling):
            path.write_text(path.name, encoding="utf-8")
        old = time.time() - 120
        for path in (stale_dead, live_old, malformed, sibling):
            os.utime(path, (old, old))

        sweep = run(kind, temp_store, "sweep")
        assert sweep["removed_temp_count"] == 1
        assert sweep["removed_temp_files"] == [{"name": stale_dead.name, "pid": stale_dead_pid}]
        assert not stale_dead.exists()
        assert fresh_dead.exists()
        assert live_old.exists()
        assert malformed.exists()
        assert sibling.exists()
        temp_sweep_results.append({"count": sweep["removed_temp_count"], "preserved": [fresh_dead.exists(), live_old.exists(), malformed.exists(), sibling.exists()]})
    assert temp_sweep_results[0]["count"] == temp_sweep_results[1]["count"] == 1
    assert temp_sweep_results[0]["preserved"] == temp_sweep_results[1]["preserved"] == [True, True, True, True]

    # Managed lease expiry releases ownership and returns, but does not retain, live checkpoint context.
    expiry = base / "expiry.json"
    assert run("py", expiry, "claim", actor, "expiring", "--lease-seconds", "1", "--checkpoint", "resume-here")["ok"] is True
    time.sleep(1.2)
    swept = run("rs", expiry, "sweep")
    assert swept["expired"] and swept["expired"][0]["scope"] == "expiring"
    snap = run("py", expiry, "snapshot", "--scope", "expiring")
    assert snap["counts"] == {"active": 0, "claims": 0, "legacy_only_claims": 0}
    assert snap["focus"]["job"] is None
    assert swept["expired"][0]["checkpoint"] == "resume-here"

    print(json.dumps({"ok": True, "python_rust_redundancy": "preserved", "queue_semantics": "retired", "ownership_parity": True}))
finally:
    shutil.rmtree(base, ignore_errors=True)
