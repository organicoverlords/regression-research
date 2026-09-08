from __future__ import annotations

import json
from pathlib import Path

from tools.worker_review_fleet_context import (
    _bounded_context,
    aggregate_faults,
    build_fleet_context,
    extract_work_refs,
    load_history,
    regression_candidates,
    write_context,
)


def write_history(root: Path, *, sha: str, population: str, started_at: str, **fields) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    value = {
        "schema": "worker-report-history.v6",
        "population": population,
        "authority": "NON_AUTHORITATIVE_REPORT_EVIDENCE",
        "report_sha256": sha,
        "display_label": fields.pop("display_label", f"{population}-{sha}"),
        "started_at": started_at,
        "repo": fields.pop("repo", "organicoverlords/p3"),
        "state": fields.pop("state", "RUN_FINISHED"),
        "scope": fields.pop("scope", ""),
        "outcome": fields.pop("outcome", ""),
        "mutation": fields.pop("mutation", ""),
        "validation": fields.pop("validation", ""),
        "remaining_gate": fields.pop("remaining_gate", ""),
        "stop_reason": fields.pop("stop_reason", None),
        "finding_tags": fields.pop("finding_tags", []),
        "findings": fields.pop("findings", None),
        **fields,
    }
    path = root / f"{sha}.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_load_history_unifies_manual_and_timed_in_one_chronology(tmp_path: Path):
    timed = tmp_path / "timed"
    manual = tmp_path / "manual"
    write_history(timed, sha="t1", population="timed", started_at="2026-09-09T00:01:00+03:00")
    write_history(manual, sha="m1", population="manual", started_at="2026-09-09T00:02:00+03:00")

    reports = load_history(timed, manual)

    assert [item["report_sha256"] for item in reports] == ["m1", "t1"]
    assert {item["population"] for item in reports} == {"manual", "timed"}


def test_extract_work_refs_qualifies_named_and_single_repo_bare_refs():
    report = {
        "repo": "organicoverlords/p3",
        "scope": "Fix #2437 after Tiny3D #428 and https://github.com/organicoverlords/p3/pull/2804",
    }
    refs = extract_work_refs(report)
    assert "p3#2437" in refs
    assert "tiny3d#428" in refs
    assert "organicoverlords/p3#2804" in refs


def test_build_context_related_history_crosses_population_boundary(tmp_path: Path):
    timed = tmp_path / "timed"
    manual = tmp_path / "manual"
    target = tmp_path / "target.md"
    target.write_text("repo: organicoverlords/p3\nscope: continue #2437 proof\n", encoding="utf-8")
    write_history(
        timed,
        sha="t1",
        population="timed",
        started_at="2026-09-09T00:03:00+03:00",
        scope="#2437 source fix",
        outcome="landed source fix",
    )
    write_history(
        manual,
        sha="m1",
        population="manual",
        started_at="2026-09-09T00:04:00+03:00",
        scope="#2437 live proof",
        outcome="capture still pending",
    )

    context = build_fleet_context(timed_root=timed, manual_root=manual, target_report=target)
    related = context["target"]["related_history"]["reports"]

    assert context["population_policy"].startswith("manual_and_timed_unified")
    assert context["history"]["population_counts"] == {"manual": 1, "timed": 1}
    assert {item["population"] for item in related} == {"manual", "timed"}


def test_fault_aggregation_detects_systemic_and_avoidable_signals():
    reports = [
        {
            "report_sha256": "a",
            "population": "timed",
            "display_label": "Aspen",
            "started_at": "2026-09-09T00:00:00+03:00",
            "repo": "p3",
            "scope": "route",
            "findings": "preflight rejected malformed PowerShell command-shape; stale wrapper was used",
            "finding_tags": ["route_problem"],
        },
        {
            "report_sha256": "b",
            "population": "manual",
            "display_label": "Manual S2",
            "started_at": "2026-09-09T00:01:00+03:00",
            "repo": "vault",
            "scope": "omen",
            "findings": "low disk admission blocked build slot until cache was reclaimed",
            "finding_tags": ["resource"],
        },
    ]
    signals = {item["family"]: item for item in aggregate_faults(reports)}
    assert signals["routing_fault"]["count"] == 1
    assert signals["avoidable_action_mistake"]["count"] == 1
    assert signals["resource_bottleneck"]["count"] == 1
    assert signals["routing_fault"]["authority"] == "report_derived_candidate_signal"


