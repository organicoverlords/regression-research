import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
PY = ROOT / "python" / "busy.py"
RS = ROOT / "rust" / "target" / "release" / "busy-coordinator.exe"


def run(kind, store, *args, expect=0):
    if kind == "py":
        cmd = [sys.executable, str(PY), "--store", str(store), *args]
        env = None
    else:
        cmd = [str(RS), "--store", str(store), *args]
        env = os.environ.copy()
    cp = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if cp.returncode != expect:
        raise AssertionError(f"{kind} rc={cp.returncode} expected={expect}\nstdout={cp.stdout}\nstderr={cp.stderr}")
    text = cp.stdout.strip() if expect == 0 else cp.stderr.strip()
    return json.loads(text) if text.startswith("{") else text


def new_store(name):
    path = pathlib.Path(tempfile.gettempdir()) / f"busy-parity-{os.getpid()}-{name}.json"
    path.unlink(missing_ok=True)
    pathlib.Path(str(path) + ".lock").unlink(missing_ok=True)
    return path


def read(store):
    return json.loads(store.read_text(encoding="utf-8"))


# Cross-language idempotency and lifecycle continuation.
store = new_store("lifecycle")
first = run("py", store, "claim", "worker-a", "repo#125:job-a", "--operation-id", "op-claim", "--lease-seconds", "60", "--checkpoint", "issue#125")
assert first["ok"] is True
assert run("rs", store, "claim", "worker-a", "repo#125:job-a", "--operation-id", "op-claim", "--lease-seconds", "60", "--checkpoint", "issue#125") == first
hb = run("rs", store, "heartbeat", "worker-a", "repo#125:job-a", "--operation-id", "op-heartbeat", "--lease-seconds", "60")
assert hb["ok"] is True
assert run("py", store, "heartbeat", "worker-a", "repo#125:job-a", "--operation-id", "op-heartbeat", "--lease-seconds", "60") == hb
blocked = run("py", store, "block", "worker-a", "repo#125:job-a", "--operation-id", "op-block", "--checkpoint", "commit:abc")
assert blocked["ok"] is True
assert run("rs", store, "block", "worker-a", "repo#125:job-a", "--operation-id", "op-block", "--checkpoint", "commit:abc") == blocked
state = read(store)
assert state["claims"] == []
assert state["coordinator"]["jobs"]["repo#125:job-a"]["state"] == "blocked"
assert state["coordinator"]["jobs"]["repo#125:job-a"]["checkpoint"] == "commit:abc"

# Ownership remains exact across implementations.
assert run("rs", store, "claim", "worker-b", "repo#125:job-a", "--operation-id", "op-reclaim")["ok"] is True
wrong = run("py", store, "release", "worker-a", "repo#125:job-a", "--operation-id", "op-wrong-release")
assert wrong["ok"] is False and wrong["reason"] == "claim_belongs_to_another_actor"
release = run("py", store, "release", "worker-b", "repo#125:job-a", "--operation-id", "op-release")
assert release["ok"] is True
assert run("rs", store, "release", "worker-b", "repo#125:job-a", "--operation-id", "op-release") == release

# Operation IDs cannot be reused for a different operation through another connector/runtime.
store2 = new_store("idempotency-conflict")
assert run("rs", store2, "claim", "worker-a", "scope-a", "--operation-id", "same-op")["ok"] is True
conflict = run("py", store2, "claim", "worker-a", "scope-b", "--operation-id", "same-op")
assert conflict["ok"] is False and conflict["reason"] == "idempotency_conflict"

# Lazy lease expiry is cross-language and releases only the claim represented by the lease metadata.
store3 = new_store("expiry")
assert run("py", store3, "claim", "lease-worker", "lease-scope", "--operation-id", "lease-op", "--lease-seconds", "1")["ok"] is True
time.sleep(1.2)
swept = run("rs", store3, "sweep")
assert swept["ok"] is True and len(swept["expired"]) == 1
assert read(store3)["claims"] == []
assert read(store3)["coordinator"]["jobs"]["lease-scope"]["state"] == "ready"
recovered = run("py", store3, "next", "recovery-worker", "--operation-id", "next-after-expiry", "--lease-seconds", "60")
assert recovered["ok"] is True and recovered["claim"]["scope"] == "lease-scope"

