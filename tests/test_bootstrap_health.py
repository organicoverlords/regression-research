import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.stack_atlas import (
    _bootstrap_cache_read_any,
    _bootstrap_cache_refresh_view,
    _bootstrap_cache_write,
    _bootstrap_github_status,
    _bootstrap_try_refresh_lease,
    _bootstrap_vault_status,
    build_live_bootstrap_glance,
)


class BootstrapHealthTests(unittest.TestCase):

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
        self.assertEqual(run.call_count, 1)
        command = run.call_args.args[0]
        self.assertEqual(command, ["gh", "api", "rate_limit"])
        self.assertNotIn("issue", " ".join(command))
        self.assertNotIn("pr", " ".join(command))

    def test_expired_cache_serves_stale_to_followers_while_one_refresher_is_elected(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"LOCALAPPDATA": tmp}):
            _bootstrap_cache_write("shared.json", {"value": 7})
            cache_path = Path(tmp) / "StackAtlas" / "bootstrap-cache" / "shared.json"
            old = cache_path.stat().st_mtime - 10.0
            os.utime(cache_path, (old, old))
            payload, age = _bootstrap_cache_read_any("shared.json")
            first, first_stale = _bootstrap_cache_refresh_view(
                "shared.json", payload, age, max_age_seconds=1.0, lease_seconds=4.0
            )
            self.assertIsNone(first)
            self.assertFalse(first_stale)
            second, second_stale = _bootstrap_cache_refresh_view(
                "shared.json", payload, age, max_age_seconds=1.0, lease_seconds=4.0
            )
            self.assertEqual(second, {"value": 7})
            self.assertTrue(second_stale)

    def test_github_expiry_follower_reuses_stale_health_without_duplicate_probe(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"LOCALAPPDATA": tmp}):
            _bootstrap_cache_write("github-status.json", {
                "available": True, "status": "OK", "cli_available": True,
                "authenticated": True, "api_reachable": True,
                "rate_limit": {"limit": 5000, "remaining": 4000, "used": 1000},
            })
            cache_path = Path(tmp) / "StackAtlas" / "bootstrap-cache" / "github-status.json"
            old = cache_path.stat().st_mtime - 61.0
            os.utime(cache_path, (old, old))
            self.assertTrue(_bootstrap_try_refresh_lease("github-status.json", 4.0))
            with patch("tools.stack_atlas.subprocess.run", side_effect=AssertionError("duplicate GitHub probe")):
                status = _bootstrap_github_status()
            self.assertEqual(status["status"], "OK")
            self.assertTrue(status["cache"]["used"])
            self.assertTrue(status["cache"]["stale_while_refresh"])
            self.assertGreater(status["cache"]["age_seconds"], 60.0)

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
        ), patch("tools.stack_atlas._bootstrap_source_freshness", return_value={"available": True, "attention_required": False}), patch(
            "tools.stack_atlas._bootstrap_mcp_recovery_state", return_value={"available": True}
        ):
            glance = build_live_bootstrap_glance()
        self.assertEqual(glance["bootstrap"]["status"], "DEGRADED")
        self.assertEqual(glance["bootstrap"]["component_statuses"], {"mcp": "OK", "vault": "OK", "github": "WATCH"})
        self.assertIn("github_watch", glance["notable_conditions"])
        self.assertIn("mcp", glance)
        self.assertIn("vault", glance)
        self.assertIn("github", glance)


if __name__ == "__main__":
    unittest.main()
