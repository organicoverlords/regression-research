import json
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from tools.stack_atlas import (
    ATLAS_CONTRACT,
    blast_radius,
    build_bootstrap_atlas,
    build_live_bootstrap_glance,
    classify_process,
    component_details,
    find_features,
    full_inventory,
    production_change_gate,
    render_manual,
    _bootstrap_pc_status,
    _bootstrap_worker_status,
    _bootstrap_disk_trend,
    _read_jsonl_tail,
    _read_jsonl_window,
    _cwd_uses_worktree,
)

ROOT = Path(__file__).resolve().parents[1]


class StackAtlasTests(unittest.TestCase):
    def test_session_cwd_worktree_match_is_one_way(self):
        worktree = r"C:\Users\Lauri\AppData\Local\Temp\p3-941-control-hints"
        self.assertTrue(_cwd_uses_worktree(worktree, worktree))
        self.assertTrue(_cwd_uses_worktree(worktree + r"\Source\LaneWar", worktree))
        self.assertFalse(_cwd_uses_worktree(r"C:\Users\Lauri", worktree))
        self.assertFalse(_cwd_uses_worktree(r"C:\Users\Lauri\AppData\Local\Temp\other-worktree", worktree))

    def test_live_bootstrap_displays_machine_workers_and_active_sessions(self):
        sample_workers = {
            "available": True,
            "latest_per_worker": [{"display_label": "Aspen", "duration_minutes": 5.0, "target_minutes": 24.0, "target_utilization_pct": 20.8, "classification": "SEVERELY_PREMATURE", "age_minutes": 10.0}],
            "attention": [{"worker": "Aspen", "duration_minutes": 5.0, "target_minutes": 24.0, "utilization_pct": 20.8, "classification": "SEVERELY_PREMATURE", "age_minutes": 10.0}],
        }
        with patch("tools.stack_atlas._bootstrap_worker_status", return_value=sample_workers):
            glance = build_live_bootstrap_glance()
        payload = json.dumps(glance, separators=(",", ":")).encode("utf-8")
        self.assertLess(len(payload), 12000)
        self.assertIn("trend", glance["pc"]["disk"])
        memory = glance["pc"]["memory"]
        self.assertIn("commit_headroom_gb", memory)
        self.assertEqual(glance["mcp"]["active_session_count"], len(glance["mcp"]["active_sessions"]))
        for session in glance["mcp"]["active_sessions"]:
            self.assertIn("caller_id", session)
            self.assertIn("cwd", session)
            self.assertIn("workspace", session)
            self.assertIn("busy_titles", session)
            self.assertLessEqual(session["activity_age_seconds"], 300)
        self.assertIn("notable_conditions", glance)
        self.assertIn("worker_report_Aspen_severely_premature_5.0m_of_24.0m", glance["notable_conditions"])
        self.assertNotIn("worker_Aspen_severely_premature_5.0m_of_24.0m", glance["notable_conditions"])
        self.assertIn("latest_per_worker", glance["workers"])
        self.assertNotIn("behavior", glance)
        self.assertEqual(glance["paths"]["rules"], r"C:\Users\Lauri\.agents\RULES.md")
        self.assertEqual(glance["paths"]["agents"], r"C:\Users\Lauri\.agents\AGENTS.md")
        self.assertNotIn("mcp_hour", glance["commands"])
        self.assertIn("production_change_gate", glance["commands"])
        self.assertNotIn("connector_reliability.py", json.dumps(glance))

    def test_production_change_gate_blocks_go_fix_style_implicit_authorization(self):
        mcp = {
            "available": True, "status": "LIVE", "active_session_count": 20,
            "active_session_count_status": "COMPLETE", "active_sessions": [{"caller_id": "c1"}],
        }
        busy = {"available": True, "claim": {"actor": "ChatGPT:test"}, "job": None}
        gate = production_change_gate(
            "mcpv3", actor="ChatGPT:test", busy_scope="mcp-production:vps-caddy-routing",
            explicit_user_authorization=False, independent_rollback_verified=True, offpath_proof_verified=True,
            mcp_status=mcp, busy_status=busy,
        )
        self.assertEqual(gate["verdict"], "BLOCK")
        self.assertIn("missing_explicit_live_production_authorization", gate["reasons"])
        self.assertTrue(gate["semantics"]["go_continue_fix_are_not_production_authorization"])
        self.assertEqual(gate["live_dependencies"]["mcp"]["active_session_count"], 20)

    def test_production_change_gate_blocks_without_independent_rollback(self):
        mcp = {
            "available": True, "status": "LIVE", "active_session_count": 3,
            "active_session_count_status": "COMPLETE", "active_sessions": [],
        }
        busy = {"available": True, "claim": {"actor": "ChatGPT:test"}, "job": None}
        gate = production_change_gate(
            "vps_edge_ingress", actor="ChatGPT:test", busy_scope="mcp-vps:/etc/caddy/Caddyfile",
            explicit_user_authorization=True, independent_rollback_verified=False, offpath_proof_verified=True,
            mcp_status=mcp, busy_status=busy,
        )
        self.assertEqual(gate["verdict"], "BLOCK")
        self.assertIn("independent_rollback_control_route_not_verified", gate["reasons"])

    def test_production_change_gate_blocks_foreign_busy_claim(self):
        mcp = {
            "available": True, "status": "LIVE", "active_session_count": 1,
            "active_session_count_status": "COMPLETE", "active_sessions": [],
        }
        busy = {"available": True, "claim": {"actor": "ChatGPT:other"}, "job": None}
        gate = production_change_gate(
            "mcp_front_door", actor="ChatGPT:test", busy_scope="mcp-production:front-door",
            explicit_user_authorization=True, independent_rollback_verified=True, offpath_proof_verified=True,
            mcp_status=mcp, busy_status=busy,
        )
        self.assertEqual(gate["verdict"], "BLOCK")
        self.assertIn("busy_scope_claimed_by_other_actor", gate["reasons"])

    def test_production_change_gate_passes_only_with_complete_evidence_and_reports_dependents(self):
        mcp = {
            "available": True, "status": "LIVE", "active_session_count": 20,
            "active_session_count_status": "COMPLETE", "active_sessions": [{"caller_id": "c1"}, {"caller_id": "c2"}],
        }
        busy = {"available": True, "claim": {"actor": "ChatGPT:test"}, "job": None}
        gate = production_change_gate(
            "mcpv3", actor="ChatGPT:test", busy_scope="mcp-production:vps-caddy-routing",
            explicit_user_authorization=True, independent_rollback_verified=True, offpath_proof_verified=True,
            mcp_status=mcp, busy_status=busy,
        )
        self.assertEqual(gate["verdict"], "PASS")
        self.assertEqual(gate["reasons"], [])
        self.assertIn("active_mcp_dependents_present", gate["warnings"])
        self.assertEqual(gate["live_dependencies"]["mcp"]["active_session_count"], 20)

    def test_worker_status_reads_runtime_history_from_live_root_not_source_root(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source_root = root / "source"
            live_root = root / "live"
            source_root.mkdir()
            history_root = live_root / "worker-reports" / "history"
            history_root.mkdir(parents=True)
            record = {
                "automation_id": "worker-1",
                "display_label": "Repo Worker Test",
                "finished_at": "2026-09-05T02:00:00+03:00",
                "duration_minutes": 24.0,
                "target_run_minutes": 24.0,
                "target_utilization_pct": 100.0,
            }
            with patch("tools.stack_atlas.ROOT", source_root), patch("tools.stack_atlas.ATLAS_LIVE_ROOT", live_root), patch("tools.worker_report_history.load_history_metadata", return_value=[record]) as load_history:
                workers = _bootstrap_worker_status()
            load_history.assert_called_once_with(history_root)
            self.assertTrue(workers["available"])
            self.assertEqual(workers["latest_per_worker"][0]["automation_id"], "worker-1")

    def test_stale_worker_archive_is_not_current_liveness_attention(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "worker-reports" / "history").mkdir(parents=True)
            now = datetime.now(timezone.utc)
            records = [
                {
                    "automation_id": "fir", "display_label": "Fir",
                    "finished_at": (now - timedelta(minutes=120)).isoformat(),
                    "duration_minutes": 3.68, "target_run_minutes": 24.0, "target_utilization_pct": 15.3,
                },
                {
                    "automation_id": "fir", "display_label": "Fir impossible future archive",
                    "finished_at": (now + timedelta(minutes=20)).isoformat(),
                    "archived_at": now.isoformat(),
                    "duration_minutes": 20.42, "target_run_minutes": 24.0, "target_utilization_pct": 85.1,
                },
                {
                    "automation_id": "hazel", "display_label": "Hazel",
                    "finished_at": (now - timedelta(minutes=10)).isoformat(),
                    "duration_minutes": 10.0, "target_run_minutes": 24.0, "target_utilization_pct": 41.7,
                },
            ]
            with patch("tools.stack_atlas.ROOT", root), patch("tools.worker_report_history.load_history_metadata", return_value=records):
                workers = _bootstrap_worker_status()
        self.assertEqual(workers["evidence_semantics"], "archived_run_quality_only_not_current_worker_liveness")
        self.assertEqual(workers["stale_after_minutes"], 90.0)
        self.assertEqual([item["worker"] for item in workers["attention"]], ["Hazel"])
        self.assertEqual(workers["stale_reports"], [{"worker": "Fir", "age_minutes": 120.0, "last_archived_classification": "SEVERELY_PREMATURE"}])
        self.assertEqual(workers["fleet"]["stale_report_count"], 1)
        fir = next(item for item in workers["latest_per_worker"] if item["display_label"] == "Fir")
        self.assertEqual(fir["report_freshness"], "STALE")

    def test_impossible_worker_archive_does_not_replace_latest_valid_run(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "worker-reports" / "history").mkdir(parents=True)
            now = datetime.now(timezone.utc)
            valid_finished = now - timedelta(minutes=30)
            valid_archived = valid_finished + timedelta(seconds=5)
            impossible_archived = now - timedelta(minutes=10)
            impossible_finished = impossible_archived + timedelta(minutes=20)
            records = [
                {
                    "automation_id": "fir", "display_label": "Fir",
                    "finished_at": valid_finished.isoformat(), "archived_at": valid_archived.isoformat(),
                    "duration_minutes": 5.0, "target_run_minutes": 24.0, "target_utilization_pct": 20.8,
                },
                {
                    "automation_id": "fir", "display_label": "Fir",
                    "finished_at": impossible_finished.isoformat(), "archived_at": impossible_archived.isoformat(),
                    "duration_minutes": 20.0, "target_run_minutes": 24.0, "target_utilization_pct": 83.3,
                },
            ]
            with patch("tools.stack_atlas.ROOT", root), patch("tools.worker_report_history.load_history_metadata", return_value=records):
                workers = _bootstrap_worker_status()
        self.assertEqual(workers["fleet"]["on_target_count"], 0)
        self.assertEqual(workers["fleet"]["short_or_worse_count"], 1)
        self.assertEqual(len(workers["latest_per_worker"]), 1)
        fir = workers["latest_per_worker"][0]
        self.assertEqual(fir["display_label"], "Fir")
        self.assertEqual(fir["finished_at"], valid_finished.isoformat())
        self.assertEqual(fir["classification"], "SEVERELY_PREMATURE")

    def test_disk_trend_can_report_approx_24h_loss(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "observations.jsonl"
            now = datetime.now(timezone.utc)
            rows = [
                {"at": (now - timedelta(hours=24)).isoformat(), "free_gb": 115.0},
                {"at": (now - timedelta(hours=2)).isoformat(), "free_gb": 70.0},
            ]
            path.write_text("\n".join(json.dumps(x) for x in rows) + "\n", encoding="utf-8")
            with patch("tools.stack_atlas.BOOTSTRAP_OBSERVATION_PATH", path):
                trend = _bootstrap_disk_trend(55.0)
            self.assertEqual(trend["previous"]["lost_gb"], 15.0)
            self.assertEqual(trend["approx_24h"]["lost_gb"], 60.0)

    def test_mcp_transport_tail_does_not_parse_historical_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "transport.jsonl"
            historical = [json.dumps({"event": "historical", "n": i}) for i in range(20000)]
            recent = [json.dumps({"event": "recent", "n": i}) for i in range(400)]
            path.write_text("\n".join(historical + recent) + "\n", encoding="utf-8")
            real_loads = json.loads
            with patch("tools.stack_atlas.json.loads", wraps=real_loads) as loads:
                rows = _read_jsonl_tail(path, 400)
            self.assertEqual(len(rows), 400)
            self.assertTrue(all(row["event"] == "recent" for row in rows))
            self.assertEqual(loads.call_count, 400)

    def test_mcp_activity_window_marks_bounded_truncation_explicitly(self):
        from datetime import datetime, timedelta, timezone

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "transport.jsonl"
            now = datetime.now(timezone.utc)
            old = {"event": "process_read", "at": (now - timedelta(minutes=10)).isoformat(), "caller_id": "caller_old"}
            recent = [
                {"event": "process_read", "at": now.isoformat(), "caller_id": f"caller_{i}", "padding": "x" * 200}
                for i in range(40)
            ]
            path.write_text("\n".join(json.dumps(x) for x in [old, *recent]) + "\n", encoding="utf-8")
            rows, complete, sample_bytes = _read_jsonl_window(
                path,
                now - timedelta(minutes=5),
                max_bytes=1024,
                chunk_bytes=256,
            )
            self.assertFalse(complete)
            self.assertLessEqual(sample_bytes, 1024)
            self.assertTrue(rows)
            self.assertTrue(all(row["caller_id"] != "caller_old" for row in rows))

    def test_mcp_status_reports_more_than_eight_callers_across_full_activity_window(self):
        from datetime import datetime, timedelta, timezone
        import os
        import subprocess
        from tools.stack_atlas import _bootstrap_mcp_status

        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp)
            root = local / "ChatGPTMcpClean" / "minimal-connectors"
            clone = root / "clone-a"
            clone.mkdir(parents=True)
            now = datetime.now(timezone.utc)
            transport = []
            for i in range(12):
                transport.append({
                    "event": "process_started",
                    "at": (now - timedelta(seconds=240 - i)).isoformat().replace("+00:00", "Z"),
                    "caller_id": f"caller_{i:02d}",
                    "owner_caller_id": f"caller_{i:02d}",
                    "process_id": f"process-{i:02d}",
                    "pid": 1000 + i,
                    "cwd": rf"C:\\work\\{i:02d}",
                })
            for i in range(600):
                transport.append({
                    "event": "process_read",
                    "at": (now - timedelta(seconds=10) + timedelta(milliseconds=i)).isoformat().replace("+00:00", "Z"),
                    "caller_id": "caller_00",
                    "owner_caller_id": "caller_00",
                    "process_id": "process-00",
                    "pid": 1000,
                    "running": True,
                })
            (clone / "transport.jsonl").write_text("\n".join(json.dumps(x) for x in transport) + "\n", encoding="utf-8")
            busy = subprocess.CompletedProcess([], 0, stdout=json.dumps({"claims": []}), stderr="")
            with patch.dict(os.environ, {"LOCALAPPDATA": str(local)}), \
                 patch("tools.stack_atlas.subprocess.run", return_value=busy):
                status = _bootstrap_mcp_status()
            self.assertEqual(status["active_session_count"], 12)
            self.assertEqual(status["active_session_count_status"], "COMPLETE")
            self.assertTrue(status["activity_summary"]["activity_window_complete"])
            self.assertGreater(status["activity_summary"]["sample_rows"], 400)

    def test_mcp_status_reads_only_tail_referenced_receipts(self):
        from datetime import datetime, timezone
        import os
        import subprocess
        from tools.stack_atlas import _bootstrap_mcp_status

        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp)
            root = local / "ChatGPTMcpClean" / "minimal-connectors"
            clone = root / "clone-a"
            receipts = root / "shared-process-receipts"
            clone.mkdir(parents=True)
            receipts.mkdir(parents=True)
            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            process_id = "target-receipt"
            transport = {
                "event": "process_started", "at": now, "caller_id": "caller_test",
                "owner_caller_id": "caller_test", "process_id": process_id,
                "pid": 123, "cwd": r"C:\work",
            }
            (clone / "transport.jsonl").write_text(json.dumps(transport) + "\n", encoding="utf-8")
            for i in range(50):
                (receipts / f"historical-{i}.json").write_text(json.dumps({"caller_id": "old", "command": "noop"}), encoding="utf-8")
            (receipts / f"{process_id}.json").write_text(
                json.dumps({"caller_id": "caller_test", "command": "busy claim 'actor-x' scope"}), encoding="utf-8"
            )
            original_read_text = Path.read_text
            receipt_reads = []

            def counted_read_text(path, *args, **kwargs):
                if path.parent == receipts:
                    receipt_reads.append(path.name)
                return original_read_text(path, *args, **kwargs)

            busy = subprocess.CompletedProcess([], 0, stdout=json.dumps({"claims": [{"actor": "actor-x"}]}), stderr="")
            with patch.dict(os.environ, {"LOCALAPPDATA": str(local)}), \
                 patch("tools.stack_atlas.subprocess.run", return_value=busy), \
                 patch.object(Path, "read_text", counted_read_text):
                status = _bootstrap_mcp_status()
            self.assertEqual(receipt_reads, [f"{process_id}.json"])
            self.assertEqual(status["active_sessions"][0]["busy_titles"], ["actor-x"])

    def test_live_powershell_probe_is_bounded(self):
        completed = __import__("subprocess").CompletedProcess([], 0, stdout="[]", stderr="")
        with patch("tools.stack_atlas.subprocess.run", return_value=completed) as run:
            __import__("tools.stack_atlas", fromlist=["_powershell_json"])._powershell_json("Get-Process")
        self.assertEqual(run.call_args.kwargs["timeout"], 5)

    def test_live_powershell_probe_timeout_is_explicit(self):
        timeout = __import__("subprocess").TimeoutExpired(["powershell"], 5)
        with patch("tools.stack_atlas.subprocess.run", side_effect=timeout):
            with self.assertRaisesRegex(RuntimeError, "timed out after 5s"):
                __import__("tools.stack_atlas", fromlist=["_powershell_json"])._powershell_json("Get-Process")

    def test_bootstrap_atlas_is_small_directory_not_live_status_cache(self):
        atlas = build_bootstrap_atlas()
        self.assertEqual(atlas["schema"], "atlas.v1")
        self.assertIn("load canonical inventory before reasoning/answer/change", atlas["must"])
        self.assertIn("touched components for live proof", atlas["must"])
        self.assertIn("blocks disruption", atlas["must"])
        self.assertNotIn("live_overlay", atlas)
        self.assertEqual(atlas["find"], "find <query>")
        self.assertLess(len(json.dumps(atlas)), 12000)

    def test_work_intake_search_routes_to_existing_issue_git_and_busy_contract(self):
        result = find_features("issue first busy claim dirty handoff")[0]
        self.assertEqual(result["id"], "work.intake")
        self.assertEqual(result["owner_components"], ["agent_rules", "github", "local_git", "busy_coordinator"])
        joined = " ".join(result["entrypoints"])
        self.assertIn("matching issue/PR", joined)
        self.assertIn("continue the matching issue or create one", joined)
        self.assertIn("live git status/HEAD", joined)
        expected_busy = str(Path(os.path.expandvars(r"%LOCALAPPDATA%\BusyCoordinator\busy-python.cmd")))
        self.assertIn(expected_busy, joined)
        self.assertIn("before yielding", joined)
        self.assertIn("not a queue", result["boundary"])
        self.assertIn("collision control only", result["boundary"])

    def test_bootstrap_points_to_canonical_issue_first_contract_without_policy_copy(self):
        with patch("tools.stack_atlas._bootstrap_pc_status", return_value={}), \
             patch("tools.stack_atlas._bootstrap_worker_status", return_value={}), \
             patch("tools.stack_atlas._bootstrap_mcp_status", return_value={}), \
             patch("tools.stack_atlas._bootstrap_memory_titles", return_value=[]):
            glance = build_live_bootstrap_glance()
        self.assertEqual(glance["paths"]["issue_first_work_intake"], r"C:\Users\Lauri\.agents\RULES.md")
        self.assertNotIn("behavior", glance)

    def test_feature_search_surfaces_existing_owner_before_archaeology(self):
        timeline = find_features("vault timeline")[0]
        self.assertEqual(timeline["id"], "vault.history")
        self.assertEqual(timeline["owner_components"], ["memory_bank"])
        self.assertIn("memory_bank.py timeline", timeline["entrypoints"])
        self.assertIn("never recursive Vault scans", timeline["boundary"])

        checkpoint = find_features("checkpoint resume")[0]
        self.assertEqual(checkpoint["id"], "coordination.checkpoint_context")
        self.assertIn("busy_coordinator", checkpoint["owner_components"])
        self.assertIn("never retained after release/recovery/expiry", checkpoint["boundary"])
        self.assertIn("never backlog", checkpoint["boundary"])

        commander = find_features("commander fallback")[0]
        self.assertEqual(commander["id"], "execution.transport")
        commander_routes = " ".join(commander["entrypoints"])
        self.assertIn("Remote Desktop Commander", commander_routes)
        self.assertIn("changed state or new evidence", commander_routes)

        reports = find_features("worker reports")[0]
        self.assertEqual(reports["id"], "worker.reports")
        self.assertIn("worker_reports", reports["owner_components"])
        self.assertIn("PENDING_REVIEW", reports["boundary"])
        self.assertIn("reviewed.json", " ".join(component_details("worker_reports")["live_status"]))
        self.assertIn(r"C:\P3Proofs", " ".join(component_details("worker_reports")["live_status"]))
        self.assertIn("worker-reports/current/<automation-id>.md", " ".join(component_details("worker_reports")["resources"]))
        self.assertIn("history/_reports", " ".join(component_details("worker_reports")["resources"]))
        self.assertNotIn("metrics.json", " ".join(component_details("worker_reports")["resources"]))

    def test_busy_feature_entrypoints_are_directly_executable_paths(self):
        expected = str(Path(os.path.expandvars(r"%LOCALAPPDATA%\BusyCoordinator\busy-python.cmd")))
        ownership = find_features("busy collision control")[0]
        self.assertEqual(ownership["id"], "coordination.ownership")
        self.assertTrue(ownership["entrypoints"])
        self.assertTrue(all(entry.startswith(expected) for entry in ownership["entrypoints"]))
        checkpoint = find_features("checkpoint resume")[0]
        self.assertTrue(all(entry.startswith(expected) for entry in checkpoint["entrypoints"]))
        details = component_details("busy")
        self.assertTrue(all(command.startswith(expected) for command in details["live_status"]))
        self.assertTrue(all(command.startswith(expected) for command in details["independent_recovery"]))
        self.assertIn(expected, details["canonical_sources"])
        self.assertTrue(Path(expected).exists())

    def test_feature_search_is_bounded_and_non_authoritative(self):
        self.assertEqual(find_features(""), [])
        self.assertEqual(find_features("definitely-unknown-capability"), [])
        self.assertEqual(find_features("plugin2"), [])
        results = find_features("current state", limit=2)
        self.assertLessEqual(len(results), 2)
        self.assertTrue(all(item["authority"] == ATLAS_CONTRACT["authority"] for item in results))

    def test_pid_is_lookup_key_not_component_identity(self):
        self.assertIn("ephemeral live lookup key", ATLAS_CONTRACT["pid_semantics"])
        self.assertIn("stable identity", ATLAS_CONTRACT["pid_semantics"])

    def test_unknown_process_is_never_disposable(self):
        processes = [{
            "pid": 4444,
            "ppid": 1,
            "name": "node.exe",
            "command_line": "node.exe unknown.js",
        }]
        result = blast_radius(4444, processes)
        self.assertEqual(result["status"], "UNRESOLVED")
        self.assertEqual(result["destructive_verdict"], "BLOCK_UNKNOWN_TOPOLOGY")
        self.assertIn("stable_component_identity", result["unknowns"])

    def test_mcp_front_door_requires_inactive_generation_update_path(self):
        details = component_details("mcp_front_door")
        self.assertIn("inactive backend generation", " ".join(details["independent_recovery"]))
        self.assertIn("exact tool contract", " ".join(details["live_status"]))

    def test_vps_edge_process_classifies_and_blocks_disruption(self):
        process = {
            "pid": 480, "ppid": 1, "name": "python.exe",
            "command_line": r"python.exe C:\Users\Lauri\AppData\Local\McpVpsEdge\vps_mcp_reverse_tunnel.py",
        }
        result = blast_radius(480, [process])
        self.assertEqual(result["identity"]["component"], "vps_edge_ingress")
        self.assertEqual(result["destructive_verdict"], "BLOCK_ACTIVE_TRANSPORT")

    def test_vps_edge_current_topology_is_wireguard_primary_with_ssh_fallbacks(self):
        details = component_details("vps_edge_ingress")
        status = " ".join(details["live_status"])
        resources = " ".join(details["resources"])
        self.assertIn("WireGuard", status)
        self.assertIn("10.203.0.2:3011 primary", status)
        self.assertIn("3101-3104", status)
        self.assertIn("intentional fallback", status)
        self.assertIn("WireGuard UDP 51820", resources)

    def test_vps_edge_native_ssh_fallback_lane_classifies_as_transport(self):
        process = {
            "pid": 25428, "ppid": 1, "name": "ssh.exe",
            "command_line": r'"C:\Program Files\Git\usr\bin\ssh.exe" -N -T -i C:\Users\Lauri\.ssh\tietokettu_edge -R 127.0.0.1:3101:127.0.0.1:3011 root@5.61.91.127',
        }
        result = blast_radius(25428, [process])
        self.assertEqual(result["identity"]["component"], "vps_edge_ingress")
        self.assertEqual(result["destructive_verdict"], "BLOCK_ACTIVE_TRANSPORT")

    def test_vps_origin_listener_wrapper_classifies_as_minimal_clone(self):
        listener = {
            "pid": 11328, "ppid": 5376, "name": "node.exe",
            "command_line": r"node.exe dist/index.js",
        }
        launcher = {
            "pid": 5376, "ppid": 1, "name": "powershell.exe",
            "command_line": r"powershell.exe -File C:\Users\Lauri\AppData\Local\Temp\launch-mcp-vps-origin.ps1",
        }
        mapping = {item["pid"]: item for item in (listener, launcher)}
        self.assertEqual(classify_process(listener, mapping)["component"], "mcp_minimal_clone")

    def test_natural_component_aliases_resolve(self):
        self.assertEqual(component_details("mcp")["id"], "mcp_front_door")
        self.assertEqual(component_details("webgpt")["id"], "chatgpt_session")
        self.assertEqual(component_details("coordinator")["id"], "busy_coordinator")
        self.assertEqual(component_details("webgpt")["role"], "session:user-facing")
        self.assertEqual(component_details("rules")["id"], "agent_rules")

    def test_bootstrap_directory_covers_major_stack_surfaces(self):
        atlas = build_bootstrap_atlas()
        ids = set(__import__("tools.stack_atlas", fromlist=["COMPONENTS"]).COMPONENTS)
        expected = {
            "busy_coordinator", "mcp_front_door", "mcp_backend", "mcp_minimal_clone",
            "agent_rules", "repo_rule_pointer", "north_star", "chatgpt_memory", "memory_bank",
            "chatgpt_session", "execution_workers", "chatgpt_automations", "local_git", "github",
            "github_actions", "github_runner", "worker_reports",
        }
        self.assertTrue(expected.issubset(ids), sorted(expected - ids))
        self.assertNotIn("operator_live", ids)

    def test_atlas_is_product_agnostic_and_product_repos_are_not_lookup_authorities(self):
        atlas = __import__("tools.stack_atlas", fromlist=["COMPONENTS"])
        self.assertIn("STACK_INFRA_MAP_ONLY", ATLAS_CONTRACT["scope"])
        self.assertFalse(hasattr(atlas, "PRODUCT_COMPONENTS"))
        self.assertFalse(hasattr(atlas, "PRODUCT_ROOTS"))
        self.assertFalse(hasattr(atlas, "PRODUCT_FLOW"))
        for product in ("lowvram", "asset_library", "tiny3d", "p3"):
            with self.subTest(product=product):
                with self.assertRaises(KeyError):
                    component_details(product)
        inventory = full_inventory()
        self.assertNotIn("product_flow", inventory)
        self.assertTrue({"lowvram", "asset_library", "tiny3d", "p3"}.isdisjoint(inventory["components"]))

    def test_generated_operational_manual_matches_atlas(self):
        manual = ROOT / "docs" / "assistant-stack-operational-atlas.md"
        self.assertEqual(manual.read_text(encoding="utf-8"), render_manual() + "\n")
        text = manual.read_text(encoding="utf-8")
        self.assertNotIn("desktop_commander", text.casefold())
        self.assertIn("### `mcp_front_door`", text)
        self.assertIn("Independent recovery", text)
        self.assertIn("Supervisor", text)
        self.assertIn("Resources", text)

    def test_vault_agents_is_pointer_only_to_canonical_rules(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(len(agents.rstrip().splitlines()), 7)
        self.assertIn(r"C:\Users\Lauri\.agents\RULES.md", agents)
        self.assertIn(r"C:\Users\Lauri\.agents\AGENTS.md", agents)
        self.assertNotIn("contexts", agents.casefold())
        self.assertIn("pointer-only", agents)
        self.assertNotIn("SHARED-AGENT-POLICY", agents)
        self.assertNotIn("### Navigation minimap", agents)

    def test_memory_bank_publishes_only_through_dedicated_memory_branch(self):
        memory = component_details("memory_bank")
        joined = " ".join([*memory["canonical_sources"], *memory["live_status"]])
        self.assertIn("origin/memory/live", joined)
        self.assertIn("forbidden publication targets", joined)

    def test_every_component_declares_its_own_live_truth_and_recovery_routes(self):
        atlas = __import__("tools.stack_atlas", fromlist=["COMPONENTS"])
        for component in atlas.COMPONENTS:
            with self.subTest(component=component):
                details = component_details(component)
                for field in ("canonical_sources", "live_status", "supervisor", "self_heal", "independent_recovery", "resources", "dependents", "runbook"):
                    self.assertIn(field, details)
                    self.assertIsNotNone(details[field])
                self.assertTrue(details["live_status"])
                self.assertTrue(details["canonical_sources"])
                self.assertTrue(details["runbook"])

class Issue394StackVisibilityTests(unittest.TestCase):
    def test_human_aliases_cover_invisible_stack_seams(self):
        self.assertEqual(component_details("tailscale")["id"], "tailscale_ingress")
        self.assertEqual(component_details("transfer")["id"], "file_transfer")
        self.assertEqual(component_details("file transfer")["id"], "file_transfer")
        self.assertEqual(component_details("visual proof")["id"], "visual_proof")
        self.assertEqual(component_details("workers")["id"], "execution_workers")
