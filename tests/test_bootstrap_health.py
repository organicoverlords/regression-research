import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.stack_atlas import (
    _bootstrap_github_status,
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
