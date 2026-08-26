import json
import tempfile
import unittest
from pathlib import Path

from tools.memory_bank import BankError, search_entries, validate_entry, source_relevance


class MemoryRankingAndBudgetTests(unittest.TestCase):
    def e(self, id_, text, *, evidence=None, scope="global", tags=None, ts="2026-08-25T10:00:00+03:00"):
        return {"id":id_,"timestamp":ts,"kind":"fact","scope":scope,"tags":tags or [],"text":text,"state":"PROVEN","evidence":evidence or [],"supersedes":[]}

    def test_verified_current_source_beats_recovery_source_when_relevance_is_equal(self):
        current=self.e("current","MCP routing failure classification",evidence=["github:organicoverlords/chatgpt-mcp-clean#7"],ts="2026-08-20T10:00:00+03:00")
        recovery=self.e("legacy","MCP routing failure classification",evidence=["legacy-seed:chatgpt-memory-seed.md"],ts="2026-08-25T10:00:00+03:00")
        hits=search_entries([recovery,current],"MCP routing failure",limit=5)
        self.assertEqual(hits[0]["id"],"current")
        self.assertGreater(source_relevance(current),source_relevance(recovery))

    def test_source_authority_never_creates_relevance(self):
        unrelated=self.e("user","Preferred response tone is concise",evidence=["user-instruction:2026-08-25"])
        relevant=self.e("mcp","MCP routing failure",evidence=["legacy-seed:chatgpt-memory-seed.md"])
        hits=search_entries([unrelated,relevant],"MCP routing")
        self.assertEqual([h["id"] for h in hits],["mcp"])

    def test_blank_unscoped_search_returns_nothing(self):
        entries=[self.e(str(i),f"entry {i}") for i in range(20)]
        self.assertEqual(search_entries(entries,""),[])

    def test_default_recall_is_capped_at_five(self):
        entries=[self.e(str(i),"shared matching topic",ts=f"2026-08-{i+1:02d}T10:00:00+03:00") for i in range(12)]
        self.assertEqual(len(search_entries(entries,"shared matching topic")),5)

    def test_requested_recall_limit_is_hard_capped_at_eight(self):
        entries=[self.e(str(i),"shared matching topic",ts=f"2026-08-{i+1:02d}T10:00:00+03:00") for i in range(12)]
        self.assertEqual(len(search_entries(entries,"shared matching topic",limit=999)),8)

    def test_history_can_expand_but_is_hard_capped_at_twenty(self):
        entries=[self.e(str(i),"history topic",ts=f"2026-08-{(i%25)+1:02d}T10:00:00+03:00") for i in range(30)]
        self.assertEqual(len(search_entries(entries,"history topic",limit=999,history=True)),20)

    def test_entry_size_limits_prevent_single_record_flood(self):
        validate_entry(self.e("boundary","x"*2000))
        e=self.e("x","x"*2001)
        with self.assertRaises(BankError): validate_entry(e)
        e=self.e("x","ok",tags=[f"t{i}" for i in range(13)])
        with self.assertRaises(BankError): validate_entry(e)


if __name__ == "__main__": unittest.main()
