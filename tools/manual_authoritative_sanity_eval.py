#!/usr/bin/env python3
"""Authoritative sanity/eval primitives backed by MCP receipts and GitHub state.

Worker reports are deliberately absent from the scoring path. MCP process receipts own
observable execution/tool-order truth. GitHub PR/ref/check state owns repository
convergence and configured automated acceptance. The two components remain separate;
there is no aggregate score until a later calibration explicitly defines one.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

TRACE_SPEC_SCHEMA = "manual-authoritative-trace-spec.v1"
TRACE_RESULT_SCHEMA = "manual-authoritative-trace-result.v1"
GITHUB_RESULT_SCHEMA = "manual-authoritative-github-result.v1"
SUPPORTED_TRACE_CHECKS = frozenset({
    "command_present",
    "command_absent",
    "successful_command_present",
    "ordered_commands",
    "command_precedes",
    "cwd_matches_for_command",
})
PASS_CONCLUSIONS = frozenset({"SUCCESS", "NEUTRAL", "SKIPPED"})


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_trace_spec(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    if not isinstance(payload, dict) or payload.get("schema") != TRACE_SPEC_SCHEMA:
        raise ValueError("unsupported trace spec schema")
    checks = payload.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("trace spec requires non-empty checks")
    for check in checks:
        if not isinstance(check, dict) or check.get("type") not in SUPPORTED_TRACE_CHECKS:
            raise ValueError(f"unsupported trace check: {check.get('type') if isinstance(check, dict) else check!r}")
    return payload


def load_mcp_receipts(
    root: Path,
    *,
    caller_id: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows: list[dict[str, Any]] = []
    discovered = parsed = incomplete = filtered = unreadable = mtime_prefiltered = 0
    start_epoch = start.timestamp() if start is not None else None
    try:
        entries = list(os.scandir(root))
    except OSError:
        raise
    for entry in entries:
        if not entry.is_file(follow_symlinks=False) or not entry.name.lower().endswith('.json'):
            continue
        discovered += 1
        if start_epoch is not None:
            try:
                # Receipts are written on/after process completion. A file whose mtime is
                # clearly older than the requested start cannot contain an in-window start.
                if entry.stat(follow_symlinks=False).st_mtime < start_epoch - 60.0:
                    mtime_prefiltered += 1
                    continue
            except OSError:
                unreadable += 1
                continue
        path = Path(entry.path)
        try:
            item = _load_json(path)
        except (OSError, json.JSONDecodeError):
            unreadable += 1
            continue
        if not isinstance(item, dict):
            unreadable += 1
            continue
        parsed += 1
        started = _dt(str(item.get('started_at') or ''))
        if started is None:
            unreadable += 1
            continue
        if caller_id and str(item.get('caller_id') or '') != caller_id:
            filtered += 1
            continue
        if start and started < start:
            filtered += 1
            continue
        if end and started >= end:
            filtered += 1
            continue
        if item.get('audit_schema') != 'process-output-evidence.v1' or item.get('evidence_completeness') != 'complete':
            incomplete += 1
            continue
        row = dict(item)
        row['_receipt_path'] = str(path)
        row['_started_dt'] = started
        rows.append(row)
    rows.sort(key=lambda item: (item['_started_dt'], str(item.get('process_id') or '')))
    return rows, {
        'discovered_receipts': discovered,
        'parsed_receipts': parsed,
        'authoritative_receipts': len(rows),
        'excluded_incomplete_receipts': incomplete,
        'excluded_by_scope': filtered,
        'unreadable_candidate_receipts': unreadable,
        'prefiltered_by_mtime_before_start': mtime_prefiltered,
    }


def _matches(rows: list[dict[str, Any]], pattern: str) -> list[tuple[int, dict[str, Any]]]:
    regex = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
    return [(i, row) for i, row in enumerate(rows) if regex.search(str(row.get("command") or ""))]


def _receipt_success(row: dict[str, Any]) -> bool:
    return str(row.get("execution_outcome") or "").lower() == "success" and row.get("exit_code") == 0


def evaluate_trace_check(
    rows: list[dict[str, Any]],
    check: dict[str, Any],
    *,
    exhaustive: bool,
) -> dict[str, Any]:
    kind = str(check['type'])
    label = str(check.get('label') or kind)
    evidence: list[str] = []
    status = 'UNKNOWN'
    passed: bool | None = None

    def missing_result() -> tuple[str, bool | None]:
        return ('FAIL', False) if exhaustive else ('UNKNOWN', None)

    if kind in {'command_present', 'command_absent', 'successful_command_present', 'cwd_matches_for_command'}:
        pattern = str(check.get('pattern') or '')
        found = _matches(rows, pattern)
        evidence = [str(row.get('process_id') or row.get('request_id') or '') for _, row in found[:8]]
        if kind == 'command_present':
            if found:
                status, passed = 'PASS', True
            else:
                status, passed = missing_result()
        elif kind == 'command_absent':
            if found:
                status, passed = 'FAIL', False
            elif exhaustive:
                status, passed = 'PASS', True
            else:
                status, passed = 'UNKNOWN', None
        elif kind == 'successful_command_present':
            if any(_receipt_success(row) for _, row in found):
                status, passed = 'PASS', True
            else:
                status, passed = missing_result()
        else:
            cwd_pattern = re.compile(str(check.get('cwd_pattern') or ''), re.IGNORECASE)
            mismatches = [row for _, row in found if cwd_pattern.search(str(row.get('cwd') or '')) is None]
            if mismatches:
                status, passed = 'FAIL', False
                evidence = [str(row.get('process_id') or row.get('request_id') or '') for row in mismatches[:8]]
            elif found:
                status, passed = 'PASS', True
            else:
                status, passed = missing_result()
    elif kind == 'ordered_commands':
        patterns = [str(value) for value in check.get('patterns') or []]
        if not patterns:
            raise ValueError('ordered_commands requires patterns')
        cursor = -1
        used: list[dict[str, Any]] = []
        sequence_found = True
        for pattern in patterns:
            candidate = next(((i, row) for i, row in _matches(rows, pattern) if i > cursor), None)
            if candidate is None:
                sequence_found = False
                break
            cursor, row = candidate
            used.append(row)
        evidence = [str(row.get('process_id') or row.get('request_id') or '') for row in used]
        if sequence_found:
            status, passed = 'PASS', True
        else:
            status, passed = missing_result()
    elif kind == 'command_precedes':
        before = _matches(rows, str(check.get('before_pattern') or ''))
        after = _matches(rows, str(check.get('after_pattern') or ''))
        pair = next(((bi, b, ai, a) for bi, b in before for ai, a in after if bi < ai), None)
        if pair:
            status, passed = 'PASS', True
            evidence = [str(pair[1].get('process_id') or ''), str(pair[3].get('process_id') or '')]
        else:
            status, passed = missing_result()
            evidence = [str(row.get('process_id') or '') for _, row in (before + after)[:8]]
    else:
        raise ValueError(f'unsupported trace check {kind!r}')
    return {'type': kind, 'label': label, 'status': status, 'passed': passed, 'evidence_process_ids': evidence}


def score_trace(
    spec: dict[str, Any],
    rows: list[dict[str, Any]],
    coverage: dict[str, int] | None = None,
    *,
    coverage_mode: str = 'partial',
) -> dict[str, Any]:
    if coverage_mode not in {'partial', 'exhaustive'}:
        raise ValueError("coverage_mode must be 'partial' or 'exhaustive'")
    coverage_info = dict(coverage or {})
    gap_count = int(coverage_info.get('excluded_incomplete_receipts') or 0) + int(coverage_info.get('unreadable_candidate_receipts') or 0)
    exhaustive = coverage_mode == 'exhaustive' and gap_count == 0
    effective_mode = 'exhaustive' if exhaustive else 'partial'
    if coverage_mode == 'exhaustive' and not exhaustive:
        coverage_info['exhaustive_claim_degraded'] = True
        coverage_info['exhaustive_claim_gap_count'] = gap_count

    results = [evaluate_trace_check(rows, check, exhaustive=exhaustive) for check in spec['checks']]
    categories: dict[str, list[str]] = defaultdict(list)
    for check, result in zip(spec['checks'], results):
        for category in check.get('categories') or ['uncategorized']:
            categories[str(category)].append(str(result['status']))

    def summarize(statuses: list[str]) -> dict[str, Any]:
        passed_count = sum(status == 'PASS' for status in statuses)
        failed_count = sum(status == 'FAIL' for status in statuses)
        unknown_count = sum(status == 'UNKNOWN' for status in statuses)
        decided_count = passed_count + failed_count
        hard: bool | None
        if failed_count:
            hard = False
        elif unknown_count:
            hard = None
        else:
            hard = True
        return {
            'check_count': len(statuses),
            'decided_check_count': decided_count,
            'unknown_check_count': unknown_count,
            'soft_satisfaction_rate': round(100.0 * passed_count / decided_count, 2) if decided_count else None,
            'hard_satisfied': hard,
        }

    overall = summarize([str(item['status']) for item in results])
    by_category = {key: summarize(values) for key, values in sorted(categories.items())}
    return {
        'schema': TRACE_RESULT_SCHEMA,
        'spec_id': spec.get('spec_id'),
        'receipt_count': len(rows),
        'coverage': coverage_info,
        'coverage_mode_requested': coverage_mode,
        'coverage_mode_effective': effective_mode,
        'hard_satisfied': overall['hard_satisfied'],
        'soft_satisfaction_rate': overall['soft_satisfaction_rate'],
        'decided_check_count': overall['decided_check_count'],
        'unknown_check_count': overall['unknown_check_count'],
        'by_category': by_category,
        'checks': results,
        'authority': 'MCP_DURABLE_PROCESS_RUNTIME_RECEIPTS',
    }


def _check_names(item: dict[str, Any]) -> set[str]:
    names = {str(item.get("name") or "").strip()}
    workflow = str(item.get("workflowName") or "").strip()
    name = str(item.get("name") or "").strip()
    if workflow and name:
        names.add(f"{workflow}/{name}")
    return {value for value in names if value}


def evaluate_github_pr_payload(payload: dict[str, Any], *, required_checks: Iterable[str] = ()) -> dict[str, Any]:
    merge_commit = payload.get('mergeCommit') or {}
    state = str(payload.get('state') or '').upper()
    merged = state == 'MERGED' and bool(merge_commit.get('oid'))
    if merged:
        convergence_status, convergence_pass = 'PASS', True
    elif state == 'OPEN':
        convergence_status, convergence_pass = 'PENDING', None
    else:
        convergence_status, convergence_pass = 'FAIL', False
    checks = list(payload.get('statusCheckRollup') or [])
    completed = [item for item in checks if str(item.get('status') or '').upper() == 'COMPLETED']
    pending = [item for item in checks if str(item.get('status') or '').upper() != 'COMPLETED']
    bad_completed = [item for item in completed if str(item.get('conclusion') or '').upper() not in PASS_CONCLUSIONS]
    required_results = []
    for required in required_checks:
        matches = [item for item in checks if required in _check_names(item)]
        if not matches:
            status, passed = 'MISSING', False
        elif any(str(item.get('status') or '').upper() != 'COMPLETED' for item in matches):
            status, passed = 'PENDING', None
        elif all(str(item.get('conclusion') or '').upper() in PASS_CONCLUSIONS for item in matches):
            status, passed = 'PASS', True
        else:
            status, passed = 'FAIL', False
        required_results.append({'name': required, 'status': status, 'passed': passed})
    if not required_results:
        required_pass = None
    elif any(item['passed'] is False for item in required_results):
        required_pass = False
    elif any(item['passed'] is None for item in required_results):
        required_pass = None
    else:
        required_pass = True
    return {
        'schema': GITHUB_RESULT_SCHEMA,
        'repository': payload.get('repository'),
        'pr_number': payload.get('number'),
        'base_ref': payload.get('baseRefName'),
        'state': payload.get('state'),
        'merged': merged,
        'merge_commit_oid': merge_commit.get('oid'),
        'convergence_status': convergence_status,
        'convergence_pass': convergence_pass,
        'required_checks_configured': bool(required_results),
        'required_checks_pass': required_pass,
        'required_checks': required_results,
        'observed_checks': {
            'count': len(checks),
            'completed': len(completed),
            'pending': len(pending),
            'bad_completed': len(bad_completed),
        },
        'nonrequired_check_failures_are_diagnostic_only': True,
        'authority': 'GITHUB_PR_REF_CHECK_STATE',
    }


def fetch_github_pr(repo: str, pr_number: int) -> dict[str, Any]:
    fields = "number,state,baseRefName,mergeCommit,statusCheckRollup,url"
    proc = subprocess.run(
        ["gh", "pr", "view", str(pr_number), "--repo", repo, "--json", fields],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    payload = json.loads(proc.stdout)
    payload["repository"] = repo
    return payload


def compose_components(trace: dict[str, Any] | None, github: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": "manual-authoritative-sanity-v4-result.v1",
        "calibration_status": "NOT_CALIBRATED",
        "aggregate_score": None,
        "instruction_execution_trace": trace,
        "github_repository_acceptance": github,
        "worker_report_input_used": False,
        "semantics": "Components stay separate. MCP receipts establish execution/tool-trace facts; GitHub establishes repository convergence and configured check evidence. No aggregate truth score exists until prospective calibration defines one.",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate authoritative MCP/GitHub evidence without worker-report scoring.")
    sub = parser.add_subparsers(dest="command", required=True)
    trace = sub.add_parser("trace")
    trace.add_argument("--receipt-root", type=Path, required=True)
    trace.add_argument("--spec", type=Path, required=True)
    trace.add_argument("--caller-id")
    trace.add_argument("--start")
    trace.add_argument("--end")
    trace.add_argument("--coverage-mode", choices=("partial", "exhaustive"), default="partial")
    gh = sub.add_parser("github-pr")
    gh.add_argument("--repo", required=True)
    gh.add_argument("--pr", type=int, required=True)
    gh.add_argument("--required-check", action="append", default=[])
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "trace":
            spec = load_trace_spec(args.spec)
            rows, coverage = load_mcp_receipts(
                args.receipt_root,
                caller_id=args.caller_id,
                start=_dt(args.start),
                end=_dt(args.end),
            )
            print(json.dumps(score_trace(spec, rows, coverage, coverage_mode=args.coverage_mode), indent=2, ensure_ascii=False))
            return 0
        payload = fetch_github_pr(args.repo, args.pr)
        print(json.dumps(evaluate_github_pr_payload(payload, required_checks=args.required_check), indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
