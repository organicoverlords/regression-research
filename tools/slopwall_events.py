from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = REPO / "02 Evidence" / "2026-08-26_slopwall_event_index.json"
FORMS = {"slopwall", "slop wall"}
CONFIDENCE = {"A", "B", "C", "D"}
SCORE_KEYS = (
    "information_slop",
    "task_displacement",
    "execution_damage",
    "correction_resistance",
    "control_state_pathology",
)


def load_index(path: Path = DEFAULT_INDEX) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_event(event: dict[str, Any]) -> None:
    event_id = event.get("event_id", "<missing>")
    _require(bool(event.get("event_id")), "event_id is required")
    _require(event.get("exact_spelling", "").casefold() in FORMS, f"{event_id}: invalid exact_spelling")
    _require(event.get("evidence_confidence") in CONFIDENCE, f"{event_id}: invalid evidence_confidence")
    _require(bool(event.get("provenance")), f"{event_id}: provenance is required")
    _require(bool(event.get("context_before")), f"{event_id}: context_before is required")
    _require(bool(event.get("context_after")), f"{event_id}: context_after is required")

    scores = event.get("scores")
    severity = event.get("severity_100")
    if event["evidence_confidence"] == "D":
        _require(scores is None, f"{event_id}: D-confidence event must not have scores")
        _require(severity is None, f"{event_id}: D-confidence event must be UNSCORABLE")
        return

    _require(isinstance(scores, dict), f"{event_id}: scores are required for A/B/C evidence")
    for key in SCORE_KEYS:
        value = scores.get(key)
        _require(isinstance(value, int) and 0 <= value <= 5, f"{event_id}: invalid score {key}")
    expected = sum(scores[key] for key in SCORE_KEYS) * 4
    _require(severity == expected, f"{event_id}: severity_100 must equal score sum * 4 ({expected})")


def validate_index(data: dict[str, Any]) -> None:
    _require(data.get("schema_version") == "1.0.0", "unsupported schema_version")
    events = data.get("events")
    _require(isinstance(events, list), "events must be a list")
    ids: set[str] = set()
    for event in events:
        validate_event(event)
        event_id = event["event_id"]
        _require(event_id not in ids, f"duplicate event_id: {event_id}")
        ids.add(event_id)
        refs = [p.get("ref") for p in event.get("provenance", []) if p.get("ref")]
        _require(len(refs) == len(set(refs)), f"{event_id}: duplicate provenance ref")


def summary(data: dict[str, Any]) -> dict[str, Any]:
    validate_index(data)
    events = data["events"]
    scored = [event for event in events if event["severity_100"] is not None]
    forms = Counter(event["exact_spelling"].casefold() for event in events)
    phenotypes = Counter(tag for event in events for tag in event.get("phenotypes", []))
    return {
        "canonical_interventions": len(events),
        "scored": len(scored),
        "unscorable": len(events) - len(scored),
        "forms": dict(sorted(forms.items())),
        "phenotypes": dict(phenotypes.most_common()),
        "excluded_meta_mentions": len(data.get("excluded_meta_mentions", [])),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and summarize the slopwall intervention index")
    parser.add_argument("command", choices=("validate", "summary"))
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    args = parser.parse_args()
    data = load_index(args.index)
    if args.command == "validate":
        validate_index(data)
        print(json.dumps({"status": "PROVEN", "events": len(data["events"])}, indent=2))
    else:
        print(json.dumps(summary(data), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
