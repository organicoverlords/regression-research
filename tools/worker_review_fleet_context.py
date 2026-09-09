from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TIMED_HISTORY = ROOT / "worker-reports" / "history" / "_reports"
DEFAULT_MANUAL_HISTORY = ROOT / "worker-reports" / "manual" / "history" / "_reports"
DEFAULT_OUTPUT = ROOT / "worker-reports" / "reviews" / "fleet-context.json"
DEFAULT_HISTORY_LIMIT = 300
DEFAULT_MAX_RELATED = 14
DEFAULT_MAX_EXAMPLES = 4
DEFAULT_MAX_OUTPUT_CHARS = 24_000

TEXT_FIELDS = (
    "repo", "scope", "outcome", "mutation", "validation",
    "remaining_gate", "stop_reason", "findings",
)

FAULT_RULES: dict[str, dict[str, Any]] = {
    "routing_fault": {
        "tags": {"route_problem"},
        "patterns": (
            r"\bpreflight(?:-| )?reject", r"\brejected (?:command|route|invocation)",
            r"\bcommand[- ]shape", r"\bwrong repo\b", r"\bwrong branch\b",
            r"\bstale (?:branch[- ]local )?wrapper\b",
            r"\bmalformed (?:gh|command|powershell)", r"\bswarm_route\b",
            r"\bswarm_exec\b", r"\broute (?:decision|assignment|mismatch|problem|failure)\b",
        ),
    },
    "resource_bottleneck": {
        "tags": {"resource", "build"},
        "patterns": (
            r"\blow[-_ ]free[-_ ]disk\b", r"\blow disk\b",
            r"\bdisk (?:pressure|admission|floor|headroom)\b", r"\bmemory pressure\b",
            r"\b(?:ram|vram) (?:pressure|headroom|available)\b", r"\bbuild[- ]slot\b",
            r"\blong_queue_wait\b", r"\bqueue (?:wait|blocked|contention)\b",
            r"\bcapacity\b", r"\bsaturated\b",
        ),
    },
    "cohort_or_stale_evidence_churn": {
        "tags": {"ci"},
        "patterns": (
            r"\bcohort\b", r"\bstale (?:receipt|evidence|head|gate|state)\b",
            r"\bcurrent[- ]main\b", r"\bmain advanced\b", r"\bexact[- ]head\b",
            r"\brebase(?:d|s|ing)?\b", r"\bmerge guard\b", r"\bstatus .*pending\b",
        ),
    },
    "ownership_or_dirty_state_contention": {
        "tags": {"contention"},
        "patterns": (
            r"\bbusy (?:claim|owner|scope|lease)\b", r"\bclaim(?:ed|ing)?\b",
            r"\bcollision\b", r"\bforeign[- ]dirty\b",
            r"\bdirty (?:root|tree|checkout|worktree|state)\b",
            r"\bforeign (?:work|state|changes)\b", r"\bownership\b",
        ),
    },
    "scheduler_or_recovery_recurrence": {
        "tags": set(),
        "patterns": (
            r"\bself[- ]disable\b", r"\bdisabled again\b", r"\bdisable recurrence\b",
            r"\bre[- ]enable\b", r"\brecovery_(?:needed|pending|retry_needed)\b",
            r"\bmissed cadence\b", r"\bstart receipt\b",
            r"\bscheduler (?:recovery|disable|disabled|failure)\b",
        ),
    },
    "avoidable_action_mistake": {
        "tags": {"error", "wrapper_anomaly"},
        "patterns": (
            r"\bmalformed\b", r"\bwrong repo\b", r"\bwrong branch\b",
            r"\bstale (?:branch[- ]local )?wrapper\b", r"\bpremature archive\b",
            r"\binvalid (?:tag|schema|command)\b", r"\bunchanged retry\b",
            r"\bretried unchanged\b", r"\bcommand[- ]shape\b",
            r"\bcontinued after .*fail", r"\bself[- ]disable\b", r"\btypo\b",
        ),
    },
    "proof_or_acceptance_gap": {
        "tags": {"proof"},
        "patterns": (
            r"\bnot[_ -]proven\b", r"\bproof pending\b",
            r"\bvisual (?:proof|review|acceptance).*(?:pending|required|remain)",
            r"\bruntime (?:proof|acceptance).*(?:pending|required|remain)",
            r"\btwo[- ]machine.*(?:pending|required|remain)",
            r"\bacceptance.*(?:pending|required|remain)",
        ),
    },
}

