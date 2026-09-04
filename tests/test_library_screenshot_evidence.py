import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "02 Evidence"


def _rows(name: str) -> list[dict]:
    path = EVIDENCE / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def _canonical_text_sha256(path: Path) -> str:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    canonical = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def test_ingested_redaction_has_no_live_generic_assignment_value():
    matches = list((EVIDENCE / "library_screenshot_text" / "page2").glob("*104732.txt"))
    assert len(matches) == 1
    text = matches[0].read_text(encoding="utf-8-sig", errors="replace")
    assert "[REDACTED_CREDENTIAL]" in text


def test_reconciled_occurrence_ledgers_keep_final_classifications():
    page1 = _rows("2026-08-26_library_screenshot_text_occurrences_001.jsonl")
    assert len(page1) == 117
    assert len({row["library_file_id"] for row in page1}) == 117
    assert all(row["library_file_id_status"] == "BACKFILLED_EXACT_LIBRARY_FILENAME" for row in page1)
    assert all(row["classification"] != "PENDING_RECONCILIATION" for row in page1)
    assert all(row["review_status"] != "TEXT_EXTRACTED_PENDING_VISUAL_REVIEW" for row in page1)
    assert Counter(row["classification"] for row in page1) == {
        "NON_CONVERSATION_IMAGE": 82,
        "CONVERSATION_SCREENSHOT_NEW": 31,
        "DUPLICATE": 4,
    }

    page4 = _rows("2026-08-27_library_screenshot_text_occurrences_002.jsonl")
    assert len(page4) == 57
    assert len({row["library_file_id"] for row in page4}) == 57
    assert all(row["library_file_id_status"] == "EXACT_LIBRARY_LIST" for row in page4)
    assert all(row["review_status"] == "VISUALLY_REVIEWED" for row in page4)
    assert all(row["reconciliation_status"] == "FINAL_VISUAL_REVIEW_2026-08-27" for row in page4)
    assert Counter(row["classification"] for row in page4) == {
        "CONVERSATION_SCREENSHOT_NEW": 35,
        "NON_CONVERSATION_IMAGE": 21,
        "DUPLICATE": 1,
    }

    page5 = _rows("2026-08-27_library_screenshot_text_occurrences_003.jsonl")
    assert len(page5) == 100
    assert len({row["library_file_id"] for row in page5}) == 100
    assert len({row["occurrence_id"] for row in page5}) == 100
    assert all(row["library_file_id_status"] == "EXACT_LIBRARY_LIST" for row in page5)
    assert all(row["review_status"] == "VISUALLY_REVIEWED" for row in page5)
    assert all(row["reconciliation_status"] == "FINAL_VISUAL_REVIEW_2026-08-27" for row in page5)
    assert Counter(row["classification"] for row in page5) == {
        "CONVERSATION_SCREENSHOT_NEW": 17,
        "NON_CONVERSATION_IMAGE": 78,
        "DUPLICATE": 5,
    }


def test_duplicate_bindings_remain_traceable():
    page1 = _rows("2026-08-26_library_screenshot_text_occurrences_001.jsonl")
    by_id = {row["library_file_id"]: row for row in page1}
    duplicates = [row for row in page1 if row["classification"] == "DUPLICATE"]
    assert len(duplicates) == 4
    for row in duplicates:
        target = row.get("duplicate_of_library_file_id")
        assert target and target in by_id
        assert target != row["library_file_id"]
        assert len(row.get("image_sha256", "")) == 64

    page4 = [row for row in _rows("2026-08-27_library_screenshot_text_occurrences_002.jsonl") if row["classification"] == "DUPLICATE"]
    assert len(page4) == 1
    assert page4[0]["duplicate_of_library_file_id"] == "file_00000000c7e07246b0f8706c32f9142f"
    assert page4[0]["image_sha256"] == "64d983e7df5d46625488ee9e2b8049a988adafb2fcb829b60d68a3e8dbadf23b"

    page5_rows = _rows("2026-08-27_library_screenshot_text_occurrences_003.jsonl")
    page5_by_id = {row["library_file_id"]: row for row in page5_rows}
    expected = {
        "file_0000000099ec722f99125116de8f1749": ("file_00000000d50c722fa08fa2d8202a9fb8", "bd7199a3342a2a394e000f892d3ce0d08146e4eb9eece9e7fa02bff7827e610e"),
        "file_00000000ebe071f4a99cf3ccb6c06d4e": ("file_000000003d907246b7e481beea133d20", "e891a8cfac658846aae6fcf99fa9565cb999b648a2e77da2dc0bafe9524b886f"),
        "file_000000006620720aa93604ceb1fa7794": ("file_0000000009b071f4b6665445ca8f1671", "0b341f4eaeddbdbebf69d6a0bcbdcee3b87cbeccfb07987efb94af349bb8a38c"),
        "file_0000000032807246adcd5340cc66f523": ("file_000000006d047246a5a5cfa46083615e", "4e375a18289b0b26efbb6b6b4d5dca0aeddc357367c9df2d853842669157b89f"),
        "file_0000000042bc7246826e3a2f6611691a": ("file_000000006488724682a9dce0678f1266", "67d1298b8dd33a089095c33b59c6ee2c06e6898fc24373b17b005e7ddca3cccb"),
    }
    duplicates = {row["library_file_id"]: row for row in page5_rows if row["classification"] == "DUPLICATE"}
    assert set(duplicates) == set(expected)
    for duplicate_id, (target_id, image_sha256) in expected.items():
        assert target_id in page5_by_id
        assert duplicates[duplicate_id]["duplicate_of_library_file_id"] == target_id
        assert duplicates[duplicate_id]["image_sha256"] == image_sha256


def test_occurrence_text_hashes_match_preserved_files(tmp_path):
    lf = tmp_path / "lf.txt"
    crlf = tmp_path / "crlf.txt"
    lf.write_bytes(b"alpha\nbeta\n")
    crlf.write_bytes(b"alpha\r\nbeta\r\n")
    assert _canonical_text_sha256(lf) == _canonical_text_sha256(crlf)

    rows = []
    for ledger in sorted(EVIDENCE.glob("*_library_screenshot_text_occurrences_*.jsonl")):
        rows.extend(json.loads(line) for line in ledger.read_text(encoding="utf-8-sig").splitlines() if line.strip())
    assert rows
    for row in rows:
        path = ROOT / row["text_path"]
        assert path.is_file(), row["text_path"]
        assert _canonical_text_sha256(path) == row["text_sha256"], row["filename"]