def test_regression_candidate_requires_earlier_repair_and_later_recurrence():
    reports = [
        {
            "report_sha256": "repair",
            "population": "manual",
            "display_label": "Manual",
            "started_at": "2026-09-09T00:00:00+03:00",
            "repo": "vault",
            "scope": "scheduler recovery",
            "outcome": "fixed worker self-disable recurrence and restored scheduler recovery",
        },
        {
            "report_sha256": "again",
            "population": "timed",
            "display_label": "Rowan",
            "started_at": "2026-09-09T00:10:00+03:00",
            "repo": "vault",
            "scope": "scheduler",
            "findings": "worker disabled again after bootstrap; recovery required",
        },
    ]
    candidates = regression_candidates(reports)
    assert candidates
    assert candidates[0]["signature"] == "self_disable"
    assert candidates[0]["family"] == "scheduler_or_recovery_recurrence"
    assert candidates[0]["repair"]["population"] == "manual"
    assert candidates[0]["recurrence"]["population"] == "timed"
    assert candidates[0]["authority"] == "heuristic_regression_candidate_not_proof"


def test_external_evidence_is_separate_from_report_signals(tmp_path: Path):
    timed = tmp_path / "timed"
    manual = tmp_path / "manual"
    write_history(
        timed,
        sha="t1",
        population="timed",
        started_at="2026-09-09T00:00:00+03:00",
        findings="route decision happened after local work",
        finding_tags=["route_problem"],
    )
    receipt = tmp_path / "receipt.json"
    receipt.write_text('{"route":"omen","actual":"windows"}', encoding="utf-8")

    context = build_fleet_context(
        timed_root=timed,
        manual_root=manual,
        external_evidence=[receipt],
    )

    assert context["fault_signals"][0]["authority"] == "report_derived_candidate_signal"
    assert context["external_evidence"][0]["authority"] == "external_supplied_evidence_not_worker_report"
    assert context["external_evidence"][0]["sha256"]


def test_context_output_compacts_to_reviewer_sized_artifact(tmp_path: Path):
    context = {
        "schema": "worker-review-fleet-context.v1",
        "history": {"report_count": 99, "population_counts": {"manual": 30, "timed": 69}},
        "fault_signals": [
            {"family": f"f{i}", "count": 20, "examples": [{"snippet": "x" * 2000} for _ in range(4)]}
            for i in range(8)
        ],
        "regression_candidates": [{"x": "y" * 2000} for _ in range(8)],
        "top_work_threads": [{"ref": f"p3#{i}", "latest": {"scope": "z" * 400}} for i in range(20)],
        "target": None,
        "external_evidence": [],
        "review_instructions": [],
    }
    bounded = _bounded_context(context, 12_000)
    assert len(json.dumps(bounded, separators=(",", ":"))) <= 12_000
    out = write_context(tmp_path / "context.json", bounded, max_chars=12_000)
    assert out.exists()


def test_top_threads_ignore_bare_only_refs_but_keep_explicit_named_refs():
    from tools.worker_review_fleet_context import top_work_threads
    reports = [
        {
            "report_sha256": "bare",
            "population": "timed",
            "display_label": "A",
            "started_at": "2026-09-09T00:00:00+03:00",
            "repo": "organicoverlords/p3",
            "scope": "worked on #999",
        },
        {
            "report_sha256": "named",
            "population": "manual",
            "display_label": "B",
            "started_at": "2026-09-09T00:01:00+03:00",
            "repo": "organicoverlords/p3",
            "scope": "worked on P3 #2442",
        },
    ]
    refs = [row["ref"] for row in top_work_threads(reports)]
    assert "p3#999" not in refs
    assert "p3#2442" in refs