FAULT_SIGNATURES: dict[str, tuple[str, ...]] = {
    "command_shape": (r"\bpreflight(?:-| )?reject", r"\bcommand[- ]shape", r"\bmalformed (?:powershell|command)"),
    "stale_wrapper": (r"\bstale (?:branch[- ]local )?wrapper", r"\bbranch[- ]local wrapper"),
    "wrong_repo_or_branch": (r"\bwrong repo\b", r"\bwrong branch\b"),
    "route_assignment_ignored": (r"\bswarm_route\b", r"\broute assignment\b", r"\brouted? .*omen.*(?:local|windows)"),
    "low_disk": (r"\blow[-_ ]free[-_ ]disk\b", r"\blow disk\b", r"\bdisk (?:pressure|admission|floor|headroom)"),
    "build_slot_or_queue": (r"\bbuild[- ]slot\b", r"\blong_queue_wait\b", r"\bqueue (?:wait|blocked|contention)"),
    "memory_pressure": (r"\bmemory pressure\b", r"\b(?:ram|vram) (?:pressure|headroom|available)"),
    "stale_receipt_or_evidence": (r"\bstale (?:receipt|evidence|head|gate|state)\b",),
    "cohort_pending": (r"\bcohort.*pending\b", r"\bpending.*cohort\b"),
    "main_churn": (r"\bcurrent[- ]main\b", r"\bmain advanced\b", r"\brebase(?:d|s|ing)?\b"),
    "dirty_foreign_state": (r"\bforeign[- ]dirty\b", r"\bdirty (?:root|tree|checkout|worktree|state)\b", r"\bforeign (?:work|state|changes)\b"),
    "busy_collision": (r"\bbusy (?:claim|owner|scope|lease)\b", r"\bcollision\b"),
    "self_disable": (r"\bself[- ]disable\b", r"\bdisabled again\b", r"\bdisable recurrence\b", r"\bis_enabled=false\b"),
    "missing_start_or_cadence": (r"\bstart receipt\b", r"\bbootstrap[- ]only\b", r"\bmissed cadence\b"),
    "recovery_loop": (r"\bre[- ]enable\b", r"\brecovery_(?:needed|pending|retry_needed)\b"),
}


SIGNATURE_FAMILY = {
    "command_shape": "routing_fault",
    "stale_wrapper": "routing_fault",
    "wrong_repo_or_branch": "routing_fault",
    "route_assignment_ignored": "routing_fault",
    "low_disk": "resource_bottleneck",
    "build_slot_or_queue": "resource_bottleneck",
    "memory_pressure": "resource_bottleneck",
    "stale_receipt_or_evidence": "cohort_or_stale_evidence_churn",
    "cohort_pending": "cohort_or_stale_evidence_churn",
    "main_churn": "cohort_or_stale_evidence_churn",
    "dirty_foreign_state": "ownership_or_dirty_state_contention",
    "busy_collision": "ownership_or_dirty_state_contention",
    "self_disable": "scheduler_or_recovery_recurrence",
    "missing_start_or_cadence": "scheduler_or_recovery_recurrence",
    "recovery_loop": "scheduler_or_recovery_recurrence",
}

REGRESSION_TRACKED_SIGNATURES = {
    "command_shape",
    "stale_wrapper",
    "wrong_repo_or_branch",
    "route_assignment_ignored",
    "low_disk",
    "stale_receipt_or_evidence",
    "busy_collision",
    "self_disable",
    "missing_start_or_cadence",
    "recovery_loop",
}


