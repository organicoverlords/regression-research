import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.stack_atlas import (
    BOOTSTRAP_GITHUB_CACHE_SECONDS,
    BOOTSTRAP_GITHUB_WATCH_CACHE_SECONDS,
    _bootstrap_cli_view,
    _bootstrap_github_status,
    _bootstrap_vault_status,
    build_live_bootstrap_glance,
)


class BootstrapHealthTests(unittest.TestCase):

    def test_bootstrap_cli_view_keeps_live_orientation_without_history_bulk(self):
        full = {
            "schema": "bootstrap.v1",
            "generated_at": "now",
            "bootstrap": {"status": "OK", "elapsed_ms": 50.0},
            "notable_conditions": ["disk_watch_free_66gb"],
            "pc": {
                "disk": {"status": "WATCH", "free_gb": 66.0, "reserve_25gb_ok": True, "trend": {"previous": {"lost_gb": 0.1}}, "used_gb": 400},
                "memory": {"status": "OK", "commit_headroom_gb": 40.0, "commit_used_pct": 35.0, "physical_free_pct": 20.0, "interpretation": "bulk"},
                "gpu": {"sample_status": "LIVE", "sample_age_seconds": 0.0, "utilization_pct": 3, "vram_free_mb": 4700, "vram_total_mb": 6144},
            },
            "workers": {
                "evidence_semantics": "reports_not_liveness",
                "archive_sample": {"historical_worker_ids_seen": 99},
                "manual_current": {
                    "evidence_semantics": "purpose_only",
                    "recent_running_report_count": 1,
                    "recent_running_report_count_status": "COMPLETE",
                    "recent_running_reports": [{"run_id": "r1", "scope": "current task"}],
                    "scan_truncated": True,
                    "recent_scan_cutoff_reached": True,
                },
                "attention": [],
            },
            "mcp": {"available": True, "status": "LIVE", "active_session_count": 1, "active_session_count_status": "COMPLETE", "active_sessions": [{"caller_id": "c1"}], "activity_summary": {"last_event_at": "now"}},
            "github": {"available": True, "status": "OK", "authenticated": True, "api_reachable": True, "rate_limit": {"remaining": 4900}, "cache": {"used": True}},
            "vault": {"available": True, "status": "OK", "head": "abc", "latency_ms": 20, "memory_bank_age_seconds": 10, "memory_bank_bytes": 999999},
            "mcp_known_good_freeze": {"status": "CANDIDATE_KNOWN_GOOD", "backend_commit": "deadbeef", "path": "bulk-path"},
            "paths": {"rules": "rules", "vault": "vault", "worker_reports": "reports", "p3": "p3", "mcp": "mcp", "mcp_known_good_freeze": "freeze", "tiny3d": "omit"},
            "commands": {"bootstrap": "repeat boilerplate"},
            "memory_overview": {"eligible_entries": 999, "projects": ["historical bulk"]},
            "recent_memory_titles": [{"title": "historical bulk"}],
        }
        compact = _bootstrap_cli_view(full)
        self.assertEqual(compact["workers"]["manual_current"]["recent_running_reports"][0]["scope"], "current task")
        self.assertEqual(compact["mcp"]["active_session_count"], 1)
        self.assertEqual(compact["github"]["status"], "OK")
        self.assertEqual(compact["mcp_known_good_freeze"]["status"], "CANDIDATE_KNOWN_GOOD")
        self.assertNotIn("commands", compact)
        self.assertNotIn("memory_overview", compact)
        self.assertNotIn("recent_memory_titles", compact)
        self.assertNotIn("archive_sample", compact["workers"])
        self.assertLess(len(json.dumps(compact, separators=(",", ":"))), 5000)

    def test_github_health_reports_rate_limit_without_listing_repo_state(self):
        api = subprocess.CompletedProcess(
            ["gh", "api", "rate_limit"],
            0,
            json.dumps({"resources": {"core": {"limit": 5000, "remaining": 4200, "used": 800, "reset": 1788640000}}}),
            "",
        )
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"LOCALAPPDATA": tmp}), patch(
            "tools.stack_atlas.shutil.which", return_value="gh"
        ), patch("tools.stack_atlas.subprocess.run", return_value=api) as run:
            status = _bootstrap_github_status()
        self.assertEqual(status["status"], "OK")
        self.assertTrue(status["authenticated"])
        self.assertTrue(status["api_reachable"])
        self.assertEqual(status["rate_limit"]["remaining"], 4200)
        self.assertEqual(status["cache"]["max_age_seconds"], BOOTSTRAP_GITHUB_CACHE_SECONDS)
        self.assertEqual(run.call_count, 1)
        command = run.call_args.args[0]
        self.assertEqual(command, ["gh", "api", "rate_limit"])
        self.assertNotIn("issue", " ".join(command))
        self.assertNotIn("pr", " ".join(command))

    def test_github_watch_cache_is_shorter_than_healthy_cache(self):
        api = subprocess.CompletedProcess(
            ["gh", "api", "rate_limit"],
            0,
            json.dumps({"resources": {"core": {"limit": 5000, "remaining": 100, "used": 4900, "reset": 1788640000}}}),
            "",
        )
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"LOCALAPPDATA": tmp}), patch(
            "tools.stack_atlas.shutil.which", return_value="gh"
        ), patch("tools.stack_atlas.subprocess.run", return_value=api):
            status = _bootstrap_github_status()
        self.assertEqual(status["status"], "WATCH")
        self.assertEqual(status["cache"]["max_age_seconds"], BOOTSTRAP_GITHUB_WATCH_CACHE_SECONDS)
        self.assertLess(BOOTSTRAP_GITHUB_WATCH_CACHE_SECONDS, BOOTSTRAP_GITHUB_CACHE_SECONDS)

    def test_vault_health_is_bounded_to_local_repo_and_memory_tail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tools").mkdir()
            (root / "tools" / "stack_atlas.py").write_text("# test\n", encoding="utf-8")
            (root / "memory").mkdir()
            (root / "memory" / "memory-bank.jsonl").write_text('{"id":"m1"}\n', encoding="utf-8")
            git = subprocess.CompletedProcess(["git"], 0, "true\nabc123\n", "")
            with patch("tools.stack_atlas.ROOT", root), patch("tools.stack_atlas.shutil.which", return_value="git"), patch(
                "tools.stack_atlas.subprocess.run", return_value=git
            ) as run:
                status = _bootstrap_vault_status()
        self.assertEqual(status["status"], "OK")
        self.assertTrue(status["memory_bank_tail_readable"])
        self.assertEqual(status["head"], "abc123")
        command = run.call_args.args[0]
        self.assertEqual(command[-3:], ["rev-parse", "--is-inside-work-tree", "HEAD"])

    def test_bootstrap_surfaces_component_health_and_notable_conditions(self):
        with patch("tools.stack_atlas._bootstrap_pc_status", return_value={"disk": {"status": "OK", "trend": {}}, "memory": {"status": "OK"}}), patch(
            "tools.stack_atlas._bootstrap_worker_status", return_value={"available": True, "attention": [], "stale_reports": [], "manual_current": {}}
        ), patch("tools.stack_atlas._bootstrap_mcp_status", return_value={"available": True, "status": "LIVE"}), patch(
            "tools.stack_atlas._bootstrap_memory_overview", return_value={"recent": []}
        ), patch("tools.stack_atlas._bootstrap_vault_status", return_value={"available": True, "status": "OK"}), patch(
            "tools.stack_atlas._bootstrap_github_status", return_value={"available": True, "status": "WATCH"}
        ), patch("tools.stack_atlas._bootstrap_mcp_known_good_freeze", return_value={"available": True}):
            glance = build_live_bootstrap_glance()
        self.assertEqual(glance["bootstrap"]["status"], "DEGRADED")
        self.assertEqual(glance["bootstrap"]["component_statuses"], {"mcp": "OK", "vault": "OK", "github": "WATCH"})
        self.assertIn("github_watch", glance["notable_conditions"])
        self.assertIn("mcp", glance)
        self.assertIn("vault", glance)
        self.assertIn("github", glance)


if __name__ == "__main__":
    unittest.main()
