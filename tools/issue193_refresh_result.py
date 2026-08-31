from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED_MEASUREMENTS = {
    "visible_or_discovered_schema",
    "direct_recipient_callable",
    "exact_client_error_class",
    "caller_id_or_process_id",
    "matching_local_request_start",
    "sibling_route_health",
    "refresh_or_reload_between_samples",
}
CANARY_DEFINITIONS = {
    "discover_primary": {"action": "discover MCP0 schema", "max_calls_per_phase": 1},
    "call_primary": {"action": "call busy_list", "max_calls_per_phase": 1},
    "discover_alternate": {"action": "discover one alternate plugin route", "max_calls_per_phase": 1},
    "call_alternate": {"action": "call alternate busy_list or harmless process echo", "max_calls_per_phase": 1},
    "local_arrival": {"action": "record local server request_start/caller evidence when available", "max_calls_per_phase": 0},
}
CANARY_IDS = set(CANARY_DEFINITIONS)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_record(record: dict) -> dict:
    _require(isinstance(record, dict), "record must be an object")
    _require(record.get("schema_version") == 1, "schema_version must be 1")
    _require(record.get("issue") == 193, "issue must be 193")
    pairs = record.get("pairs")
    _require(isinstance(pairs, list) and pairs, "pairs must be a non-empty list")
    seen_conversations: set[str] = set()
    expected_model: str | None = None
    expected_configuration: str | None = None
    expected_canaries: dict | None = None
    normalized = []
    for pair in pairs:
        _require(isinstance(pair, dict), "each pair must be an object")
        _require(pair.get("kind") in {"control", "treatment"}, "pair kind must be control or treatment")
        conversation_id = pair.get("conversation_id")
        _require(isinstance(conversation_id, str) and conversation_id.strip(), "conversation_id is required")
        canonical_conversation_id = conversation_id.strip()
        _require(canonical_conversation_id not in seen_conversations, "conversation_id values must be independent")
        seen_conversations.add(canonical_conversation_id)
        _require(isinstance(pair.get("model"), str) and pair["model"].strip(), "model is required")
        _require(isinstance(pair.get("configuration"), str) and pair["configuration"].strip(), "configuration is required")
        canonical_model = pair["model"].strip()
        canonical_configuration = pair["configuration"].strip()
        if expected_model is None:
            expected_model = canonical_model
            expected_configuration = canonical_configuration
        else:
            _require(canonical_model == expected_model, "all pairs must use the same model")
            _require(canonical_configuration == expected_configuration, "all pairs must use the same configuration")
        before = pair.get("before")
        after = pair.get("after")
        _require(isinstance(before, dict) and isinstance(after, dict), "before and after samples are required")
        for sample_name, sample in (("before", before), ("after", after)):
            canaries = sample.get("canaries")
            _require(isinstance(canaries, dict), f"{sample_name}.canaries must be an object")
            _require(set(canaries) == CANARY_IDS, f"{sample_name} must contain the exact preregistered canaries")
            _require(all(isinstance(definition, dict) for definition in canaries.values()), f"{sample_name} canary definitions must be objects")
            measurements = sample.get("measurements")
            _require(isinstance(measurements, dict), f"{sample_name}.measurements must be an object")
            missing = REQUIRED_MEASUREMENTS - set(measurements)
            _require(not missing, f"{sample_name} missing measurements: {sorted(missing)}")
            for field in (
                "visible_or_discovered_schema",
                "direct_recipient_callable",
                "matching_local_request_start",
                "sibling_route_health",
                "refresh_or_reload_between_samples",
            ):
                _require(isinstance(measurements[field], bool), f"{sample_name}.{field} must be boolean")
            caller_identity = measurements["caller_id_or_process_id"]
            _require(caller_identity is None or (isinstance(caller_identity, str) and caller_identity.strip()), f"{sample_name}.caller_id_or_process_id must be null or a non-empty string")
            error_class = measurements["exact_client_error_class"]
            _require(error_class is None or (isinstance(error_class, str) and error_class.strip()), f"{sample_name}.exact_client_error_class must be null or a non-empty string")
            if measurements["direct_recipient_callable"]:
                _require(error_class is None, f"{sample_name}.exact_client_error_class must be null when direct_recipient_callable is true")
            else:
                _require(isinstance(error_class, str) and error_class.strip(), f"{sample_name}.exact_client_error_class must be a non-empty string when direct_recipient_callable is false")
        _require(before["canaries"] == after["canaries"], "paired samples must rerun identical canary definitions")
        if expected_canaries is None:
            expected_canaries = before["canaries"]
        else:
            _require(before["canaries"] == expected_canaries, "all pairs must use identical canary definitions")
        _require(before["canaries"] == CANARY_DEFINITIONS, "canary definitions must match preregistration exactly")
        _require(before["measurements"]["refresh_or_reload_between_samples"] is False, "before sample must precede refresh/reload")
        if pair["kind"] == "treatment":
            _require(pair.get("stimulus") == "refresh your memory", "treatment stimulus must match preregistration exactly")
            _require(after["measurements"]["refresh_or_reload_between_samples"] is True, "treatment must record refresh between samples")
        else:
            _require(not pair.get("stimulus"), "control must not include refresh stimulus")
            _require(after["measurements"]["refresh_or_reload_between_samples"] is False, "control must not record refresh between samples")
        normalized.append(pair)

    return {"ok": True, "pairs": normalized}
def classify(record: dict) -> str:
    validated = validate_record(record)
    controls = [p for p in validated["pairs"] if p["kind"] == "control"]
    treatments = [p for p in validated["pairs"] if p["kind"] == "treatment"]
    stable_controls = bool(controls) and all(
        p["before"]["measurements"]["direct_recipient_callable"] is True
        and p["after"]["measurements"]["direct_recipient_callable"] is True
        for p in controls
    )
    changed_treatments = [
        p for p in treatments
        if p["before"]["measurements"]["direct_recipient_callable"] is True
        and p["after"]["measurements"]["direct_recipient_callable"] is False
        and p["before"]["measurements"]["sibling_route_health"] is True
        and p["after"]["measurements"]["sibling_route_health"] is True
        and p["after"]["measurements"]["matching_local_request_start"] is False
    ]
    if stable_controls and len(changed_treatments) >= 2:
        return "SUPPORT_H1"
    if changed_treatments:
        return "REPRODUCTION_ONLY"
    return "WEAKEN_H1"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("record", type=Path)
    args = parser.parse_args()
    record = json.loads(args.record.read_text(encoding="utf-8"))
    try:
        result = {"ok": True, "classification": classify(record)}
    except ValueError as exc:
        result = {"ok": False, "error": str(exc)}
    print(json.dumps(result, separators=(",", ":")))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