REGRESSION_PRIORITY = {
    "self_disable": 100,
    "command_shape": 95,
    "route_assignment_ignored": 90,
    "wrong_repo_or_branch": 85,
    "stale_wrapper": 85,
    "missing_start_or_cadence": 80,
    "recovery_loop": 75,
    "stale_receipt_or_evidence": 70,
    "busy_collision": 65,
    "low_disk": 60,
}

REPAIR_SIGNATURE_PATTERNS: dict[str, tuple[str, ...]] = {
    "command_shape": (
        r"\bpreflight.{0,180}\b(?:prevent|guard|normaliz|rule-level|reject unsafe|command-shape)",
        r"\b(?:prevent|guard|normaliz|rule-level).{0,180}\bpreflight",
    ),
    "self_disable": (
        r"\bself[- ]disable.{0,180}\b(?:fix|restor|forbid|prohibit|guard|invariant|block)",
        r"\b(?:fix|restor|forbid|prohibit|guard|invariant|block).{0,180}\b(?:worker )?self[- ]disable",
    ),
    "route_assignment_ignored": (
        r"\broute assignment.{0,220}\b(?:execution|enforc|require|guard|swarm_exec)",
        r"\b(?:enforc|require|guard|swarm_exec).{0,220}\broute assignment",
    ),
    "low_disk": (
        r"\b(?:reclaim|restor|harden|fix).{0,180}\b(?:low[-_ ]free[-_ ]disk|low disk|disk (?:pressure|admission|headroom))",
        r"\b(?:low[-_ ]free[-_ ]disk|low disk|disk (?:pressure|admission|headroom)).{0,180}\b(?:reclaim|restor|harden|fix)",
    ),
    "stale_receipt_or_evidence": (
        r"\bstale (?:receipt|evidence).{0,180}\b(?:fix|repair|harden|guard)",
        r"\b(?:fix|repair|harden|guard).{0,180}\bstale (?:receipt|evidence)",
    ),
    "busy_collision": (
        r"\b(?:busy|scope|claim).{0,180}\bcollision.{0,180}\b(?:harden|guard|reject|fix)",
        r"\b(?:harden|guard|reject|fix).{0,180}\b(?:busy|scope|claim).{0,180}\bcollision",
    ),
    "stale_wrapper": (
        r"\bstale (?:branch[- ]local )?wrapper.{0,180}\b(?:fix|repair|guard|current-main)",
    ),
    "wrong_repo_or_branch": (
        r"\bwrong (?:repo|branch).{0,180}\b(?:fix|guard|prevent|reject)",
    ),
    "missing_start_or_cadence": (
        r"\b(?:start receipt|missed cadence|bootstrap[- ]only).{0,180}\b(?:fix|repair|guard|recover)",
    ),
    "recovery_loop": (
        r"\brecovery.{0,180}\b(?:loop|recurrence).{0,180}\b(?:fix|guard|escalat|prevent)",
        r"\b(?:fix|guard|escalat|prevent).{0,180}\brecovery.{0,180}\b(?:loop|recurrence)",
    ),
}


def _repair_near_signature(report: dict[str, Any], signature: str, *, window: int = 320) -> bool:
    # A report can describe a transient workaround in findings while the owned defect
    # remains unchanged. Only repair-bearing result fields may establish the historical
    # repair boundary used for regression-after-fix candidates.
    text = " ".join(
        str(report.get(field) or "")
        for field in ("outcome", "mutation", "validation")
    )
    explicit = REPAIR_SIGNATURE_PATTERNS.get(signature, ())
    if explicit:
        return any(re.search(pattern, text, re.IGNORECASE | re.DOTALL) for pattern in explicit)
    patterns = FAULT_SIGNATURES[signature]
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            start = max(0, match.start() - window)
            end = min(len(text), match.end() + window)
            if REPAIR_RE.search(text[start:end]):
                return True
    return False