# A newer legacy/MCP refresh cancels coordinator auto-expiry instead of deleting newer ownership.
store4 = new_store("legacy-refresh")
assert run("rs", store4, "claim", "legacy-worker", "legacy-scope", "--operation-id", "legacy-op", "--lease-seconds", "1")["ok"] is True
state4 = read(store4)
state4["claims"][0]["timestamp"] = (datetime.now(timezone.utc) + timedelta(seconds=5)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
time.sleep(1.2)
store4.write_text(json.dumps(state4, indent=2) + "\n", encoding="utf-8")
swept4 = run("py", store4, "sweep")
assert swept4["expired"] == []
state4b = read(store4)
assert len(state4b["claims"]) == 1
assert state4b["coordinator"]["jobs"]["legacy-scope"]["lease_expires_at"] is None

# Unknown top-level data survives both implementations.
store5 = new_store("passthrough")
store5.write_text(json.dumps({"claims": [], "foreign": {"keep": 7}}, indent=2) + "\n", encoding="utf-8")
assert run("py", store5, "claim", "p", "pass-scope", "--operation-id", "p1")["ok"] is True
assert read(store5)["foreign"] == {"keep": 7}
assert run("rs", store5, "release", "p", "pass-scope", "--operation-id", "p2")["ok"] is True
assert read(store5)["foreign"] == {"keep": 7}


# Existing queue primitives are interchangeable and blocked jobs do not occupy a worker.
store6 = new_store("queue")
enqueued = run("py", store6, "enqueue", "queue-job", "--operation-id", "enqueue-1", "--checkpoint", "issue#125")
assert enqueued["ok"] is True and enqueued["job"]["state"] == "ready"
assert run("rs", store6, "enqueue", "queue-job", "--operation-id", "enqueue-1", "--checkpoint", "issue#125") == enqueued
next1 = run("rs", store6, "next", "worker-queue", "--operation-id", "next-1", "--lease-seconds", "60")
assert next1["ok"] is True and next1["claim"]["scope"] == "queue-job"
assert run("py", store6, "next", "worker-queue", "--operation-id", "next-1", "--lease-seconds", "60") == next1
blocked_q = run("py", store6, "block", "worker-queue", "queue-job", "--operation-id", "block-q", "--checkpoint", "waiting:ci")
assert blocked_q["ok"] is True
assert run("rs", store6, "next", "other-worker", "--operation-id", "next-none")["reason"] == "no_actionable_job"
ready_q = run("rs", store6, "ready", "queue-job", "--operation-id", "ready-q", "--checkpoint", "ci:green")
assert ready_q["ok"] is True
next2 = run("py", store6, "next", "other-worker", "--operation-id", "next-2")
assert next2["ok"] is True and next2["claim"]["scope"] == "queue-job"
completed_q = run("rs", store6, "complete", "other-worker", "queue-job", "--operation-id", "complete-q", "--checkpoint", "merge:done")
assert completed_q["ok"] is True
assert run("py", store6, "ready", "queue-job", "--operation-id", "ready-after-complete")["reason"] == "job_completed"

for path in [store, store2, store3, store4, store5, store6]:
    path.unlink(missing_ok=True)
    pathlib.Path(str(path) + ".lock").unlink(missing_ok=True)

# Scout fan-in: a finding becomes a separate ready job with durable provenance and
# survives the parent owner's completion.
store7 = new_store("handoff-fanin")
assert run("py", store7, "claim", "owner", "repo#125:parent", "--operation-id", "parent-claim", "--lease-seconds", "60")["ok"] is True
handoff = run(
    "rs", store7, "handoff", "scout", "repo#125:parent",
    "--finding-id", "finding-1",
    "--source", "github:issue#125:comment-42",
    "--summary", "actionable scout result",
    "--operation-id", "handoff-1",
)
assert handoff["ok"] is True and handoff["job"]["state"] == "ready"
follow_scope = handoff["job"]["scope"]
assert follow_scope == "repo#125:parent::handoff:finding-1"
assert handoff["handoff"]["reported_by"] == "scout"
assert handoff["handoff"]["source"] == "github:issue#125:comment-42"
assert run(
    "py", store7, "handoff", "scout", "repo#125:parent",
    "--finding-id", "finding-1",
    "--source", "github:issue#125:comment-42",
    "--summary", "actionable scout result",
    "--operation-id", "handoff-1",
) == handoff
assert run("py", store7, "complete", "owner", "repo#125:parent", "--operation-id", "parent-complete", "--checkpoint", "parent:done")["ok"] is True
claimed_finding = run("rs", store7, "next", "reconciler", "--operation-id", "next-finding", "--lease-seconds", "60")
assert claimed_finding["ok"] is True and claimed_finding["claim"]["scope"] == follow_scope
assert claimed_finding["job"]["handoff"]["source"] == "github:issue#125:comment-42"
assert claimed_finding["job"]["handoff"]["summary"] == "actionable scout result"

# Handoff provenance is bounded so one finding cannot grow the canonical coordinator store without limit.
store9 = new_store("handoff-bounds")
for kind, field, value, expected in [
    ("py", "--source", "s" * 2049, "source exceeds 2048 characters"),
    ("rs", "--summary", "x" * 8193, "summary exceeds 8192 characters"),
]:
    args = [
        "handoff", "scout", "repo#194:parent",
        "--finding-id", f"oversized-{kind}",
        "--source", "source:ok",
        "--summary", "summary ok",
    ]
    args[args.index(field) + 1] = value
    failure = run(kind, store9, *args, expect=1)
    assert failure == expected
assert not store9.exists(), "rejected handoffs must not create coordinator state"
pathlib.Path(str(store9) + ".lock").unlink(missing_ok=True)

# Blocking one exact sub-job releases only that ownership; sibling work remains claimable.
store8 = new_store("subjob-block-isolation")
assert run("py", store8, "claim", "import-worker", "repo#99:import", "--operation-id", "import-claim", "--lease-seconds", "60")["ok"] is True
assert run("rs", store8, "enqueue", "repo#99:analysis", "--operation-id", "analysis-enqueue", "--checkpoint", "independent")["ok"] is True
assert run("rs", store8, "block", "import-worker", "repo#99:import", "--operation-id", "import-block", "--checkpoint", "waiting:source-quiescence")["ok"] is True
next_sibling = run("py", store8, "next", "analysis-worker", "--operation-id", "analysis-next", "--lease-seconds", "60")
assert next_sibling["ok"] is True and next_sibling["claim"]["scope"] == "repo#99:analysis"
assert all(claim["scope"] != "repo#99:import" for claim in read(store8)["claims"])

# Queue selection is age-first, not lexicographic by scope.
for kind in ("py", "rs"):
    store9 = new_store(f"age-first-{kind}")
    assert run(kind, store9, "enqueue", "z-oldest", "--operation-id", f"{kind}-enqueue-old")["ok"] is True
    time.sleep(0.02)
    assert run(kind, store9, "enqueue", "a-newer", "--operation-id", f"{kind}-enqueue-new")["ok"] is True
    picked = run(kind, store9, "next", f"{kind}-age-worker", "--operation-id", f"{kind}-age-next")
    assert picked["ok"] is True and picked["claim"]["scope"] == "z-oldest"
    store9.unlink(missing_ok=True)
    pathlib.Path(str(store9) + ".lock").unlink(missing_ok=True)

print(json.dumps({
    "result": "PASS",
    "cross_language_idempotency": True,
    "cross_language_lifecycle": True,
    "exact_ownership": True,
    "lease_expiry": True,
    "legacy_refresh_guard": True,
    "passthrough_metadata": True,
    "queue_handoff": True,
    "scout_fanin": True,
    "subjob_block_isolation": True,
}))
