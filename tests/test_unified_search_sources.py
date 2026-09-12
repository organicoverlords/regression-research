from __future__ import annotations

import json
import pickle
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from tools.stack_atlas import _timeline_discovery_hits
from tools.timeline_materializer import DEFAULT_GITHUB_EVENTS_PER_KIND, DEFAULT_MAX_EVENTS, DEFAULT_REPO_EVENTS, _query_concepts, _rank_query_events
from tools.unified_search_sources import search_gh_buffer_cache


class UnifiedSearchSourcesTests(unittest.TestCase):
    def test_finnish_natural_language_reuses_timeline_concepts(self):
        concepts = _query_concepts("MCP kuvahommeli kommentit")
        self.assertTrue(any("image" in concept for concept in concepts))
        self.assertTrue(any("comment" in concept for concept in concepts))

    def test_materialized_git_hit_exposes_branch_and_commit_label(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            state = root / ".state" / "timeline"
            state.mkdir(parents=True)
            generated = "2026-09-12T02:30:00+03:00"
            event_id = "git:mcp:" + "a" * 40
            (state / "status.json").write_text(json.dumps({
                "generated_at": generated,
                "events": 1,
                "truncated": False,
                "saturated_sources": [],
            }), encoding="utf-8")
            with (state / "timeline-query-index.pkl").open("wb") as handle:
                pickle.dump({
                    "schema": "vault.timeline.query-index.v1",
                    "generated_at": generated,
                    "ids": [event_id],
                    "postings": {"mcp": [0], "image": [0]},
                    "weight_codes": {"mcp": bytes([4]), "image": bytes([5])},
                    "anchors": [["github:organicoverlords/chatgpt-mcp-clean#240"]],
                    "branch_refs": [["chatgpt/240-image-handoff"]],
                    "opaque_labels": {event_id: "Fix same-turn image vision handoff"},
                }, handle)
            hits, coverage = _timeline_discovery_hits("MCP kuvahommeli", limit=5, root=root)
        self.assertEqual(coverage["status"], "OK")
        self.assertEqual(hits[0]["kind"], "git_commit")
        self.assertEqual(hits[0]["label"], "Fix same-turn image vision handoff")
        self.assertEqual(hits[0]["branches"], ["chatgpt/240-image-handoff"])

    def test_gh_buffer_cache_search_is_local_and_searches_cached_body(self):
        with tempfile.TemporaryDirectory() as d:
            cache = Path(d) / "cache.sqlite3"
            connection = sqlite3.connect(cache)
            connection.execute("""
                CREATE TABLE cache_entries (
                    key TEXT PRIMARY KEY, created_at REAL NOT NULL, expires_at REAL NOT NULL,
                    returncode INTEGER NOT NULL, stdout BLOB NOT NULL, stderr BLOB NOT NULL,
                    command_json TEXT NOT NULL, context TEXT NOT NULL
                )
            """)
            payload = {
                "number": 301,
                "title": "Restore Library media persistence for Work",
                "body": "MCP exact image resource and native vision handoff",
                "comments": [{"body": "same-turn exact original image"}],
            }
            command = [
                "issue", "view", "301", "--repo", "organicoverlords/chatgpt-mcp-clean",
                "--json", "number,title,body,comments",
            ]
            now = time.time()
            connection.execute(
                "INSERT INTO cache_entries VALUES (?,?,?,?,?,?,?,?)",
                ("k", now, now + 60, 0, json.dumps(payload).encode(), b"", json.dumps(command),
                 "host=github.com\nrepo=organicoverlords/chatgpt-mcp-clean"),
            )
            connection.commit()
            connection.close()
            hits, coverage = search_gh_buffer_cache("MCP kuvahommeli", cache_path=cache)
        self.assertEqual(coverage["status"], "OK")
        self.assertFalse(coverage["network_fanout"])
        self.assertFalse(coverage["repo_content_scan"])
        self.assertEqual(hits[0]["reference"], "organicoverlords/chatgpt-mcp-clean#301")
        self.assertEqual(hits[0]["label"], "Restore Library media persistence for Work")

    def test_gh_buffer_batch_list_searches_each_cached_issue_independently(self):
        with tempfile.TemporaryDirectory() as d:
            cache = Path(d) / "cache.sqlite3"
            connection = sqlite3.connect(cache)
            connection.execute("""
                CREATE TABLE cache_entries (
                    key TEXT PRIMARY KEY, created_at REAL NOT NULL, expires_at REAL NOT NULL,
                    returncode INTEGER NOT NULL, stdout BLOB NOT NULL, stderr BLOB NOT NULL,
                    command_json TEXT NOT NULL, context TEXT NOT NULL
                )
            """)
            payload = [
                {"number": 240, "title": "Image handoff", "body": "resource link", "comments": []},
                {"number": 301, "title": "Library media", "body": "Work persistence",
                 "comments": [{"body": "Bonsai exact original native vision"}]},
            ]
            command = [
                "issue", "list", "--repo", "organicoverlords/chatgpt-mcp-clean",
                "--state", "all", "--json", "number,title,body,comments",
            ]
            now = time.time()
            connection.execute(
                "INSERT INTO cache_entries VALUES (?,?,?,?,?,?,?,?)",
                ("batch", now, now + 60, 0, json.dumps(payload).encode(), b"", json.dumps(command),
                 "host=github.com\nrepo=organicoverlords/chatgpt-mcp-clean"),
            )
            connection.commit()
            connection.close()
            hits, coverage = search_gh_buffer_cache("Bonsai kommentit native vision", cache_path=cache)
        self.assertEqual(coverage["objects_seen"], 2)
        self.assertEqual(hits[0]["reference"], "organicoverlords/chatgpt-mcp-clean#301")
        self.assertEqual(hits[0]["cache_command"], "issue list")
        self.assertEqual(hits[0]["cached_comment_count"], 1)
        self.assertEqual(hits[0]["cached_content"], "title_body_comments")

    def test_timeline_ranking_prefers_explicit_project_identity(self):
        events = [
            {"id": "p3", "source_type": "GITHUB_ISSUE", "project": "p3", "projects": ["p3"],
             "title": "MCP image handoff", "summary": "native image", "event_at": "2026-09-12T00:00:00Z"},
            {"id": "mcp", "source_type": "GITHUB_ISSUE", "project": "mcp", "projects": ["mcp"],
             "title": "MCP image handoff", "summary": "native image", "event_at": "2026-09-12T00:00:00Z"},
        ]
        ranked = _rank_query_events(events, "MCP kuvahommeli")
        self.assertEqual(ranked[0][1]["id"], "mcp")

    def test_gh_buffer_ranking_prefers_matching_repo_identity(self):
        with tempfile.TemporaryDirectory() as d:
            cache = Path(d) / "cache.sqlite3"
            connection = sqlite3.connect(cache)
            connection.execute("""
                CREATE TABLE cache_entries (
                    key TEXT PRIMARY KEY, created_at REAL NOT NULL, expires_at REAL NOT NULL,
                    returncode INTEGER NOT NULL, stdout BLOB NOT NULL, stderr BLOB NOT NULL,
                    command_json TEXT NOT NULL, context TEXT NOT NULL
                )
            """)
            now = time.time()
            for key, repo in (("p3", "organicoverlords/p3"), ("mcp", "organicoverlords/chatgpt-mcp-clean")):
                payload = [{"number": 1, "title": "MCP image handoff", "body": "native image", "comments": []}]
                command = ["issue", "list", "--repo", repo, "--json", "number,title,body,comments"]
                connection.execute(
                    "INSERT INTO cache_entries VALUES (?,?,?,?,?,?,?,?)",
                    (key, now, now + 60, 0, json.dumps(payload).encode(), b"", json.dumps(command),
                     f"host=github.com\nrepo={repo}"),
                )
            connection.commit()
            connection.close()
            hits, _ = search_gh_buffer_cache("MCP kuvahommeli", limit=2, cache_path=cache)
        self.assertEqual(hits[0]["reference"], "organicoverlords/chatgpt-mcp-clean#1")

    def test_materialized_history_has_large_headroom(self):
        self.assertGreaterEqual(DEFAULT_REPO_EVENTS, 25000)
        self.assertGreaterEqual(DEFAULT_GITHUB_EVENTS_PER_KIND, 25000)
        self.assertGreaterEqual(DEFAULT_MAX_EVENTS, 200000)


if __name__ == "__main__":
    unittest.main()
