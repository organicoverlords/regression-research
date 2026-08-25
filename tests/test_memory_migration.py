import json
import tempfile
import unittest
from pathlib import Path

from tools.migrate_memory_bank import migrate_candidates


class MemoryMigrationTests(unittest.TestCase):
    def e(self,id_,text,state="PROVEN",evidence=None,scope="mcp",supersedes=None):
        return {"id":id_,"timestamp":"2026-08-25T10:00:00+03:00","kind":"lesson","scope":scope,"tags":["test"],"text":text,"state":state,"evidence":evidence or [],"supersedes":supersedes or []}

    def test_exact_semantic_duplicates_collapse_and_merge_evidence(self):
        a=self.e("a","Research after unexpected MCP failure.",evidence=["incident:1"])
        b=self.e("b","Research after unexpected MCP failure.",evidence=["issue:7"])
        out=migrate_candidates([a,b])
        self.assertEqual(len(out),1)
        self.assertEqual(set(out[0]["evidence"]),{"incident:1","issue:7"})

    def test_conflicting_claims_are_preserved(self):
        a=self.e("a","A hard 6KB MCP threshold exists.",state="REJECTED")
        b=self.e("b","A hard 6KB MCP threshold is not supported by current evidence.",state="PROVEN")
        self.assertEqual(len(migrate_candidates([a,b])),2)

    def test_supersedes_is_preserved(self):
        e=self.e("new","Path trigger is unproven.",supersedes=["old"])
        self.assertEqual(migrate_candidates([e])[0]["supersedes"],["old"])


if __name__ == "__main__": unittest.main()
