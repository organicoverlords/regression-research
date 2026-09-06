from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.memory_bank import BankError, _append_entry_file, _bank_has_id
from tools.memory_timeline import _case_anchors, _event_anchors
from tools.timeline_materializer import (
    SCHEMA,
    _atomic_json,
    _atomic_pickle,
    _event_query_fields,
    _query_cache_key,
    _read_query_result_cache,
    _refresh_cached_query_result,
    _write_query_result_cache,
    QUERY_INDEX_SCHEMA,
    _query_index_candidate_ids,
    _read_query_index,
    _rank_query_events,
    _rank_query_events_indexed,
    load_materialized,
)


class MemoryWriteHotPathTests(unittest.TestCase):
    def test_duplicate_lookup_is_exact_without_decoding_bank(self):
        with tempfile.TemporaryDirectory() as td:
            bank = Path(td) / "bank.jsonl"
            bank.write_text('{ "id" : "mem-unicode-åäö", "value": 1 }\n', encoding="utf-8")
            self.assertTrue(_bank_has_id(bank, "mem-unicode-åäö"))
            self.assertFalse(_bank_has_id(bank, "mem-unicode-åä"))

    def test_nested_id_does_not_false_positive_as_entry_id(self):
        with tempfile.TemporaryDirectory() as td:
            bank = Path(td) / "bank.jsonl"
            bank.write_text('{"id":"outer","metadata":{"id":"nested-only"}}\n', encoding="utf-8")
            self.assertFalse(_bank_has_id(bank, "nested-only"))
            self.assertTrue(_bank_has_id(bank, "outer"))

    def test_append_does_not_parse_entire_bank_and_still_rejects_duplicate(self):
        with tempfile.TemporaryDirectory() as td:
            bank = Path(td) / "bank.jsonl"
            bank.write_text('{"id":"existing","value":1}\n', encoding="utf-8")
            with patch("tools.memory_bank._read_bank_file", side_effect=AssertionError("full parse not allowed")):
                _append_entry_file(bank, {"id": "new", "value": 2})
                with self.assertRaises(BankError):
                    _append_entry_file(bank, {"id": "existing", "value": 3})


class TimelineDerivedCacheTests(unittest.TestCase):
    def test_anchor_helpers_reuse_materialized_values(self):
        event = {
            "_all_anchors_cache": ["github:x#1", "artifact:a"],
            "case_anchors": ["THREAD:ABC", "artifact:a"],
            "evidence": ["this would be expensive to parse"],
        }
        self.assertEqual(_event_anchors(event), ["github:x#1", "artifact:a"])
        self.assertEqual(_case_anchors(event), ["artifact:a", "thread:abc"])

    def test_query_field_cache_preserves_weighted_tokens(self):
        event = {"_query_fields_cache": [[4.0, ["alpha"]], [2.0, ["beta"]], [1.2, []], [2.2, ["gamma"]], [0.7, ["delta"]]]}
        fields = _event_query_fields(event)
        self.assertEqual(fields[0], (4.0, {"alpha"}))
        self.assertEqual(fields[-1], (0.7, {"delta"}))

    def test_compact_query_index_validates_generation_and_candidates(self):
        with tempfile.TemporaryDirectory() as td:
            index_path = Path(td) / "timeline-query-index.pkl"
            payload = {
                "schema": QUERY_INDEX_SCHEMA,
                "generated_at": "g1",
                "ids": ["a", "b", "c"],
                "postings": {"regression": [0, 2], "incident": [1]},
                "weight_codes": {"regression": bytes([5, 3]), "incident": bytes([5])},
                "anchors": [["artifact:a"], [], ["thread:c"]],
            }
            _atomic_pickle(index_path, payload)
            loaded = _read_query_index(index_path, generated_at="g1")
            self.assertIsNotNone(loaded)
            self.assertEqual(_query_index_candidate_ids(loaded, "regression"), {"a", "b", "c"})
            self.assertIsNone(_read_query_index(index_path, generated_at="g2"))

    def test_rank_corpus_override_preserves_full_candidate_rarity(self):
        events = [
            {"id": "a", "title": "regression", "source_type": "VAULT_MEMORY"},
            {"id": "b", "title": "incident", "source_type": "VAULT_MEMORY"},
        ]
        normal = _rank_query_events(events, "regression")
        expanded = _rank_query_events(events, "regression", corpus_size_override=20)
        self.assertEqual([event["id"] for _, event in normal], [event["id"] for _, event in expanded])
        self.assertGreater(expanded[0][0], normal[0][0])

    def test_indexed_rank_matches_baseline_rank_exactly(self):
        events = [
            {"id": "a", "title": "regression incident", "summary": "alpha", "source_type": "VAULT_MEMORY", "event_at": "2026-09-06T10:00:00+03:00"},
            {"id": "b", "title": "incident", "summary": "regression", "source_type": "WORKER_REPORT", "event_at": "2026-09-06T11:00:00+03:00"},
            {"id": "c", "title": "unrelated", "summary": "noise", "source_type": "GIT_COMMIT", "event_at": "2026-09-06T12:00:00+03:00"},
        ]
        # regression concept expands to regression+incident. Codes preserve each token's best field weight.
        index = {
            "ids": ["a", "b", "c"],
            "postings": {"regression": [0, 1], "incident": [0, 1]},
            "weight_codes": {"regression": bytes([5, 3]), "incident": bytes([5, 5])},
            "anchors": [[], [], []],
        }
        baseline = _rank_query_events(events, "regression", corpus_size_override=3)
        indexed = _rank_query_events_indexed(events, "regression", index, corpus_size_override=3)
        self.assertIsNotNone(indexed)
        self.assertEqual([event["id"] for _, event in baseline], [event["id"] for _, event in indexed])
        for (left_score, _), (right_score, _) in zip(baseline, indexed):
            self.assertAlmostEqual(left_score, right_score, places=10)



class TimelineQueryResultCacheTests(unittest.TestCase):
    def test_cached_result_refreshes_materialized_age_without_recomputing_query(self):
        from datetime import datetime, timedelta
        as_of = datetime.now().astimezone() - timedelta(seconds=30)
        result = {
            "materialized": {
                "as_of": as_of.isoformat(),
                "stale_after_seconds": 60.0,
                "absence_unsafe_reasons": [],
            }
        }
        refreshed = _refresh_cached_query_result(result, 2.5)
        self.assertGreaterEqual(refreshed["materialized"]["age_seconds"], 29.0)
        self.assertLess(refreshed["materialized"]["age_seconds"], 32.0)
        self.assertEqual(refreshed["materialized"]["status"], "FRESH")
        self.assertTrue(refreshed["query_cache"]["used"])
        self.assertEqual(refreshed["query_cache"]["age_seconds"], 2.5)

    def test_identical_query_key_is_stable_and_cache_is_local(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            key1 = _query_cache_key("generation", query="  Regression ", view="general", project="P3", thread=None, days=7, limit=20, include_workers=True)
            key2 = _query_cache_key("generation", query="regression", view="general", project="p3", thread=None, days=7, limit=20, include_workers=True)
            self.assertEqual(key1, key2)
            result = {"matching_events": 7, "events": [{"id": "x"}]}
            _write_query_result_cache(root, key1, result)
            cached, age = _read_query_result_cache(root, key1)
            self.assertEqual(cached, result)
            self.assertIsNotNone(age)
            self.assertLess(age, 1.0)


if __name__ == "__main__":
    unittest.main()
