import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.full_stack_timeline import (
    EPISTEMIC_CLASSES,
    RepoSpec,
    _epistemic_counts,
    _project_explicit_relationships,
    collect_all_commit_events,
    collect_document_sources,
    collect_git_state,
    collect_memory_events,
    checkout_mutation_admission,
)


class FullStackTimelineTests(unittest.TestCase):
    def make_repo(self, root: Path) -> Path:
        repo = root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
        (repo / "README.md").write_text("# Read me", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
        env = dict(os.environ, GIT_AUTHOR_DATE="2026-09-01T10:00:00+03:00", GIT_COMMITTER_DATE="2026-09-01T10:00:00+03:00")
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "initial"], check=True, env=env)
        return repo
    def test_git_state_includes_branches_tags_stashes_worktrees_and_reflog(self):
        with tempfile.TemporaryDirectory() as d:
            repo = self.make_repo(Path(d))
            subprocess.run(["git", "-C", str(repo), "branch", "experiment"], check=True)
            subprocess.run(["git", "-C", str(repo), "tag", "v1"], check=True)
            (repo / "dirty.txt").write_text("dirty", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "dirty.txt"], check=True)
            subprocess.run(["git", "-C", str(repo), "stash", "push", "-m", "saved lesson"], check=True, capture_output=True)
            state = collect_git_state("demo", repo, reflog_limit=10)
            self.assertIn("experiment", state["branches"])
            self.assertIn("v1", state["tags"])
            self.assertTrue(any("saved lesson" in row["subject"] for row in state["stashes"]))
            self.assertTrue(state["worktrees"])
            self.assertTrue(state["reflog"])
            self.assertEqual(state["authority"], "LOCAL_GIT_OBJECT_DATABASE")

    def test_dirty_checkout_is_not_direct_stack_mutation_source(self):
        state = {"available": True, "dirty_entries": 3, "head": "aaa", "origin_main": "bbb", "branch": "main"}
        result = checkout_mutation_admission(state)
        self.assertEqual(result["decision"], "ISOLATED_WORKTREE_REQUIRED")
        self.assertIn("dirty_checkout", result["reasons"])
        self.assertFalse(result["direct_mutation_admitted"])

    def test_clean_current_base_is_directly_admitted(self):
        state = {"available": True, "dirty_entries": 0, "head": "aaa", "origin_main": "aaa", "branch": "main"}
        result = checkout_mutation_admission(state)
        self.assertEqual(result["decision"], "DIRECT_MUTATION_ADMITTED")
        self.assertTrue(result["direct_mutation_admitted"])

    def test_document_inventory_classifies_durable_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for rel in ["README.md", "CHANGELOG.md", "01 Reports/red-alert_bug_report.md", "03 Fixtures and Experiments/repro.json"]:
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("x", encoding="utf-8")
            docs = collect_document_sources(root)
            by_name = {Path(item["path"]).name: item for item in docs}
            self.assertEqual(by_name["README.md"]["category"], "project_document")
            self.assertEqual(by_name["CHANGELOG.md"]["category"], "project_document")
            self.assertEqual(by_name["red-alert_bug_report.md"]["category"], "incident_or_audit")
            self.assertEqual(by_name["repro.json"]["category"], "fixture_or_experiment")
            self.assertTrue(all(item["epistemic_class"] == "HISTORICAL_CLAIM" for item in docs))
            self.assertEqual(by_name["repro.json"]["epistemic_class"], "HISTORICAL_CLAIM")

    def test_git_commit_metadata_is_observed_fact_not_claimed_effect(self):
        with tempfile.TemporaryDirectory() as d:
            repo = self.make_repo(Path(d))
            events = collect_all_commit_events(RepoSpec("demo", repo))
            self.assertEqual(events[0]["epistemic_class"], "OBSERVED_FACT")
            self.assertEqual(events[0]["epistemic_basis"], "commit object metadata observed in local Git")

    def test_memory_claims_preserve_explicit_supersession_without_upgrading_truth(self):
        with tempfile.TemporaryDirectory() as d:
            bank = Path(d) / "memory-bank.jsonl"
            bank.write_text(
                '{"id":"old","timestamp":"2026-09-01T10:00:00+03:00","title":"old claim"}\n'
                '{"id":"new","timestamp":"2026-09-02T10:00:00+03:00","title":"correction","supersedes":["old"],"contradicts":["other"]}\n',
                encoding="utf-8",
            )
            events = collect_memory_events(bank)
            self.assertTrue(all(event["epistemic_class"] == "HISTORICAL_CLAIM" for event in events))
            projected, relationships = _project_explicit_relationships(events)
            by_id = {event["id"]: event for event in projected}
            self.assertEqual(by_id["old"]["superseded_by"], ["new"])
            self.assertTrue(all(rel["explicit"] for rel in relationships))
            self.assertEqual({rel["relation"] for rel in relationships}, {"SUPERSEDES", "CONTRADICTS"})

    def test_epistemic_counts_keep_unobserved_classes_visible(self):
        counts = _epistemic_counts([{"epistemic_class": "OBSERVED_FACT"}])
        self.assertEqual(tuple(counts), EPISTEMIC_CLASSES)
        self.assertEqual(counts["OBSERVED_FACT"], 1)
        self.assertEqual(counts["REPRODUCED_FACT"], 0)
        self.assertEqual(counts["INFERENCE"], 0)
        self.assertEqual(counts["HISTORICAL_CLAIM"], 0)

    def test_mutation_admission_rejects_dirty_or_stale_checkout(self):
        with tempfile.TemporaryDirectory() as d:
            repo = self.make_repo(Path(d))
            head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
            subprocess.run(["git", "-C", str(repo), "update-ref", "refs/remotes/origin/main", head], check=True)
            clean = collect_git_state("demo", repo)
            self.assertEqual(clean["mutation_admission"]["status"], "DIRECT_OK")
            (repo / "dirty.txt").write_text("x", encoding="utf-8")
            dirty = collect_git_state("demo", repo)
            self.assertEqual(dirty["mutation_admission"]["status"], "ISOLATE_REQUIRED")
            self.assertIn("dirty_checkout", dirty["mutation_admission"]["reasons"])
            subprocess.run(["git", "-C", str(repo), "add", "dirty.txt"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "lane"], check=True)
            stale = collect_git_state("demo", repo)
            self.assertEqual(stale["mutation_admission"]["status"], "ISOLATE_REQUIRED")
            self.assertIn("head_differs_from_origin_main", stale["mutation_admission"]["reasons"])
