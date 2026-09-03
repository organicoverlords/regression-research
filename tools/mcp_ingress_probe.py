from __future__ import annotations

import argparse
import http.client
import json
import ssl
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class ProbeStep:
    method: str
    path: str
    body: str | None = None
    headers: dict[str, str] | None = None


def _read_new_jsonl(path: Path, offset: int) -> tuple[list[dict[str, object]], int]:
    if not path.exists():
        return [], offset
    events: list[dict[str, object]] = []
    with path.open("rb") as handle:
        handle.seek(offset)
        data = handle.read()
        end = handle.tell()
    for raw in data.splitlines():
        try:
            row = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(row, dict):
            events.append(row)
    return events, end


def classify_observation(*, status: int | None, error: str | None, backend_events: list[dict[str, object]], request_id: str | None) -> str:
    starts = [event for event in backend_events if event.get("event") == "request_start"]
    if request_id:
        matching = [event for event in starts if event.get("request_id") == request_id]
        if matching:
            return "BACKEND_ARRIVED"
    if error and starts:
        return "FAILURE_WITH_UNCORRELATED_BACKEND_ACTIVITY"
    if error:
        return "PRE_BACKEND_OR_EDGE_DROP"
    if status is not None and starts:
        return "BACKEND_ARRIVED"
    if status is not None:
        return "EDGE_RESPONDED_BACKEND_UNOBSERVED"
    return "INDETERMINATE"


def default_steps() -> list[ProbeStep]:
    initialize = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    return [
        ProbeStep("GET", "health"),
        ProbeStep("POST", "mcp", initialize, {"content-type": "application/json"}),
        ProbeStep("GET", "health"),
    ]


def load_plan(path: Path | None) -> list[ProbeStep]:
    if path is None:
        return default_steps()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("plan must be a non-empty JSON array")
    steps: list[ProbeStep] = []
    for item in payload:
        if not isinstance(item, dict) or not isinstance(item.get("method"), str) or not isinstance(item.get("path"), str):
            raise ValueError("each plan step needs string method and path")
        body = item.get("body")
        if body is not None and not isinstance(body, str):
            body = json.dumps(body, separators=(",", ":"))
        headers = item.get("headers") or {}
        if not isinstance(headers, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in headers.items()):
            raise ValueError("step headers must be a string map")
        steps.append(ProbeStep(item["method"].upper(), item["path"], body, headers))
    return steps


def _target_path(base_path: str, step_path: str) -> str:
    if step_path.startswith("/"):
        return step_path
    prefix = base_path.rstrip("/")
    return f"{prefix}/{step_path}" if prefix else f"/{step_path}"


def run_probe(base_url: str, steps: list[ProbeStep], *, backend_log: Path | None = None, timeout: float = 10.0, fresh_connection: bool = False, settle_ms: int = 80, repeat: int = 1) -> dict[str, object]:
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("base URL must be http(s) with a hostname")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    context = ssl.create_default_context() if parsed.scheme == "https" else None
    connection = None
    log_offset = backend_log.stat().st_size if backend_log and backend_log.exists() else 0
    observations: list[dict[str, object]] = []

    def new_connection():
        if parsed.scheme == "https":
            return http.client.HTTPSConnection(parsed.hostname, port, timeout=timeout, context=context)
        return http.client.HTTPConnection(parsed.hostname, port, timeout=timeout)

    try:
        expanded_steps = steps * repeat
        for index, step in enumerate(expanded_steps, 1):
            if connection is None or fresh_connection:
                if connection is not None:
                    connection.close()
                connection = new_connection()
            target = _target_path(parsed.path, step.path)
            started = time.monotonic()
            status: int | None = None
            error: str | None = None
            response_headers: dict[str, str] = {}
            try:
                connection.request(step.method, target, body=step.body, headers=step.headers or {})
                response = connection.getresponse()
                status = response.status
                response_headers = {key.lower(): value for key, value in response.getheaders()}
                response.read()
            except Exception as exc:  # transport failure is the evidence under test
                error = f"{type(exc).__name__}: {exc}"
                connection.close()
                connection = None
            if settle_ms:
                time.sleep(settle_ms / 1000.0)
            backend_events: list[dict[str, object]] = []
            if backend_log:
                backend_events, log_offset = _read_new_jsonl(backend_log, log_offset)
            request_id = response_headers.get("x-shell-mcp-request-id")
            classification = classify_observation(status=status, error=error, backend_events=backend_events, request_id=request_id)
            observations.append({
                "index": index,
                "method": step.method,
                "path": target,
                "status": status,
                "error": error,
                "request_id": request_id,
                "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                "backend_request_starts": sum(1 for event in backend_events if event.get("event") == "request_start"),
                "classification": classification,
            })
    finally:
        if connection is not None:
            connection.close()

    counts: dict[str, int] = {}
    for observation in observations:
        key = str(observation["classification"])
        counts[key] = counts.get(key, 0) + 1
    return {"base_url": base_url, "connection_mode": "fresh" if fresh_connection else "reused", "observations": observations, "classification_counts": counts}


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe MCP public ingress and correlate client failures with backend transport arrival.")
    parser.add_argument("--base-url", required=True, help="Public connector origin, including a path prefix such as /clone-a")
    parser.add_argument("--plan", type=Path, help="Optional JSON request plan; default is health, protected-resource metadata, initialize")
    parser.add_argument("--backend-log", type=Path, help="Optional owned backend transport.jsonl for arrival correlation")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--fresh-connection", action="store_true", help="Disable HTTP connection reuse for differential comparison")
    parser.add_argument("--settle-ms", type=int, default=80)
    parser.add_argument("--repeat", type=int, default=1, help="Repeat the request plan on the same connection to expose intermittent drops")
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be >= 1")
    report = run_probe(args.base_url, load_plan(args.plan), backend_log=args.backend_log, timeout=args.timeout, fresh_connection=args.fresh_connection, settle_ms=args.settle_ms, repeat=args.repeat)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report["classification_counts"].get("PRE_BACKEND_OR_EDGE_DROP", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())





