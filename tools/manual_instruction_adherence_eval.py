#!/usr/bin/env python3
"""Deterministic instruction-adherence scorer for provider-agnostic chat outputs.

The suite structure borrows benchmark design principles rather than benchmark prompts:
- IFEval: objectively verifiable constraints and strict all-instructions pass.
- FollowBench: hard (all constraints) and soft (per-constraint) satisfaction.
- IH-Challenge/System IFEval: higher-priority instruction vs lower-priority conflict.
- IFBench: held-out/OOD-style constraints and multi-turn constraint persistence.
- SystemCheck: system-prompt reliability as a separate eval surface (S-IFEval/RealGuardrails/TensorTrust).

No model judge is used. This tool scores supplied outputs only; model invocation stays
with the caller/harness so the same suite can test ChatGPT custom instructions, API
system/developer messages, or another chat harness without provider coupling.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

DEFAULT_SUITE = Path(__file__).resolve().parents[1] / "04 Operating Contracts" / "manual-instruction-adherence-suite.json"
SUITE_SCHEMA = "manual-instruction-adherence-suite.v1"
RESULT_SCHEMA = "manual-instruction-adherence-result.v1"
SUPPORTED_CHECKS = frozenset({
    "equals",
    "stripped_equals",
    "starts_with",
    "ends_with",
    "contains",
    "not_contains",
    "regex",
    "not_regex",
    "exact_count",
    "one_of",
    "json_object_keys",
    "json_field_equals",
    "min_words",
    "max_words",
})


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_suite(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    if not isinstance(payload, dict) or payload.get("schema") != SUITE_SCHEMA:
        raise ValueError(f"unsupported suite schema: {payload.get('schema') if isinstance(payload, dict) else type(payload).__name__}")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("suite requires a non-empty cases list")
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("every case must be an object")
        case_id = str(case.get("id") or "").strip()
        if not case_id or case_id in seen:
            raise ValueError(f"case id missing or duplicated: {case_id!r}")
        seen.add(case_id)
        messages = case.get("messages")
        checks = case.get("checks")
        if not isinstance(messages, list) or not messages:
            raise ValueError(f"case {case_id}: messages must be non-empty")
        if not isinstance(checks, list) or not checks:
            raise ValueError(f"case {case_id}: checks must be non-empty")
        for check in checks:
            if not isinstance(check, dict):
                raise ValueError(f"case {case_id}: each check must be an object")
            check_type = str(check.get("type") or "")
            if check_type not in SUPPORTED_CHECKS:
                raise ValueError(f"case {case_id}: unsupported check {check_type!r}")
    return payload


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text, flags=re.UNICODE))


def _json_object(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def evaluate_check(response: str, check: dict[str, Any]) -> tuple[bool, str]:
    check_type = str(check["type"])
    value = check.get("value")
    if check_type == "equals":
        ok = response == str(value)
    elif check_type == "stripped_equals":
        ok = response.strip() == str(value)
    elif check_type == "starts_with":
        ok = response.lstrip().startswith(str(value))
    elif check_type == "ends_with":
        ok = response.rstrip().endswith(str(value))
    elif check_type == "contains":
        ok = str(value) in response
    elif check_type == "not_contains":
        ok = str(value) not in response
    elif check_type == "regex":
        ok = re.search(str(value), response, flags=re.MULTILINE) is not None
    elif check_type == "not_regex":
        ok = re.search(str(value), response, flags=re.MULTILINE) is None
    elif check_type == "exact_count":
        needle = str(value)
        expected = int(check.get("count"))
        ok = response.count(needle) == expected
    elif check_type == "one_of":
        options = value if isinstance(value, list) else []
        ok = response.strip() in [str(item) for item in options]
    elif check_type == "json_object_keys":
        obj = _json_object(response)
        keys = value if isinstance(value, list) else []
        ok = obj is not None and set(obj) == {str(item) for item in keys}
    elif check_type == "json_field_equals":
        obj = _json_object(response)
        field = str(check.get("field") or "")
        ok = obj is not None and field in obj and obj[field] == value
    elif check_type == "min_words":
        ok = _word_count(response) >= int(value)
    elif check_type == "max_words":
        ok = _word_count(response) <= int(value)
    else:  # guarded by load_suite, retained for direct unit calls
        raise ValueError(f"unsupported check {check_type!r}")
    detail = check.get("label") or check_type
    return bool(ok), str(detail)


def evaluate_case(case: dict[str, Any], response: str) -> dict[str, Any]:
    results = []
    for index, check in enumerate(case["checks"]):
        passed, detail = evaluate_check(response, check)
        results.append({"index": index, "type": check["type"], "label": detail, "passed": passed})
    return {
        "case_id": case["id"],
        "categories": list(case.get("categories") or []),
        "passed": all(item["passed"] for item in results),
        "passed_checks": sum(item["passed"] for item in results),
        "total_checks": len(results),
        "checks": results,
    }


def load_responses(path: Path) -> dict[str, str]:
    responses: dict[str, str] = {}
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            item = json.loads(raw)
            if not isinstance(item, dict):
                raise ValueError(f"responses line {line_number}: object required")
            case_id = str(item.get("case_id") or item.get("id") or "").strip()
            if not case_id:
                raise ValueError(f"responses line {line_number}: case_id required")
            if case_id in responses:
                raise ValueError(f"responses line {line_number}: duplicate case_id {case_id!r}")
            response = item.get("response")
            if not isinstance(response, str):
                raise ValueError(f"responses line {line_number}: response string required")
            responses[case_id] = response
    return responses


def score_suite(suite: dict[str, Any], responses: dict[str, str]) -> dict[str, Any]:
    case_ids = {str(case["id"]) for case in suite["cases"]}
    unknown = sorted(set(responses) - case_ids)
    if unknown:
        raise ValueError(f"responses contain unknown cases: {', '.join(unknown)}")
    rows = []
    missing = []
    for case in suite["cases"]:
        case_id = str(case["id"])
        if case_id not in responses:
            missing.append(case_id)
            continue
        rows.append(evaluate_case(case, responses[case_id]))

    total_checks = sum(row["total_checks"] for row in rows)
    passed_checks = sum(row["passed_checks"] for row in rows)
    category_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for category in row["categories"]:
            category_rows[str(category)].append(row)
    by_category = {}
    for category, items in sorted(category_rows.items()):
        checks = sum(item["total_checks"] for item in items)
        passed = sum(item["passed_checks"] for item in items)
        by_category[category] = {
            "case_count": len(items),
            "hard_satisfaction_rate": round(100.0 * sum(item["passed"] for item in items) / len(items), 2),
            "soft_satisfaction_rate": round(100.0 * passed / checks, 2) if checks else None,
        }
    return {
        "schema": RESULT_SCHEMA,
        "suite_id": suite.get("suite_id"),
        "suite_revision": suite.get("revision"),
        "case_count": len(suite["cases"]),
        "evaluated_case_count": len(rows),
        "missing_case_count": len(missing),
        "missing_cases": missing,
        "hard_satisfaction_rate": round(100.0 * sum(row["passed"] for row in rows) / len(rows), 2) if rows else None,
        "soft_satisfaction_rate": round(100.0 * passed_checks / total_checks, 2) if total_checks else None,
        "all_cases_evaluated": not missing,
        "by_category": by_category,
        "cases": rows,
    }


def selftest_suite(suite: dict[str, Any]) -> dict[str, Any]:
    failures = []
    for case in suite["cases"]:
        case_id = str(case["id"])
        positive = case.get("positive_response")
        negative = case.get("negative_response")
        if not isinstance(positive, str) or not isinstance(negative, str):
            failures.append({"case_id": case_id, "reason": "missing positive_response or negative_response"})
            continue
        good = evaluate_case(case, positive)
        bad = evaluate_case(case, negative)
        if not good["passed"]:
            failures.append({"case_id": case_id, "reason": "positive control rejected", "checks": good["checks"]})
        if bad["passed"]:
            failures.append({"case_id": case_id, "reason": "negative control accepted", "checks": bad["checks"]})
    return {
        "schema": "manual-instruction-adherence-selftest.v1",
        "suite_id": suite.get("suite_id"),
        "case_count": len(suite["cases"]),
        "passed": not failures,
        "failures": failures,
    }


def emit_cases(suite: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for case in suite["cases"]:
        yield {
            "case_id": case["id"],
            "categories": case.get("categories") or [],
            "messages": case["messages"],
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministically score custom/system instruction adherence outputs.")
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("emit", help="Emit provider-agnostic test conversations as JSONL.")
    score = sub.add_parser("score", help="Score JSONL responses with case_id and response fields.")
    score.add_argument("--responses", type=Path, required=True)
    sub.add_parser("selftest", help="Verify that every checker accepts its positive control and rejects its negative control.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        suite = load_suite(args.suite)
        if args.command == "emit":
            for item in emit_cases(suite):
                print(json.dumps(item, ensure_ascii=False))
            return 0
        if args.command == "selftest":
            result = selftest_suite(suite)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if result["passed"] else 1
        responses = load_responses(args.responses)
        result = score_suite(suite, responses)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["all_cases_evaluated"] else 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