def test_bounded_context_preserves_regression_candidates_under_pressure():
    context = {
        "schema": "worker-review-fleet-context.v1",
        "history": {"report_count": 200, "population_counts": {"manual": 100, "timed": 100}},
        "fault_signals": [
            {"family": f"f{i}", "count": 20, "examples": [{"snippet": "x" * 3000} for _ in range(4)]}
            for i in range(6)
        ],
        "regression_candidates": [
            {
                "signature": "self_disable",
                "family": "scheduler_or_recovery_recurrence",
                "authority": "heuristic_regression_candidate_not_proof",
                "repair": {"report_sha256": "r", "snippet": "r" * 1500, "work_refs": ["p3#1"]},
                "recurrence": {"report_sha256": "n", "snippet": "n" * 1500, "work_refs": ["p3#1"]},
            }
        ],
        "top_work_threads": [{"ref": f"p3#{i}", "latest": {"scope": "z" * 700}} for i in range(20)],
        "target": None,
        "external_evidence": [],
        "review_instructions": [],
    }
    bounded = _bounded_context(context, 9000)
    assert bounded["regression_candidates"]
    assert bounded["regression_candidates"][0]["signature"] == "self_disable"


def test_repair_run_is_not_itself_regression_without_explicit_recurrence():
    from tools.worker_review_fleet_context import regression_candidates
    reports = [
        {
            "report_sha256": "old",
            "population": "timed",
            "display_label": "Old",
            "started_at": "2026-09-09T00:00:00+03:00",
            "repo": "vault",
            "findings": "LOW_FREE_DISK blocked admission; fix restored disk headroom",
        },
        {
            "report_sha256": "maintenance",
            "population": "manual",
            "display_label": "Maintenance",
            "started_at": "2026-09-09T00:10:00+03:00",
            "repo": "vault",
            "outcome": "reclaimed generated cache and restored low disk headroom",
        },
    ]
    assert regression_candidates(reports) == []


def test_regression_shortlist_deduplicates_signature_before_priority():
    from tools.worker_review_fleet_context import regression_candidates
    reports = [
        {
            "report_sha256": "command-repair",
            "population": "manual",
            "display_label": "Preflight repair",
            "started_at": "2026-09-09T00:00:00+03:00",
            "repo": "ChatGPTMcpClean",
            "outcome": "preflight rejects now use rule-level prevention for command-shape failures",
        },
        {
            "report_sha256": "command-again",
            "population": "timed",
            "display_label": "Worker",
            "started_at": "2026-09-09T00:01:00+03:00",
            "repo": "p3",
            "findings": "command-shape preflight rejected the invocation again",
        },
    ]
    for index in range(12):
        reports.extend(
            [
                {
                    "report_sha256": f"disk-repair-{index}",
                    "population": "manual",
                    "display_label": "Disk repair",
                    "started_at": f"2026-09-09T00:{index + 10:02d}:00+03:00",
                    "repo": "vault",
                    "outcome": "reclaimed cache and restored low disk headroom",
                },
                {
                    "report_sha256": f"disk-again-{index}",
                    "population": "timed",
                    "display_label": "Disk worker",
                    "started_at": f"2026-09-09T00:{index + 30:02d}:00+03:00",
                    "repo": "p3",
                    "findings": "LOW_FREE_DISK blocked admission again",
                },
            ]
        )
    candidates = regression_candidates(reports, max_items=2)
    assert [item["signature"] for item in candidates] == ["command_shape", "low_disk"]


def test_related_history_excludes_target_and_future_reports(tmp_path: Path):
    from tools.worker_review_fleet_context import related_history
    target = {
        "report_sha256": "target",
        "started_at": "2026-09-09T00:10:00+03:00",
        "repo": "organicoverlords/p3",
        "scope": "P3 #2442",
    }
    reports = [
        {"report_sha256": "future", "started_at": "2026-09-09T00:11:00+03:00", "repo": "p3", "scope": "P3 #2442"},
        {"report_sha256": "target", "started_at": "2026-09-09T00:10:00+03:00", "repo": "p3", "scope": "P3 #2442"},
        {"report_sha256": "past", "started_at": "2026-09-09T00:09:00+03:00", "repo": "p3", "scope": "P3 #2442"},
    ]
    related = related_history(target, reports)
    assert [item["report_sha256"] for item in related["reports"]] == ["past"]
