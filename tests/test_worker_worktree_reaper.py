import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.worker_report_history import _archive_execution_cwd, _schedule_own_worktree_reap, begin_timed_run, create_manual_run
from tools.worker_worktree_reaper import release_own_worktree


class WorkerWorktreeReaperTests(unittest.TestCase):
    def _repo_with_worktree(self, root: Path) -> tuple[Path, Path, str]:
        repo = root / "repo"
        lane = root / "lane"
        subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.invalid"], check=True)
        (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "seed.txt"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "seed"], check=True)
        subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", "-b", "worker/test", str(lane)], check=True)
        head = subprocess.check_output(["git", "-C", str(lane), "rev-parse", "HEAD"], text=True).strip()
        return repo, lane, head

    @patch("tools.worker_worktree_reaper.windows_processes", return_value=[{"ProcessId": 9001, "CommandLine": "idle.exe"}])
    def test_clean_secondary_lane_is_removed_nonforce_and_branch_is_preserved(self, _processes):
        with tempfile.TemporaryDirectory() as d:
            repo, lane, head = self._repo_with_worktree(Path(d))
            result = release_own_worktree(lane)
            self.assertTrue(result["ok"])
            self.assertEqual(result["action"], "REMOVED_OWN_WORKTREE")
            self.assertFalse(lane.exists())
            branch_head = subprocess.check_output(
                ["git", "-C", str(repo), "rev-parse", "refs/heads/worker/test"], text=True
            ).strip()
            self.assertEqual(branch_head, head)

    @patch("tools.worker_worktree_reaper.windows_processes", return_value=[{"ProcessId": 9001, "CommandLine": "idle.exe"}])
    def test_dirty_lane_is_preserved_but_own_ignored_target_is_cleaned(self, _processes):
        with tempfile.TemporaryDirectory() as d:
            _repo, lane, _head = self._repo_with_worktree(Path(d))
            (lane / ".gitignore").write_text("target/\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(lane), "add", ".gitignore"], check=True)
            subprocess.run(["git", "-C", str(lane), "commit", "-q", "-m", "ignore target"], check=True)
            (lane / "dirty.txt").write_text("unique\n", encoding="utf-8")
            (lane / "target").mkdir()
            (lane / "target" / "cache.bin").write_bytes(b"cache")
            result = release_own_worktree(lane)
            self.assertEqual(result["action"], "PRESERVE")
            self.assertEqual(result["reason"], "dirty")
            self.assertEqual(result["cleaned_cache"], ["target"])
            self.assertTrue(lane.exists())
            self.assertTrue((lane / "dirty.txt").exists())
            self.assertFalse((lane / "target").exists())

    @patch("tools.worker_worktree_reaper.windows_processes", return_value=[{"ProcessId": 9001, "CommandLine": "idle.exe"}])
    def test_dirty_p3_lane_reclaims_only_ignored_unreal_generated_cache(self, _processes):
        with tempfile.TemporaryDirectory() as d:
            _repo, lane, _head = self._repo_with_worktree(Path(d))
            (lane / "p3.uproject").write_text("{}\n", encoding="utf-8")
            (lane / ".gitignore").write_text(
                "/Binaries/\n/Intermediate/\n/DerivedDataCache/\n", encoding="utf-8"
            )
            subprocess.run(["git", "-C", str(lane), "add", "p3.uproject", ".gitignore"], check=True)
            subprocess.run(["git", "-C", str(lane), "commit", "-q", "-m", "p3 marker"], check=True)
            (lane / "dirty.txt").write_text("unique\n", encoding="utf-8")
            for name in ("Binaries", "Intermediate", "DerivedDataCache"):
                directory = lane / name
                directory.mkdir()
                (directory / "generated.bin").write_bytes(b"cache")

            result = release_own_worktree(lane)

            self.assertEqual(result["action"], "PRESERVE")
            self.assertEqual(result["reason"], "dirty")
            self.assertEqual(set(result["cleaned_cache"]), {"Binaries", "Intermediate", "DerivedDataCache"})
            self.assertTrue((lane / "dirty.txt").exists())
            self.assertTrue((lane / "p3.uproject").exists())
            self.assertFalse((lane / "Binaries").exists())
            self.assertFalse((lane / "Intermediate").exists())
            self.assertFalse((lane / "DerivedDataCache").exists())

    def test_active_p3_lane_does_not_cleanup_generated_cache(self):
        with tempfile.TemporaryDirectory() as d:
            _repo, lane, _head = self._repo_with_worktree(Path(d))
            (lane / "p3.uproject").write_text("{}\n", encoding="utf-8")
            (lane / ".gitignore").write_text("/Binaries/\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(lane), "add", "p3.uproject", ".gitignore"], check=True)
            subprocess.run(["git", "-C", str(lane), "commit", "-q", "-m", "p3 marker"], check=True)
            (lane / "dirty.txt").write_text("unique\n", encoding="utf-8")
            binaries = lane / "Binaries"
            binaries.mkdir()
            (binaries / "generated.bin").write_bytes(b"cache")
            processes = [{"ProcessId": 9001, "CommandLine": f'build.exe -Project="{lane}\\p3.uproject"'}]
            with patch("tools.worker_worktree_reaper.windows_processes", return_value=processes):
                result = release_own_worktree(lane)
            self.assertEqual(result["reason"], "external_process_targets_path")
            self.assertTrue((binaries / "generated.bin").exists())

    @patch("tools.worker_worktree_reaper.windows_processes", return_value=[{"ProcessId": 9001, "CommandLine": "idle.exe"}])
    def test_primary_worktree_is_never_removed(self, _processes):
        with tempfile.TemporaryDirectory() as d:
            repo, _lane, _head = self._repo_with_worktree(Path(d))
            result = release_own_worktree(repo)
            self.assertEqual(result["action"], "PRESERVE")
            self.assertEqual(result["reason"], "primary_worktree")
            self.assertTrue(repo.exists())

    def test_process_targeted_lane_is_preserved_with_target_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            _repo, lane, _head = self._repo_with_worktree(Path(d))
            (lane / ".gitignore").write_text("target/\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(lane), "add", ".gitignore"], check=True)
            subprocess.run(["git", "-C", str(lane), "commit", "-q", "-m", "ignore target"], check=True)
            (lane / "target").mkdir()
            (lane / "target" / "cache.bin").write_bytes(b"cache")
            processes = [{"ProcessId": 9001, "CommandLine": f'build.exe -Project="{lane}\\p3.uproject"'}]
            with patch("tools.worker_worktree_reaper.windows_processes", return_value=processes):
                result = release_own_worktree(lane)
            self.assertEqual(result["action"], "PRESERVE")
            self.assertEqual(result["reason"], "external_process_targets_path")
            self.assertTrue((lane / "target" / "cache.bin").exists())


    def test_manual_start_records_execution_cwd(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            current = root / "manual" / "current"
            with patch("tools.worker_report_history.Path.cwd", return_value=Path(r"C:\Temp\manual-lane")):
                created = create_manual_run(current, repo="p3", stem="cwd-test")
            report = Path(created["report_path"])
            self.assertIn(r"execution_cwd: C:\Temp\manual-lane", report.read_text(encoding="utf-8"))
            self.assertEqual(_archive_execution_cwd(report), Path(r"C:\Temp\manual-lane"))

    def test_timed_begin_records_execution_cwd_in_start_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            current = root / "worker-reports" / "current"
            current.mkdir(parents=True)
            report = current / "worker123.md"
            now = __import__("datetime").datetime.now().astimezone().isoformat()
            report.write_text(
                "automation_id: worker123\n"
                f"started_at: {now}\n"
                f"last_activity_at: {now}\n"
                "repo: p3\nscope: test\nstate: RUNNING\noutcome: in progress\n"
                "mutation: none\nvalidation: none\nremaining_gate: none\nfinding_tags: none\nfindings: none\n",
                encoding="utf-8",
            )
            with patch("tools.worker_report_history.Path.cwd", return_value=Path(r"C:\Temp\timed-lane")):
                result = begin_timed_run(report)
            payload = __import__("json").loads(Path(result["receipt_path"]).read_text(encoding="utf-8"))
            self.assertEqual(payload["execution_cwd"], r"C:\Temp\timed-lane")
            self.assertEqual(_archive_execution_cwd(report), Path(r"C:\Temp\timed-lane"))

    @patch("tools.worker_report_history.subprocess.Popen")
    def test_archive_cleanup_launch_is_out_of_band_and_hidden(self, popen):
        popen.return_value.pid = 1234
        result = _schedule_own_worktree_reap(Path(r"C:\Temp\worker-lane"))
        self.assertTrue(result["scheduled"])
        self.assertEqual(result["pid"], 1234)
        command = popen.call_args.args[0]
        kwargs = popen.call_args.kwargs
        self.assertIn("worker_worktree_reaper.py", " ".join(str(item) for item in command))
        self.assertIn("--quiet", command)
        self.assertIs(kwargs["stdin"], subprocess.DEVNULL)
        self.assertIs(kwargs["stdout"], subprocess.DEVNULL)
        self.assertIs(kwargs["stderr"], subprocess.DEVNULL)
        if os.name == "nt":
            self.assertTrue(kwargs["creationflags"] & getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))


if __name__ == "__main__":
    unittest.main()
