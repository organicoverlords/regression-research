import json
from datetime import datetime
from pathlib import Path

import pytest

from tools.mcp_reroute_evidence import load_jsonl, verify


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8", newline="\n")


def incident(memory_id: str = "mem-incident", timestamp: str = "2026-09-06T19:11:14+03:00") -> dict:
    return {
        "id": memory_id,
        "timestamp": timestamp,
        "tags": ["security_incident", "reroute", "assistant-recorded"],
        "source_messages": ["security rerouted save in vault"],
        "evidence": ["02 Evidence/mcp-security-routing-events.jsonl", "conversation:file-example"],
        "text": "Fresh user-visible reroute.",
    }


def test_linked_incident_passes(tmp_path: Path) -> None:
    memory = tmp_path / "memory.jsonl"
    routing = tmp_path / "mcp-security-routing-events.jsonl"
    write_jsonl(memory, [incident(), {"id": "lesson", "tags": ["reroute"], "evidence": [routing.name]}])
    write_jsonl(routing, [{"source_memory_id": "mem-incident", "classification": "user_observed_security_reroute_post_refresh"}])

    report = verify(memory, routing)

    assert report["status"] == "PASS"
    assert report["required_incident_count"] == 1
    assert report["linked_incident_count"] == 1
    assert report["missing"] == []


def test_claimed_routing_evidence_without_cross_link_fails(tmp_path: Path) -> None:
    memory = tmp_path / "memory.jsonl"
    routing = tmp_path / "mcp-security-routing-events.jsonl"
    write_jsonl(memory, [incident()])
    write_jsonl(routing, [{"classification": "some_other_event"}])

    report = verify(memory, routing)

    assert report["status"] == "FAIL"
    assert report["missing"] == [{
        "id": "mem-incident",
        "timestamp": "2026-09-06T19:11:14+03:00",
        "reason": "routing_log_missing_matching_event",
    }]


def test_since_bound_excludes_older_incident(tmp_path: Path) -> None:
    memory = tmp_path / "memory.jsonl"
    routing = tmp_path / "mcp-security-routing-events.jsonl"
    write_jsonl(memory, [incident(timestamp="2026-09-06T17:00:00+03:00")])
    write_jsonl(routing, [])

    report = verify(memory, routing, since=datetime.fromisoformat("2026-09-06T17:52:42+03:00"))

    assert report["status"] == "PASS"
    assert report["required_incident_count"] == 0




def test_exact_source_message_and_near_report_time_is_valid_fallback(tmp_path: Path) -> None:
    memory = tmp_path / "memory.jsonl"
    routing = tmp_path / "mcp-security-routing-events.jsonl"
    write_jsonl(memory, [incident()])
    write_jsonl(routing, [{
        "reported_at": "2026-09-06T19:09:30+03:00",
        "source_message": "security rerouted save in vault",
        "classification": "user_observed_security_reroute_post_refresh",
    }])

    report = verify(memory, routing)

    assert report["status"] == "PASS"
    assert report["linked_incident_count"] == 1


def test_same_source_message_outside_time_tolerance_does_not_match(tmp_path: Path) -> None:
    memory = tmp_path / "memory.jsonl"
    routing = tmp_path / "mcp-security-routing-events.jsonl"
    write_jsonl(memory, [incident()])
    write_jsonl(routing, [{
        "reported_at": "2026-09-06T18:30:00+03:00",
        "source_message": "security rerouted save in vault",
    }])

    report = verify(memory, routing)

    assert report["status"] == "FAIL"
    assert report["linked_incident_count"] == 0
    assert report["missing"][0]["reason"] == "routing_log_missing_matching_event"


def test_since_with_timezone_missing_memory_timestamp_fails_without_negative_count(tmp_path: Path) -> None:
    memory = tmp_path / "memory.jsonl"
    routing = tmp_path / "mcp-security-routing-events.jsonl"
    write_jsonl(memory, [incident(timestamp="2026-09-06T19:11:14")])
    write_jsonl(routing, [])

    report = verify(memory, routing, since=datetime.fromisoformat("2026-09-06T17:52:42+03:00"))

    assert report["status"] == "FAIL"
    assert report["required_incident_count"] == 1
    assert report["linked_incident_count"] == 0
    assert report["missing"][0]["reason"] == "invalid_or_timezone_missing_timestamp"


def test_malformed_jsonl_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "broken.jsonl"
    path.write_text("{broken\n", encoding="utf-8")
    with pytest.raises(ValueError, match="malformed JSONL"):
        load_jsonl(path)


def test_size_bound_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "large.jsonl"
    path.write_text('{}\n' * 8, encoding="utf-8")
    with pytest.raises(ValueError, match="bounded verifier limit"):
        load_jsonl(path, max_bytes=4)
