import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOCK_TIMEOUT_S = 2.0
LOCK_STALE_S = 15.0
LOCK_RETRY_S = 0.01
DEFAULT_LEASE_S = 3600
MAX_OPERATIONS = 512
MAX_HANDOFF_SOURCE_CHARS = 2048
MAX_HANDOFF_SUMMARY_CHARS = 8192


def default_store() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "ChatGPTMcpClean" / ".state" / "busy-claims.json"


def now_dt() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None = None) -> str:
    return (dt or now_dt()).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def canonical_scope(scope: str) -> str:
    value = scope.strip()
    if not value:
        raise ValueError("scope must not be empty")
    return value


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


def empty_state() -> dict:
    return {"claims": [], "coordinator": {"version": 1, "jobs": {}, "operations": {}}}


def load_state(store: Path) -> dict:
    try:
        data = json.loads(store.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return empty_state()
    except Exception as exc:
        raise RuntimeError(f"cannot safely read BUSY store: {store}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("claims"), list):
        raise RuntimeError("invalid BUSY store shape")
    claims = []
    for claim in data["claims"]:
        if isinstance(claim, dict) and all(isinstance(claim.get(k), str) for k in ("actor", "scope", "timestamp")):
            claims.append({"actor": claim["actor"], "scope": claim["scope"], "timestamp": claim["timestamp"]})
    data["claims"] = claims
    coord = data.get("coordinator")
    if not isinstance(coord, dict):
        coord = {}
    if not isinstance(coord.get("jobs"), dict):
        coord["jobs"] = {}
    if not isinstance(coord.get("operations"), dict):
        coord["operations"] = {}
    coord["version"] = 1
    data["coordinator"] = coord
    return data


def persist(store: Path, state: dict) -> None:
    store.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(store) + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    os.replace(tmp, store)


def claim_for(state: dict, scope: str):
    return next((c for c in state["claims"] if c["scope"] == scope), None)


def job_for(state: dict, scope: str):
    job = state["coordinator"]["jobs"].get(scope)
    return job if isinstance(job, dict) else None


def prune_operations(state: dict) -> None:
    ops = state["coordinator"]["operations"]
    if len(ops) <= MAX_OPERATIONS:
        return
    ordered = sorted(ops.items(), key=lambda item: str(item[1].get("at", "")))
    for key, _ in ordered[: len(ops) - MAX_OPERATIONS]:
        ops.pop(key, None)


def idempotent(state: dict, operation_id: str | None, signature: dict):
    if not operation_id:
        return None
    current = state["coordinator"]["operations"].get(operation_id)
    if current is None:
        return None
    if current.get("signature") != signature:
        return {"ok": False, "reason": "idempotency_conflict", "operation_id": operation_id}
    result = current.get("result")
    return result if isinstance(result, dict) else {"ok": False, "reason": "invalid_idempotency_record"}


def remember(state: dict, operation_id: str | None, signature: dict, result: dict) -> dict:
    if operation_id:
        state["coordinator"]["operations"][operation_id] = {
            "at": iso(),
            "signature": signature,
            "result": result,
        }
        prune_operations(state)
    return result


def sweep_expired(state: dict) -> tuple[list[dict], bool]:
    now = now_dt()
    expired = []
    changed = False
    jobs = state["coordinator"]["jobs"]
    for scope, job in list(jobs.items()):
        if not isinstance(job, dict) or job.get("state") != "active":
            continue
        lease = job.get("lease_expires_at")
        owner = job.get("owner")
        if not isinstance(lease, str) or not isinstance(owner, str):
            continue
        try:
            is_expired = parse_iso(lease) <= now
        except Exception:
            continue
        if not is_expired:
            continue
        current = claim_for(state, scope)
        if current and current.get("actor") == owner:
            expected_timestamp = job.get("claim_timestamp")
            if isinstance(expected_timestamp, str) and current.get("timestamp") != expected_timestamp:
                # A legacy/current MCP writer renewed this claim after the coordinator
                # recorded its lease. Treat the live claim as newer authority and stop
                # automatic expiry rather than deleting work we no longer own safely.
                job["claim_timestamp"] = current.get("timestamp")
                job["lease_expires_at"] = None
                job["updated_at"] = current.get("timestamp")
                changed = True
                continue
            state["claims"] = [c for c in state["claims"] if c["scope"] != scope]
        job["state"] = "ready"
        job["owner"] = None
        job["lease_expires_at"] = None
        job["updated_at"] = iso(now)
        expired.append({"scope": scope, "previous_owner": owner, "checkpoint": job.get("checkpoint")})
        changed = True
    return expired, changed


def operate(store: Path, command: str, actor: str | None = None, raw_scope: str | None = None,
            *, lease_seconds: int = DEFAULT_LEASE_S, checkpoint: str | None = None,
            operation_id: str | None = None, finding_id: str | None = None,
            source: str | None = None, summary: str | None = None) -> dict:
    with StoreLock(store):
        state = load_state(store)
        swept, sweep_changed = sweep_expired(state)
        if command in {"list", "sweep"}:
            if sweep_changed:
                persist(store, state)
            if command == "list":
                return {"claims": sorted(state["claims"], key=lambda c: c["scope"])}
            return {"ok": True, "expired": swept}

        if command == "next":
            if actor is None:
                raise ValueError("actor required")
            signature = {"command": command, "actor": actor, "lease_seconds": lease_seconds}
            replay = idempotent(state, operation_id, signature)
            if replay is not None:
                if sweep_changed:
                    persist(store, state)
                return replay
            result = {"ok": False, "reason": "no_actionable_job", "expired": swept}
            for scope in sorted(state["coordinator"]["jobs"]):
                job = job_for(state, scope)
                if not job or job.get("state") != "ready" or claim_for(state, scope):
                    continue
                timestamp = iso()
                claim = {"actor": actor, "scope": scope, "timestamp": timestamp}
                state["claims"].append(claim)
                job.update({
                    "state": "active",
                    "owner": actor,
                    "lease_expires_at": iso(now_dt() + timedelta(seconds=lease_seconds)),
                    "claim_timestamp": timestamp,
                    "updated_at": timestamp,
                })
                result = {"ok": True, "claim": claim, "job": job, "expired": swept}
                break
            result = remember(state, operation_id, signature, result)
            persist(store, state)
            return result

        if command == "handoff":
            if actor is None:
                raise ValueError("actor required")
            if raw_scope is None:
                raise ValueError("scope required")
            parent_scope = canonical_scope(raw_scope)
            finding = canonical_scope(finding_id or "")
            source_value = (source or "").strip()
            summary_value = (summary or "").strip()
            if not source_value:
                raise ValueError("source must not be empty")
            if not summary_value:
                raise ValueError("summary must not be empty")
            if len(source_value) > MAX_HANDOFF_SOURCE_CHARS:
                raise ValueError(f"source exceeds {MAX_HANDOFF_SOURCE_CHARS} characters")
            if len(summary_value) > MAX_HANDOFF_SUMMARY_CHARS:
                raise ValueError(f"summary exceeds {MAX_HANDOFF_SUMMARY_CHARS} characters")
            scope = f"{parent_scope}::handoff:{finding}"
            signature = {
                "command": command,
                "actor": actor,
                "scope": parent_scope,
                "finding_id": finding,
                "source": source_value,
                "summary": summary_value,
            }
            replay = idempotent(state, operation_id, signature)
            if replay is not None:
                if sweep_changed:
                    persist(store, state)
                return replay
            existing = job_for(state, scope)
            if existing is not None:
                result = {"ok": False, "reason": "finding_id_conflict", "job": existing}
            else:
                timestamp = iso()
                handoff = {
                    "parent_scope": parent_scope,
                    "finding_id": finding,
                    "reported_by": actor,
                    "source": source_value,
                    "summary": summary_value,
                    "reported_at": timestamp,
                }
                job = {
                    "job_id": scope,
                    "scope": scope,
                    "state": "ready",
                    "owner": None,
                    "lease_expires_at": None,
                    "claim_timestamp": None,
                    "checkpoint": summary_value,
                    "updated_at": timestamp,
                    "handoff": handoff,
                }
                state["coordinator"]["jobs"][scope] = job
                result = {"ok": True, "job": job, "handoff": handoff}
            result = remember(state, operation_id, signature, result)
            persist(store, state)
            return result

        if raw_scope is None:
            raise ValueError("scope required")
        scope = canonical_scope(raw_scope)
        signature = {"command": command, "scope": scope}
        if actor is not None:
            signature["actor"] = actor
        if checkpoint is not None:
            signature["checkpoint"] = checkpoint
        if command in {"claim", "heartbeat"}:
            signature["lease_seconds"] = lease_seconds
        replay = idempotent(state, operation_id, signature)
        if replay is not None:
            if sweep_changed:
                persist(store, state)
            return replay

        if command in {"enqueue", "ready"}:
            job = job_for(state, scope)
            if job is None:
                job = {"job_id": scope, "scope": scope}
                state["coordinator"]["jobs"][scope] = job
            if job.get("state") == "completed":
                result = {"ok": False, "reason": "job_completed", "job": job}
            elif job.get("state") == "active":
                result = {"ok": False, "reason": "job_active", "job": job}
            else:
                job.update({"state": "ready", "owner": None, "lease_expires_at": None, "updated_at": iso()})
                if checkpoint is not None:
                    job["checkpoint"] = checkpoint
                result = {"ok": True, "job": job}
            result = remember(state, operation_id, signature, result)
            persist(store, state)
            return result

        if actor is None:
            raise ValueError("actor required")

        current = claim_for(state, scope)
        job = job_for(state, scope)
        result: dict

        if command == "claim":
            if current and current["actor"] != actor:
                result = {"ok": False, "reason": "scope_already_claimed", "claim": current}
            else:
                timestamp = iso()
                claim = {"actor": actor, "scope": scope, "timestamp": timestamp}
                state["claims"] = [c for c in state["claims"] if c["scope"] != scope] + [claim]
                deadline = now_dt() + timedelta(seconds=lease_seconds)
                state["coordinator"]["jobs"][scope] = {
                    "job_id": scope,
                    "scope": scope,
                    "state": "active",
                    "owner": actor,
                    "lease_expires_at": iso(deadline),
                    "claim_timestamp": timestamp,
                    "checkpoint": checkpoint if checkpoint is not None else (job or {}).get("checkpoint"),
                    "updated_at": timestamp,
                }
                result = {"ok": True, "claim": claim}
        elif command == "heartbeat":
            if not current:
                result = {"ok": False, "reason": "scope_not_claimed"}
            elif current["actor"] != actor:
                result = {"ok": False, "reason": "claim_belongs_to_another_actor", "claim": current}
            else:
                timestamp = iso()
                current["timestamp"] = timestamp
                deadline = now_dt() + timedelta(seconds=lease_seconds)
                if job is None:
                    job = {"job_id": scope, "scope": scope, "checkpoint": checkpoint}
                    state["coordinator"]["jobs"][scope] = job
                job.update({"state": "active", "owner": actor, "lease_expires_at": iso(deadline), "claim_timestamp": timestamp, "updated_at": timestamp})
                if checkpoint is not None:
                    job["checkpoint"] = checkpoint
                result = {"ok": True, "claim": current}
        elif command in {"release", "block", "complete"}:
            if not current:
                result = {"ok": False, "reason": "scope_not_claimed"}
            elif current["actor"] != actor:
                result = {"ok": False, "reason": "claim_belongs_to_another_actor", "claim": current}
            else:
                state["claims"] = [c for c in state["claims"] if c["scope"] != scope]
                timestamp = iso()
                if command != "release" or job is not None:
                    if job is None:
                        job = {"job_id": scope, "scope": scope}
                        state["coordinator"]["jobs"][scope] = job
                    job.update({
                        "state": {"release": "ready", "block": "blocked", "complete": "completed"}[command],
                        "owner": None,
                        "lease_expires_at": None,
                        "updated_at": timestamp,
                    })
                    if checkpoint is not None:
                        job["checkpoint"] = checkpoint
                key = "released" if command == "release" else command
                result = {"ok": True, key: current}
        elif command == "inspect":
            result = {"ok": True, "job": job, "claim": current}
        else:
            raise ValueError(f"unknown command: {command}")

        result = remember(state, operation_id, signature, result)
        persist(store, state)
        return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="busy")
    parser.add_argument("--store", type=Path, default=default_store())
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sub.add_parser("sweep")
    nxt = sub.add_parser("next")
    nxt.add_argument("actor")
    nxt.add_argument("--lease-seconds", type=int, default=DEFAULT_LEASE_S)
    nxt.add_argument("--operation-id")
    handoff = sub.add_parser("handoff")
    handoff.add_argument("actor")
    handoff.add_argument("scope")
    handoff.add_argument("--finding-id", required=True)
    handoff.add_argument("--source", required=True)
    handoff.add_argument("--summary", required=True)
    handoff.add_argument("--operation-id")
    for name in ("enqueue", "ready"):
        p = sub.add_parser(name)
        p.add_argument("scope")
        p.add_argument("--operation-id")
        p.add_argument("--checkpoint")
    for name in ("claim", "heartbeat", "release", "block", "complete", "inspect"):
        p = sub.add_parser(name)
        p.add_argument("actor")
        p.add_argument("scope")
        p.add_argument("--operation-id")
        if name in {"claim", "heartbeat"}:
            p.add_argument("--lease-seconds", type=int, default=DEFAULT_LEASE_S)
        if name in {"claim", "heartbeat", "block", "complete"}:
            p.add_argument("--checkpoint")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.cmd in {"list", "sweep"}:
            result = operate(args.store, args.cmd)
        elif args.cmd == "next":
            result = operate(args.store, args.cmd, args.actor, lease_seconds=args.lease_seconds, operation_id=args.operation_id)
        elif args.cmd == "handoff":
            result = operate(
                args.store,
                args.cmd,
                args.actor,
                args.scope,
                operation_id=args.operation_id,
                finding_id=args.finding_id,
                source=args.source,
                summary=args.summary,
            )
        elif args.cmd in {"enqueue", "ready"}:
            result = operate(args.store, args.cmd, raw_scope=args.scope, checkpoint=args.checkpoint, operation_id=args.operation_id)
        else:
            result = operate(
                args.store,
                args.cmd,
                args.actor,
                args.scope,
                lease_seconds=getattr(args, "lease_seconds", DEFAULT_LEASE_S),
                checkpoint=getattr(args, "checkpoint", None),
                operation_id=getattr(args, "operation_id", None),
            )
        print(json.dumps(result, separators=(",", ":")))
        return 0
    except TimeoutError as exc:
        print(json.dumps({"ok": False, "reason": "store_locked", "error": str(exc)}), file=sys.stderr)
        return 75
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
