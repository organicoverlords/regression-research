import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tools.stack_atlas as atlas


class McpBootstrapIdentitySemanticsTests(unittest.TestCase):
    def test_live_mcp_status_still_probes_canonical_backend_identity(self):
        live_status = {
            "available": True,
            "status": "LIVE",
            "active_session_count": 3,
            "active_session_count_status": "LOWER_BOUND",
            "active_sessions": [],
            "workspace_counts": {"MCP": 1},
        }
        backend_health = {
            "available": True,
            "status": "LIVE",
            "backend_generation": "backend-current",
            "pid": 4242,
            "live_process_count": 0,
            "latency_ms": 1.2,
        }
        with (
            patch("tools.stack_atlas.build_live_swarm_snapshot", return_value={"available": True}),
            patch("tools.stack_atlas._bootstrap_mcp_from_live_swarm", return_value=live_status),
            patch("tools.stack_atlas._bootstrap_mcp_backend_health", return_value=backend_health) as health_probe,
        ):
            status = atlas._bootstrap_mcp_status()

        health_probe.assert_called_once_with()
        self.assertEqual(status["service_health"]["backend_generation"], "backend-current")
        self.assertEqual(status["service_health"]["pid"], 4242)

    def test_recovery_projection_cannot_masquerade_as_live_backend_identity(self):
        recovery = {
            "schema": "mcp-recovery-state.v1",
            "deployment": {
                "id": "deployment:recovery-target",
                "generation": "backend-recovery-target",
            },
            "recovery_target": {
                "deployment_id": "deployment:recovery-target",
                "selected_at": "2026-09-06T17:46:18+03:00",
                "policy": {"restore_first_on_regression": True},
                "recovery_lanes": {},
            },
            "conditions": [],
            "evidence": {},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mcp-recovery-state.json"
            path.write_text(json.dumps(recovery), encoding="utf-8")
            with patch.object(atlas, "MCP_RECOVERY_STATE_PATH", path):
                projected = atlas._bootstrap_mcp_recovery_state()

        self.assertEqual(
            projected["recovery_target_deployment_id"], "deployment:recovery-target"
        )
        self.assertEqual(
            projected["recovery_target_generation"], "backend-recovery-target"
        )
        self.assertNotIn("deployment_id", projected)
        self.assertNotIn("backend_generation", projected)
        self.assertEqual(
            projected["authority"],
            "recovery_target_not_live_serving_identity",
        )


if __name__ == "__main__":
    unittest.main()
