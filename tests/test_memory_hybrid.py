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

    def test_long_generic_library_queries_do_not_inject_visual_transport_memory(self):
        visual = self.entry(
            "visual",
            "Use the shared visual library to inspect the same stored proof image instead of rediscovering transport.",
            title="Shared visual proof library",
        )
        visual["kind"] = "correction"
        visual["tags"] = ["assistant-recorded", "verbatim-source"]
        visual["source_messages"] = ["make the stored proof easy to show here"]
        visual["turn_task"] = "Implement durable visual proof library integration."
        visual["interpretation"] = "Expose prior proof through one stable transport path."
        visual["confidence"] = 100
        visual["confidence_reason"] = "Explicit correction."

        self.assertEqual(
            search_entries_hybrid([visual], "which python standard library module handles a filesystem path", strict_admission=True),
            [],
        )
        self.assertEqual(
            search_entries_hybrid([visual], "how should a software library expose its public api", strict_admission=True),
            [],
        )
        self.assertEqual(
            search_entries_hybrid([visual], "explain image transport over a network protocol", strict_admission=True),
            [],
        )

    def test_rich_shared_proof_paraphrase_still_recalls_visual_library_memory(self):
        visual = self.entry(
            "visual",
            "Use the shared visual library to inspect the same stored proof image instead of rediscovering transport.",
            title="Shared visual proof library",
        )
        hits = search_entries_hybrid(
            [visual],
            "use the same stored visual proof in chat instead of rebuilding the transfer path",
            strict_admission=True,
        )
        self.assertEqual([entry["id"] for entry in hits], ["visual"])

    def test_proof_scoped_picture_synonyms_match_image_wording_without_consumer_photo_leakage(self):
        visual = self.entry(
            "visual",
            "Use the shared visual library to inspect the same stored proof image.",
            title="Shared visual proof library",
        )
        visual["kind"] = "correction"
        self.assertEqual(
            [entry["id"] for entry in search_entries_hybrid([visual], "stored proof picture", strict_admission=True)],
            ["visual"],
        )
        self.assertEqual(
            [entry["id"] for entry in search_entries_hybrid([visual], "old proof photo", strict_admission=True)],
            ["visual"],
        )
        self.assertEqual(search_entries_hybrid([visual], "store family photos", strict_admission=True), [])
        self.assertEqual(search_entries_hybrid([visual], "picture library", strict_admission=True), [])

    def test_proof_history_aliases_require_recurrence_and_visual_surface(self):
        history = self.entry(
            "history",
            "Consult project history and prior attempts before inventing a new visual transport path for proof retrieval.",
            title="Consult prior proof integration history",
        )
        history["kind"] = "correction"

        for query in (
            "previous proof path",
            "earlier proof transport",
            "last proof setup",
            "past visual proof",
            "prior proof path",
        ):
            with self.subTest(query=query):
                self.assertEqual(
                    [entry["id"] for entry in search_entries_hybrid([history], query, strict_admission=True)],
                    ["history"],
                )

        for query in (
            "previous proof method",
            "past proof theorem",
            "previous deployment path",
            "last family photo",
        ):
            with self.subTest(query=query):
                self.assertEqual(search_entries_hybrid([history], query, strict_admission=True), [])

    def test_strict_context_drops_recurrence_glue_without_losing_semantic_recall(self):
        visual = self.entry(
            "visual",
            "Use the shared visual library to inspect the same stored proof image.",
            title="Shared visual proof library",
        )
        noise = self.entry(
            "noise",
            "The same reassurance failure happened again after proof was requested.",
            title="Repeated reassurance failure",
        )
        error = self.entry("error", "The routing error repeated after recovery.", title="Routing error recurrence")

        ids = [
            entry["id"]
            for entry in search_entries_hybrid([noise, visual], "same proof image again", strict_admission=True)
        ]
        self.assertEqual(ids[0], "visual")
        self.assertEqual(search_entries_hybrid([noise, visual], "same picture again", strict_admission=True), [])
        self.assertEqual(
            [entry["id"] for entry in search_entries_hybrid([error], "same routing error again", strict_admission=True)],
            ["error"],
        )

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

    def test_preserved_correction_fields_are_searchable_without_changing_state(self):
        for field, value, query in (
            ("source_messages", ["walking animation keeps resetting"], "walking animation resetting"),
            ("interpretation", "all roster causes remain unproven", "roster causes unproven"),
            ("turn_task", "compare generated pawn bindings", "generated pawn bindings"),
        ):
            with self.subTest(field=field):
                entry = self.entry("correction", "Measured inputs differ from defaults.", state="PROVISIONAL")
                entry[field] = value
                hits = search_entries_hybrid([entry], query)
                self.assertEqual([hit["id"] for hit in hits], ["correction"])
                self.assertEqual(hits[0]["state"], "PROVISIONAL")

    def test_natural_recurrence_and_dimension_paraphrases_match(self):
        recurrence = self.entry("recurrence", "walking animation keeps resetting", scope="p3:2610")
        dimensions = self.entry("dimensions", "mesh height measured after V2 cutover", scope="p3:2610")
        self.assertEqual(
            [hit["id"] for hit in search_entries_hybrid([recurrence], "walking repeatedly restarts")],
            ["recurrence"],
        )
        self.assertEqual(
            [hit["id"] for hit in search_entries_hybrid([dimensions], "p3 character body size wrong")],
            ["dimensions"],
        )
    def test_source_wording_does_not_reorder_canonical_hits(self):
        canonical = self.entry(
            "canonical",
            "A connector can disappear while the command process still survives.",
            title="Tool loss does not imply process loss",
        )
        source_only = self.entry("source-only", "Measured inputs differ from defaults.", title="Later correction")
        source_only["source_messages"] = ["connector disappeared command job died"]
        hits = search_entries_hybrid([source_only, canonical], "connector disappeared command job died", limit=2)
        self.assertEqual([hit["id"] for hit in hits], ["canonical", "source-only"])

    def test_source_wording_does_not_restore_rejected_or_sensitive_entries(self):
        rejected = self.entry("rejected", "Measured inputs differ.", state="REJECTED")
        rejected["source_messages"] = ["walking animation keeps resetting"]
        expired = self.entry("expired", "Measured inputs differ.")
        expired["source_messages"] = ["walking animation keeps resetting"]
        expired["expires_at"] = "2020-01-01T00:00:00+00:00"
        self.assertEqual(search_entries_hybrid([rejected, expired], "walking animation resetting"), [])


if __name__ == "__main__":
    unittest.main()
