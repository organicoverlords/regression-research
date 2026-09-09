import io
import json
import sys
import tempfile
import unittest
from contextlib import nullcontext, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import tools.memory_bank as memory_bank
from tools.memory_bank import BankError, _compact_timeline_report, _main, _materialized_context_query_eligible, _materialized_lesson_history, append_entry, attach_materialized_orientation, load_bank, validate_entry


class MaterializedContextPriorTests(unittest.TestCase):
    def test_query_gate_skips_trivial_context_and_accepts_substantive_task_wording(self):
        self.assertFalse(_materialized_context_query_eligible("go"))
        self.assertFalse(_materialized_context_query_eligible("status"))
        self.assertFalse(_materialized_context_query_eligible("mem-20260909-deadbeef"))
        self.assertTrue(_materialized_context_query_eligible("shared visual library"))
        self.assertTrue(_materialized_context_query_eligible("p3 rigging"))

    def test_materialized_packet_becomes_two_labeled_historical_priors(self):
        report = {
            "materialized": {"status": "FRESH", "as_of": "2026-09-09T02:00:00Z"},
            "lesson_packet": {
                "status": "READY", "authority": "DERIVED_HISTORICAL_PRIORS_ONLY",
                "validation": "SLICE1_RETRIEVAL_ONLY_NOT_VALIDATED", "live_truth_required": True,
                "items": [
                    {
                        "source_event_id": "github-pr:repo#778", "source_type": "GITHUB_PR", "project": "vault",
                        "event_at": "2026-09-08T21:43:17Z", "title": "Owner map", "conclusion": "Reuse owner map",
                        "evidence_anchors": ["github:repo#778"],
                    },
                    {
                        "source_event_id": "git:repo:abc", "source_type": "GIT_COMMIT", "project": "vault",
                        "event_at": "2026-09-08T20:00:00Z", "title": "Prior fix", "conclusion": "Keep the supported path",
                        "evidence_anchors": ["gitsha:abc"], "lineage_event_ids": ["a", "b"],
                        "lineage_projects": ["vault", "tiny3d"], "lineage_copy_count": 2,
                        "lineage_semantics": "COPIED_LINEAGE_NOT_INDEPENDENT_SUPPORT",
                    },
                    {"source_event_id": "third", "source_type": "GIT_COMMIT", "title": "Third", "conclusion": "Third"},
                ],
            },
        }
        with tempfile.TemporaryDirectory() as d, patch("tools.timeline_materializer.query_materialized", return_value=report) as query:
            priors = _materialized_lesson_history("shared visual library", root=Path(d), limit=2)

        self.assertEqual([item["source_event_id"] for item in priors], ["github-pr:repo#778", "git:repo:abc"])
        self.assertTrue(all(item["source_class"] == "HISTORICAL_CONTEXT" for item in priors))
        self.assertTrue(all(item["retrieval_role"] == "LESSON_PRIOR" for item in priors))
        self.assertEqual(priors[1]["lineage_copy_count"], 2)
        self.assertEqual(priors[0]["materialized_status"], "FRESH")
        query.assert_called_once()

    def test_default_bank_context_cli_includes_labeled_materialized_prior(self):
        prior = {
            "source_class": "HISTORICAL_CONTEXT", "retrieval_role": "LESSON_PRIOR",
            "source_event_id": "github-pr:repo#778", "source_type": "GITHUB_PR",
            "title": "Owner map", "conclusion": "Reuse owner map",
            "evidence_anchors": ["github:repo#778"],
            "authority": "DERIVED_HISTORICAL_PRIORS_ONLY",
            "validation": "SLICE1_RETRIEVAL_ONLY_NOT_VALIDATED", "live_truth_required": True,
        }
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            bank = root / "memory-bank.jsonl"
            overlay = root / "memory-bank.local.jsonl"
            bank.write_text("", encoding="utf-8")
            overlay.write_text("", encoding="utf-8")
            output = io.StringIO()
            with (
                patch.object(memory_bank, "DEFAULT_BANK", bank),
                patch.object(memory_bank, "DEFAULT_LOCAL_BANK", overlay),
                patch.object(memory_bank, "_materialized_lesson_history", return_value=[prior]) as materialized,
                patch.object(sys, "argv", ["memory_bank.py", "context", "shared visual library"]),
                redirect_stdout(output),
            ):
                rc = memory_bank._main()

        self.assertEqual(rc, 0)
        pack = json.loads(output.getvalue())
        self.assertEqual(pack["durable_memory"], [])
        self.assertEqual(pack["historical_evidence"][0]["kind"], "lesson-prior")
        self.assertEqual(pack["historical_evidence"][0]["source_event_id"], "github-pr:repo#778")
        materialized.assert_called_once()

    def test_trivial_context_does_not_open_materialized_reader(self):
        with tempfile.TemporaryDirectory() as d, patch("tools.timeline_materializer.query_materialized") as query:
            self.assertEqual(_materialized_lesson_history("go", root=Path(d), limit=2), [])
        query.assert_not_called()

    def test_default_context_command_injects_materialized_lesson_prior(self):
        report = {
            "materialized": {"status": "FRESH", "as_of": "2026-09-09T02:00:00Z"},
            "lesson_packet": {
                "status": "READY", "authority": "DERIVED_HISTORICAL_PRIORS_ONLY",
                "validation": "SLICE1_RETRIEVAL_ONLY_NOT_VALIDATED", "live_truth_required": True,
                "items": [{
                    "source_event_id": "github-pr:repo#778", "source_type": "GITHUB_PR", "project": "vault",
                    "event_at": "2026-09-08T21:43:17Z", "title": "Owner map",
                    "conclusion": "Reuse the owner map", "evidence_anchors": ["github:repo#778"],
                }],
            },
        }
        with (
            patch("sys.argv", ["memory_bank.py", "context", "shared visual library"]),
            patch("tools.memory_bank.load_bank", return_value=[]),
            patch("tools.memory_bank.build_recurrence_context", return_value=[]),
            patch("tools.timeline_materializer.query_materialized", return_value=report) as query,
            patch("tools.memory_bank._print_json") as emit,
        ):
            self.assertEqual(_main(), 0)
        query.assert_called_once()
        pack = emit.call_args.args[0]
        self.assertEqual(pack["durable_memory"], [])
        self.assertEqual(pack["historical_evidence"][0]["kind"], "lesson-prior")
        self.assertEqual(pack["historical_evidence"][0]["source_event_id"], "github-pr:repo#778")
        self.assertTrue(pack["historical_evidence"][0]["live_truth_required"])




