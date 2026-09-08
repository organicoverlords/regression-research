import ctypes
import json
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
GUARD = ROOT / "python" / "lease_guard.py"
PY_CORE = [sys.executable, str(ROOT / "python" / "busy.py")]
RS_CORE = ROOT / "rust" / "target" / "release" / "busy-coordinator.exe"


def core_command(kind: str) -> list[str]:
    return PY_CORE if kind == "python" else [str(RS_CORE)]


def run_core(kind: str, store: pathlib.Path, *args: str) -> dict:
    cp = subprocess.run(
        [*core_command(kind), "--store", str(store), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if cp.returncode != 0:
        raise AssertionError(cp.stderr or cp.stdout)
    return json.loads(cp.stdout)


def guard_command(
    kind: str,
    store: pathlib.Path,
    actor: str,
    scope: str,
    command: list[str],
    *,
    lease: int = 2,
    heartbeat: float = 0.4,
) -> list[str]:
    return [
        sys.executable,
        str(GUARD),
        "--impl",
        kind,
        "--store",
        str(store),
        "--lease-seconds",
        str(lease),
        "--heartbeat-seconds",
        str(heartbeat),
        actor,
        scope,
        "--",
        *command,
    ]


def wait_claim(store: pathlib.Path, scope: str, timeout: float = 20.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            state = json.loads(store.read_text(encoding="utf-8"))
        except (FileNotFoundError, PermissionError, json.JSONDecodeError):
            time.sleep(0.05)
            continue
        for claim in state.get("claims", []):
            if claim.get("scope") == scope:
                return claim
        time.sleep(0.05)
    raise AssertionError(f"claim did not appear: {scope}")


def wait_file(path: pathlib.Path, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.05)
    raise AssertionError(f"file did not appear: {path}")


def recover_current(kind: str, store: pathlib.Path, scope: str, timeout: float = 8.0) -> dict:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        claim = run_core(kind, store, "inspect", scope).get("claim")
        if not claim:
            return {"ok": False, "reason": "scope_not_claimed"}
        last = run_core(
            kind,
            store,
            "recover",
            claim["actor"],
            scope,
            "--expected-claim-timestamp",
            claim["timestamp"],
        )
        if last.get("ok"):
            return last
        time.sleep(0.02)
    return last or {"ok": False, "reason": "recover_timeout"}


def process_live(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    kernel32.GetExitCodeProcess.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        code = ctypes.c_uint32()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def wait_dead(pid: int, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not process_live(pid):
            return
        time.sleep(0.05)
    raise AssertionError(f"process remained alive after guard ended: {pid}")


def sleeping_child(seconds: float) -> list[str]:
    return [sys.executable, "-c", f"import time; time.sleep({seconds})"]


def pid_child(pid_file: pathlib.Path, seconds: float = 30.0) -> list[str]:
    return [
        sys.executable,
        "-c",
        "import os,pathlib,sys,time; pathlib.Path(sys.argv[1]).write_text(str(os.getpid()),encoding='utf-8'); time.sleep(float(sys.argv[2]))",
        str(pid_file),
        str(seconds),
    ]


subprocess.run(
    ["cargo", "build", "--release", "--manifest-path", str(ROOT / "rust" / "Cargo.toml")],
    check=True,
)
base = pathlib.Path(tempfile.mkdtemp(prefix="busy-lease-guard-"))
try:
    # A live foreign claim blocks the child before it can execute, for both cores.
    for kind in ("python", "rust"):
        store = base / f"collision-{kind}.json"
        marker = base / f"collision-{kind}.marker"
        scope = f"guard:collision:{kind}"
        owner = f"ChatGPT-guard-existing-{kind}"
        assert run_core(kind, store, "claim", owner, scope, "--lease-seconds", "60")["ok"] is True
        cp = subprocess.run(
            guard_command(
                kind,
                store,
                f"ChatGPT-guard-contender-{kind}",
                scope,
                [sys.executable, "-c", "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('ran')", str(marker)],
            ),
            capture_output=True,
            text=True,
        )
        assert cp.returncode == 75, (kind, cp.stdout, cp.stderr)
        assert not marker.exists()
        assert run_core(kind, store, "release", owner, scope)["ok"] is True

    # Heartbeats keep a deliberately tiny lease valid beyond its original TTL,
    # and normal child exit releases immediately instead of waiting for expiry.
    for kind in ("python", "rust"):
        store = base / f"heartbeat-{kind}.json"
        scope = f"guard:heartbeat:{kind}"
        proc = subprocess.Popen(
            guard_command(
                kind,
                store,
                f"ChatGPT-guard-heartbeat-{kind}",
                scope,
                sleeping_child(3.0),
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        wait_claim(store, scope)
        time.sleep(2.2)
        snap = run_core(kind, store, "snapshot", "--scope", scope)
        assert snap["counts"]["active"] == 1, (kind, snap)
        stdout, stderr = proc.communicate(timeout=10)
        assert proc.returncode == 0, (kind, stdout, stderr)
        snap = run_core(kind, store, "snapshot", "--scope", scope)
        assert snap["counts"]["active"] == 0, (kind, snap)

    # If ownership is externally replaced, the next heartbeat fails closed and
    # the guarded child is killed rather than continuing mutation unowned.
    replace_store = base / "replaced.json"
    replace_scope = "guard:ownership-replaced"
    replace_pid_file = base / "replaced-child.pid"
    replace_guard = subprocess.Popen(
        guard_command(
            "python",
            replace_store,
            "ChatGPT-guard-replaced",
            replace_scope,
            pid_child(replace_pid_file),
            lease=5,
            heartbeat=0.5,
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    wait_claim(replace_store, replace_scope)
    wait_file(replace_pid_file)
    child_pid = int(replace_pid_file.read_text(encoding="utf-8"))
    recovered = recover_current("python", replace_store, replace_scope)
    assert recovered["ok"] is True
    intruder = "ChatGPT-guard-replacement-owner"
    assert run_core("python", replace_store, "claim", intruder, replace_scope, "--lease-seconds", "60")["ok"] is True
    stdout, stderr = replace_guard.communicate(timeout=8)
    assert replace_guard.returncode == 76, (stdout, stderr)
    wait_dead(child_pid)
    current = run_core("python", replace_store, "inspect", replace_scope)["claim"]
    assert current["actor"] == intruder
    assert run_core("python", replace_store, "release", intruder, replace_scope)["ok"] is True

    # Hard-killing the guard closes the Windows Job / Linux parent-death coupling,
    # so the child dies. With heartbeats stopped, only the short lease remains and
    # ordinary sweep clears it while preserving an unrelated claim.
    crash_store = base / "guard-crash.json"
    crash_scope = "guard:crash"
    other_scope = "guard:unrelated"
    other_actor = "ChatGPT-guard-unrelated"
    assert run_core("python", crash_store, "claim", other_actor, other_scope, "--lease-seconds", "60")["ok"] is True
    crash_pid_file = base / "crash-child.pid"
    crash_guard = subprocess.Popen(
        guard_command(
            "python",
            crash_store,
            "ChatGPT-guard-crash",
            crash_scope,
            pid_child(crash_pid_file),
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    wait_claim(crash_store, crash_scope)
    wait_file(crash_pid_file)
    crash_child_pid = int(crash_pid_file.read_text(encoding="utf-8"))
    crash_guard.kill()
    crash_guard.wait(timeout=5)
    wait_dead(crash_child_pid)
    time.sleep(2.3)
    swept = run_core("python", crash_store, "sweep")
    assert any(item["scope"] == crash_scope for item in swept["expired"]), swept
    snap = run_core("python", crash_store, "snapshot")
    assert snap["counts"]["active"] == 1, snap
    assert run_core("python", crash_store, "inspect", other_scope)["claim"]["actor"] == other_actor
    assert run_core("python", crash_store, "release", other_actor, other_scope)["ok"] is True

    print(
        json.dumps(
            {
                "ok": True,
                "guard_collision_blocks_child": True,
                "guard_heartbeats_short_lease": True,
                "ownership_loss_kills_child": True,
                "guard_crash_kills_child_and_expires_claim": True,
                "unrelated_claim_preserved": True,
            }
        )
    )
finally:
    import shutil

    shutil.rmtree(base, ignore_errors=True)

