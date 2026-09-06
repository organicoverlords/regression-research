import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from tools.repo_timeline import RepoSpec, collect_repo_history, discover_repo_specs, git_commit_events, parse_repo_arg, tracked_artifact_events


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
            self.assertEqual(events[0]["repo_state"], "ALL_BRANCHES")
            self.assertNotEqual(events[0]["sha"], old)

    def test_all_branch_history_preserves_reachable_commits_without_main_privilege(self):
        with tempfile.TemporaryDirectory() as d:
            repo = self.make_repo(Path(d))
            older = self.commit(repo, "older.txt", "older integration commit", "2026-08-28T10:00:00+03:00")
            subprocess.run(["git", "-C", str(repo), "update-ref", "refs/remotes/origin/main", older], check=True)
            newer = self.commit(repo, "newer.txt", "worker branch commit", "2026-08-29T01:00:00+03:00")
            subprocess.run(["git", "-C", str(repo), "branch", "worker/topic", newer], check=True)
            events = git_commit_events(RepoSpec("p3", repo), limit=5)
            by_sha = {event["sha"]: event for event in events}
            self.assertIn(older, by_sha)
            self.assertIn(newer, by_sha)
            self.assertEqual(by_sha[older]["repo_state"], "ALL_BRANCHES")
            self.assertEqual(by_sha[newer]["repo_state"], "ALL_BRANCHES")
            self.assertNotIn("on_origin_main", by_sha[older])

    def test_small_window_returns_newest_commit_across_all_branches(self):
        with tempfile.TemporaryDirectory() as d:
            repo = self.make_repo(Path(d))
            self.commit(repo, "old.txt", "old", "2026-08-28T10:00:00+03:00")
            self.commit(repo, "mid.txt", "mid", "2026-08-29T01:00:00+03:00")
            newest = self.commit(repo, "new.txt", "newest", "2026-08-29T02:00:00+03:00")
            events = git_commit_events(RepoSpec("p3", repo), limit=1)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["sha"], newest)

    def test_tracked_artifact_events_project_reports_logs_screenshots_and_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            repo = self.make_repo(Path(d))
            report = repo / "01 Reports" / "2026-09-04_INC-20260904-TEST_incident_report.md"
            screenshot = repo / "02 Evidence" / "2026-09-04_binding.png"
            log = repo / "02 Evidence" / "routing-events.jsonl"
            for path, content in ((report, "incident"), (screenshot, "png"), (log, "{}\n")):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            (repo / "provenance.json").write_text(json.dumps({
                "entries": [{
                    "incident_id": "INC-20260904-TEST",
                    "report_path": "01 Reports/2026-09-04_INC-20260904-TEST_incident_report.md",
                    "title": "Binding incident",
                    "evidence_type": "evidence_bounded_incident_report",
                    "raw_transcripts": [],
                    "evidence_files": ["02 Evidence/2026-09-04_binding.png", "02 Evidence/routing-events.jsonl"],
                    "contract_snapshots": [],
                }]
            }), encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            env = dict(os.environ, GIT_AUTHOR_DATE="2026-09-04T22:03:00+03:00", GIT_COMMITTER_DATE="2026-09-04T22:03:00+03:00")
            subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "preserve binding evidence (#511)"], check=True, env=env)

            events = tracked_artifact_events(repo, limit=20)
            by_path = {event["path"]: event for event in events}
            self.assertEqual(by_path[report.relative_to(repo).as_posix()]["artifact_type"], "report")
            self.assertEqual(by_path[report.relative_to(repo).as_posix()]["incident_id"], "INC-20260904-TEST")
            self.assertIn("incident", by_path[report.relative_to(repo).as_posix()]["evidence_type"])
            self.assertEqual(by_path[screenshot.relative_to(repo).as_posix()]["artifact_type"], "screenshot")
            self.assertEqual(by_path[log.relative_to(repo).as_posix()]["artifact_type"], "evidence_log")
            self.assertEqual(by_path[report.relative_to(repo).as_posix()]["title"], "report: Binding incident")
            self.assertIn("incident:inc-20260904-test", by_path[screenshot.relative_to(repo).as_posix()]["anchors"])
            self.assertIn("artifact:02 evidence/2026-09-04_binding.png", by_path[screenshot.relative_to(repo).as_posix()]["anchors"])
            self.assertEqual(by_path[screenshot.relative_to(repo).as_posix()]["authority"], "PRESERVED_REPO_ARTIFACT_HISTORY")

    def test_tracked_artifact_events_ignore_untracked_files(self):
        with tempfile.TemporaryDirectory() as d:
            repo = self.make_repo(Path(d))
            tracked = repo / "01 Reports" / "tracked.md"
            tracked.parent.mkdir(parents=True, exist_ok=True)
            tracked.write_text("tracked", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "tracked report"], check=True)
            untracked = repo / "02 Evidence" / "untracked.log"
            untracked.parent.mkdir(parents=True, exist_ok=True)
            untracked.write_text("wip", encoding="utf-8")
            paths = {event["path"] for event in tracked_artifact_events(repo, limit=20)}
            self.assertIn("01 Reports/tracked.md", paths)
            self.assertNotIn("02 Evidence/untracked.log", paths)

    def test_repo_timeline_owns_product_roots_without_importing_stack_atlas(self):
        import tools.repo_timeline as repo_timeline
        import tools.stack_atlas as stack_atlas

        self.assertEqual(set(repo_timeline.PRODUCT_ROOTS), {"lowvram", "tiny3d", "p3", "mcp", "agents"})
        original = dict(repo_timeline.PRODUCT_ROOTS)
        with patch.object(stack_atlas, "PRODUCT_ROOTS", {"sentinel": r"C:\definitely-not-a-product-root"}, create=True):
            self.assertEqual(repo_timeline.PRODUCT_ROOTS, original)
        source = (Path(__file__).resolve().parents[1] / "tools" / "repo_timeline.py").read_text(encoding="utf-8")
        self.assertNotIn("from .stack_atlas import PRODUCT_ROOTS", source)
        self.assertNotIn("from stack_atlas import PRODUCT_ROOTS", source)

    def test_repo_discovery_uses_canonical_product_roots_without_projection(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            repo = self.make_repo(root)
            with patch("tools.repo_timeline.PRODUCT_ROOTS", {"tiny3d": str(repo), "missing": str(root / "missing")}):
                specs = discover_repo_specs()
            self.assertEqual(specs, [RepoSpec("tiny3d", repo)])
            history = collect_repo_history(specs, limit_per_repo=5)
            self.assertEqual(history["events"], [])

    def test_collect_repo_history_reads_actual_local_git_not_external_projection(self):
        with tempfile.TemporaryDirectory() as d:
            repo = self.make_repo(Path(d))
            sha = self.commit(repo, "real.txt", "real commit #42", "2026-08-29T01:00:00+03:00")
            history = collect_repo_history([RepoSpec("lowvram", repo)], limit_per_repo=5)
            self.assertEqual(history["events"][0]["sha"], sha)
            self.assertEqual(history["events"][0]["refs"], ["#42"])
            self.assertIn("local Git history only; no network fetch and no memory authority", history["contract"])
            self.assertFalse(history["coverage"]["lowvram"]["saturated"])

    def test_missing_repo_degrades_without_blocking_other_repos(self):
        with tempfile.TemporaryDirectory() as d:
            repo = self.make_repo(Path(d))
            sha = self.commit(repo, "ok.txt", "ok", "2026-08-29T01:00:00+03:00")
            history = collect_repo_history([
                RepoSpec("missing", Path(d) / "does-not-exist"), RepoSpec("p3", repo),
            ], limit_per_repo=3)
            self.assertEqual(history["events"][0]["sha"], sha)

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