class CompactTimelineProjectionTests(unittest.TestCase):
    def test_compact_projection_removes_repeated_forensic_bulk_and_bounds_text(self):
        events = []
        for index in range(20):
            events.append({
                "id": f"event-{index}", "source_type": "VAULT_MEMORY", "event_at": "2026-09-09T00:00:00Z",
                "title": "T" * 500, "summary": "S" * 1200, "continuity": {"classification_basis": ["X" * 1000] * 10},
                "refs": ["R" * 500] * 10,
            })
        report = {
            "schema_version": 1, "authority": "DERIVED_HISTORY_ONLY", "query": "memory benchmark",
            "materialized": {"status": "FRESH", "as_of": "2026-09-09T00:00:00Z", "live_truth_required": True, "huge": "M" * 10000},
            "snapshots": {"authority": "DERIVED_HISTORY_ONLY", "windows": [{"window": "24h", "observations": 100, "case_examples": ["X" * 5000]}]},
            "continuity_graph": {"semantics": "cases", "summary": {"matched_cases": 9}, "cases": [{"case_id": f"c{i}", "latest_title": "C" * 500, "event_ids": ["x"] * 100} for i in range(8)]},
            "lesson_packet": {"status": "READY", "items": [{"source_event_id": f"p{i}", "title": "P" * 500, "conclusion": "Q" * 800} for i in range(8)]},
            "work_graph": {"summary": {"matched_commit_groups": 8}, "commit_groups": [{"work_id": f"w{i}", "title": "W" * 500, "workers": [{"findings": "F" * 2000}]} for i in range(8)]},
            "matching_events": 20, "events": events, "truncated": False,
        }
        compact = _compact_timeline_report(report, limit=20)
        encoded = json.dumps(compact, ensure_ascii=False).encode("utf-8")
        self.assertLess(len(encoded), 24000)
        self.assertEqual(len(compact["events"]), 20)
        self.assertNotIn("continuity", compact["events"][0])
        self.assertLessEqual(len(compact["events"][0]["summary"]), 320)
        self.assertLessEqual(len(compact["continuity_graph"]["cases"]), 3)
        self.assertLessEqual(len(compact["lesson_packet"]["items"]), 3)
        self.assertLessEqual(len(compact["work_graph"]["commit_groups"]), 3)

