import unittest

from tools.memory_hybrid import search_entries_hybrid


class HybridMemoryTests(unittest.TestCase):
    @staticmethod
    def entry(id_, text, *, title="", state="PROVEN", supersedes=None, evidence=None, scope="global", tags=None, ts="2026-08-27T10:00:00+03:00"):
        return {
            "id": id_, "timestamp": ts, "kind": "fact", "scope": scope, "tags": tags or [],
            "title": title, "text": text, "state": state, "evidence": evidence or [], "supersedes": supersedes or [],
        }

    def test_title_and_body_hybrid_prefers_specific_memory(self):
        entries = [
            self.entry("noise", "refresh context background detail", title="Other context note", ts="2026-08-27T11:00:00+03:00"),
            self.entry("target", "A refresh is incomplete until retrieval actually occurs.", title="Refresh requires retrieval before completion", ts="2026-08-27T09:00:00+03:00"),
        ]
        hits = search_entries_hybrid(entries, "when asked to refresh, reread before saying it is done")
        self.assertEqual(hits[0]["id"], "target")

    def test_unrelated_query_with_one_weak_overlap_abstains(self):
        entries = [
            self.entry("root-cause", "Root cause evidence for an MCP regression", title="Hidden root cause"),
            self.entry("other", "Connector reliability evidence", title="Connector evidence"),
        ]
        self.assertEqual(search_entries_hybrid(entries, "orchid repotting sphagnum root aeration"), [])

    def test_rejected_and_superseded_stay_hidden(self):
        old = self.entry("old", "connector route failed", title="Old connector route")
        new = self.entry("new", "connector route correction", title="Correct connector route", supersedes=["old"])
        rejected = self.entry("bad", "connector route correction", title="Rejected connector route", state="REJECTED")
        ids = [e["id"] for e in search_entries_hybrid([old, rejected, new], "correct connector route")]
        self.assertEqual(ids, ["new"])

    def test_ephemeral_and_sensitive_memory_stay_hidden(self):
        ephemeral = self.entry("ephemeral", "worker tool checkpoint", title="Tool checkpoint")
        ephemeral["kind"] = "status"
        ephemeral["scope"] = "tool-availability/checkpoint"
        secret = self.entry("secret", "token=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890 worker tool checkpoint", title="Secret checkpoint")
        current = self.entry("current", "worker tool checkpoint durable rule", title="Durable checkpoint rule")
        ids = [e["id"] for e in search_entries_hybrid([ephemeral, secret, current], "worker tool checkpoint")]
        self.assertEqual(ids, ["current"])

    def test_expired_memory_stays_hidden(self):
        expired = self.entry("expired", "connector routing target", title="Connector target")
        expired["expires_at"] = "2026-08-01T00:00:00+03:00"
        current = self.entry("current", "connector routing target", title="Connector target")
        current["expires_at"] = "2099-08-01T00:00:00+03:00"
        ids = [e["id"] for e in search_entries_hybrid([expired, current], "connector routing target")]
        self.assertEqual(ids, ["current"])

    def test_deterministic(self):
        entries = [
            self.entry("a", "tool connection task process survives", title="Connection process continuity"),
            self.entry("b", "tool connection failed", title="Connection failure"),
        ]
        first = [e["id"] for e in search_entries_hybrid(entries, "connection disappeared but process survives")]
        second = [e["id"] for e in search_entries_hybrid(entries, "connection disappeared but process survives")]
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
