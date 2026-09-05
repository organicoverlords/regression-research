#!/usr/bin/env python3
import contextlib
import importlib.util
import io
import json
import pathlib
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "python" / "audit_wrapper.py"
spec = importlib.util.spec_from_file_location("busy_audit_wrapper_best_effort", WRAPPER)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load audit wrapper")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def call_log(store: pathlib.Path) -> tuple[int, dict, float]:
    out = io.StringIO()
    started = time.monotonic()
    with contextlib.redirect_stdout(out):
        rc = module.handle_log(store, ["ChatGPT:test", "scope", "--action", "finding", "--detail", "proof"], {})
    elapsed = time.monotonic() - started
    payload = json.loads(out.getvalue().strip())
    return rc, payload, elapsed


with tempfile.TemporaryDirectory(prefix="busy-log-best-effort-") as temporary:
    store = pathlib.Path(temporary) / "busy-claims.json"
    audit = module.default_audit_log(store)
    lock = pathlib.Path(str(audit) + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("other-writer\n", encoding="utf-8")

    rc, payload, elapsed = call_log(store)
    assert rc == 0, (rc, payload)
    assert payload["ok"] is True, payload
    assert payload["logged"] is False, payload
    assert payload["non_authoritative"] is True, payload
    assert "audit log locked" in payload["warning"], payload
    assert elapsed < 1.0, elapsed

    lock.unlink()
    rc, payload, elapsed = call_log(store)
    assert rc == 0, (rc, payload)
    assert payload["ok"] is True, payload
    assert isinstance(payload["logged"], dict), payload
    assert audit.exists(), audit
    assert elapsed < 1.0, elapsed

print(json.dumps({"ok": True, "locked_log_exit_zero": True, "lock_budget_seconds": 0.25}))
