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
OCCURRENCE_ROLES = {
    "CORRECTIVE_INTERVENTION",
    "META_REFERENCE",
    "QUOTED/RECONSTRUCTED_REFERENCE",
    "AMBIGUOUS",
}
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


def validate_occurrence(occurrence: dict[str, Any], event_ids: set[str]) -> None:
    occurrence_id = occurrence.get("occurrence_id", "<missing>")
    _require(bool(occurrence.get("occurrence_id")), "occurrence_id is required")
    matched_form = occurrence.get("matched_form", "").casefold()
    _require(matched_form in FORMS, f"{occurrence_id}: invalid matched_form")
    raw_user_text = occurrence.get("raw_user_text")
    _require(isinstance(raw_user_text, str) and raw_user_text, f"{occurrence_id}: raw_user_text is required")
    _require(matched_form in raw_user_text.casefold(), f"{occurrence_id}: matched_form is not literal in raw_user_text")
    role = occurrence.get("occurrence_role")
    _require(role in OCCURRENCE_ROLES, f"{occurrence_id}: invalid occurrence_role")
    _require(bool(occurrence.get("provenance")), f"{occurrence_id}: provenance is required")

    canonical_event_id = occurrence.get("canonical_event_id")
    if role == "CORRECTIVE_INTERVENTION":
        _require(canonical_event_id in event_ids, f"{occurrence_id}: corrective occurrence must link to a canonical event")
    elif canonical_event_id is not None:
        _require(canonical_event_id in event_ids, f"{occurrence_id}: unknown canonical_event_id")


def _computed_counts(data: dict[str, Any]) -> dict[str, Any]:
    events = data["events"]
    occurrences = data["occurrences"]
    scored = [event for event in events if event["severity_100"] is not None]
    forms = Counter(occurrence["matched_form"].casefold() for occurrence in occurrences)
    roles = Counter(occurrence["occurrence_role"] for occurrence in occurrences)
    return {
        "lexical_occurrences": len(occurrences),
        "canonical_interventions": len(events),
        "slopwall": forms.get("slopwall", 0),
        "slop wall": forms.get("slop wall", 0),
        "scored": len(scored),
        "unscorable": len(events) - len(scored),
        "occurrence_roles": dict(sorted(roles.items())),
    }


def validate_index(data: dict[str, Any]) -> None:
    _require(data.get("schema_version") == "1.1.0", "unsupported schema_version")
    events = data.get("events")
    occurrences = data.get("occurrences")
    _require(isinstance(events, list), "events must be a list")
    _require(isinstance(occurrences, list), "occurrences must be a list")

    event_ids: set[str] = set()
    for event in events:
        validate_event(event)
        event_id = event["event_id"]
        _require(event_id not in event_ids, f"duplicate event_id: {event_id}")
        event_ids.add(event_id)
        refs = [p.get("ref") for p in event.get("provenance", []) if p.get("ref")]
        _require(len(refs) == len(set(refs)), f"{event_id}: duplicate provenance ref")

    occurrence_ids: set[str] = set()
    corrective_links: Counter[str] = Counter()
    for occurrence in occurrences:
        validate_occurrence(occurrence, event_ids)
        occurrence_id = occurrence["occurrence_id"]
        _require(occurrence_id not in occurrence_ids, f"duplicate occurrence_id: {occurrence_id}")
        occurrence_ids.add(occurrence_id)
        if occurrence["occurrence_role"] == "CORRECTIVE_INTERVENTION":
            corrective_links[occurrence["canonical_event_id"]] += 1

    _require(set(corrective_links) == event_ids, "every canonical event must have a corrective lexical occurrence")
    _require(all(count == 1 for count in corrective_links.values()), "each canonical event must map to exactly one corrective lexical occurrence")

    confirmed_counts = data.get("confirmed_counts")
    _require(isinstance(confirmed_counts, dict), "confirmed_counts is required")
    _require(confirmed_counts == _computed_counts(data), "confirmed_counts must match computed counts")


def summary(data: dict[str, Any]) -> dict[str, Any]:
    validate_index(data)
    phenotypes = Counter(tag for event in data["events"] for tag in event.get("phenotypes", []))
    return {
        **_computed_counts(data),
        "phenotypes": dict(phenotypes.most_common()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and summarize the slopwall occurrence/event index")
    parser.add_argument("command", choices=("validate", "summary"))
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    args = parser.parse_args()
    data = load_index(args.index)
    if args.command == "validate":
        validate_index(data)
        print(json.dumps({
            "status": "PROVEN",
            "events": len(data["events"]),
            "occurrences": len(data["occurrences"]),
        }, indent=2))
    else:
        print(json.dumps(summary(data), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
