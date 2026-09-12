import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.runtime_dependency_graph import (
    _arg_paths,
    _comparison,
    _task_runtime_info,
    build_surface,
    explain_runtime_dependency_node,
    runtime_dependency_path,
    runtime_graph_for_components,
    search_runtime_dependency_graph,
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class RuntimeDependencyGraphTests(unittest.TestCase):
    def test_windows_task_argument_paths_are_extracted_without_enumerating_tasks(self):
        args = (
            '"C:\\Users\\Lauri\\AppData\\Local\\VaultBootstrapSnapshot\\bootstrap_read_loop.py" '
            '--once --atlas-path "C:\\Users\\Lauri\\AppData\\Local\\VaultBootstrapSnapshot\\stack_atlas.py"'
        )
        self.assertEqual(
            _arg_paths(args),
            [
                r"C:\Users\Lauri\AppData\Local\VaultBootstrapSnapshot\bootstrap_read_loop.py",
                r"C:\Users\Lauri\AppData\Local\VaultBootstrapSnapshot\stack_atlas.py",
            ],
        )

    def test_bootstrap_surface_maps_source_runtime_tasks_outputs_and_detects_drift(self):
        with tempfile.TemporaryDirectory() as raw_root, tempfile.TemporaryDirectory() as raw_local:
            root = Path(raw_root)
            local = Path(raw_local)
            (root / "tools").mkdir()
            (root / ".state" / "bootstrap").mkdir(parents=True)
            runtime = local / "VaultBootstrapSnapshot"
            runtime.mkdir()
            source_bytes = {
                "tools/bootstrap_read_loop.py": b"producer-v2\n",
                "tools/memory_recent_projection.py": b"helper-v2\n",
                "tools/stack_atlas.py": b"atlas-v2\n",
                "tools/install_bootstrap_snapshot_task.ps1": b"installer\n",
            }
            for rel, data in source_bytes.items():
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            (runtime / "bootstrap_read_loop.py").write_bytes(source_bytes["tools/bootstrap_read_loop.py"])
            (runtime / "memory_recent_projection.py").write_bytes(source_bytes["tools/memory_recent_projection.py"])
            (runtime / "stack_atlas.py").write_bytes(source_bytes["tools/stack_atlas.py"])
            (root / ".state" / "bootstrap" / "latest.json").write_text("{}", encoding="utf-8")
            (root / ".state" / "bootstrap" / "producer-status.json").write_text("{}", encoding="utf-8")
            task_rows = {
                "VaultBootstrapSnapshot": {
                    "TaskName": "VaultBootstrapSnapshot", "Exists": True, "State": "Ready", "LastTaskResult": 0,
                    "Actions": [{"Execute": str(runtime / "bootstrap_read_loop.py"), "Arguments": "", "WorkingDirectory": str(root)}],
                },
                "VaultBootstrapSnapshotWatchdog": {
                    "TaskName": "VaultBootstrapSnapshotWatchdog", "Exists": True, "State": "Ready", "LastTaskResult": 0,
                    "Actions": [{"Execute": str(runtime / "bootstrap_read_loop.py"), "Arguments": "", "WorkingDirectory": str(root)}],
                },
            }
            desired = {rel: _sha(data) for rel, data in source_bytes.items()}

            def desired_blob(_root, _ref, relpath):
                return desired.get(relpath)

            def clean_blob(_root, _relpath, path, *, apply_filters=True):
                return _sha(Path(path).read_bytes()) if path and Path(path).is_file() else None

            with patch.dict(os.environ, {"LOCALAPPDATA": str(local)}), \
                    patch("tools.runtime_dependency_graph._git_blob_oid", side_effect=desired_blob), \
                    patch("tools.runtime_dependency_graph._file_git_blob_oid", side_effect=clean_blob):
                surface = build_surface(
                    "vault.bootstrap_snapshot", root=root, task_rows=task_rows,
                    task_coverage={"status": "INJECTED", "broad_enumeration": False},
                )
                self.assertEqual(surface["status"], "OK")
                by_key = {node["key"]: node for node in surface["nodes"]}
                self.assertEqual(by_key["runtime:producer"]["deployment"]["status"], "MATCH")
                self.assertEqual(
                    by_key["runtime:producer"]["deployment"]["deployment_mechanism"],
                    "PRODUCER_BUNDLE_SYNC_FROM_CACHED_ORIGIN_MAIN",
                )
                self.assertEqual(by_key["runtime:producer"]["deployment"]["desired_ref"], "refs/remotes/origin/main")
                self.assertEqual(by_key["runtime:atlas"]["deployment"]["status"], "MATCH")
                self.assertEqual(
                    by_key["runtime:atlas"]["deployment"]["deployment_mechanism"],
                    "PRODUCER_BUNDLE_SYNC_FROM_CACHED_ORIGIN_MAIN",
                )
                task_edge = next(
                    edge for edge in surface["edges"]
                    if edge["relation"] == "EXECUTES" and edge["from"].endswith("task:VaultBootstrapSnapshot")
                )
                self.assertTrue(task_edge["observed_action_match"])
                self.assertEqual(task_edge["provenance"]["evidence_class"], "DECLARED")
                self.assertEqual(task_edge["verification"]["evidence_class"], "OBSERVED")
                self.assertEqual(task_edge["verification"]["status"], "MATCH")
                deploy_edge = next(
                    edge for edge in surface["edges"]
                    if edge["from"].endswith("source:producer") and edge["to"].endswith("runtime:producer")
                )
                self.assertEqual(deploy_edge["provenance"]["evidence_class"], "DECLARED")
                self.assertEqual(deploy_edge["verification"]["evidence_class"], "DERIVED")
                self.assertEqual(deploy_edge["verification"]["status"], "MATCH")
                self.assertTrue(any(edge["relation"] == "EXPOSED_AS" for edge in surface["edges"]))

                (runtime / "stack_atlas.py").write_bytes(b"stale-atlas\n")
                drifted = build_surface(
                    "vault.bootstrap_snapshot", root=root, task_rows=task_rows,
                    task_coverage={"status": "INJECTED", "broad_enumeration": False},
                )
                self.assertEqual(drifted["status"], "DRIFT")
                drift_node = next(node for node in drifted["nodes"] if node["key"] == "runtime:atlas")
                self.assertEqual(drift_node["deployment"]["status"], "DRIFT")
                self.assertEqual(
                    drift_node["deployment"]["comparison_basis"],
                    "GIT_REF:refs/remotes/origin/main:tools/stack_atlas.py",
                )

                (runtime / "stack_atlas.py").write_bytes(source_bytes["tools/stack_atlas.py"])
                (runtime / "bootstrap_read_loop.py").write_bytes(b"older-producer-copy\n")
                producer_drift = build_surface(
                    "vault.bootstrap_snapshot", root=root, task_rows=task_rows,
                    task_coverage={"status": "INJECTED", "broad_enumeration": False},
                )
                producer_node = next(node for node in producer_drift["nodes"] if node["key"] == "runtime:producer")
                self.assertEqual(producer_drift["status"], "DRIFT")
                self.assertEqual(producer_node["deployment"]["status"], "DRIFT")
                self.assertEqual(
                    producer_node["deployment"]["comparison_basis"],
                    "GIT_REF:refs/remotes/origin/main:tools/bootstrap_read_loop.py",
                )

    def test_timeline_surface_resolves_commit_addressed_task_runtime_and_siblings(self):
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            source_names = [
                "timeline_materializer.py", "memory_bank.py", "memory_git_sync.py",
                "memory_timeline.py", "repo_timeline.py", "worker_report_history.py",
            ]
            for name in source_names:
                path = root / "tools" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((name + "\n").encode())
            pin = "abcdef1234567890"
            runtime_tools = root / "runtime" / pin / "tools"
            runtime_tools.mkdir(parents=True)
            for name in source_names:
                (runtime_tools / name).write_bytes((name + "\n").encode())
            task_rows = {
                "Vault Timeline Materializer": {
                    "TaskName": "Vault Timeline Materializer", "Exists": True, "State": "Ready", "LastTaskResult": 0,
                    "Actions": [{"Execute": str(runtime_tools / "timeline_materializer.py"), "Arguments": "", "WorkingDirectory": str(root)}],
                }
            }

            def desired_blob(_root, ref, relpath):
                self.assertEqual(ref, pin)
                return _sha((Path(relpath).name + "\n").encode())

            def clean_blob(_root, _relpath, path, *, apply_filters=True):
                return _sha(Path(path).read_bytes()) if path and Path(path).is_file() else None

            with patch("tools.runtime_dependency_graph._git_blob_oid", side_effect=desired_blob), \
                    patch("tools.runtime_dependency_graph._file_git_blob_oid", side_effect=clean_blob):
                surface = build_surface(
                    "vault.timeline_materializer", root=root, task_rows=task_rows,
                    task_coverage={"status": "INJECTED", "broad_enumeration": False},
                )
            self.assertEqual(surface["status"], "OK")
            by_key = {node["key"]: node for node in surface["nodes"]}
            self.assertEqual(by_key["runtime:entry"]["deployment"]["pinned_commit"], pin)
            self.assertEqual(Path(by_key["runtime:repo_timeline"]["resolved_path"]), runtime_tools / "repo_timeline.py")
            self.assertEqual(by_key["runtime:worker_history"]["deployment"]["status"], "MATCH")

    def test_git_ref_runtime_comparison_uses_exact_blob_bytes_not_autocrlf_filters(self):
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "config", "core.autocrlf", "true"], check=True)
            runtime = root / "runtime-stack-atlas.py"
            runtime.write_bytes(b"line-one\r\nline-two\r\n")

            exact = subprocess.check_output(
                ["git", "-C", str(root), "hash-object", "--no-filters", str(runtime)], text=True
            ).strip()
            filtered = subprocess.check_output(
                ["git", "-C", str(root), "hash-object", "--path=tools/stack_atlas.py", str(runtime)], text=True
            ).strip()
            self.assertNotEqual(exact, filtered)

            with patch("tools.runtime_dependency_graph._git_blob_oid", return_value=exact):
                result = _comparison(
                    root, "tools/stack_atlas.py", runtime, "refs/remotes/origin/main"
                )

            self.assertEqual(result["status"], "MATCH")
            self.assertEqual(result["runtime_exact_blob"], exact)
            self.assertEqual(result["runtime_clean_blob"], filtered)
            self.assertEqual(result["runtime_comparison_blob"], exact)
            self.assertEqual(result["comparison_mode"], "EXACT_RUNTIME_BYTES_VS_GIT_BLOB")

    def test_pinned_worktree_copy_uses_clean_filtered_runtime_against_pinned_commit(self):
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "config", "core.autocrlf", "true"], check=True)
            pin = "a" * 40
            runtime = root / "runtime" / pin / "worktree_hygiene_task.py"
            runtime.parent.mkdir(parents=True)
            runtime.write_bytes(b"line-one\r\nline-two\r\n")
            exact = subprocess.check_output(
                ["git", "-C", str(root), "hash-object", "--no-filters", str(runtime)], text=True
            ).strip()
            filtered = subprocess.check_output(
                ["git", "-C", str(root), "hash-object", "--path=tools/worktree_hygiene_task.py", str(runtime)], text=True
            ).strip()
            self.assertNotEqual(exact, filtered)
            with patch("tools.runtime_dependency_graph._git_blob_oid", return_value=filtered):
                result = _comparison(
                    root, "tools/worktree_hygiene_task.py", runtime, "pinned_worktree_copy"
                )
        self.assertEqual(result["status"], "MATCH")
        self.assertEqual(result["pinned_commit"], pin)
        self.assertEqual(result["runtime_exact_blob"], exact)
        self.assertEqual(result["runtime_clean_blob"], filtered)
        self.assertEqual(result["runtime_comparison_blob"], filtered)
        self.assertEqual(result["comparison_mode"], "GIT_CLEAN_FILTERED_RUNTIME_VS_PINNED_GIT_BLOB")
        self.assertEqual(result["deployment_mechanism"], "COMMIT_ADDRESSED_WORKTREE_COPY")

    def test_worktree_hygiene_surface_maps_immutable_bundle_and_health_result_without_false_drift(self):
        with tempfile.TemporaryDirectory() as raw_root, tempfile.TemporaryDirectory() as raw_local:
            root = Path(raw_root)
            local = Path(raw_local)
            (root / "tools").mkdir()
            pin = "b" * 40
            runtime = local / "VaultWorktreeHygiene" / "runtime" / pin
            runtime.mkdir(parents=True)
            names = [
                "worktree_hygiene_task.py", "worktree_hygiene_guard.py",
                "cleanup_converger.py", "live_swarm.py",
            ]
            source_bytes = {f"tools/{name}": (name + "\n").encode() for name in names}
            source_bytes["tools/Install-WorktreeHygieneTask.ps1"] = b"installer\n"
            for rel, data in source_bytes.items():
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            for name in names:
                (runtime / name).write_bytes(source_bytes[f"tools/{name}"])
            latest = local / "VaultWorktreeHygiene" / "latest.json"
            latest.write_text('{"status":"degraded"}', encoding="utf-8")
            task_rows = {
                "VaultWorktreeHygiene": {
                    "TaskName": "VaultWorktreeHygiene", "Exists": True, "State": "Ready",
                    "Enabled": True, "LastTaskResult": 3, "LastRunTime": "now", "NextRunTime": "next",
                    "RuntimeInfoStatus": "OK",
                    "Actions": [{
                        "Execute": "pythonw.exe",
                        "Arguments": f'"{runtime / "worktree_hygiene_task.py"}"',
                        "WorkingDirectory": str(runtime),
                    }],
                }
            }
            desired = {rel: _sha(data) for rel, data in source_bytes.items()}

            def desired_blob(_root, ref, relpath):
                self.assertEqual(ref, pin)
                return desired.get(relpath)

            def clean_blob(_root, _relpath, path, *, apply_filters=True):
                return _sha(Path(path).read_bytes()) if path and Path(path).is_file() else None

            with patch.dict(os.environ, {"LOCALAPPDATA": str(local)}), \
                    patch("tools.runtime_dependency_graph._git_blob_oid", side_effect=desired_blob), \
                    patch("tools.runtime_dependency_graph._file_git_blob_oid", side_effect=clean_blob):
                surface = build_surface(
                    "vault.worktree_hygiene", root=root, task_rows=task_rows,
                    task_coverage={"status": "INJECTED", "broad_enumeration": False},
                )
                self.assertEqual(surface["status"], "OK")
                self.assertEqual(surface["operational_health"]["status"], "degraded")
                by_key = {node["key"]: node for node in surface["nodes"]}
                task = by_key["task:VaultWorktreeHygiene"]
                self.assertEqual(task["observation"]["last_task_result"], 3)
                self.assertEqual(task["observation"]["state"], "Ready")
                self.assertEqual(task["result_meaning"], "DEGRADED_HEALTH_STATE")
                self.assertEqual(task["result_semantics"]["3"], "DEGRADED_HEALTH_STATE")
                self.assertIn("not task-definition drift", task["result_semantics"]["note"])
                for key in ("runtime:entry", "runtime:guard", "runtime:cleanup", "runtime:live_swarm"):
                    deployment = by_key[key]["deployment"]
                    self.assertEqual(deployment["status"], "MATCH")
                    self.assertEqual(deployment["pinned_commit"], pin)
                    self.assertEqual(
                        deployment["comparison_mode"],
                        "GIT_CLEAN_FILTERED_RUNTIME_VS_PINNED_GIT_BLOB",
                    )
                self.assertEqual(Path(by_key["output:latest"]["resolved_path"]), latest)
                self.assertEqual(
                    by_key["output:latest"]["observation"]["json_projection"]["fields"]["status"],
                    "degraded",
                )
                self.assertTrue(any(
                    edge["relation"] == "EXECUTES" and edge.get("observed_action_match")
                    for edge in surface["edges"]
                ))

                (runtime / "worktree_hygiene_guard.py").write_bytes(b"stale\n")
                drifted = build_surface(
                    "vault.worktree_hygiene", root=root, task_rows=task_rows,
                    task_coverage={"status": "INJECTED", "broad_enumeration": False},
                )
                self.assertEqual(drifted["status"], "DRIFT")
                guard = next(node for node in drifted["nodes"] if node["key"] == "runtime:guard")
                self.assertEqual(guard["deployment"]["status"], "DRIFT_FROM_PINNED_INSTALL_SOURCE")

    def test_task_runtime_info_reads_one_exact_verbose_task_row(self):
        csv_row = (
            '"KONE","\\\\VaultWorktreeHygiene","12.9.2026 18.44.16","Ready","Interactive only",'
            '"12.9.2026 18.43.17","3","N/A","pythonw.exe task.py","runtime","N/A","Enabled"\n'
        )
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=csv_row, stderr="")
        with patch("tools.runtime_dependency_graph.subprocess.run", return_value=completed) as run:
            result = _task_runtime_info("VaultWorktreeHygiene")
        self.assertEqual(result["RuntimeInfoStatus"], "OK")
        self.assertEqual(result["State"], "Ready")
        self.assertEqual(result["LastTaskResult"], 3)
        self.assertTrue(result["Enabled"])
        args = run.call_args.args[0]
        self.assertEqual(
            args,
            ["schtasks.exe", "/Query", "/TN", "VaultWorktreeHygiene", "/V", "/FO", "CSV", "/NH"],
        )

    def test_runtime_explain_requires_exact_disambiguation_and_returns_edge_evidence(self):
        with tempfile.TemporaryDirectory() as raw_root, tempfile.TemporaryDirectory() as raw_local:
            root = Path(raw_root)
            with patch.dict(os.environ, {"LOCALAPPDATA": raw_local}):
                ambiguous = explain_runtime_dependency_node(
                    "source:installer", root=root, probe_live=False
                )
                exact = explain_runtime_dependency_node(
                    "vault.bootstrap_snapshot:runtime:producer", root=root, probe_live=False
                )

        self.assertEqual(ambiguous["status"], "AMBIGUOUS")
        self.assertEqual(ambiguous["resolution"]["match_mode"], "EXACT_KEY")
        self.assertEqual(
            [row["id"] for row in ambiguous["resolution"]["candidates"]],
            [
                "vault.bootstrap_snapshot:source:installer",
                "vault.checkout_sync:source:installer",
                "vault.worktree_hygiene:source:installer",
            ],
        )
        self.assertEqual(exact["status"], "OK")
        self.assertEqual(exact["resolution"]["match_mode"], "EXACT_NODE_ID")
        self.assertEqual(exact["node"]["id"], "vault.bootstrap_snapshot:runtime:producer")
        self.assertTrue(exact["incoming"])
        self.assertTrue(all("provenance" in edge for edge in exact["incoming"] + exact["outgoing"]))

    def test_runtime_path_is_deterministic_directed_and_preserves_provenance(self):
        with tempfile.TemporaryDirectory() as raw_root, tempfile.TemporaryDirectory() as raw_local:
            root = Path(raw_root)
            with patch.dict(os.environ, {"LOCALAPPDATA": raw_local}):
                first = runtime_dependency_path(
                    "vault.bootstrap_snapshot:source:producer",
                    "vault.bootstrap_snapshot:consumer:bootstrap_alias",
                    root=root,
                    probe_live=False,
                )
                second = runtime_dependency_path(
                    "vault.bootstrap_snapshot:source:producer",
                    "vault.bootstrap_snapshot:consumer:bootstrap_alias",
                    root=root,
                    probe_live=False,
                )
                no_path = runtime_dependency_path(
                    "vault.checkout_sync:source:installer",
                    "vault.timeline_materializer:consumer:memory",
                    root=root,
                    probe_live=False,
                )

        self.assertEqual(first, second)
        self.assertEqual(first["status"], "OK")
        self.assertEqual(first["distance"], 3)
        self.assertEqual(
            [hop["relation"] for hop in first["hops"]],
            ["PRODUCER_BUNDLE_SYNCS_FROM_CACHED_ORIGIN_MAIN", "WRITES", "EXPOSED_AS"],
        )
        self.assertTrue(all(hop["provenance"]["evidence_class"] == "DECLARED" for hop in first["hops"]))
        self.assertEqual(no_path["status"], "NO_PATH")
        self.assertEqual(no_path["hops"], [])

    def test_runtime_path_output_is_hash_seed_invariant(self):
        with tempfile.TemporaryDirectory() as raw_root, tempfile.TemporaryDirectory() as raw_local:
            script = (
                "import json; from pathlib import Path; "
                "from tools.runtime_dependency_graph import runtime_dependency_path; "
                f"value=runtime_dependency_path('vault.bootstrap_snapshot:source:producer',"
                f"'vault.bootstrap_snapshot:consumer:bootstrap_alias',root=Path({raw_root!r}),probe_live=False); "
                "print(json.dumps(value,sort_keys=True,separators=(',',':')))"
            )
            outputs = []
            for seed in ("1", "777"):
                env = os.environ.copy()
                env["PYTHONHASHSEED"] = seed
                env["LOCALAPPDATA"] = raw_local
                cp = subprocess.run(
                    [sys.executable, "-c", script],
                    cwd=str(Path(__file__).resolve().parents[1]),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=20,
                    env=env,
                )
                self.assertEqual(cp.returncode, 0, cp.stderr)
                outputs.append(cp.stdout.strip())
        self.assertEqual(outputs[0], outputs[1])

    def test_checkout_sync_surface_exposes_exact_missing_task_and_source_chain(self):
        task_rows = {
            "VaultCheckoutSync": {
                "TaskName": "VaultCheckoutSync", "Exists": False, "Actions": [],
            }
        }
        hits, coverage = search_runtime_dependency_graph(
            "VaultCheckoutSync origin/main refresh", root=Path.cwd(), limit=3,
            task_rows=task_rows, probe_live=True,
        )
        self.assertEqual([hit["surface_id"] for hit in hits], ["vault.checkout_sync"])
        surface = hits[0]
        self.assertEqual(surface["status"], "DEGRADED")
        by_key = {node["key"]: node for node in surface["nodes"]}
        self.assertFalse(by_key["task:VaultCheckoutSync"]["observation"]["exists"])
        self.assertTrue(by_key["source:sync"]["resolved_path"].endswith("tools\\Sync-VaultCheckout.ps1"))
        self.assertTrue(any(edge["relation"] == "REFRESHES_CACHED_REF" for edge in surface["edges"]))
        self.assertFalse(coverage["broad_task_enumeration"])

    def test_search_and_component_lookup_use_same_runtime_surface_model(self):
        with patch("tools.runtime_dependency_graph.probe_tasks", return_value=({}, {"status": "INJECTED", "broad_enumeration": False})):
            hits, coverage = search_runtime_dependency_graph(
                "VaultBootstrapSnapshot runtime copy", root=Path.cwd(), limit=2
            )
            graph = runtime_graph_for_components(["bootstrap_snapshot"], root=Path.cwd(), probe_live=False)
        self.assertTrue(hits)
        self.assertEqual(hits[0]["surface_id"], "vault.bootstrap_snapshot")
        self.assertEqual(graph["surfaces"][0]["surface_id"], "vault.bootstrap_snapshot")
        self.assertEqual(
            {surface["surface_id"] for surface in graph["surfaces"]},
            {"vault.bootstrap_snapshot", "vault.checkout_sync"},
        )
        self.assertFalse(coverage["broad_task_enumeration"])
        self.assertFalse(coverage["network_fanout"])


if __name__ == "__main__":
    unittest.main()