import importlib.util
from pathlib import Path
import subprocess, tempfile, unittest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("swarm_exec",ROOT/"tools"/"swarm_exec.py")
m=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(m)

class SwarmExecTests(unittest.TestCase):
    CACHE_ID="0"*24
    def test_safe_work_id(self):
        self.assertEqual(m.safe_work_id("issue/768:test"), "issue_768_test")
        with self.assertRaises(ValueError): m.safe_work_id("bad space")

    def test_remote_workspace_is_nvme_and_sources_worker_tools(self):
        workspace, script=m.remote_script("issue-768", "python3 -V", self.CACHE_ID)
        self.assertTrue(workspace.startswith("/mnt/ue/worker-workspaces/"))
        self.assertIn("/mnt/ue/worker-tools/env.sh",script)
        self.assertIn("/mnt/ue/worker-tools/python-packages",script)

    def test_remote_workspace_cleans_by_default_and_can_be_kept(self):
        _workspace, cleanup_script=m.remote_script("cleanup", "true", self.CACHE_ID)
        self.assertIn("keep_workspace=0", cleanup_script)
        self.assertIn("trap cleanup EXIT", cleanup_script)
        self.assertIn('if [ "$keep_workspace" -eq 0 ] && [ "$published" -eq 1 ]; then', cleanup_script)
        _workspace, keep_script=m.remote_script("keep", "true", self.CACHE_ID, keep_workspace=True)
        self.assertIn("keep_workspace=1", keep_script)

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

    def test_manifest_delta_only_sends_changes_and_deletes(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/"a.txt").write_text("a",encoding="utf-8")
            (root/"b.txt").write_text("b",encoding="utf-8")
            before=m.snapshot_manifest(root,[Path("a.txt"),Path("b.txt")])
            (root/"a.txt").write_text("changed",encoding="utf-8")
            (root/"b.txt").unlink()
            (root/"c.txt").write_text("c",encoding="utf-8")
            after=m.snapshot_manifest(root,[Path("a.txt"),Path("c.txt")])
            changed,deleted=m.manifest_delta(after,before)
            self.assertEqual({p.as_posix() for p in changed},{"a.txt","c.txt"})
            self.assertEqual(deleted,["b.txt"])

    def test_manifest_delta_ignores_metadata_only_changes(self):
        current={"a.txt":{"type":"file","sha256":"a"*64,"size":1,"mode":0o755,"mtime_ns":99}}
        remote={"a.txt":{"type":"file","sha256":"a"*64,"size":1,"mode":0o644,"mtime_ns":1}}
        changed,deleted=m.manifest_delta(current,remote)
        self.assertEqual(changed,[])
        self.assertEqual(deleted,[])

    def test_cache_protocol_and_remote_lock_are_explicit(self):
        manifest={"a.txt":{"type":"file","sha256":"0"*64,"size":1,"mode":0o644,"mtime_ns":1}}
        line=m.CACHE_PROTOCOL_PREFIX + __import__("json").dumps(manifest,separators=(",",":")).encode() + b"\n"
        self.assertEqual(m.parse_remote_manifest(line),manifest)
        _workspace,script=m.remote_script("cache-proof","true",self.CACHE_ID)
        self.assertIn("/mnt/ue/worker-cache/"+self.CACHE_ID,script)
        self.assertIn("flock 9",script)
        self.assertIn("SWARM_EXEC_CACHE_MANIFEST",script)
        self.assertIn('cp -a -- \"$cache\" \"$final\"',script)

    def test_generated_remote_python_heredocs_compile(self):
        _workspace,script=m.remote_script("compile-proof","true",self.CACHE_ID)
        parts=script.split("<<'PY'\n")[1:]
        self.assertEqual(len(parts),2)
        for part in parts:
            source=part.split("\nPY\n",1)[0]
            compile(source,"<remote-heredoc>","exec")
        self.assertIn("printf '%s\\n' 'SWARM_EXEC_CACHE_MANIFEST {}'",script)

    def test_reserved_cache_metadata_name_is_rejected(self):
        with self.assertRaises(ValueError):
            m._safe_manifest_path(m.CACHE_MANIFEST_NAME)

    def test_snapshot_size_counts_selected_files(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/"a").write_bytes(b"123"); (root/"b").write_bytes(b"4567")
            self.assertEqual(m.snapshot_bytes(root,[Path("a"),Path("b")]),7)

if __name__=="__main__": unittest.main()
