import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import tools.process_duration_baselines as baselines


class ProcessDurationBaselinesTests(unittest.TestCase):
    def test_default_output_is_runtime_state_not_repo_checkout(self):
        repo_root = Path(baselines.__file__).resolve().parents[1]
        self.assertFalse(baselines.DEFAULT_OUTPUT.is_relative_to(repo_root))
        self.assertEqual(baselines.DEFAULT_OUTPUT.name, "process-duration-baselines.json")

    def test_normalize_recognizes_supported_jobs_and_rejects_diagnostics(self):
        family, key = baselines.normalize("pytest tests/test_memory_bank.py -q", r"C:\\work\\vault")
        self.assertEqual(family, "pytest")
        self.assertIn("test_memory_bank.py", key)
        self.assertEqual(baselines.normalize("rg -n pytest tools", r"C:\\work\\vault")[0], "other")

    def test_summarize_reports_median_p90_and_trend(self):
        samples = []
        start = datetime(2026, 9, 9, tzinfo=timezone.utc)
        for index, duration in enumerate((10.0, 12.0, 20.0, 24.0)):
            samples.append({
                "finished_at": (start + timedelta(minutes=index)).isoformat().replace("+00:00", "Z"),
                "duration_seconds": duration,
            })
        summary = baselines.summarize(samples)
        self.assertEqual(summary["samples"], 4)
        self.assertEqual(summary["median_seconds"], 16.0)
        self.assertEqual(summary["p90_seconds"], 24.0)
        self.assertEqual(summary["trend"], "rising")

    def test_main_refresh_is_bounded_to_hot_receipts_and_writes_snapshot(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            receipts = root / "receipts"
            receipts.mkdir()
            output = root / "baseline.json"
            now = datetime.now(timezone.utc)
            for index, seconds in enumerate((7, 9)):
                started = now - timedelta(minutes=5-index, seconds=seconds)
                finished = started + timedelta(seconds=seconds)
                payload = {
                    "process_id": f"p{index}",
                    "command": "pytest tests/test_memory_bank.py -q",
                    "cwd": str(root / "vault"),
                    "started_at": started.isoformat().replace("+00:00", "Z"),
                    "finished_at": finished.isoformat().replace("+00:00", "Z"),
                    "exit_code": 0,
                }
                (receipts / f"p{index}.json").write_text(json.dumps(payload), encoding="utf-8")
            argv = [
                "process_duration_baselines.py",
                "--receipt-root", str(receipts),
                "--output", str(output),
                "--lookback-hours", "24",
            ]
            with patch("sys.argv", argv):
                self.assertEqual(baselines.main(), 0)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["hot_receipts_seen"], 2)
            self.assertEqual(report["tracked_samples"], 2)
            self.assertIn("pytest", report["families"])
            self.assertLessEqual(len(report["sample_cache"]), baselines.MAX_SAMPLES_PER_JOB)


if __name__ == "__main__":
    unittest.main()
