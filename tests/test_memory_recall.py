import json
import tempfile
import unittest
from pathlib import Path

from tools.memory_bank import append_entry, search_entries, load_bank


class MemoryBankRecallTests(unittest.TestCase):
    def entry(self, id_, ts, text, *, scope="global", tags=None, state="PROVEN", supersedes=None):
        return {"id":id_,"timestamp":ts,"kind":"fact","scope":scope,"tags":tags or [],"text":text,"state":state,"evidence":[],"supersedes":supersedes or []}

    def test_append_generates_id_and_timestamp(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"bank.jsonl"
            e=append_entry(p,{"kind":"lesson","scope":"mcp","tags":["routing"],"text":"Research after unexpected failure.","state":"PROVEN","evidence":[],"supersedes":[]})
            self.assertRegex(e["id"],r"^mem-\d{8}-[a-f0-9]{8}$")
            self.assertIn("+",e["timestamp"])
            self.assertEqual(load_bank(p)[0]["id"],e["id"])

    def test_scope_tag_text_ranking_and_recency(self):
        es=[
          self.entry("a","2026-08-20T10:00:00+03:00","MCP routing lesson",scope="mcp",tags=["safety"]),
          self.entry("b","2026-08-25T10:00:00+03:00","Other routing note",scope="mcp",tags=["other"]),
          self.entry("c","2026-08-24T10:00:00+03:00","MCP safety blocks",scope="global",tags=["safety"]),
        ]
        r=search_entries(es,"MCP safety",scope="mcp",tags=["safety"],limit=3)
        self.assertEqual(r[0]["id"],"a")

    def test_rejected_and_superseded_hidden_by_default(self):
        old=self.entry("old","2026-08-20T10:00:00+03:00","6KB threshold",state="REJECTED")
        replaced=self.entry("x","2026-08-21T10:00:00+03:00","old path theory")
        new=self.entry("new","2026-08-22T10:00:00+03:00","path theory unproven",supersedes=["x"])
        self.assertEqual([e["id"] for e in search_entries([old,replaced,new],"theory")],["new"])
        hist=search_entries([old,replaced,new],"",history=True,limit=10)
        self.assertEqual({e["id"] for e in hist},{"old","x","new"})


if __name__ == "__main__": unittest.main()
