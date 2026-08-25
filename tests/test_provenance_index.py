from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools.provenance import validate

REPO = Path(__file__).resolve().parents[1]
INDEX = REPO / "provenance.json"


def test_provenance_validates():
    ok, messages, stats = validate(INDEX)
    assert ok, f"provenance should be valid: {messages}"
    assert stats["reports_indexed"] == 7
    assert stats["errors"] == 0


def test_every_report_indexed():
    data = json.loads(INDEX.read_text(encoding="utf-8-sig"))
    reports_dir = REPO / "01 Reports"
    actual = {f"01 Reports/{p.name}" for p in reports_dir.iterdir() if p.is_file() and p.suffix.lower() in (".md", ".txt")}
    indexed = {e["report_path"] for e in data["entries"]}
    missing = actual - indexed
    assert not missing, f"unindexed reports: {missing}"


def test_every_indexed_path_exists():
    data = json.loads(INDEX.read_text(encoding="utf-8-sig"))
    repo = REPO

    def check_paths():
        for e in data["entries"]:
            assert (repo / e["report_path"]).exists(), f"missing report {e['report_path']}"
            for kind in ("raw_transcripts", "evidence_files", "contract_snapshots"):
                for p in e.get(kind, []):
                    assert (repo / p).exists(), f"missing {kind} path {p}"
        for o in data.get("orphan_evidence", []):
            assert (repo / o["path"]).exists(), f"missing orphan path {o['path']}"

    check_paths()


def test_duplicate_archive_empty_and_marked():
    data = json.loads(INDEX.read_text(encoding="utf-8-sig"))
    dup = data.get("duplicate_archive", {})
    assert dup.get("status") == "empty_no_superseded_artifacts_currently_archived"
    assert dup.get("entries") == []
    dup_dir = REPO / "99 Duplicate Archive"
    files = [p for p in dup_dir.iterdir() if p.is_file()] if dup_dir.exists() else []
    assert files == [], f"duplicate archive should be empty, found {files}"


def test_validator_detects_broken_path(tmp_path: Path):
    data = json.loads(INDEX.read_text(encoding="utf-8-sig"))
    bad = copy.deepcopy(data)
    # inject broken evidence file into first entry
    bad["entries"][0]["evidence_files"] = ["02 Evidence/THIS_FILE_DOES_NOT_EXIST_999.txt"]
    tmp_index = tmp_path / "provenance.json"
    tmp_index.write_text(json.dumps(bad), encoding="utf-8")
    ok, messages, _ = validate(tmp_index)
    assert not ok
    assert any("broken path" in m and "THIS_FILE_DOES_NOT_EXIST" in m for m in messages)


def test_validator_detects_duplicate_incident_id(tmp_path: Path):
    data = json.loads(INDEX.read_text(encoding="utf-8-sig"))
    dup = copy.deepcopy(data)
    dup["entries"][0]["incident_id"] = "INC-DUPLICATE-TEST"
    dup["entries"][1]["incident_id"] = "INC-DUPLICATE-TEST"
    tmp_index = tmp_path / "provenance.json"
    tmp_index.write_text(json.dumps(dup), encoding="utf-8")
    ok, messages, _ = validate(tmp_index)
    assert not ok
    assert any("duplicate incident_id" in m for m in messages)


def test_validator_detects_malformed_required_field(tmp_path: Path):
    data = json.loads(INDEX.read_text(encoding="utf-8-sig"))
    bad = copy.deepcopy(data)
    bad["entries"][0]["title"] = ""
    tmp_index = tmp_path / "provenance.json"
    tmp_index.write_text(json.dumps(bad), encoding="utf-8")
    ok, messages, _ = validate(tmp_index)
    assert not ok
    assert any("title must be non-empty string" in m for m in messages)


def test_validator_detects_unsafe_link(tmp_path: Path):
    data = json.loads(INDEX.read_text(encoding="utf-8-sig"))
    bad = copy.deepcopy(data)
    bad["entries"][0]["evidence_files"] = ["../outside-evidence.txt"]
    tmp_index = tmp_path / "provenance.json"
    tmp_index.write_text(json.dumps(bad), encoding="utf-8")
    ok, messages, _ = validate(tmp_index)
    assert not ok
    assert any("unsafe" in m and "outside-evidence" in m for m in messages)


def test_validator_detects_duplicate_archive_inconsistency(tmp_path: Path):
    data = json.loads(INDEX.read_text(encoding="utf-8-sig"))
    bad = copy.deepcopy(data)
    bad["duplicate_archive"]["entries"] = [{"path": "01 Reports/not-an-archive-file.txt"}]
    tmp_index = tmp_path / "provenance.json"
    tmp_index.write_text(json.dumps(bad), encoding="utf-8")
    ok, messages, _ = validate(tmp_index)
    assert not ok
    assert any("must be under '99 Duplicate Archive/'" in m for m in messages)


def test_no_credential_bearing_material():
    data = json.loads(INDEX.read_text(encoding="utf-8-sig"))
    text = json.dumps(data).lower()
    for deny in [".env", "tailscale", "_share_check.html"]:
        # provenance should not reference credential files; actual repo also denies those extensions via .gitignore
        if deny == ".env":
            # allow mention in validation_rules but not as path
            paths = []
            for e in data["entries"]:
                paths.extend([e["report_path"]] + e.get("evidence_files", []) + e.get("raw_transcripts", []) + e.get("contract_snapshots", []))
            for o in data.get("orphan_evidence", []):
                paths.append(o["path"])
            assert not any(".env" in p for p in paths), "credential path in index"
        else:
            # ensure no path contains deny string
            paths = []
            for e in data["entries"]:
                paths.extend([e["report_path"]] + e.get("evidence_files", []) + e.get("raw_transcripts", []) + e.get("contract_snapshots", []))
            for o in data.get("orphan_evidence", []):
                paths.append(o["path"])
            assert not any(deny in p.lower() for p in paths), f"credential-bearing path '{deny}' found"

    # also check provenance file itself does not contain secrets pattern
    raw = INDEX.read_text(encoding="utf-8-sig")
    assert "credential" not in raw.lower() or "no_credentials" in raw.lower()  # only validation_rules may mention it


def test_missing_recorded_explicitly():
    data = json.loads(INDEX.read_text(encoding="utf-8-sig"))
    for e in data["entries"]:
        missing = e.get("missing", [])
        assert isinstance(missing, list) and len(missing) > 0, f"{e['report_path']} must have explicit missing array (even if empty would be guess)"
        # each entry has at least incident_id or raw not assigned
        assert any("incident_id" in m or "raw" in m or "evidence" in m for m in missing), f"{e['report_path']} missing should describe unresolved links"