def fault_signatures(report: dict[str, Any]) -> list[str]:
    text = _report_text(report)
    return sorted(
        name
        for name, patterns in FAULT_SIGNATURES.items()
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)
    )


REPAIR_RE = re.compile(
    r"\b(fix(?:ed|es)?|repair(?:ed|s)?|harden(?:ed|s)?|resolved?|prevent(?:ed|s|ion)?|forbid(?:s|den)?|prohibit(?:s|ed)?|guard(?:ed|s)?|restored|reclaimed)\b",
    re.IGNORECASE,
)
RECURRENCE_RE = re.compile(
    r"\b(again|recurr(?:ed|ence|ing)|reappeared|returned|still (?:hits?|fails?|blocked|broken|disabled)|after (?:the )?(?:fix|repair)|previously fixed|already fixed)\b",
    re.IGNORECASE,
)
URL_REF_RE = re.compile(
    r"https?://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/(?:issues|pull)/(\d+)",
    re.IGNORECASE,
)
NAMED_REF_RE = re.compile(
    r"\b(P3|Tiny3D|regression-research|agents|chatgpt-mcp-clean|BusyCoordinator)\s*#(\d+)\b",
    re.IGNORECASE,
)
BARE_REF_RE = re.compile(r"(?<![A-Za-z0-9])#(\d+)\b")

