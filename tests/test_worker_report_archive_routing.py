from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


def test_archive_cli_routes_current_snapshot_to_canonical_history(tmp_path: Path) -> None:
    reports = tmp_path / "worker-reports"
    current = reports / "current"
    current.mkdir(parents=True)
    report = current / "worker-id.md"
    raw = (
        "automation_id: worker-id\n"
        "display_label: TestWorker\n"
        "started_at: 2026-09-03T21:00:00+03:00\n"
        "last_activity_at: 2026-09-03T21:05:00+03:00\n"
        "repo: p3\n"
        "scope: p3#test\n"
        "state: WAITING\n"
        "outcome: WAITING_EXTERNAL\n"
        "mutation: none\n"
        "validation: archive routing fixture\n"
        "remaining_gate: external wait\n"
        "stop_reason: WAITING_EXTERNAL\n"
    ).encode("utf-8")
    report.write_bytes(raw)

    script = Path(__file__).resolve().parents[1] / "tools" / "worker_report_history.py"
    result = subprocess.run(
        [sys.executable, str(script), "archive", "--report", str(report)],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    digest = hashlib.sha256(raw).hexdigest()

    assert payload["ok"] is True
    archived = Path(payload["path"]).resolve()
    canonical_history = (reports / "history").resolve()
    assert archived.is_relative_to(canonical_history)
    assert archived.read_bytes() == raw
    metrics_path = reports / "metrics.json"
    assert metrics_path.exists()
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert metrics["schema"] == "worker-report-metrics.v1"
    assert metrics["runs_with_duration"] == 0
    assert metrics["average_duration_minutes"] is None
    assert metrics["average_target_utilization_pct"] is None
    assert metrics["duration_filter"]["require_machine_observed_start"] is True
    assert metrics["duration_filter"]["excluded_unmeasured_count"] == 1
    latest = metrics["latest_reports"][0]
    assert latest["automation_id"] == "worker-id"
    assert latest["duration_minutes"] is None
    assert latest["timing_evidence"] == "UNMEASURED_NO_MACHINE_START"
    assert "early_stop" not in latest
    assert "tool_failures_total" not in latest
    assert not archived.is_relative_to((current / "history").resolve())
    assert not (current / "history").exists()
