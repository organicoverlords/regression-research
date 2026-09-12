import json
import os
import tempfile
import subprocess
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools.live_swarm import _command_target, _git_identity, _read_window, _workspace, build_live_swarm_snapshot, compact_for_bootstrap


class LiveSwarmTests(unittest.TestCase):
    def test_command_target_prefers_explicit_execution_surface(self):
        path,basis=_command_target("$wt='C:\\work\\tiny3d-wt'; Set-Location $wt; python test.py")
        self.assertEqual(path, r"C:\work\tiny3d-wt")
        self.assertEqual(basis, "command_cwd")
        path,basis=_command_target("git -C 'C:\\repo\\p3' status")
        self.assertEqual(path, r"C:\repo\p3")
        self.assertEqual(basis, "command_git_c")

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
            self.assertTrue(enough["transport_sources"][0]["activity_window_complete"])

            with patch.dict("os.environ",{"LOCALAPPDATA":str(local)}), \
                 patch("tools.live_swarm.MAX_TRANSPORT_BYTES",1000):
                truncated=build_live_swarm_snapshot(now=now)
            self.assertFalse(truncated["evidence"]["observation_window_complete"])
            self.assertFalse(truncated["evidence"]["activity_window_complete"])
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

    def test_bootstrap_compaction_keeps_counts_and_no_scopes(self):
        snapshot={"summary":{"recent_callers":3,"lanes":2,"busy_scopes":5},"evidence":{"source_age_seconds":0.1},"elapsed_ms":10.0,"lanes":[{"basis":"worktree","workspace":"Tiny3D","worktree":{"path":"C:/wt","branch":"b","head":"1"},"callers":[{"caller_id":"c","last_activity_age_seconds":1,"observed_span_minutes":20}],"busy":[{"owner":"o","scope_count":5,"scopes":["secret/path"]}]}]}
        compact=compact_for_bootstrap(snapshot)
        self.assertEqual(compact["summary"]["recent_callers"],3)
        self.assertEqual(compact["lanes"][0]["busy"][0]["scope_count"],5)
        self.assertNotIn("scopes",compact["lanes"][0]["busy"][0])
        self.assertNotIn("lanes_truncated",compact)
        self.assertEqual(compact["lane_details"], {
            "policy":"most_recent", "limit":8, "returned":1, "total":1, "bounded":False,
            "semantics":"bootstrap_detail_bound_not_evidence_truncation",
        })


if __name__ == "__main__":
    unittest.main()
