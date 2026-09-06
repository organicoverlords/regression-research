import json
import tempfile
from pathlib import Path

from tools.chatgpt_artifact_manifest import ingest, normalize_row


def test_normalize_files_library_metadata_preserves_ids_and_timestamps():
    row = normalize_row({
        "file_id": "file_123",
        "name": "proof.png",
        "library_artifact_type": "image",
        "size_bytes": 123,
        "created_at_utc": "2026-09-06T03:22:38Z",
        "modified_at_utc": "2026-09-06T03:22:39Z",
        "model_generated": True,
    }, observed_at="2026-09-06T04:00:00+00:00", default_source_kind="library", default_project="p3")
    assert row["file_id"] == "file_123"
    assert row["filename"] == "proof.png"
    assert row["artifact_type"] == "image"
    assert row["created_at_utc"] == "2026-09-06T03:22:38+00:00"
    assert row["observed_at"] == "2026-09-06T04:00:00+00:00"
    assert row["model_generated"] is True
    assert row["project"] == "p3"


def test_ingest_deduplicates_across_existing_shards_and_keeps_review_metadata():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        evidence = root / "02 Evidence"
        evidence.mkdir(parents=True)
        old = {
            "file_id": "file_same",
            "filename": "screen.png",
            "created_at_utc": "2026-09-01T10:00:00+00:00",
            "observed_at": "2026-09-01T11:00:00+00:00",
            "artifact_type": "screenshot",
            "subject": "reviewed client failure",
            "review_status": "VISUALLY_REVIEWED",
            "source_kind": "upload",
            "provenance": "CURRENT_CONVERSATION_FILES",
            "tags": ["client"],
        }
        (evidence / "2026-09-01_chatgpt_artifact_occurrences.jsonl").write_text(
            json.dumps(old) + "\n", encoding="utf-8"
        )
        output = evidence / "chatgpt_artifact_occurrences.jsonl"
        result = ingest([{
            "file_id": "file_same", "name": "screen.png", "library_artifact_type": "image",
            "modified_at_utc": "2026-09-06T04:00:00Z", "tags": ["library"],
        }], output=output, observed_at="2026-09-06T04:01:00Z")
        assert result["inserted"] == 0
        assert result["updated"] == 1
        rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
        assert len(rows) == 1
        row = rows[0]
        assert row["subject"] == "reviewed client failure"
        assert row["review_status"] == "VISUALLY_REVIEWED"
        assert row["artifact_type"] == "screenshot"
        assert row["source_kind"] == "upload"
        assert row["provenance"] == "CURRENT_CONVERSATION_FILES"
        assert row["tags"] == ["client", "library"]
        assert row["observed_at"] == "2026-09-01T11:00:00+00:00"


def test_ingest_is_idempotent_for_same_observation():
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "02 Evidence" / "chatgpt_artifact_occurrences.jsonl"
        source = [{"file_id": "file_one", "name": "note.md", "library_artifact_type": "writing_block"}]
        first = ingest(source, output=output, observed_at="2026-09-06T04:00:00Z")
        second = ingest(source, output=output, observed_at="2026-09-06T05:00:00Z")
        assert first["inserted"] == 1
        assert second["unchanged"] == 1
        assert second["output_rows"] == 1
        row = json.loads(output.read_text(encoding="utf-8").strip())
        assert row["artifact_type"] == "library_artifact"
        assert row["observed_at"] == "2026-09-06T04:00:00+00:00"


def test_manifest_is_consumed_by_canonical_timeline_adapter():
    from datetime import datetime, timezone
    from tools.timeline_materializer import library_artifact_events

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        output = root / "02 Evidence" / "chatgpt_artifact_occurrences.jsonl"
        ingest([{
            "file_id": "file_timeline", "name": "proof.png", "artifact_type": "proof_preview",
            "created_at_utc": "2026-09-06T03:00:00Z", "project": "p3", "tags": ["proof"],
        }], output=output, observed_at="2026-09-06T04:00:00Z")
        events, coverage = library_artifact_events(root, since=datetime(2026, 9, 5, tzinfo=timezone.utc))
        assert coverage["events"] == 1
        assert events[0]["id"] == "library-artifact:file_timeline"
        assert events[0]["artifact_type"] == "proof_preview"
        assert events[0]["project"] == "p3"


def test_dry_run_never_writes_output():
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "02 Evidence" / "chatgpt_artifact_occurrences.jsonl"
        result = ingest(
            [{"file_id": "file_dry", "name": "dry.txt"}], output=output,
            observed_at="2026-09-06T04:00:00Z", dry_run=True,
        )
        assert result["inserted"] == 1
        assert not output.exists()
