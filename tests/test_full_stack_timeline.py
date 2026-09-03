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
    collect_explicit_evidence_events,
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

    def test_explicit_evidence_manifest_ingests_only_declared_valid_events(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            manifest_dir = root / "02 Evidence" / "timeline-events"
            manifest_dir.mkdir(parents=True)
            (root / "proof.json").write_text("{}", encoding="utf-8")
            (manifest_dir / "sample.json").write_text(
                '{"schema":"full-stack-timeline-events.v1","events":['
                '{"id":"repro","event_at":"2026-09-02T19:41:00+03:00","title":"Closure reproduced","epistemic_class":"REPRODUCED_FACT","epistemic_basis":"exact closure replay passed","evidence":["proof.json"],"supersedes":["old"]},'
                '{"id":"bad","event_at":"2026-09-02T19:42:00+03:00","title":"Bad class","epistemic_class":"PROVEN","epistemic_basis":"label only","evidence":["claim.md"]}'
                ']}',
                encoding="utf-8",
            )
            events, errors = collect_explicit_evidence_events(root)
            self.assertEqual([event["id"] for event in events], ["repro"])
            self.assertEqual(events[0]["source_type"], "STRUCTURED_EVIDENCE_EVENT")
            self.assertEqual(events[0]["authority"], "EXPLICIT_EVIDENCE_MANIFEST")
            self.assertEqual(events[0]["epistemic_class"], "REPRODUCED_FACT")
            self.assertEqual(events[0]["supersedes"], ["old"])
            self.assertEqual(len(errors), 1)
            self.assertIn("invalid epistemic_class", errors[0]["error"])

    def test_stronger_explicit_evidence_requires_existing_local_proof(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            manifest_dir = root / "02 Evidence" / "timeline-events"
            manifest_dir.mkdir(parents=True)
            (manifest_dir / "bad.json").write_text(
                '{"schema":"full-stack-timeline-events.v1","events":['
                '{"id":"missing","event_at":"2026-09-02T19:41:00+03:00","title":"Missing local proof","epistemic_class":"REPRODUCED_FACT","epistemic_basis":"claimed replay","evidence":["02 Evidence/missing.json","github:org/repo#1"]},'
                '{"id":"external-only","event_at":"2026-09-02T19:42:00+03:00","title":"External only","epistemic_class":"INFERENCE","epistemic_basis":"claimed inference","evidence":["github:org/repo#1","git:repo:abc"]}'
                ']}',
                encoding="utf-8",
            )
            events, errors = collect_explicit_evidence_events(root)
            self.assertEqual(events, [])
            self.assertEqual(len(errors), 2)
            messages = [error["error"] for error in errors]
            self.assertTrue(any("missing local evidence" in message for message in messages))
            self.assertTrue(any("requires at least one existing Vault-relative evidence file" in message for message in messages))

    def test_stronger_explicit_evidence_records_verified_local_and_external_refs(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            proof = root / "02 Evidence" / "proof.json"
            proof.parent.mkdir(parents=True)
            proof.write_text("{}", encoding="utf-8")
            manifest_dir = proof.parent / "timeline-events"
            manifest_dir.mkdir()
            (manifest_dir / "good.json").write_text(
                '{"schema":"full-stack-timeline-events.v1","events":['
                '{"id":"repro","event_at":"2026-09-02T19:41:00+03:00","title":"Verified replay","epistemic_class":"REPRODUCED_FACT","epistemic_basis":"exact replay passed","evidence":["02 Evidence/proof.json","github:org/repo#1","git:repo:abc"]}'
                ']}',
                encoding="utf-8",
            )
            events, errors = collect_explicit_evidence_events(root)
            self.assertEqual(errors, [])
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["evidence_validation"]["verified_local"], ["02 Evidence/proof.json"])
            self.assertEqual(events[0]["evidence_validation"]["external_refs"], ["github:org/repo#1", "git:repo:abc"])

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
