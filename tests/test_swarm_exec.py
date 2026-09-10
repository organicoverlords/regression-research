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

    def test_main_routes_without_vps_capability(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            subprocess.run(["git","init","-q",str(root)],check=True)
            state=root/"state.json"
            calls=[]
            execute_calls=[]
            original_route=m.swarm_route.route_work
            original_execute=m.execute_omen
            try:
                def fake_route(*args,**kwargs):
                    calls.append((args,kwargs))
                    return {"route":"omen","reason":"OMEN_PORTABLE_ADMITTED","decision_id":"test"}
                m.swarm_route.route_work=fake_route
                def fake_execute(*args,**kwargs):
                    execute_calls.append((args,kwargs))
                    return 0
                m.execute_omen=fake_execute
                rc=m.main(["--state",str(state),"--work-id","issue-936","--kind","portable-light","--repo-root",str(root),"--sync-path","tests","--","true"])
            finally:
                m.swarm_route.route_work=original_route
                m.execute_omen=original_execute
            self.assertEqual(rc,0)
            self.assertEqual(calls[0][1].get("allow_vps"),False)
            self.assertEqual(execute_calls[0][1].get("sync_paths"),[Path("tests")])

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

    def test_snapshot_sync_paths_exclude_unrelated_large_files(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            subprocess.run(["git","init","-q",str(root)],check=True)
            subprocess.run(["git","-C",str(root),"config","user.email","test@example.invalid"],check=True)
            subprocess.run(["git","-C",str(root),"config","user.name","Test"],check=True)
            (root/"small").mkdir(); (root/"huge").mkdir()
            (root/"small"/"test.py").write_text("print('ok')\n",encoding="utf-8")
            (root/"small"/"helper.py").write_text("VALUE=1\n",encoding="utf-8")
            (root/"huge"/"content.bin").write_bytes(b"x"*(2*1024*1024))
            subprocess.run(["git","-C",str(root),"add","."],check=True)
            subprocess.run(["git","-C",str(root),"commit","-qm","base"],check=True)
            paths=m.snapshot_paths(root,[Path("small")])
            self.assertEqual({p.as_posix() for p in paths},{"small/helper.py","small/test.py"})
            self.assertLess(m.snapshot_bytes(root,paths),1024)
            self.assertGreater(m.snapshot_bytes(root,m.snapshot_paths(root)),2*1024*1024)

    def test_snapshot_sync_paths_fail_closed_for_unsafe_or_empty_selection(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            subprocess.run(["git","init","-q",str(root)],check=True)
            with self.assertRaisesRegex(ValueError,"SWARM_EXEC_BAD_SYNC_PATH"):
                m.snapshot_paths(root,[Path("../outside")])
            with self.assertRaisesRegex(ValueError,"SWARM_EXEC_SYNC_PATH_EMPTY"):
                m.snapshot_paths(root,[Path("missing")])

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

    def test_cached_manifest_reuses_unchanged_hashes(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); cache=root/"hash-cache.json"
            (root/"a.txt").write_text("a",encoding="utf-8")
            (root/"b.txt").write_text("b",encoding="utf-8")
            paths=[Path("a.txt"),Path("b.txt")]
            first,size1,hits1,misses1=m.cached_snapshot_manifest(root,paths,cache_file=cache)
            self.assertEqual((size1,hits1,misses1),(2,0,2))
            cache_mtime=cache.stat().st_mtime_ns
            second,size2,hits2,misses2=m.cached_snapshot_manifest(root,paths,cache_file=cache)
            self.assertEqual((size2,hits2,misses2),(2,2,0))
            self.assertEqual(first,second)
            self.assertEqual(cache.stat().st_mtime_ns,cache_mtime)
            (root/"a.txt").write_text("z",encoding="utf-8")
            st=(root/"a.txt").stat(); __import__("os").utime(root/"a.txt",ns=(st.st_atime_ns,st.st_mtime_ns+1_000_000))
            third,_size3,hits3,misses3=m.cached_snapshot_manifest(root,paths,cache_file=cache)
            self.assertEqual((hits3,misses3),(1,1))
            self.assertNotEqual(first["a.txt"]["sha256"],third["a.txt"]["sha256"])

    def test_corrupt_local_hash_cache_fails_open_to_rehash(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); cache=root/"hash-cache.json"; cache.write_text("not json",encoding="utf-8")
            (root/"a.txt").write_text("a",encoding="utf-8")
            _manifest,_size,hits,misses=m.cached_snapshot_manifest(root,[Path("a.txt")],cache_file=cache)
            self.assertEqual((hits,misses),(0,1))

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
        self.assertEqual(len(parts),3)
        for part in parts:
            source=part.split("\nPY\n",1)[0]
            compile(source,"<remote-heredoc>","exec")
        self.assertIn("printf '%s\\n' 'SWARM_EXEC_CACHE_MANIFEST {}'",script)
        self.assertIn("index-pack",script)
        self.assertIn("update-index",script)
        self.assertIn("symbolic-ref",script)
        self.assertLess(script.index(m.OMEN_TOOL_ENV),script.index("index-pack"))

    def test_git_provenance_payload_reconstructs_head_branch_and_dirty_status(self):
        import base64, json, shutil
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); src=root/"src"; dst=root/"dst"; src.mkdir(); dst.mkdir()
            subprocess.run(["git","-C",str(src),"init","-q","-b","topic/provenance"],check=True)
            subprocess.run(["git","-C",str(src),"config","user.email","test@example.invalid"],check=True)
            subprocess.run(["git","-C",str(src),"config","user.name","Test"],check=True)
            subprocess.run(["git","-C",str(src),"config","core.autocrlf","true"],check=True)
            subprocess.run(["git","-C",str(src),"config","core.filemode","false"],check=True)
            (src/"sub").mkdir(); (src/"a.txt").write_text("base\n",encoding="utf-8"); (src/"sub"/"b.txt").write_text("bee\n",encoding="utf-8")
            subprocess.run(["git","-C",str(src),"add","."],check=True)
            subprocess.run(["git","-C",str(src),"commit","-qm","base"],check=True)
            base=subprocess.check_output(["git","-C",str(src),"rev-parse","HEAD"],text=True).strip()
            (src/"a.txt").write_text("second\n",encoding="utf-8")
            (src/"sub"/"b.txt").write_text("second bee\n",encoding="utf-8")
            subprocess.run(["git","-C",str(src),"commit","-qam","second"],check=True)
            head=subprocess.check_output(["git","-C",str(src),"rev-parse","HEAD"],text=True).strip()
            (src/"a.txt").write_text("dirty\n",encoding="utf-8"); (src/"new.txt").write_text("new\n",encoding="utf-8")

            payload,size=m.git_provenance_payload(src)
            self.assertEqual(payload["version"],m.GIT_PROVENANCE_VERSION)
            self.assertEqual(payload["head"],head)
            self.assertEqual(payload["branch"],"topic/provenance")
            self.assertEqual(payload["config"]["core.autocrlf"],"true")
            self.assertEqual(payload["config"]["core.filemode"],"false")
            self.assertLess(size,m.MAX_GIT_PROVENANCE_BYTES)
            with self.assertRaisesRegex(
                ValueError, r"SWARM_EXEC_GIT_PROVENANCE_TOO_LARGE bytes=.+ limit=1"
            ):
                m.git_provenance_payload(src, max_bytes=1)
            payload_with_budget,size_with_budget=m.git_provenance_payload(
                src, max_bytes=size + 1
            )
            self.assertEqual(payload_with_budget["head"],head)
            self.assertEqual(size_with_budget,size)
            self.assertNotIn(str(src),json.dumps(payload))

            subprocess.run(["git","-C",str(dst),"init","-q"],check=True)
            for key,value in payload["config"].items():
                subprocess.run(["git","-C",str(dst),"config",key,value],check=True)
            pack=base64.b64decode(payload["pack_b64"],validate=True)
            subprocess.run(["git","-C",str(dst),"index-pack","--stdin","--fix-thin"],input=pack,stdout=subprocess.DEVNULL,check=True)
            subprocess.run(["git","-C",str(dst),"update-index","-z","--index-info"],input=base64.b64decode(payload["index_b64"],validate=True),check=True)
            ref="refs/heads/"+str(payload["branch"])
            subprocess.run(["git","-C",str(dst),"update-ref",ref,head],check=True)
            subprocess.run(["git","-C",str(dst),"symbolic-ref","HEAD",ref],check=True)
            shutil.copy2(src/"a.txt",dst/"a.txt"); (dst/"sub").mkdir(); shutil.copy2(src/"sub"/"b.txt",dst/"sub"/"b.txt"); shutil.copy2(src/"new.txt",dst/"new.txt")

            self.assertEqual(subprocess.check_output(["git","-C",str(dst),"rev-parse","HEAD"],text=True).strip(),head)
            self.assertEqual(subprocess.check_output(["git","-C",str(dst),"symbolic-ref","--short","HEAD"],text=True).strip(),"topic/provenance")
            status=subprocess.check_output(["git","-C",str(dst),"status","--short","--branch"],text=True).splitlines()
            self.assertEqual(status[0],"## topic/provenance")
            self.assertIn(" M a.txt",status)
            self.assertIn("?? new.txt",status)
            self.assertIn("second",subprocess.check_output(["git","-C",str(dst),"log","-1","--oneline"],text=True))
            changed=set(subprocess.check_output(["git","-C",str(dst),"diff","--name-only",f"{base}...{head}"],text=True).splitlines())
            self.assertEqual(changed,{"a.txt","sub/b.txt"})
            working_changed=set(subprocess.check_output(["git","-C",str(dst),"diff","--name-only","HEAD"],text=True).splitlines())
            self.assertEqual(working_changed,{"a.txt"})

    def test_git_provenance_pack_uses_low_compression_and_bounded_cold_timeout(self):
        with tempfile.TemporaryDirectory() as td:
            src=Path(td)/"src"; src.mkdir()
            subprocess.run(["git","-C",str(src),"init","-q","-b","topic/provenance-pack"],check=True)
            subprocess.run(["git","-C",str(src),"config","user.email","test@example.invalid"],check=True)
            subprocess.run(["git","-C",str(src),"config","user.name","Test"],check=True)
            (src/"a.txt").write_text("base\n",encoding="utf-8")
            subprocess.run(["git","-C",str(src),"add","a.txt"],check=True)
            subprocess.run(["git","-C",str(src),"commit","-qm","base"],check=True)
            real_run=m.subprocess.run
            pack_calls=[]
            def recording_run(args,*pargs,**kwargs):
                if "pack-objects" in args:
                    pack_calls.append((list(args),kwargs.get("timeout")))
                return real_run(args,*pargs,**kwargs)
            m.subprocess.run=recording_run
            try:
                m.git_provenance_payload(src)
            finally:
                m.subprocess.run=real_run
            self.assertEqual(len(pack_calls),1)
            args,timeout=pack_calls[0]
            self.assertIn(f"--compression={m.GIT_PROVENANCE_PACK_COMPRESSION}",args)
            self.assertEqual(m.GIT_PROVENANCE_PACK_COMPRESSION,1)
            self.assertEqual(timeout,m.GIT_PROVENANCE_PACK_TIMEOUT_SECONDS)
            self.assertEqual(m.GIT_PROVENANCE_PACK_TIMEOUT_SECONDS,90.0)

    def test_reserved_cache_metadata_name_is_rejected(self):
        with self.assertRaises(ValueError):
            m._safe_manifest_path(m.CACHE_MANIFEST_NAME)

    def test_snapshot_size_counts_selected_files(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/"a").write_bytes(b"123"); (root/"b").write_bytes(b"4567")
            self.assertEqual(m.snapshot_bytes(root,[Path("a"),Path("b")]),7)

if __name__=="__main__": unittest.main()
