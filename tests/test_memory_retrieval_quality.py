import json
import unittest
from pathlib import Path

from tools.memory_bank import load_bank, search_context_memory
from tools.memory_hybrid import search_entries_hybrid


ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "memory" / "memory-bank.jsonl"
FIXTURE = ROOT / "tests" / "fixtures" / "memory-retrieval-eval-v1.json"


def _current_expected(entries, expected_ids):
    superseded_by = {}
    for entry in entries:
        for old_id in entry.get("supersedes", []):
            superseded_by.setdefault(str(old_id), []).append(str(entry["id"]))
    resolved = set()
    pending = list(expected_ids)
    seen = set()
    while pending:
        item = pending.pop()
        if item in seen:
            continue
        seen.add(item)
        replacements = superseded_by.get(item, [])
        pending.extend(replacements)
        if not replacements:
            resolved.add(item)
    return resolved


class MemoryRetrievalQualityTests(unittest.TestCase):
    def test_general_retrieval_quality_gate(self):
        entries = load_bank(BANK)
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8-sig"))
        known = {entry["id"] for entry in entries}
        paraphrase_total = paraphrase_hits = 0
        exact_total = exact_hits = 0
        abstain_total = abstain_hits = 0
        for case in fixture["cases"]:
            missing = [item for item in case["expected"] if item not in known]
            self.assertFalse(missing, f"fixture {case['id']} references missing memory IDs: {missing}")
            ids = [hit["id"] for hit in search_entries_hybrid(entries, case["query"], limit=5)]
            expected = _current_expected(entries, case["expected"])
            if case["cohort"] == "paraphrase":
                paraphrase_total += 1
                paraphrase_hits += int(any(item in expected for item in ids[:5]))
            elif case["cohort"] == "exact_control":
                exact_total += 1
                exact_hits += int(bool(ids) and ids[0] in expected)
            elif case["cohort"] == "abstain":
                abstain_total += 1
                abstain_hits += int(not ids)
        self.assertGreaterEqual(paraphrase_hits / paraphrase_total, 0.95)
        self.assertEqual(exact_hits, exact_total)
        self.assertEqual(abstain_hits, abstain_total)

    def test_context_retrieval_is_relevance_based(self):
        entries = [
            {"id": "relevant", "timestamp": "2026-08-27T10:00:00+03:00", "kind": "lesson", "scope": "global", "tags": [],
             "title": "Preserve inherited task", "text": "Preserve inherited task when one detail changes", "state": "PROVEN",
             "evidence": ["user-instruction:test"], "supersedes": [], "behavior_rule": True},
            {"id": "other", "timestamp": "2026-08-27T10:01:00+03:00", "kind": "lesson", "scope": "global", "tags": [],
             "title": "Unrelated cache note", "text": "Unrelated cache cleanup evidence", "state": "PROVEN",
             "evidence": ["incident:test"], "supersedes": []},
        ]
        hits = search_context_memory(entries, "preserve inherited", limit=8)
        self.assertEqual([entry["id"] for entry in hits], ["relevant"])


if __name__ == "__main__":
    unittest.main()
