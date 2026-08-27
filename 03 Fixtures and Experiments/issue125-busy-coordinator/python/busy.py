import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

LOCK_TIMEOUT_S = 2.0
LOCK_STALE_S = 15.0
LOCK_RETRY_S = 0.01


def default_store() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "ChatGPTMcpClean" / ".state" / "busy-claims.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class StoreLock:
    def __init__(self, store: Path):
        self.path = Path(str(store) + ".lock")
        self.fd = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + LOCK_TIMEOUT_S
        while True:
            try:
                self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, f"{os.getpid()}\n".encode())
                return self
            except (FileExistsError, PermissionError):
                try:
                    if time.time() - self.path.stat().st_mtime > LOCK_STALE_S:
                        self.path.unlink(missing_ok=True)
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError("busy store locked by another writer")
                time.sleep(LOCK_RETRY_S)

    def __exit__(self, *_):
        if self.fd is not None:
            os.close(self.fd)
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def load(store: Path):
    try:
        data = json.loads(store.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"claims": []}
    except Exception:
        raise RuntimeError(f"cannot safely read BUSY store: {store}")
    claims = data.get("claims")
    if not isinstance(claims, list):
        raise RuntimeError("invalid BUSY store shape")
    out = []
    for c in claims:
        if isinstance(c, dict) and all(isinstance(c.get(k), str) for k in ("actor", "scope", "timestamp")):
            out.append({"actor": c["actor"], "scope": c["scope"], "timestamp": c["timestamp"]})
    data["claims"] = out
    return data


def persist(store: Path, state):
    store.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(store) + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, store)


def list_claims(store: Path):
    with StoreLock(store):
        return sorted(load(store)["claims"], key=lambda c: c["scope"])


def claim(store: Path, actor: str, scope: str):
    with StoreLock(store):
        state = load(store)
        claims = state["claims"]
        current = next((c for c in claims if c["scope"] == scope), None)
        if current and current["actor"] != actor:
            return {"ok": False, "reason": "scope_already_claimed", "claim": current}
        new = {"actor": actor, "scope": scope, "timestamp": now_iso()}
        claims = [c for c in claims if c["scope"] != scope] + [new]
        state["claims"] = claims
        persist(store, state)
        return {"ok": True, "claim": new}


def release(store: Path, actor: str, scope: str):
    with StoreLock(store):
        state = load(store)
        claims = state["claims"]
        current = next((c for c in claims if c["scope"] == scope), None)
        if current is None:
            return {"ok": False, "reason": "scope_not_claimed"}
        if current["actor"] != actor:
            return {"ok": False, "reason": "claim_belongs_to_another_actor", "claim": current}
        state["claims"] = [c for c in claims if c["scope"] != scope]
        persist(store, state)
        return {"ok": True, "released": current}


def main():
    parser = argparse.ArgumentParser(prog="busy")
    parser.add_argument("--store", type=Path, default=default_store())
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    for name in ("claim", "release"):
        p = sub.add_parser(name)
        p.add_argument("actor")
        p.add_argument("scope")
    a = parser.parse_args()
    if a.cmd == "list":
        result = {"claims": list_claims(a.store)}
    elif a.cmd == "claim":
        result = claim(a.store, a.actor, a.scope)
    else:
        result = release(a.store, a.actor, a.scope)
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    try:
        main()
    except TimeoutError as e:
        print(json.dumps({"ok": False, "reason": "store_locked", "error": str(e)}), file=sys.stderr)
        raise SystemExit(75)
