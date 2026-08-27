import concurrent.futures
import json
import os
import pathlib
import subprocess
import sys
import tempfile

root = pathlib.Path(__file__).resolve().parents[1]
py = root / "python" / "busy.py"
rs = root / "rust" / "target" / "release" / "busy-coordinator.exe"
rounds = 20
contenders = 10
failures = []

if not rs.exists():
    raise SystemExit(f"build Rust first: cargo build --release --manifest-path {root / 'rust' / 'Cargo.toml'}")

for round_index in range(rounds):
    store = pathlib.Path(tempfile.gettempdir()) / f"busy-mixed-{os.getpid()}-{round_index}.json"
    for path in (store, pathlib.Path(str(store) + ".lock")):
        path.unlink(missing_ok=True)

    def run(index):
        actor = f"actor-{round_index}-{index}"
        if index % 2 == 0:
            command = [sys.executable, str(py), "--store", str(store), "claim", actor, "same-scope"]
            environment = None
        else:
            command = [str(rs), "claim", actor, "same-scope"]
            environment = os.environ.copy()
            environment["BUSY_STORE_PATH"] = str(store)
        result = subprocess.run(command, capture_output=True, text=True, env=environment)
        if result.returncode != 0:
            return {"error": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
        return json.loads(result.stdout)

    with concurrent.futures.ThreadPoolExecutor(max_workers=contenders) as executor:
        results = list(executor.map(run, range(contenders)))

    wins = sum(result.get("ok") is True for result in results)
    losses = sum(result.get("ok") is False and result.get("reason") == "scope_already_claimed" for result in results)
    claims = json.loads(store.read_text(encoding="utf-8")).get("claims", [])
    if wins != 1 or losses != contenders - 1 or len(claims) != 1:
        failures.append({"round": round_index, "wins": wins, "losses": losses, "claims": claims, "results": results})

    store.unlink(missing_ok=True)
    pathlib.Path(str(store) + ".lock").unlink(missing_ok=True)

summary = {
    "rounds": rounds,
    "contenders_per_round": contenders,
    "total_attempts": rounds * contenders,
    "failures": len(failures),
    "result": "PASS" if not failures else "FAIL",
}
print(json.dumps(summary))
raise SystemExit(0 if not failures else 1)
