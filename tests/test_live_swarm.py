import json
import os
import tempfile
import subprocess
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools.live_swarm import (
    _action_mode, _actor_candidate_map, _canonical_actor_specs, _command_target, _git_identity, _read_window,
    _recurring_actor_evidence, _repo_root, _resolve_busy_identity, _resolve_caller_identity, _workspace,
    build_live_swarm_snapshot, compact_for_bootstrap,
    identify_current_actor,
)


class LiveSwarmTests(unittest.TestCase):


    def test_repo_root_override_keeps_deployed_runtime_bound_to_serving_repo(self):
        with tempfile.TemporaryDirectory() as td, patch.dict("os.environ",{"STACK_ATLAS_ROOT_OVERRIDE":td}):
            self.assertEqual(_repo_root(),Path(td).resolve())

    def test_canonical_actor_specs_follow_current_slot_bindings(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            registry=root/"worker-reports"/".supervision"/"recurring-slot-bindings.json"
            registry.parent.mkdir(parents=True)
            registry.write_text(json.dumps({
                "schema":"recurring-worker-slot-bindings.v1",
                "authority":"MUTABLE_OPERATIONAL_SLOT_BINDINGS_NOT_LIVENESS",
                "bindings":{
                    "S1/1":{"automation_id":"1"*32,"label":"Repo Worker Hazel S1 New","bound_at":"2026-09-13T05:00:00+00:00"},
                    "S2/1":{"automation_id":"a"*32,"label":"Repo Worker Rowan #S2","bound_at":"2026-09-13T05:00:00+00:00"},
                    "S2/2":{"automation_id":"b"*32,"label":"Repo Worker Alder #S2","bound_at":"2026-09-13T05:00:00+00:00"},
                },
            }),encoding="utf-8")
            specs=_canonical_actor_specs(root)
            payload=json.loads(registry.read_text(encoding="utf-8"))
            payload["bindings"]["S1/1"]={
                "automation_id":"2"*32,
                "label":"Repo Worker Aspen #S1",
                "bound_at":"2026-09-13T06:00:00+00:00",
            }
            registry.write_text(json.dumps(payload),encoding="utf-8")
            rebound={row["actor"]:row for row in _canonical_actor_specs(root)}
        by_actor={row["actor"]:row for row in specs}
        self.assertEqual(set(by_actor),{"S1/Hazel","S2/Rowan","S2/Alder"})
        self.assertEqual(by_actor["S1/Hazel"]["slot_id"],"S1/1")
        self.assertEqual(by_actor["S2/Rowan"]["name"],"rowan")
        self.assertNotIn("S1/Hazel",rebound)
        self.assertEqual(rebound["S1/Aspen"]["slot_id"],"S1/1")

    def test_canonical_actor_specs_ignore_unbound_slots_and_disambiguate_duplicate_names(self):
        snapshot={
            "status":"OK",
            "bound_workers":[
                {"partition":"S1","slot_id":"S1/1","label":"Repo Worker Alder"},
                {"partition":"S2","slot_id":"S2/5","label":"Repo Worker Alder #S2"},
            ],
        }
        with patch("tools.live_swarm.load_slot_snapshot",return_value=snapshot):
            specs=_canonical_actor_specs()
        self.assertEqual({row["actor"] for row in specs},{"S1/Alder","S2/Alder"})
        self.assertTrue(all(not row["name_unique"] for row in specs))
        got=_actor_candidate_map(
            {"worktree":{"branch":"chatgpt/alder-s2-work","path":r"C:\wt\alder-s2"}},[],specs
        )
        self.assertEqual(got,{"S2/Alder":{"worktree_branch","worktree_path"}})

    def test_canonical_actor_specs_fail_soft_when_slot_registry_unavailable(self):
        with patch("tools.live_swarm.load_slot_snapshot",return_value={"status":"MISSING"}):
            self.assertEqual(_canonical_actor_specs(),[])

    def test_actor_candidate_requires_partition_for_duplicate_names(self):
        specs=[
            {"actor":"S1/Alder","partition":"s1","name":"alder","name_unique":False},
            {"actor":"S2/Alder","partition":"s2","name":"alder","name_unique":False},
            {"actor":"S2/Spruce","partition":"s2","name":"spruce","name_unique":True},
        ]
        detail={"worktree":{"branch":"chatgpt/3013-cohort-pressure-retry-spruce-s2","path":r"C:\\wt\\spruce-s2"}}
        got=_actor_candidate_map(detail,[{"owner":"ChatGPT-alder-s2-run11"}],specs)
        self.assertEqual(got,{"S2/Alder":{"busy_owner"},"S2/Spruce":{"worktree_branch","worktree_path"}})

    def test_busy_scope_can_resolve_coordination_actor_without_claiming_liveness(self):
        specs=[{"actor":"S2/Spruce","partition":"s2","slot_id":"S2/2","name":"spruce","name_unique":True}]
        busy={
            "owner":"ChatGPT-generic-worker",
            "scopes":["p3:git-ref:refs/heads/chatgpt/3013-retry-spruce-s2"],
            "last_update_age_seconds":12.0,
        }
        identity=_resolve_busy_identity(busy,specs)
        self.assertEqual(identity["status"],"ATTRIBUTED")
        self.assertEqual(identity["actor"],"S2/Spruce")
        self.assertEqual(identity["source"],"resolved_coordination")
        self.assertEqual(identity["resolved_by"],["busy_scope"])

    def test_ambiguous_busy_identity_stays_unattributed(self):
        specs=[
            {"actor":"S1/Alder","partition":"s1","slot_id":"S1/5","name":"alder","name_unique":False},
            {"actor":"S2/Alder","partition":"s2","slot_id":"S2/5","name":"alder","name_unique":False},
        ]
        identity=_resolve_busy_identity({"owner":"ChatGPT-Alder","scopes":[]},specs)
        self.assertEqual(identity,{"status":"UNATTRIBUTED","actor":None,"source":None})

    def test_recurring_actor_projection_separates_mcp_coordination_and_absence(self):
        specs=[
            {"actor":"S1/Hazel","partition":"s1","slot_id":"S1/1","name":"hazel","name_unique":True},
            {"actor":"S2/Spruce","partition":"s2","slot_id":"S2/2","name":"spruce","name_unique":True},
            {"actor":"S2/Juniper","partition":"s2","slot_id":"S2/4","name":"juniper","name_unique":True},
        ]
        callers=[{
            "caller_id":"caller_hazel",
            "last_activity_age_seconds":4.0,
            "workspace":"Vault",
            "worktree":{"branch":"chatgpt/hazel-s1-fix","path":r"C:\wt\hazel"},
            "activity_target":{"type":"card","id":"1132","project":"regression-research"},
            "identity":{"status":"ATTRIBUTED","actor":"S1/Hazel","source":"resolved"},
        }]
        busy={
            "owner":"ChatGPT-spruce-s2-run",
            "scopes":["p3:git-ref:refs/heads/chatgpt/spruce-s2-work"],
            "last_update_age_seconds":9.0,
            "checkpoint":"working on #3013",
            "identity":{"status":"ATTRIBUTED","actor":"S2/Spruce","source":"resolved_coordination","resolved_by":["busy_owner","busy_scope"]},
        }
        rows=_recurring_actor_evidence(specs,callers,[{"busy":[busy]}])
        by_actor={row["actor"]:row for row in rows}
        self.assertEqual(by_actor["S1/Hazel"]["evidence_state"],"RECENT_ATTRIBUTED_MCP_ACTIVITY")
        self.assertEqual(by_actor["S1/Hazel"]["mcp"]["activity_target"]["id"],"1132")
        self.assertEqual(by_actor["S2/Spruce"]["evidence_state"],"RECENT_COORDINATION_ONLY")
        self.assertEqual(by_actor["S2/Spruce"]["coordination"]["latest_owner"],"ChatGPT-spruce-s2-run")
        self.assertEqual(by_actor["S2/Juniper"]["evidence_state"],"NO_RECENT_EVIDENCE")
        self.assertNotIn("health",by_actor["S2/Juniper"])
        self.assertNotIn("liveness",by_actor["S2/Juniper"])

    def test_explicit_actor_wins_resolver_mismatch_without_health_failure(self):
        now=datetime(2026,9,13,3,0,0,tzinfo=timezone.utc)
        detail={"caller_id":"caller_abc123","worktree":{"branch":"chatgpt/rowan-s2","path":r"C:\\wt\\rowan-s2"}}
        specs=[{"actor":"S2/Rowan","partition":"s2","name":"rowan","name_unique":True}]
        with patch("tools.live_swarm._load_explicit_actor_binding",return_value={"actor":"manual/reviewer","bound_at":now.isoformat(),"age_seconds":0}):
            identity=_resolve_caller_identity(detail,[],now=now,specs=specs)
        self.assertEqual(identity["status"],"ATTRIBUTED")
        self.assertEqual(identity["actor"],"manual/reviewer")
        self.assertEqual(identity["source"],"self_declared")
        self.assertEqual(identity["diagnostic"],"RESOLVER_MISMATCH")
        self.assertEqual(identity["resolver_candidates"][0]["actor"],"S2/Rowan")

    def test_unattributed_actor_is_normal_state(self):
        now=datetime(2026,9,13,3,0,0,tzinfo=timezone.utc)
        detail={"caller_id":"caller_abc123","worktree":None}
        with patch("tools.live_swarm._load_explicit_actor_binding",return_value=None):
            identity=_resolve_caller_identity(detail,[],now=now,specs=[])
        self.assertEqual(identity,{"status":"UNATTRIBUTED","actor":None,"source":None})

    def test_identify_current_actor_persists_per_caller_binding(self):
        now=datetime(2026,9,13,3,0,0,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as td, patch.dict("os.environ",{"LOCALAPPDATA":td}), \
             patch("tools.live_swarm._find_current_caller_id",return_value="caller_abc123"):
            result=identify_current_actor("manual/reviewer",now=now,parent_pid=123)
            self.assertTrue(result["bound"])
            self.assertEqual(result["caller_id"],"caller_abc123")
            path=Path(td)/"ChatGPTMcpClean"/".state"/"swarm-actor-bindings"/"caller_abc123.json"
            payload=json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["actor"],"manual/reviewer")
            self.assertEqual(payload["source"],"self_declared")

    def test_command_target_prefers_explicit_execution_surface(self):
        path,basis=_command_target("$wt='C:\\work\\tiny3d-wt'; Set-Location $wt; python test.py")
        self.assertEqual(path, r"C:\work\tiny3d-wt")
        self.assertEqual(basis, "command_cwd")
        path,basis=_command_target("git -C 'C:\\repo\\p3' status")
        self.assertEqual(path, r"C:\repo\p3")
        self.assertEqual(basis, "command_git_c")

    def test_action_mode_requires_explicit_plan_label(self):
        self.assertEqual(_action_mode("package_plan"), "PLAN_ONLY")
        self.assertEqual(_action_mode("content-plan"), "PLAN_ONLY")
        self.assertEqual(_action_mode("plan_only"), "PLAN_ONLY")
        self.assertEqual(_action_mode("repo_mutation"), "UNKNOWN")
        self.assertEqual(_action_mode("planonly_evidence_probe"), "UNKNOWN")

    def test_workspace_is_orientation_not_identity(self):
        self.assertEqual(_workspace(r"C:\Users\Lauri\Desktop\tiny3d-x"), "Tiny3D")
        self.assertEqual(_workspace(r"C:\Users\Lauri\.agents"), "Agents")
        self.assertEqual(_workspace(r"C:\Users\Lauri\AppData\Local\ChatGPTMcpMinimal"), "MCP-runtime")

    def test_git_identity_reports_commit_sha_not_branch_name(self):
        with tempfile.TemporaryDirectory() as td:
            repo=Path(td)/"repo"
            repo.mkdir()
            subprocess.run(["git","init","-b","truth-test",str(repo)],check=True,capture_output=True,text=True)
            subprocess.run(["git","-C",str(repo),"config","user.email","test@example.invalid"],check=True)
            subprocess.run(["git","-C",str(repo),"config","user.name","Test"],check=True)
            (repo/"a.txt").write_text("x\n",encoding="utf-8")
            subprocess.run(["git","-C",str(repo),"add","a.txt"],check=True)
            subprocess.run(["git","-C",str(repo),"commit","-m","seed"],check=True,capture_output=True,text=True)
            expected=subprocess.check_output(["git","-C",str(repo),"rev-parse","--short=8","HEAD"],text=True).strip()
            got=_git_identity(str(repo/"a.txt"),{})
            self.assertEqual(got["branch"],"truth-test")
            self.assertEqual(got["head"],expected)
            self.assertNotEqual(got["head"],got["branch"])

    def test_window_marks_truncation_as_incomplete(self):
        now=datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"transport.jsonl"
            rows=[{"at":(now-timedelta(seconds=i)).isoformat(),"event":"process_read","caller_id":"c"} for i in range(4)]
            p.write_text("\n".join(json.dumps(x) for x in reversed(rows))+"\n",encoding="utf-8")
            out,complete,_=_read_window(p,now-timedelta(seconds=10))
            self.assertTrue(complete)
            self.assertEqual(len(out),4)


    def test_unavailable_snapshot_keeps_activity_window_shape_without_claiming_completeness(self):
        now=datetime(2026,9,10,3,0,0,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as td, patch.dict("os.environ",{"LOCALAPPDATA":td}):
            snapshot=build_live_swarm_snapshot(now=now)
        self.assertFalse(snapshot["available"])
        self.assertEqual(snapshot["summary"]["active_callers"],{"15s":0,"60s":0,"2m":0,"5m":0,"15m":0,"30m":0})
        self.assertEqual(snapshot["evidence"]["active_callers_complete_through_seconds"],0)

    def test_activity_window_completeness_is_distinct_from_observation_window(self):
        now=datetime(2026,9,10,3,0,0,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            local=Path(td)
            root=local/"ChatGPTMcpClean"/"minimal-connectors"
            root.mkdir(parents=True)
            (root/"shared-process-receipts").mkdir()
            state=local/"ChatGPTMcpClean"/".state"
            state.mkdir()
            (state/"busy-claims.json").write_text(json.dumps({"coordinator":{"jobs":{}}}),encoding="utf-8")
            folder=root/"busy-source"
            folder.mkdir()
            path=folder/"transport.jsonl"
            rows=[
                {"at":(now-timedelta(seconds=seconds_ago)).isoformat(),"event":"process_read","caller_id":"caller_busy","process_id":"p"}
                for seconds_ago in range(0,1801,15)
            ]
            path.write_text("\n".join(json.dumps(row) for row in reversed(rows))+"\n",encoding="utf-8")
            stamp=now.timestamp()
            os.utime(path,(stamp,stamp))

            with patch.dict("os.environ",{"LOCALAPPDATA":str(local)}), \
                 patch("tools.live_swarm.MAX_TRANSPORT_BYTES",5000):
                enough=build_live_swarm_snapshot(now=now)
            self.assertFalse(enough["evidence"]["observation_window_complete"])
            self.assertTrue(enough["evidence"]["activity_window_complete"])
            self.assertEqual(enough["evidence"]["active_callers_complete_through_seconds"],300)
            self.assertTrue(enough["transport_sources"][0]["activity_window_complete"])

            with patch.dict("os.environ",{"LOCALAPPDATA":str(local)}), \
                 patch("tools.live_swarm.MAX_TRANSPORT_BYTES",1000):
                truncated=build_live_swarm_snapshot(now=now)
            self.assertFalse(truncated["evidence"]["observation_window_complete"])
            self.assertFalse(truncated["evidence"]["activity_window_complete"])
            self.assertEqual(truncated["evidence"]["active_callers_complete_through_seconds"],0)
            self.assertFalse(truncated["transport_sources"][0]["activity_window_complete"])

    def test_stale_candidate_overflow_does_not_poison_complete_window(self):
        now=datetime(2026,9,10,3,0,0,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            local=Path(td)
            root=local/"ChatGPTMcpClean"/"minimal-connectors"
            root.mkdir(parents=True)
            (root/"shared-process-receipts").mkdir()
            state=local/"ChatGPTMcpClean"/".state"
            state.mkdir()
            (state/"busy-claims.json").write_text(json.dumps({"coordinator":{"jobs":{}}}),encoding="utf-8")

            def source(name, at):
                folder=root/name
                folder.mkdir()
                path=folder/"transport.jsonl"
                path.write_text(json.dumps({"at":at.isoformat(),"event":"process_read","caller_id":name})+"\n",encoding="utf-8")
                stamp=at.timestamp()
                os.utime(path,(stamp,stamp))

            source("live-a",now-timedelta(minutes=1))
            source("live-b",now-timedelta(minutes=2))
            source("stale-overflow",now-timedelta(hours=2))
            with patch.dict("os.environ",{"LOCALAPPDATA":str(local)}), \
                 patch("tools.live_swarm.MAX_TRANSPORT_SOURCE_CANDIDATES",2):
                snapshot=build_live_swarm_snapshot(now=now)
            discovery=snapshot["transport_source_discovery"]
            self.assertTrue(discovery["truncated"])
            self.assertFalse(discovery["truncation_affects_window"])
            self.assertFalse(discovery["truncation_affects_activity_window"])
            self.assertTrue(snapshot["evidence"]["observation_window_complete"])
            self.assertTrue(snapshot["evidence"]["activity_window_complete"])
            self.assertEqual(snapshot["evidence"]["transport_source_count"],2)

    def test_in_window_candidate_overflow_keeps_window_incomplete(self):
        now=datetime(2026,9,10,3,0,0,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            local=Path(td)
            root=local/"ChatGPTMcpClean"/"minimal-connectors"
            root.mkdir(parents=True)
            (root/"shared-process-receipts").mkdir()
            state=local/"ChatGPTMcpClean"/".state"
            state.mkdir()
            (state/"busy-claims.json").write_text(json.dumps({"coordinator":{"jobs":{}}}),encoding="utf-8")

            for index in range(3):
                folder=root/f"live-{index}"
                folder.mkdir()
                at=now-timedelta(minutes=index+1)
                path=folder/"transport.jsonl"
                path.write_text(json.dumps({"at":at.isoformat(),"event":"process_read","caller_id":f"live-{index}"})+"\n",encoding="utf-8")
                stamp=at.timestamp()
                os.utime(path,(stamp,stamp))
            with patch.dict("os.environ",{"LOCALAPPDATA":str(local)}), \
                 patch("tools.live_swarm.MAX_TRANSPORT_SOURCE_CANDIDATES",2):
                snapshot=build_live_swarm_snapshot(now=now)
            discovery=snapshot["transport_source_discovery"]
            self.assertTrue(discovery["truncated"])
            self.assertTrue(discovery["truncation_affects_window"])
            self.assertTrue(discovery["truncation_affects_activity_window"])
            self.assertFalse(snapshot["evidence"]["observation_window_complete"])
            self.assertFalse(snapshot["evidence"]["activity_window_complete"])
            self.assertEqual(snapshot["evidence"]["transport_source_count"],2)

    def test_snapshot_aggregates_current_mcpv4_transport_sources(self):
        now=datetime(2026,9,9,1,30,0,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            local=Path(td)
            root=local/"ChatGPTMcpClean"/"minimal-connectors"
            root.mkdir(parents=True)
            (root/"shared-process-receipts").mkdir()
            state=local/"ChatGPTMcpClean"/".state"
            state.mkdir()
            (state/"busy-claims.json").write_text(json.dumps({"coordinator":{"jobs":{}}}),encoding="utf-8")

            def write_source(name, rows):
                folder=root/name
                folder.mkdir()
                (folder/"transport.jsonl").write_text("\n".join(json.dumps(row) for row in rows)+"\n",encoding="utf-8")

            write_source("clone-a",[
                {"at":(now-timedelta(seconds=21)).isoformat(),"event":"connection_open","server_pid":201,"local_port":3011},
                {"at":(now-timedelta(seconds=20)).isoformat(),"event":"process_started","caller_id":"caller_a","process_id":"pa","pid":101,"server_pid":201,"cwd":r"C:\work\a"},
                {"at":(now-timedelta(seconds=19)).isoformat(),"event":"process_read","caller_id":"caller_a","owner_caller_id":"caller_a","process_id":"pa","pid":101},
            ])
            write_source("home-direct-test",[
                {"at":(now-timedelta(seconds=11)).isoformat(),"event":"connection_open","server_pid":202,"local_port":3022},
                {"at":(now-timedelta(seconds=10)).isoformat(),"event":"process_started","caller_id":"caller_b","process_id":"pb","pid":102,"server_pid":202,"cwd":r"C:\work\b"},
                {"at":(now-timedelta(seconds=9)).isoformat(),"event":"process_read","caller_id":"caller_b","owner_caller_id":"caller_b","process_id":"pb","pid":102},
            ])
            write_source("stale-replacement",[
                {"at":(now-timedelta(hours=1)).isoformat(),"event":"process_started","caller_id":"caller_stale","process_id":"ps","pid":103,"cwd":r"C:\work\stale"},
            ])
            with patch.dict("os.environ",{"LOCALAPPDATA":str(local)}):
                snapshot=build_live_swarm_snapshot(now=now)
            callers={c["caller_id"] for lane in snapshot["lanes"] for c in lane["callers"]}
            self.assertEqual(callers,{"caller_a","caller_b"})
            self.assertEqual(snapshot["evidence"]["transport"],"MCPv4")
            self.assertEqual(snapshot["evidence"]["transport_source_count"],2)
            self.assertEqual({s["instance"] for s in snapshot["transport_sources"]},{"clone-a","home-direct-test"})
            source_by_instance={s["instance"]:s for s in snapshot["transport_sources"]}
            self.assertEqual(source_by_instance["clone-a"]["server_pid"],201)
            self.assertEqual(source_by_instance["clone-a"]["local_port"],3011)
            self.assertEqual(source_by_instance["home-direct-test"]["server_pid"],202)
            self.assertEqual(source_by_instance["home-direct-test"]["local_port"],3022)
            self.assertNotIn("caller_stale",callers)

    def test_snapshot_counts_unique_mcp_callers_across_recent_windows(self):
        now=datetime(2026,9,9,1,30,0,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            local=Path(td)
            root=local/"ChatGPTMcpClean"/"minimal-connectors"
            source=root/"clone-a"
            source.mkdir(parents=True)
            (root/"shared-process-receipts").mkdir()
            state=local/"ChatGPTMcpClean"/".state"
            state.mkdir()
            (state/"busy-claims.json").write_text(json.dumps({"coordinator":{"jobs":{}}}),encoding="utf-8")
            rows=[]
            for caller,seconds_ago in (("c15",5),("c60",30),("c2m",90),("c5m",240),("c15m",600),("c30m",1200),("c_exit",600)):
                row={"at":(now-timedelta(seconds=seconds_ago)).isoformat(),"event":"process_started","caller_id":caller,"process_id":caller,"cwd":fr"C:\work\{caller}"}
                if caller=="c15": row.update(action_class="package_plan",activity_target={"type":"project","id":"plan-target","project":"p3"})
                elif caller=="c60": row.update(action_class="repo_mutation",activity_target={"type":"card","id":"42","project":"p3"})
                rows.append(row)
            rows.append({"at":(now-timedelta(seconds=4)).isoformat(),"event":"process_exit_observed","caller_id":"c_exit","process_id":"c_exit","exit_code":0})
            rows.sort(key=lambda row: row["at"])
            (source/"transport.jsonl").write_text("\n".join(json.dumps(row) for row in rows)+"\n",encoding="utf-8")
            with patch.dict("os.environ",{"LOCALAPPDATA":str(local)}):
                snapshot=build_live_swarm_snapshot(now=now)
            self.assertEqual(snapshot["summary"]["active_callers"],{
                "15s":1,"60s":2,"2m":3,"5m":4,"15m":6,"30m":7,
            })
            self.assertEqual(snapshot["summary"]["recent_callers"],4)
            self.assertEqual(snapshot["summary"]["activity_buckets"],{
                "0_15s":1,"15_60s":1,"1_2m":1,"2_5m":1,"5_15m":2,"15_30m":1,
            })
            self.assertEqual(snapshot["summary"]["caller_modes"],{"PLAN_ONLY":1,"UNKNOWN":3})
            caller_by_id={caller["caller_id"]:caller for caller in snapshot["callers"]}
            self.assertEqual(caller_by_id["c15"]["mode"],"PLAN_ONLY")
            self.assertEqual(caller_by_id["c15"]["action_class"],"package_plan")
            self.assertEqual(caller_by_id["c15"]["activity_target"],{"type":"project","id":"plan-target","project":"p3"})
            self.assertEqual(caller_by_id["c60"]["mode"],"UNKNOWN")
            self.assertEqual(snapshot["evidence"]["active_callers_complete_through_seconds"],1800)
            self.assertEqual(snapshot["evidence"]["active_callers_semantics"],"unique_non_observer_callers_with_process_started_or_process_read_in_window")
            self.assertIn("PLAN_ONLY_only_when",snapshot["evidence"]["caller_mode_semantics"])

    def test_snapshot_uses_newer_rotated_archive_for_same_mcpv4_instance(self):
        now=datetime(2026,9,9,1,30,0,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            local=Path(td)
            root=local/"ChatGPTMcpClean"/"minimal-connectors"
            clone=root/"clone-a"
            archive=clone/"transport.jsonl.archive"
            archive.mkdir(parents=True)
            (root/"shared-process-receipts").mkdir()
            state=local/"ChatGPTMcpClean"/".state"
            state.mkdir()
            (state/"busy-claims.json").write_text(json.dumps({"coordinator":{"jobs":{}}}),encoding="utf-8")
            (clone/"transport.jsonl").write_text(json.dumps({
                "at":(now-timedelta(minutes=10)).isoformat(),"event":"process_started",
                "caller_id":"caller_old","process_id":"old","pid":101,"cwd":r"C:\work\old",
            })+"\n",encoding="utf-8")
            rotated=archive/"transport.jsonl.2026-09-09T01-29-00Z.jsonl"
            rotated.write_text(json.dumps({
                "at":(now-timedelta(seconds=5)).isoformat(),"event":"process_started",
                "caller_id":"caller_live","process_id":"live","pid":102,"cwd":r"C:\work\live",
            })+"\n",encoding="utf-8")
            with patch.dict("os.environ",{"LOCALAPPDATA":str(local)}):
                snapshot=build_live_swarm_snapshot(now=now)
            callers={c["caller_id"] for lane in snapshot["lanes"] for c in lane["callers"]}
            self.assertEqual(callers,{"caller_live"})
            self.assertEqual(snapshot["evidence"]["transport_source_count"],1)
            self.assertEqual(snapshot["transport_sources"][0]["instance"],"clone-a")

    def test_bootstrap_compaction_omits_no_recent_actor_rows_but_keeps_summary(self):
        snapshot={
            "summary":{
                "recurring_actor_evidence":{
                    "available":True,
                    "slot_registry_status":"OK",
                    "bound_actors":10,
                    "evidence_states":{"NO_RECENT_EVIDENCE":10},
                    "unbound_slots":[],
                    "semantics":"long full live-swarm semantics should not consume bootstrap budget",
                }
            },
            "evidence":{"recurring_actor_evidence_semantics":"full live-swarm semantics only"},
            "elapsed_ms":1.0,
            "recurring_actors":[
                {"slot_id":f"S1/{i}","actor":f"S1/W{i}","evidence_state":"NO_RECENT_EVIDENCE"}
                for i in range(1,6)
            ] + [
                {"slot_id":f"S2/{i}","actor":f"S2/W{i}","evidence_state":"NO_RECENT_EVIDENCE"}
                for i in range(1,6)
            ],
            "lanes":[],
        }
        compact=compact_for_bootstrap(snapshot)
        self.assertEqual(compact["recurring_actors"],[])
        self.assertEqual(compact["summary"]["recurring_actor_evidence"]["bound_actors"],10)
        self.assertEqual(compact["summary"]["recurring_actor_evidence"]["evidence_states"]["NO_RECENT_EVIDENCE"],10)
        self.assertNotIn("semantics",compact["summary"]["recurring_actor_evidence"])
        self.assertNotIn("slot_registry_status",compact["summary"]["recurring_actor_evidence"])
        self.assertNotIn("recurring_actor_evidence_semantics",compact["evidence"])

    def test_bootstrap_compaction_keeps_counts_and_no_scopes(self):
        snapshot={"summary":{"recent_callers":3,"caller_modes":{"PLAN_ONLY":1,"UNKNOWN":2},"lanes":2,"busy_scopes":5},"evidence":{"source_age_seconds":0.1},"elapsed_ms":10.0,"recurring_actors":[{"slot_id":"S2/2","actor":"S2/Spruce","evidence_state":"RECENT_COORDINATION_ONLY","coordination":{"latest_owner":"o","latest_scope":"secret/coordination/scope","checkpoint":"secret checkpoint"}}],"lanes":[{"basis":"worktree","state":"ACTIVE","workspace":"Tiny3D","worktree":{"path":"C:/wt","branch":"b","head":"1"},"callers":[{"caller_id":"c","last_activity_age_seconds":1,"observed_span_minutes":20,"mode":"PLAN_ONLY","action_class":"content_plan","activity_target":{"type":"project","id":"tiny3d"}}],"busy":[{"owner":"o","scope_count":5,"scopes":["secret/path"],"identity":{"status":"ATTRIBUTED","actor":"S2/Spruce","source":"resolved_coordination"}}]}]}
        compact=compact_for_bootstrap(snapshot)
        self.assertEqual(compact["summary"]["recent_callers"],3)
        self.assertEqual(compact["lanes"][0]["busy"][0]["scope_count"],5)
        self.assertEqual(compact["lanes"][0]["state"],"ACTIVE")
        self.assertEqual(compact["lanes"][0]["callers"][0]["mode"],"PLAN_ONLY")
        self.assertNotIn("action_class",compact["lanes"][0]["callers"][0])
        self.assertNotIn("activity_target",compact["lanes"][0]["callers"][0])
        self.assertNotIn("scopes",compact["lanes"][0]["busy"][0])
        self.assertNotIn("identity",compact["lanes"][0]["busy"][0])
        self.assertEqual(compact["recurring_actors"][0]["evidence_state"],"RECENT_COORDINATION_ONLY")
        self.assertNotIn("latest_scope",compact["recurring_actors"][0]["coordination"])
        self.assertNotIn("checkpoint",compact["recurring_actors"][0]["coordination"])
        self.assertNotIn("lanes_truncated",compact)
        self.assertEqual(compact["lane_details"], {
            "policy":"most_recent", "limit":8, "returned":1, "total":1, "bounded":False,
            "semantics":"bootstrap_detail_bound_not_evidence_truncation",
        })


if __name__ == "__main__":
    unittest.main()
