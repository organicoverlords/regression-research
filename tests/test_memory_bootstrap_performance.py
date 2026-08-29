import unittest
from datetime import datetime
from unittest.mock import patch

import tools.memory_authority as memory_authority
import tools.memory_timeline as memory_timeline
from tools.memory_bank import load_bank


def legacy_behavioral_context(entries):
    selected = []
    for entry in memory_authority.current_entries(entries):
        authority = memory_authority.behavioral_authority(entry)
        if not authority["may_change_behavior"]:
            continue
        stamp = datetime.fromisoformat(str(entry["timestamp"]).replace("Z", "+00:00"))
        selected.append((
            int(authority["precedence"]),
            stamp,
            str(entry.get("id") or ""),
            memory_authority.annotate_memory(entry),
        ))
    selected.sort(key=lambda item: (-item[0], -item[1].timestamp(), item[2]))
    return [entry for _, _, _, entry in selected]


class MemoryBootstrapPerformanceTests(unittest.TestCase):
    def test_optimized_bootstrap_matches_legacy_logical_payload(self):
        entries = load_bank()
        optimized = memory_timeline.build_behavior_bootstrap(entries)
        with patch.object(memory_timeline, "behavioral_context", side_effect=legacy_behavioral_context):
            legacy = memory_timeline.build_behavior_bootstrap(entries)
        self.assertEqual(optimized, legacy)

    def test_behavioral_context_classifies_only_authoritative_candidates_once(self):
        entries = load_bank()
        original = memory_authority.classify_entry
        classified_ids = []

        def tracked(entry):
            classified_ids.append(str(entry.get("id") or ""))
            return original(entry)

        with patch.object(memory_authority, "classify_entry", side_effect=tracked):
            selected = memory_authority.behavioral_context(entries)

        authoritative_ids = {
            str(entry.get("id") or "")
            for entry in entries
            if memory_authority.behavioral_authority(entry)["may_change_behavior"]
        }
        self.assertTrue(selected)
        self.assertTrue(classified_ids)
        self.assertEqual(len(classified_ids), len(set(classified_ids)))
        self.assertTrue(set(classified_ids).issubset(authoritative_ids))


if __name__ == "__main__":
    unittest.main()
