import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[1]
PY = [sys.executable, str(ROOT / "python" / "busy.py")]
RS = [str(ROOT / "rust" / "target" / "release" / "busy-coordinator.exe")]
subprocess.run(["cargo", "build", "--release", "--manifest-path", str(ROOT / "rust" / "Cargo.toml")], check=True)
base = pathlib.Path(tempfile.mkdtemp(prefix="busy-mixed-contention-"))
store = base / "state.json"


def claim(cmd, actor):
    cp = subprocess.run([*cmd, "--store", str(store), "claim", actor, "same-scope", "--lease-seconds", "60"], capture_output=True, text=True)
    if cp.returncode != 0:
        return {"transport_error": cp.stderr or cp.stdout}
    return json.loads(cp.stdout)

try:
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda item: claim(*item), [(PY, "ChatGPT-python-race"), (RS, "ChatGPT-rust-race")]))
    winners = [value for value in results if value.get("ok") is True]
    losers = [value for value in results if value.get("reason") == "scope_already_claimed"]
    assert len(winners) == 1 and len(losers) == 1, results
    state = json.loads(store.read_text(encoding="utf-8"))
    assert len(state["claims"]) == 1
    assert state["coordinator"]["jobs"]["same-scope"]["state"] == "active"
    print(json.dumps({"ok": True, "winners": len(winners), "losers": len(losers)}))
finally:
    shutil.rmtree(base, ignore_errors=True)
