import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.repo_timeline import RepoSpec, collect_repo_history, discover_repo_specs, git_commit_events, parse_repo_arg


class RepoTimelineTests(unittest.TestCase):
    def make_repo(self, root: Path) -> Path:
        repo = root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", "https://github.com/example/project.git"], check=True)
        return repo

    def commit(self, repo: Path, name: str, title: str, stamp: str) -> str:
        (repo / name).write_text(title, encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", name], check=True)
        env = dict(os.environ, GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", title], check=True, env=env)
        return subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True, encoding="utf-8").strip()

    def test_git_commit_events_are_read_only_bounded_and_keep_issue_refs(self):
        with tempfile.TemporaryDirectory() as d:
            repo = self.make_repo(Path(d))
            old = self.commit(repo, "a.txt", "initial", "2026-08-28T10:00:00+03:00")
            new = self.commit(repo, "b.txt", "fix HUD acceptance (#617)", "2026-08-29T01:00:00+03:00")
            before = subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True)
            events = git_commit_events(RepoSpec("p3", repo), limit=1)
            after = subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True)
            self.assertEqual(before, after)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["sha"], new)
            self.assertEqual(events[0]["project"], "p3")
            self.assertEqual(events[0]["refs"], ["#617"])
            self.assertEqual(events[0]["source_type"], "GIT_COMMIT")
            self.assertEqual(events[0]["authority"], "REPO_HISTORY")
            self.assertEqual(events[0]["repo_state"], "UNKNOWN")
            self.assertNotEqual(events[0]["sha"], old)

    def test_mainline_and_lane_commits_are_distinguished(self):
        with tempfile.TemporaryDirectory() as d:
            repo = self.make_repo(Path(d))
            main = self.commit(repo, "main.txt", "mainline", "2026-08-28T10:00:00+03:00")
            subprocess.run(["git", "-C", str(repo), "update-ref", "refs/remotes/origin/main", main], check=True)
            lane = self.commit(repo, "lane.txt", "worker lane", "2026-08-29T01:00:00+03:00")
            events = git_commit_events(RepoSpec("p3", repo), limit=5)
            by_sha = {event["sha"]: event for event in events}
            self.assertEqual(by_sha[main]["repo_state"], "MAINLINE")
            self.assertTrue(by_sha[main]["on_origin_main"])
            self.assertEqual(by_sha[lane]["repo_state"], "LANE")
            self.assertFalse(by_sha[lane]["on_origin_main"])

    def test_busy_lane_cannot_crowd_mainline_out_of_small_window(self):
        with tempfile.TemporaryDirectory() as d:
            repo = self.make_repo(Path(d))
            main = self.commit(repo, "main.txt", "landed", "2026-08-28T10:00:00+03:00")
            subprocess.run(["git", "-C", str(repo), "update-ref", "refs/remotes/origin/main", main], check=True)
            self.commit(repo, "lane1.txt", "lane one", "2026-08-29T01:00:00+03:00")
            newest_lane = self.commit(repo, "lane2.txt", "lane two", "2026-08-29T02:00:00+03:00")
            events = git_commit_events(RepoSpec("p3", repo), limit=1)
            self.assertEqual(len(events), 2)
            by_state = {event["repo_state"]: event for event in events}
            self.assertEqual(by_state["MAINLINE"]["sha"], main)
            self.assertEqual(by_state["LANE"]["sha"], newest_lane)

    def test_operator_live_is_only_repo_path_discovery(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            repo = self.make_repo(root)
            operator = root / "operator-live.json"
            operator.write_text(json.dumps({
                "repos": [{"id": "tiny3d", "path": str(repo), "available": True}],
                "recent_progress": [{"project": "tiny3d", "sha": "fabricated", "title": "must not be consumed"}],
            }), encoding="utf-8")
            specs = discover_repo_specs(operator)
            self.assertEqual(specs, [RepoSpec("tiny3d", repo)])
            history = collect_repo_history(specs, limit_per_repo=5)
            self.assertEqual(history["events"], [])
            self.assertEqual(history["repo_snapshots"][0]["project"], "tiny3d")

    def test_collect_repo_history_reads_actual_local_git_not_external_projection(self):
        with tempfile.TemporaryDirectory() as d:
            repo = self.make_repo(Path(d))
            sha = self.commit(repo, "real.txt", "real commit #42", "2026-08-29T01:00:00+03:00")
            history = collect_repo_history([RepoSpec("lowvram", repo)], limit_per_repo=5)
            self.assertEqual(history["events"][0]["sha"], sha)
            self.assertEqual(history["events"][0]["refs"], ["#42"])
            self.assertEqual(history["contract"], "local Git history only; no network fetch and no memory authority")

    def test_missing_repo_degrades_without_blocking_other_repos(self):
        with tempfile.TemporaryDirectory() as d:
            repo = self.make_repo(Path(d))
            sha = self.commit(repo, "ok.txt", "ok", "2026-08-29T01:00:00+03:00")
            history = collect_repo_history([
                RepoSpec("missing", Path(d) / "does-not-exist"), RepoSpec("p3", repo),
            ], limit_per_repo=3)
            self.assertEqual(history["events"][0]["sha"], sha)
            self.assertFalse(history["repo_snapshots"][0]["available"])
            self.assertTrue(history["repo_snapshots"][1]["available"])

    def test_explicit_repo_argument_is_simple_shared_input(self):
        spec = parse_repo_arg(r"p3=C:\work\p3")
        self.assertEqual(spec.project, "p3")
        self.assertEqual(str(spec.path), r"C:\work\p3")
        with self.assertRaises(ValueError):
            parse_repo_arg("not-a-pair")

    def test_source_has_no_busy_coordinator_or_network_client_dependency(self):
        source = (Path(__file__).resolve().parents[1] / "tools" / "repo_timeline.py").read_text(encoding="utf-8")
        lowered = source.casefold()
        self.assertNotIn("busycoordinator", lowered)
        self.assertNotIn("busy_claim", lowered)
        self.assertNotIn("requests.", lowered)
        self.assertNotIn("urllib", lowered)
        self.assertNotIn("gh ", lowered)