REPO_ALIASES = {
    "p3": "p3", "organicoverlords/p3": "p3",
    "tiny3d": "tiny3d", "organicoverlords/tiny3d": "tiny3d",
    "regression-research": "regression-research",
    "organicoverlords/regression-research": "regression-research",
    "agents": "agents", "organicoverlords/agents": "agents",
    "chatgpt-mcp-clean": "chatgpt-mcp-clean",
    "organicoverlords/chatgpt-mcp-clean": "chatgpt-mcp-clean",
    "busycoordinator": "busycoordinator", "local/busycoordinator": "busycoordinator",
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _timestamp(report: dict[str, Any]) -> datetime:
    for key in ("observed_started_at", "started_at", "finished_at", "archived_at"):
        parsed = _parse_dt(report.get(key))
        if parsed is not None:
            return parsed
    return datetime.min.replace(tzinfo=timezone.utc)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _markdown_report(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    fields: dict[str, Any] = {}
    for raw in text.splitlines():
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        key = key.strip().lstrip("\ufeff").lower()
        if key and key.replace("_", "").isalnum():
            fields[key] = value.strip()
    tags = fields.get("finding_tags")
    if isinstance(tags, str):
        fields["finding_tags"] = [x.strip() for x in tags.split(",") if x.strip()]
    fields.setdefault("report_sha256", _sha256(path.read_bytes()))
    fields.setdefault(
        "population",
        "manual" if "manual" in {part.lower() for part in path.parts} else "timed",
    )
    fields["source_path"] = str(path)
    return fields


def load_target_report(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".json":
        value = _read_json(path)
        if value is None:
            raise ValueError(f"target report is not valid JSON: {path}")
        value = dict(value)
        value["source_path"] = str(path)
        return value
    return _markdown_report(path)


def load_history(
    timed_root: Path,
    manual_root: Path,
    *,
    limit: int = DEFAULT_HISTORY_LIMIT,
) -> list[dict[str, Any]]:
    candidates: list[Path] = []
    for root in (timed_root, manual_root):
        if root.is_dir():
            candidates.extend(root.glob("*.json"))
    candidates.sort(
        key=lambda p: p.stat().st_mtime_ns if p.exists() else 0,
        reverse=True,
    )
    reports: list[dict[str, Any]] = []
    for path in candidates:
        value = _read_json(path)
        if value is None or value.get("schema") != "worker-report-history.v6":
            continue
        item = dict(value)
        item["source_path"] = str(path)
        reports.append(item)
    reports.sort(key=_timestamp, reverse=True)
    return reports[: max(1, limit)]


def _report_text(report: dict[str, Any]) -> str:
    parts = [str(report.get(key)) for key in TEXT_FIELDS if report.get(key) is not None]
    tags = report.get("finding_tags") or []
    if isinstance(tags, str):
        parts.append(tags)
    elif isinstance(tags, list):
        parts.extend(str(tag) for tag in tags)
    return "\n".join(parts)


def _repo_candidates(report: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for token in re.split(r"[;,]", str(report.get("repo") or "")):
        alias = REPO_ALIASES.get(token.strip().lower())
        if alias and alias not in values:
            values.append(alias)
    return values


def extract_work_refs(report: dict[str, Any], *, include_bare: bool = True) -> list[str]:
    text = _report_text(report)
    refs: set[str] = set()
    covered: set[str] = set()
    for owner, repo, number in URL_REF_RE.findall(text):
        refs.add(f"{owner.lower()}/{repo.lower()}#{number}")
        covered.add(number)
    for name, number in NAMED_REF_RE.findall(text):
        refs.add(f"{REPO_ALIASES.get(name.lower(), name.lower())}#{number}")
        covered.add(number)
    if not include_bare:
        return sorted(refs)
    repos = _repo_candidates(report)
    for number in BARE_REF_RE.findall(text):
        if number in covered:
            continue
        refs.add(f"{repos[0]}#{number}" if repos else f"ambiguous#{number}")
    return sorted(refs)


def _tags(report: dict[str, Any]) -> set[str]:
    value = report.get("finding_tags") or []
    if isinstance(value, str):
        return {x.strip().lower() for x in value.split(",") if x.strip()}
    if isinstance(value, list):
        return {str(x).strip().lower() for x in value if str(x).strip()}
    return set()


def _snippet(text: str, patterns: Iterable[str], *, limit: int = 260) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    starts: list[int] = []
    for pattern in patterns:
        match = re.search(pattern, compact, re.IGNORECASE)
        if match:
            starts.append(max(0, match.start() - 80))
    start = min(starts) if starts else 0
    piece = compact[start : start + limit]
    if start:
        piece = "..." + piece
    if start + limit < len(compact):
        piece += "..."
    return piece


def _compact_report(
    report: dict[str, Any],
    *,
    include_snippet: str | None = None,
) -> dict[str, Any]:
    result = {
        "report_sha256": report.get("report_sha256"),
        "population": report.get("population"),
        "worker": report.get("display_label") or report.get("worker"),
        "run_id": report.get("run_id"),
        "automation_id": report.get("automation_id"),
        "started_at": report.get("observed_started_at") or report.get("started_at"),
        "state": report.get("state"),
        "repo": report.get("repo"),
        "scope": str(report.get("scope") or "")[:320],
        "work_refs": extract_work_refs(report),
    }
    if include_snippet:
        result["snippet"] = include_snippet
    return result


def fault_families(report: dict[str, Any]) -> list[str]:
    text = _report_text(report)
    tags = _tags(report)
    families: list[str] = []
    for family, rule in FAULT_RULES.items():
        if tags.intersection(rule["tags"]) or any(
            re.search(pattern, text, re.IGNORECASE) for pattern in rule["patterns"]
        ):
            families.append(family)
    return families


def aggregate_faults(
    reports: list[dict[str, Any]],
    *,
    max_examples: int = DEFAULT_MAX_EXAMPLES,
) -> list[dict[str, Any]]:
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    population_totals = Counter(str(report.get("population") or "unknown") for report in reports)
    total_reports = max(1, len(reports))
    for report in reports:
        text = _report_text(report)
        for family in fault_families(report):
            by_family[family].append(
                _compact_report(
                    report,
                    include_snippet=_snippet(text, FAULT_RULES[family]["patterns"]),
                )
            )
    result: list[dict[str, Any]] = []
    for family, examples in by_family.items():
        populations = Counter(str(x.get("population") or "unknown") for x in examples)
        workers = {str(x.get("worker")) for x in examples if x.get("worker")}
        result.append(
            {
                "family": family,
                "authority": "report_derived_candidate_signal",
                "count": len(examples),
                "rate_pct": round(len(examples) * 100.0 / total_reports, 1),
                "population_counts": dict(sorted(populations.items())),
                "population_rates_pct": {
                    population: round(count * 100.0 / max(1, population_totals[population]), 1)
                    for population, count in sorted(populations.items())
                },
                "distinct_workers": len(workers),
                "examples": examples[:max_examples],
            }
        )
    result.sort(key=lambda x: (-int(x["count"]), str(x["family"])))
    return result


def regression_candidates(
    reports: list[dict[str, Any]],
    *,
    max_items: int = 12,
) -> list[dict[str, Any]]:
    latest_repair: dict[str, dict[str, Any]] = {}
    candidates: list[dict[str, Any]] = []
    for report in sorted(reports, key=_timestamp):
        text = _report_text(report)
        signatures = [
            signature
            for signature in fault_signatures(report)
            if signature in REGRESSION_TRACKED_SIGNATURES
        ]
        for signature in signatures:
            earlier = latest_repair.get(signature)
            is_repair = _repair_near_signature(report, signature)
            explicit_recurrence = bool(RECURRENCE_RE.search(text))
            if (
                earlier is not None
                and earlier is not report
                and (not is_repair or explicit_recurrence)
            ):
                candidates.append(
                    {
                        "signature": signature,
                        "family": SIGNATURE_FAMILY[signature],
                        "authority": "heuristic_regression_candidate_not_proof",
                        "explicit_recurrence_language": explicit_recurrence,
                        "repair": _compact_report(
                            earlier,
                            include_snippet=_snippet(_report_text(earlier), FAULT_SIGNATURES[signature]),
                        ),
                        "recurrence": _compact_report(
                            report,
                            include_snippet=_snippet(text, FAULT_SIGNATURES[signature]),
                        ),
                    }
                )
            if is_repair:
                latest_repair[signature] = report
    # Keep newest unique repair/recurrence pair per signature/report pair.
    # Keep the newest recurrence pair for each fault signature, then rank classes.
    unique: list[dict[str, Any]] = []
    seen_signatures: set[str] = set()
    for item in reversed(candidates):
        signature = str(item.get("signature") or "")
        if not signature or signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        unique.append(item)
    unique.sort(
        key=lambda item: (
            REGRESSION_PRIORITY.get(str(item.get("signature")), 0)
            + (25 if item.get("explicit_recurrence_language") else 0),
            _timestamp(item.get("recurrence") if isinstance(item.get("recurrence"), dict) else {}),
        ),
        reverse=True,
    )
    return unique[:max_items]


def related_history(
    target: dict[str, Any],
    reports: list[dict[str, Any]],
    *,
    max_related: int = DEFAULT_MAX_RELATED,
) -> dict[str, Any]:
    target_refs = set(extract_work_refs(target))
    target_sha = target.get("report_sha256")
    target_time = _timestamp(target)
    has_target_time = target_time != datetime.min.replace(tzinfo=timezone.utc)
    related: list[dict[str, Any]] = []
    for report in reports:
        if target_sha and report.get("report_sha256") == target_sha:
            continue
        if has_target_time and _timestamp(report) > target_time:
            continue
        shared = sorted(target_refs.intersection(extract_work_refs(report)))
        if not shared:
            continue
        item = _compact_report(report)
        item["shared_refs"] = shared
        item["outcome"] = str(report.get("outcome") or "")[:500]
        item["remaining_gate"] = str(report.get("remaining_gate") or "")[:500]
        related.append(item)
        if len(related) >= max_related:
            break
    return {"target_refs": sorted(target_refs), "reports": related}


def top_work_threads(
    reports: list[dict[str, Any]],
    *,
    max_threads: int = 12,
) -> list[dict[str, Any]]:
    occurrences: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for report in reports:
        for ref in extract_work_refs(report, include_bare=False):
            if ref.startswith("ambiguous#"):
                continue
            occurrences[ref].append(report)
    rows: list[dict[str, Any]] = []
    for ref, items in occurrences.items():
        workers = {str(x.get("display_label") or x.get("worker")) for x in items}
        populations = Counter(str(x.get("population") or "unknown") for x in items)
        rows.append(
            {
                "ref": ref,
                "report_count": len(items),
                "distinct_workers": len(workers),
                "population_counts": dict(sorted(populations.items())),
                "latest": _compact_report(items[0]),
            }
        )
    rows.sort(key=lambda x: (-int(x["report_count"]), str(x["ref"])))
    return rows[:max_threads]


def load_external_evidence(
    paths: list[Path],
    *,
    per_file_chars: int = 2_000,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for path in paths:
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig", errors="replace")
        if len(text) > per_file_chars:
            text = text[:per_file_chars] + "...[TRUNCATED]"
        result.append(
            {
                "authority": "external_supplied_evidence_not_worker_report",
                "path": str(path),
                "sha256": _sha256(raw),
                "content": text,
            }
        )
    return result


def build_fleet_context(
    *,
    timed_root: Path = DEFAULT_TIMED_HISTORY,
    manual_root: Path = DEFAULT_MANUAL_HISTORY,
    target_report: Path | None = None,
    external_evidence: list[Path] | None = None,
    history_limit: int = DEFAULT_HISTORY_LIMIT,
    max_related: int = DEFAULT_MAX_RELATED,
    max_examples: int = DEFAULT_MAX_EXAMPLES,
) -> dict[str, Any]:
    reports = load_history(timed_root, manual_root, limit=history_limit)
    populations = Counter(str(x.get("population") or "unknown") for x in reports)
    workers = {
        str(x.get("display_label") or x.get("worker"))
        for x in reports
        if x.get("display_label") or x.get("worker")
    }
    context: dict[str, Any] = {
        "schema": "worker-review-fleet-context.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "authority": "DERIVED_REVIEW_CONTEXT_NOT_WORK_AUTHORITY",
        "population_policy": (
            "manual_and_timed_unified_population_population_field_is_metadata_only"
        ),
        "history": {
            "report_count": len(reports),
            "population_counts": dict(sorted(populations.items())),
            "distinct_workers": len(workers),
            "timed_root": str(timed_root),
            "manual_root": str(manual_root),
        },
        "fault_signals": aggregate_faults(reports, max_examples=max_examples),
        "regression_candidates": regression_candidates(reports),
        "top_work_threads": top_work_threads(reports),
        "target": None,
        "external_evidence": load_external_evidence(external_evidence or []),
        "review_instructions": [
            "Treat fault signals and regression candidates as hypotheses derived from worker reports, never as authority.",
            "Do not penalize manual versus timed population; compare evidence and work delta, not scheduler origin.",
            "Population rates are report-mention prevalence only, not fault incidence or worker performance scores.",
            "For routing faults or avoidable mistakes, require process/routing receipts or another external source before making a high-confidence blame claim.",
            "Distinguish repeated valid revalidation after state changed from same-state duplicate churn.",
            "If a repair predates a recurrence candidate, verify that repair was deployed/active before calling it regression-after-fix.",
        ],
    }
    if target_report is not None:
        target = load_target_report(target_report)
        context["target"] = {
            "report": _compact_report(target),
            "related_history": related_history(target, reports, max_related=max_related),
        }
    return context


def _encoded(context: dict[str, Any]) -> str:
    return json.dumps(context, ensure_ascii=False, separators=(",", ":"))


def _bounded_context(context: dict[str, Any], max_chars: int) -> dict[str, Any]:
    if len(_encoded(context)) <= max_chars:
        return context
    compact = json.loads(json.dumps(context))
    for signal in compact.get("fault_signals", []):
        if isinstance(signal, dict):
            signal["examples"] = signal.get("examples", [])[:2]
    compact["regression_candidates"] = compact.get("regression_candidates", [])[:4]
    compact["top_work_threads"] = compact.get("top_work_threads", [])[:8]
    target = compact.get("target")
    if isinstance(target, dict) and isinstance(target.get("related_history"), dict):
        target["related_history"]["reports"] = target["related_history"].get("reports", [])[:8]
    for item in compact.get("external_evidence", []):
        if isinstance(item, dict):
            text = str(item.get("content") or "")
            item["content"] = text[:800] + ("...[TRUNCATED]" if len(text) > 800 else "")
    if len(_encoded(compact)) <= max_chars:
        return compact
    for signal in compact.get("fault_signals", []):
        if isinstance(signal, dict):
            signal.pop("examples", None)
    compact["top_work_threads"] = compact.get("top_work_threads", [])[:5]
    regressions = compact.get("regression_candidates", [])[:4]
    for candidate in regressions:
        if not isinstance(candidate, dict):
            continue
        for side in ("repair", "recurrence"):
            item = candidate.get(side)
            if isinstance(item, dict):
                item.pop("snippet", None)
                item["work_refs"] = item.get("work_refs", [])[:4]
    compact["regression_candidates"] = regressions
    if isinstance(target, dict) and isinstance(target.get("related_history"), dict):
        target["related_history"]["reports"] = target["related_history"].get("reports", [])[:4]
    size = len(_encoded(compact))
    if size <= max_chars:
        return compact
    # Preserve at least the two newest regression candidates before dropping lower-value thread detail.
    compact["top_work_threads"] = compact.get("top_work_threads", [])[:2]
    compact["regression_candidates"] = regressions[:2]
    size = len(_encoded(compact))
    if size > max_chars:
        raise ValueError(
            f"fleet context exceeds max output size after compaction: {size} > {max_chars}"
        )
    return compact


def write_context(
    path: Path,
    context: dict[str, Any],
    *,
    max_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
) -> Path:
    bounded = _bounded_context(context, max_chars)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(bounded, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build bounded unified manual+timed fleet context for worker-report review."
    )
    parser.add_argument("--report", type=Path)
    parser.add_argument("--timed-root", type=Path, default=DEFAULT_TIMED_HISTORY)
    parser.add_argument("--manual-root", type=Path, default=DEFAULT_MANUAL_HISTORY)
    parser.add_argument("--external-evidence", type=Path, action="append", default=[])
    parser.add_argument("--history-limit", type=int, default=DEFAULT_HISTORY_LIMIT)
    parser.add_argument("--max-related", type=int, default=DEFAULT_MAX_RELATED)
    parser.add_argument("--max-examples", type=int, default=DEFAULT_MAX_EXAMPLES)
    parser.add_argument("--max-output-chars", type=int, default=DEFAULT_MAX_OUTPUT_CHARS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--stdout", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        context = build_fleet_context(
            timed_root=args.timed_root,
            manual_root=args.manual_root,
            target_report=args.report,
            external_evidence=args.external_evidence,
            history_limit=args.history_limit,
            max_related=args.max_related,
            max_examples=args.max_examples,
        )
        bounded = _bounded_context(context, args.max_output_chars)
        if args.stdout:
            print(json.dumps(bounded, indent=2, ensure_ascii=False))
        else:
            target = write_context(args.output, bounded, max_chars=args.max_output_chars)
            print(
                json.dumps(
                    {
                        "ok": True,
                        "output": str(target),
                        "reports": bounded["history"]["report_count"],
                        "population_counts": bounded["history"]["population_counts"],
                        "fault_families": len(bounded["fault_signals"]),
                        "regression_candidates": len(bounded["regression_candidates"]),
                    }
                )
            )
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
