import importlib.util
from pathlib import Path
import subprocess, tempfile, unittest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("swarm_exec",ROOT/"tools"/"swarm_exec.py")
m=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(m)

class SwarmExecTests(unittest.TestCase):
    def test_safe_work_id(self):
        self.assertEqual(m.safe_work_id("issue/768:test"), "issue_768_test")
        with self.assertRaises(ValueError): m.safe_work_id("bad space")

    def test_remote_workspace_is_nvme_and_sources_worker_tools(self):
        workspace, script=m.remote_script("issue-768", "python3 -V")
        self.assertTrue(workspace.startswith("/mnt/ue/worker-workspaces/"))
        self.assertIn("/mnt/ue/worker-tools/env.sh",script)
        self.assertIn("/mnt/ue/worker-tools/python-packages",script)

    def test_snapshot_uses_current_nonignored_files(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            subprocess.run(["git","init","-q",str(root)],check=True)
            subprocess.run(["git","-C",str(root),"config","user.email","test@example.invalid"],check=True)
            subprocess.run(["git","-C",str(root),"config","user.name","Test"],check=True)
            (root/"tracked.txt").write_text("base",encoding="utf-8")
            (root/".gitignore").write_text("ignored.bin\n",encoding="utf-8")
            subprocess.run(["git","-C",str(root),"add","tracked.txt",".gitignore"],check=True)
            subprocess.run(["git","-C",str(root),"commit","-qm","base"],check=True)
            (root/"tracked.txt").write_text("dirty",encoding="utf-8")
            (root/"new.txt").write_text("new",encoding="utf-8")
            (root/"ignored.bin").write_bytes(b"x"*20)
            names={p.as_posix() for p in m.snapshot_paths(root)}
            self.assertIn("tracked.txt",names)
            self.assertIn("new.txt",names)
            self.assertNotIn("ignored.bin",names)

    def test_snapshot_size_counts_selected_files(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/"a").write_bytes(b"123"); (root/"b").write_bytes(b"4567")
            self.assertEqual(m.snapshot_bytes(root,[Path("a"),Path("b")]),7)

if __name__=="__main__": unittest.main()