class MemoryBankValidationTests(unittest.TestCase):
    def valid(self):
        return {
            "id": "mem-20260825-abc123",
            "timestamp": "2026-08-25T11:30:00+03:00",
            "kind": "lesson",
            "scope": "mcp",
            "tags": ["routing", "turvallisuus"],
            "text": "Server non-arrival is distinct from local transport failure.",
            "state": "PROVEN",
            "evidence": ["github:chatgpt-mcp-clean#7"],
            "supersedes": [],
        }

    def test_sensitive_value_is_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as raw:
            bank = Path(raw) / "bank.jsonl"
            entry = self.valid()
            entry["text"] = "my password is CorrectHorseBatteryStaple123!"
            with self.assertRaisesRegex(BankError, "sensitive memory content rejected before write"):
                append_entry(bank, entry)
            self.assertFalse(bank.exists())

    def test_sensitive_verbatim_source_is_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as raw:
            bank = Path(raw) / "bank.jsonl"
            entry = self.valid()
            entry.update({
                "tags": ["assistant-recorded", "verbatim-source"],
                "source_messages": ["Bearer abcdefghijklmnopqrstuvwxyz0123456789"],
                "interpretation": "safe summary",
                "confidence": 100,
                "confidence_reason": "test",
            })
            with self.assertRaisesRegex(BankError, "sensitive memory content rejected before write"):
                append_entry(bank, entry)
            self.assertFalse(bank.exists())

    def test_valid_entry_and_utf8(self):
        validate_entry(self.valid())

    def test_positive_milestone_uses_canonical_tiny_star_sticker(self):
        entry = self.valid()
        entry["positive_milestone"] = True
        entry["milestone_sticker"] = "★"
        validate_entry(entry)

        wrong = self.valid()
        wrong["positive_milestone"] = True
        wrong["milestone_sticker"] = "🏆"
        with self.assertRaisesRegex(BankError, "positive milestone requires milestone_sticker"):
            validate_entry(wrong)

        orphan = self.valid()
        orphan["milestone_sticker"] = "★"
        with self.assertRaisesRegex(BankError, "milestone_sticker requires positive_milestone"):
            validate_entry(orphan)

    def test_missing_required_field_rejected(self):
        e = self.valid(); del e["text"]
        with self.assertRaises(BankError): validate_entry(e)

    def test_invalid_enum_rejected(self):
        e = self.valid(); e["state"] = "MAYBE"
        with self.assertRaises(BankError): validate_entry(e)

    def test_arrays_must_be_string_arrays(self):
        for field in ("tags", "evidence", "supersedes"):
            e = self.valid(); e[field] = [123]
            with self.subTest(field=field), self.assertRaises(BankError): validate_entry(e)

    def test_append_infers_single_project_from_scope(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "bank.jsonl"
            created = append_entry(path, {
                "kind": "lesson", "scope": "p3/build", "tags": [],
                "text": "Build rule", "state": "PROVEN", "evidence": [], "supersedes": [],
            })
            self.assertEqual(created["project"], "p3")
            self.assertEqual(load_bank(path)[0]["project"], "p3")

    def test_append_does_not_infer_project_from_body_only(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "bank.jsonl"
            created = append_entry(path, {
                "kind": "lesson", "scope": "global", "tags": [],
                "text": "P3 appears only in this body example", "state": "PROVEN", "evidence": [], "supersedes": [],
            })
            self.assertNotIn("project", created)

    def test_project_and_expiry_validate(self):
        e = self.valid()
        e["project"] = "p3"
        e["expires_at"] = "2099-08-21T10:00:00+03:00"
        validate_entry(e)
        bad = self.valid(); bad["expires_at"] = "2099-08-21T10:00:00"
        with self.assertRaises(BankError): validate_entry(bad)
        bad = self.valid(); bad["project"] = ""
        with self.assertRaises(BankError): validate_entry(bad)

    def test_behavior_rule_is_typed_forensic_metadata_only(self):
        e = self.valid()
        e["kind"] = "fact"
        e["behavior_rule"] = True
        validate_entry(e)
        bad = self.valid()
        bad["behavior_rule"] = "true"
        with self.assertRaises(BankError):
            validate_entry(bad)

    def test_thread_validates_nonempty(self):
        e = self.valid()
        e["thread"] = "incident-family-42"
        validate_entry(e)
        bad = self.valid()
        bad["thread"] = ""
        with self.assertRaises(BankError):
            validate_entry(bad)

    def test_iso_fraction_beyond_microseconds_is_accepted_without_rewriting(self):
        e = self.valid()
        e["timestamp"] = "2026-09-06T01:58:15.2203558+03:00"
        e["event_at"] = "2026-09-06T01:58:15.9876543+03:00"
        validate_entry(e)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bank.jsonl"
            p.write_text(json.dumps(e) + "\n", encoding="utf-8")
            loaded = load_bank(p)
        self.assertEqual(loaded[0]["timestamp"], e["timestamp"])
        self.assertEqual(loaded[0]["event_at"], e["event_at"])

    def test_event_at_validates_timezone(self):
        e = self.valid()
        e["event_at"] = "2026-08-28T20:00:00+03:00"
        validate_entry(e)
        bad = self.valid()
        bad["event_at"] = "2026-08-28T20:00:00"
        with self.assertRaises(BankError):
            validate_entry(bad)


    def test_malformed_jsonl_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bank.jsonl"; p.write_text('{"id":"x"}\nnot-json\n', encoding="utf-8")
            with self.assertRaises(BankError): load_bank(p)

    def test_duplicate_ids_rejected(self):
        e = self.valid()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bank.jsonl"
            p.write_text(json.dumps(e)+"\n"+json.dumps(e)+"\n", encoding="utf-8")
            with self.assertRaises(BankError): load_bank(p)

    def test_canonical_load_is_read_only(self):
        e = self.valid()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bank.jsonl"
            p.write_text(json.dumps(e)+"\n", encoding="utf-8")
            with patch("tools.memory_bank._is_canonical_bank", return_value=True), patch("tools.memory_bank.sync_bank") as sync:
                self.assertEqual(load_bank(p), [e])
            sync.assert_not_called()

    def test_canonical_append_is_local_only_by_default(self):
        values = self.valid()
        values.pop("id")
        values.pop("timestamp")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bank.jsonl"
            p.write_text("", encoding="utf-8")
            with patch("tools.memory_bank._is_canonical_bank", return_value=True), patch(
                "tools.memory_bank.sync_lock", side_effect=lambda path: nullcontext()
            ), patch("tools.memory_bank._sync_canonical_locked") as sync:
                saved = append_entry(p, values)
            self.assertEqual(saved["text"], values["text"])
            sync.assert_not_called()

    def test_canonical_append_publish_syncs_before_and_after_write(self):
        values = self.valid()
        values.pop("id")
        values.pop("timestamp")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bank.jsonl"
            p.write_text("", encoding="utf-8")
            with patch("tools.memory_bank._is_canonical_bank", return_value=True), patch(
                "tools.memory_bank.sync_lock", side_effect=lambda path: nullcontext()
            ), patch("tools.memory_bank._sync_canonical_locked") as sync:
                saved = append_entry(p, values, publish=True)
            self.assertEqual(saved["text"], values["text"])
            self.assertEqual(sync.call_count, 2)
            self.assertFalse(sync.call_args_list[0].kwargs["strict"])
            self.assertTrue(sync.call_args_list[1].kwargs["strict"])


    def test_default_bank_local_record_uses_external_overlay_and_keeps_seed_unchanged(self):
        seed_entry = self.valid()
        values = self.valid()
        values.pop("id")
        values.pop("timestamp")
        values["text"] = "Local overlay entry"
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            seed = root / "repo" / "memory" / "memory-bank.jsonl"
            overlay = root / "state" / "memory-bank.local.jsonl"
            seed.parent.mkdir(parents=True)
            seed.write_text(json.dumps(seed_entry) + "\n", encoding="utf-8")
            before = seed.read_bytes()
            with patch("tools.memory_bank.DEFAULT_BANK", seed), patch(
                "tools.memory_bank.DEFAULT_LOCAL_BANK", overlay
            ), patch("tools.memory_bank.sync_bank") as sync:
                saved = append_entry(seed, values)
                effective = load_bank(seed)
            self.assertEqual(seed.read_bytes(), before)
            self.assertEqual([entry["id"] for entry in effective], [seed_entry["id"], saved["id"]])
            self.assertEqual([entry["id"] for entry in load_bank(overlay)], [saved["id"]])
            sync.assert_not_called()

    def test_default_bank_overlay_conflict_fails_closed_on_read(self):
        seed_entry = self.valid()
        conflicting = dict(seed_entry)
        conflicting["text"] = "Conflicting local text"
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            seed = root / "repo" / "memory" / "memory-bank.jsonl"
            overlay = root / "state" / "memory-bank.local.jsonl"
            seed.parent.mkdir(parents=True)
            overlay.parent.mkdir(parents=True)
            seed.write_text(json.dumps(seed_entry) + "\n", encoding="utf-8")
            overlay.write_text(json.dumps(conflicting) + "\n", encoding="utf-8")
            with patch("tools.memory_bank.DEFAULT_BANK", seed), patch(
                "tools.memory_bank.DEFAULT_LOCAL_BANK", overlay
            ):
                with self.assertRaisesRegex(BankError, "memory id conflict"):
                    load_bank(seed)

    def test_default_bank_publish_syncs_effective_overlay_without_mutating_seed(self):
        seed_entry = self.valid()
        values = self.valid()
        values.pop("id")
        values.pop("timestamp")
        values["text"] = "Publish from overlay"
        calls = []

        def fake_sync(staged, *, publish):
            calls.append((Path(staged), publish, Path(staged).read_bytes()))
            return {"status": "PROVEN", "pulled": 0, "pending_push": 0, "pushed": 1, "aligned_head": False}

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            seed = root / "repo" / "memory" / "memory-bank.jsonl"
            overlay = root / "state" / "memory-bank.local.jsonl"
            seed.parent.mkdir(parents=True)
            seed.write_text(json.dumps(seed_entry) + "\n", encoding="utf-8")
            before = seed.read_bytes()
            with patch("tools.memory_bank.DEFAULT_BANK", seed), patch(
                "tools.memory_bank.DEFAULT_LOCAL_BANK", overlay
            ), patch("tools.memory_bank.sync_bank", side_effect=fake_sync):
                saved = append_entry(seed, values, publish=True)
                effective = load_bank(seed)
            self.assertEqual(seed.read_bytes(), before)
            self.assertEqual(len(calls), 2)
            self.assertTrue(all(publish for _, publish, _ in calls))
            self.assertTrue(all(staged != seed for staged, _, _ in calls))
            self.assertNotIn(saved["id"].encode(), calls[0][2])
            self.assertIn(saved["id"].encode(), calls[1][2])
            self.assertEqual([entry["id"] for entry in effective], [seed_entry["id"], saved["id"]])


    def _reroute_memory(self):
        entry = self.valid()
        entry.update({
            "id": "mem-reroute-write-guard",
            "timestamp": "2026-09-06T19:11:14+03:00",
            "tags": ["security_incident", "reroute", "assistant-recorded", "verbatim-source"],
            "source_messages": ["security rerouted save in vault"],
            "evidence": ["02 Evidence/mcp-security-routing-events.jsonl"],
            "interpretation": "Preserve a reported reroute without inferring cause.",
            "confidence": 98,
            "confidence_reason": "The source message explicitly reports the visible symptom.",
        })
        return entry

    def test_canonical_reroute_memory_cannot_cite_missing_routing_event(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            bank = root / "memory-bank.jsonl"
            bank.write_text("", encoding="utf-8")
            routing = root / "mcp-security-routing-events.jsonl"
            routing.write_text("", encoding="utf-8")
            with patch("tools.memory_bank._is_canonical_bank", return_value=True), patch(
                "tools.mcp_reroute_evidence.DEFAULT_ROUTING", routing
            ), patch("tools.memory_bank.sync_lock", side_effect=lambda path: nullcontext()), patch(
                "tools.memory_bank._sync_canonical_locked"
            ):
                with self.assertRaisesRegex(BankError, "append the routing event first"):
                    append_entry(bank, self._reroute_memory())
            self.assertEqual(bank.read_text(encoding="utf-8"), "")

    def test_canonical_reroute_memory_accepts_prior_exact_source_event(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            bank = root / "memory-bank.jsonl"
            bank.write_text("", encoding="utf-8")
            routing = root / "mcp-security-routing-events.jsonl"
            routing.write_text(json.dumps({
                "reported_at": "2026-09-06T19:10:00+03:00",
                "source_message": "security rerouted save in vault",
            }) + "\n", encoding="utf-8")
            with patch("tools.memory_bank._is_canonical_bank", return_value=True), patch(
                "tools.mcp_reroute_evidence.DEFAULT_ROUTING", routing
            ), patch("tools.memory_bank.sync_lock", side_effect=lambda path: nullcontext()), patch(
                "tools.memory_bank._sync_canonical_locked"
            ):
                saved = append_entry(bank, self._reroute_memory())
            self.assertEqual(saved["id"], "mem-reroute-write-guard")
            self.assertEqual(len(load_bank(bank)), 1)


    def test_assistant_recorded_requires_verbatim_provenance(self):
        e = self.valid()
        e["tags"] = ["assistant-recorded"]
        with self.assertRaises(BankError):
            validate_entry(e)

    def test_assistant_recorded_structured_fields_validate(self):
        e = self.valid()
        e.update({
            "tags": ["assistant-recorded", "verbatim-source"],
            "source_messages": ["and hwat you think it means with like confidence score etc? dunno"],
            "turn_task": "make it permanent that the original actual words are always included in every assistant recorder memory so there is no ambiguity afterwards",
            "interpretation": "Preserve source wording separately from assistant interpretation.",
            "confidence": 98,
            "confidence_reason": "The user stated the desired recorder behavior explicitly across several consecutive turns.",
        })
        validate_entry(e)
        self.assertEqual(e["source_messages"][0], "and hwat you think it means with like confidence score etc? dunno")

    def test_structured_fields_rejected_without_assistant_recorded_tag(self):
        e = self.valid()
        e["source_messages"] = ["exact source"]
        with self.assertRaises(BankError):
            validate_entry(e)



class MemoryBankMaterializedOverviewTests(unittest.TestCase):
    def test_overview_orientation_uses_same_materialized_freshness_and_coverage_contract(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            state = root / ".state" / "timeline"
            state.mkdir(parents=True)
            projection = {
                "schema": "vault.timeline.bootstrap.v1",
                "generated_at": "2026-09-06T05:58:00+00:00",
                "overview": {
                    "timeline_snapshots": {"authority": "DERIVED_HISTORY_ONLY", "windows": [{"window": "24h", "events": 3}]},
                    "timeline_materialized": {
                        "refresh_minutes": 5,
                        "horizon_days": 30,
                        "backfill_incomplete_sources": ["github"],
                    },
                },
            }
            (state / "bootstrap-memory-overview.json").write_text(json.dumps(projection), encoding="utf-8")
            report = {"schema": "memory-bank.overview.v1", "contract": "history only"}
            attach_materialized_orientation(
                report, vault_root=root, now=__import__("datetime").datetime(2026, 9, 6, 6, 0, tzinfo=__import__("datetime").timezone.utc)
            )
        self.assertEqual(report["timeline_materialized"]["status"], "FRESH")
        self.assertEqual(report["timeline_materialized"]["coverage_status"], "HISTORICAL_INCOMPLETE")
        self.assertEqual(report["timeline_materialized"]["absence_semantics"], "NO_MATCH_IS_NOT_PROOF_OF_ABSENCE")
        self.assertEqual(report["timeline_snapshots"]["windows"][0]["window"], "24h")
        self.assertEqual(report["debugging_boundary"]["current_diagnosis"], "VERIFY_THE_OWNING_LIVE_REPO_RUNTIME_SCHEDULER_OR_COORDINATOR")

    def test_missing_materialization_never_becomes_evidence_of_absence(self):
        with tempfile.TemporaryDirectory() as d:
            report = {}
            attach_materialized_orientation(report, vault_root=Path(d))
        self.assertEqual(report["timeline_materialized"]["status"], "MISSING")
        self.assertIn("DO_NOT_INFER_ABSENCE", report["timeline_materialized"]["absence_semantics"])
        self.assertTrue(report["timeline_materialized"]["live_truth_required"])

if __name__ == "__main__": unittest.main()
