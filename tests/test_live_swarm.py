import json
import tempfile
import subprocess
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools.live_swarm import _command_target, _git_identity, _read_window, _workspace, compact_for_bootstrap


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

    def test_bootstrap_compaction_keeps_counts_and_no_scopes(self):
        snapshot={"summary":{"recent_callers":3,"lanes":2,"busy_scopes":5},"evidence":{"source_age_seconds":0.1},"elapsed_ms":10.0,"lanes":[{"basis":"worktree","workspace":"Tiny3D","worktree":{"path":"C:/wt","branch":"b","head":"1"},"callers":[{"caller_id":"c","last_activity_age_seconds":1,"observed_span_minutes":20}],"busy":[{"owner":"o","scope_count":5,"scopes":["secret/path"]}]}]}
        compact=compact_for_bootstrap(snapshot)
        self.assertEqual(compact["summary"]["recent_callers"],3)
        self.assertEqual(compact["lanes"][0]["busy"][0]["scope_count"],5)
        self.assertNotIn("scopes",compact["lanes"][0]["busy"][0])


if __name__ == "__main__":
    unittest.main()
