import unittest

from tools.live_swarm_search import search_live_swarm


class LiveSwarmSearchTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = {
            "schema": "live-swarm.v1",
            "lanes": [
                {
                    "lane_id": "busy:chatgpt:manual-mcp-outputschema-7f3a",
                    "basis": "busy_owner",
                    "workspace": None,
                    "worktree": None,
                    "callers": [],
                    "busy": [
                        {
                            "owner": "ChatGPT:manual-mcp-outputschema-7f3a",
                            "scopes": [
                                "mcp_minimal_clone:scheduled-task:McpV4FrozenIssue281Main3036",
                                "mcp_minimal_clone:local-home-direct-caddy",
                            ],
                            "checkpoint": "prepare stable side generation second",
                            "last_update_age_seconds": 41.6,
                        }
                    ],
                },
                {
                    "lane_id": "wt:mcp",
                    "basis": "worktree",
                    "workspace": "MCP",
                    "worktree": {
                        "branch": "fix/242-stall-watchdog",
                        "path": "C:/work/ChatGPTMcpClean",
                    },
                    "busy": [],
                    "callers": [
                        {
                            "caller_id": "caller_watchdog",
                            "command": "Write-Output PEER_OUTPUT_SCHEMA_PROBE",
                            "workspace": "MCP",
                            "worktree": {
                                "branch": "fix/242-stall-watchdog",
                                "path": "C:/work/ChatGPTMcpClean",
                            },
                            "last_activity_age_seconds": 12.0,
                        }
                    ],
                },
            ],
            "transport_sources": [
                {
                    "instance": "home-direct-7a457c6-library-work-canary",
                    "local_port": 3045,
                    "server_pid": 24136,
                    "latest_event_at": "2026-09-11T23:25:06Z",
                    "activity_window_complete": True,
                    "observation_window_complete": True,
                }
            ],
        }

    def test_checkpoint_and_scope_are_searchable_handoff_context(self):
        result = search_live_swarm(self.snapshot, "stable generation")[0]
        self.assertEqual(result["kind"], "busy_handoff")
        self.assertEqual(result["owner"], "ChatGPT:manual-mcp-outputschema-7f3a")
        self.assertEqual(result["checkpoint"], "prepare stable side generation second")
        self.assertIn("McpV4FrozenIssue281Main3036", " ".join(result["scopes"]))

        by_scope = search_live_swarm(self.snapshot, "Issue281Main3036")[0]
        self.assertEqual(by_scope["owner"], "ChatGPT:manual-mcp-outputschema-7f3a")

    def test_active_branch_and_activity_are_searchable(self):
        result = search_live_swarm(self.snapshot, "stall watchdog")[0]
        self.assertEqual(result["kind"], "caller_activity")
        self.assertEqual(result["match_semantics"], "query_matched_execution_surface_or_identity_not_activity_command")
        self.assertIn("branch", result["matched_fields"])
        self.assertEqual(result["branch"], "fix/242-stall-watchdog")
        self.assertEqual(result["caller_id"], "caller_watchdog")

        probe = search_live_swarm(self.snapshot, "output schema probe")[0]
        self.assertEqual(probe["caller_id"], "caller_watchdog")
        self.assertEqual(probe["match_semantics"], "query_matched_activity_command")
        self.assertIn("activity", probe["matched_fields"])

    def test_multi_term_query_rejects_single_generic_term_noise(self):
        noisy = search_live_swarm(self.snapshot, "issue 301 library file transfer", limit=5)
        self.assertEqual(noisy, [])
        exact = search_live_swarm(self.snapshot, "stable generation", limit=5)
        self.assertEqual(exact[0]["kind"], "busy_handoff")
        self.assertEqual(set(exact[0]["matched_terms"]), {"stable", "generation"})
        caller = search_live_swarm(self.snapshot, "stall watchdog", limit=5)
        self.assertEqual(caller[0]["kind"], "caller_activity")
        self.assertEqual(set(caller[0]["matched_terms"]), {"stall", "watchdog"})

    def test_numeric_terms_are_required_and_transport_sources_are_searchable(self):
        self.assertEqual(search_live_swarm(self.snapshot, "issue 301 library file transfer", limit=5), [])
        canary = search_live_swarm(self.snapshot, "library canary", limit=5)[0]
        self.assertEqual(canary["kind"], "transport_source")
        self.assertEqual(canary["authority"], "LIVE_MCP_TRANSPORT_SOURCE_EVIDENCE")
        self.assertEqual(canary["instance"], "home-direct-7a457c6-library-work-canary")
        self.assertEqual(canary["match_semantics"], "query_matched_transport_source_identity")
        self.assertEqual(set(canary["matched_fields"]), {"instance"})
        self.assertEqual(set(canary["matched_terms"]), {"library", "canary"})
        by_port = search_live_swarm(self.snapshot, "port 3045", limit=5)[0]
        self.assertEqual(by_port["kind"], "transport_source")
        self.assertEqual(by_port["local_port"], 3045)

    def test_semantic_concepts_can_match_live_fields_without_literal_query_synonym(self):
        self.snapshot["lanes"][0]["busy"][0]["checkpoint"] = "MCP image handoff ready"
        hits = search_live_swarm(
            self.snapshot,
            "MCP kuvahommeli",
            query_concepts=[{"mcp"}, {"image", "images", "visual", "kuvahommeli"}],
        )
        self.assertEqual(hits[0]["kind"], "busy_handoff")
        self.assertIn("image", hits[0]["matched_terms"])
        self.assertIn("mcp", hits[0]["matched_terms"])
        self.assertIn("checkpoint", hits[0]["matched_fields"])

    def test_search_is_bounded_and_uses_existing_snapshot_only(self):
        self.assertEqual(search_live_swarm(self.snapshot, ""), [])
        self.assertEqual(search_live_swarm(self.snapshot, "missing-term"), [])
        self.assertEqual(len(search_live_swarm(self.snapshot, "mcp", limit=1)), 1)
        hits = search_live_swarm(self.snapshot, "mcp", limit=5)
        self.assertEqual({item["authority"] for item in hits}, {"BUSY_COORDINATION_EVIDENCE", "LIVE_MCP_RUNTIME_EVIDENCE"})
        busy = next(item for item in hits if item["kind"] == "busy_handoff")
        caller = next(item for item in hits if item["kind"] == "caller_activity")
        self.assertEqual(busy["liveness_semantics"], "not_worker_liveness_or_progress")
        self.assertEqual(caller["liveness_semantics"], "recent_caller_activity_within_snapshot_window")


if __name__ == "__main__":
    unittest.main()
