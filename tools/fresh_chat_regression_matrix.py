from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = ROOT / "03 Fixtures and Experiments" / "issue122-fresh-chat-regression-matrix.json"


def _text(message: dict[str, Any]) -> str:
    content = message.get("content") or {}
    parts = [part for part in (content.get("parts") or []) if isinstance(part, str)]
    if content.get("text"):
        parts.append(str(content["text"]))
    return " ".join(parts).strip()


def _model_family(slug: str | None) -> str:
    if not slug:
        return "unknown"
    if slug.startswith("gpt-5-6"):
        return "gpt-5-6"
    if slug.startswith("gpt-5-5"):
        return "gpt-5-5"
    return slug


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def select_snapshot(day_root: Path, conversation_id: str) -> tuple[Path, dict[str, Any]]:
    matches: list[tuple[tuple[int, float, str], Path, dict[str, Any]]] = []
    for path in day_root.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("conversation_id") != conversation_id:
            continue
        score = (len(payload.get("mapping") or {}), float(payload.get("update_time") or 0), path.name)
        matches.append((score, path, payload))
    if not matches:
        raise FileNotFoundError(f"conversation {conversation_id} not found under {day_root}")
    _, path, payload = max(matches, key=lambda row: row[0])
    return path, payload


def analyze_snapshot(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    events: list[tuple[float, dict[str, Any]]] = []
    for node in (payload.get("mapping") or {}).values():
        message = node.get("message") or {}
        created = message.get("create_time")
        if isinstance(created, (int, float)):
            events.append((float(created), message))
    events.sort(key=lambda row: row[0])
    users = [(t, m) for t, m in events if (m.get("author") or {}).get("role") == "user" and _text(m)]
    if not users:
        raise ValueError(f"no visible user message in {path}")
    start, first_user = users[0]
    next_user_time = users[1][0] if len(users) > 1 else None
    window = [(t, m) for t, m in events if t >= start and (next_user_time is None or t < next_user_time)]
    tools = [
        (t, m) for t, m in window
        if (m.get("author") or {}).get("role") == "assistant" and m.get("recipient") not in (None, "all")
    ]
    visible = [
        (t, m) for t, m in window
        if (m.get("author") or {}).get("role") == "assistant"
        and m.get("recipient") in (None, "all") and _text(m)
    ]
    slugs: list[str] = []
    efforts: list[str] = []
    recipients: list[str] = []
    for _, message in window:
        metadata = message.get("metadata") or {}
        for key in ("resolved_model_slug", "model_slug"):
            value = metadata.get(key)
            if value and value not in slugs:
                slugs.append(value)
        effort = metadata.get("thinking_effort")
        if effort and effort not in efforts:
            efforts.append(effort)
        recipient = message.get("recipient")
        if recipient and recipient not in recipients:
            recipients.append(recipient)
    final_text = _text(visible[-1][1]) if visible else ""
    next_user = _text(users[1][1]) if len(users) > 1 else ""
    default_model = payload.get("default_model_slug") or "unknown"
    return {
        "conversation_id": payload.get("conversation_id"),
        "title": payload.get("title") or "",
        "prompt": _text(first_user),
        "default_model": default_model,
        "model_family": _model_family(default_model),
        "model_slugs": slugs,
        "thinking_efforts": efforts,
        "tool_calls": len(tools),
        "time_to_first_tool_s": round(tools[0][0] - start, 3) if tools else None,
        "turn_duration_s": round(visible[-1][0] - start, 3) if visible else None,
        "next_user_delay_min": round((next_user_time - start) / 60, 3) if next_user_time else None,
        "next_user": next_user,
        "final_text": final_text,
        "recipients": recipients,
        "snapshot": path.name,
        "snapshot_sha256": _sha256(path),
    }


def check_case(case: dict[str, Any], measured: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    def fail(name: str, got: Any, want: Any) -> None:
        failures.append(f"{name}: got={got!r} want={want!r}")

    if measured["prompt"] != case["expected_prompt"]:
        fail("prompt", measured["prompt"], case["expected_prompt"])
    if measured["default_model"] != case["expected_default_model"]:
        fail("default_model", measured["default_model"], case["expected_default_model"])
    family = case.get("required_model_family")
    if family and measured["model_family"] != family:
        fail("model_family", measured["model_family"], family)
    for slug in case.get("required_model_slugs", []):
        if slug not in measured["model_slugs"]:
            fail("required_model_slug", measured["model_slugs"], slug)
    effort = case.get("required_thinking_effort")
    if effort and effort not in measured["thinking_efforts"]:
        fail("thinking_effort", measured["thinking_efforts"], effort)
    calls = measured["tool_calls"]
    if "exact_tool_calls" in case and calls != case["exact_tool_calls"]:
        fail("tool_calls", calls, case["exact_tool_calls"])
    if "min_tool_calls" in case and calls < case["min_tool_calls"]:
        fail("min_tool_calls", calls, case["min_tool_calls"])
    if "max_tool_calls" in case and calls > case["max_tool_calls"]:
        fail("max_tool_calls", calls, case["max_tool_calls"])
    max_tft = case.get("max_time_to_first_tool_s")
    if max_tft is not None:
        got = measured["time_to_first_tool_s"]
        if got is None or got > max_tft:
            fail("time_to_first_tool_s", got, max_tft)
    min_duration = case.get("min_turn_duration_s")
    if min_duration is not None:
        got = measured["turn_duration_s"]
        if got is None or got < min_duration:
            fail("turn_duration_s", got, min_duration)
    if case.get("next_user_exact") is not None and measured["next_user"] != case["next_user_exact"]:
        fail("next_user", measured["next_user"], case["next_user_exact"])
    needle = case.get("next_user_contains")
    if needle and needle.lower() not in measured["next_user"].lower():
        fail("next_user_contains", measured["next_user"], needle)
    needle = case.get("final_contains")
    if needle and needle.lower() not in measured["final_text"].lower():
        fail("final_contains", measured["final_text"], needle)
    return failures


def run_matrix(raw_root: Path, spec_path: Path = DEFAULT_SPEC) -> dict[str, Any]:
    spec = json.loads(spec_path.read_text(encoding="utf-8-sig"))
    rows: list[dict[str, Any]] = []
    failed = 0
    for case in spec["cases"]:
        path, payload = select_snapshot(raw_root / case["day"], case["conversation_id"])
        measured = analyze_snapshot(path, payload)
        failures = check_case(case, measured)
        failed += bool(failures)
        final_text = measured.pop("final_text")
        rows.append({
            "case_id": case["id"],
            "phase": case["phase"],
            "behavior": case["behavior"],
            "purpose": case["purpose"],
            **measured,
            "final_text_excerpt": final_text[:240],
            "final_text_sha256": hashlib.sha256(final_text.encode("utf-8")).hexdigest(),
            "checks_passed": not failures,
            "failures": failures,
        })
    return {
        "schema_version": 1,
        "source_issue": spec["issue"],
        "raw_root": "<provided-external-raw-root>",
        "cases": rows,
        "summary": {"cases": len(rows), "passed": len(rows) - failed, "failed": failed},
    }


def write_csv(path: Path, result: dict[str, Any]) -> None:
    fields = [
        "case_id", "phase", "behavior", "conversation_id", "title", "prompt", "default_model",
        "model_family", "model_slugs", "thinking_efforts", "tool_calls", "time_to_first_tool_s",
        "turn_duration_s", "next_user_delay_min", "next_user", "snapshot", "snapshot_sha256", "checks_passed"
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in result["cases"]:
            out = {field: row.get(field, "") for field in fields}
            out["model_slugs"] = ";".join(row["model_slugs"])
            out["thinking_efforts"] = ";".join(row["thinking_efforts"])
            writer.writerow(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate issue #122 fresh-chat regression cases against raw ChatGPT exports.")
    parser.add_argument("--raw-root", type=Path, required=True, help="Root containing YYYY-MM-DD raw export directories")
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--csv-out", type=Path)
    args = parser.parse_args()
    try:
        result = run_matrix(args.raw_root, args.spec)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "REJECTED", "error": str(exc)}, ensure_ascii=False))
        return 2
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.csv_out:
        write_csv(args.csv_out, result)
    print(json.dumps(result["summary"], ensure_ascii=False))
    if result["summary"]["failed"]:
        for row in result["cases"]:
            if row["failures"]:
                print(row["case_id"] + ": " + "; ".join(row["failures"]))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
