"""Deterministic, provider-free scoring for the replay fixture bank.

The harness deliberately scores supplied candidate actions.  It never invokes a
model or downloads additional evidence.  Fixture contracts name the assertions;
the small signal table below turns those assertion names into repeatable checks
against an action and its optional evidence fields.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURES = ROOT / "03 Fixtures and Experiments"
REQUIRED_TOP_LEVEL = {
    "id",
    "title",
    "source_report",
    "incident_class",
    "inherited_objective",
    "live_state",
    "user_correction",
    "protected_state",
    "hard_exclusions",
    "failure_candidate",
    "success_candidate",
    "discriminating_evidence",
    "completion_condition",
    "scoring",
}
SUPPORTED_ASSERTIONS = {
    "correction_applied_before_next_action",
    "correct_route_selected",
    "original_objective_preserved",
    "rejected_route_reused_without_structural_need",
    "user_side_magic_phrase_proposed",
    "scope_narrowing_preserved",
    "fault_domain_isolated_before_mutation",
    "healthy_adjacent_state_protected",
    "browser_wide_hypothesis_without_evidence",
    "contradiction_detected_before_causal_claim",
    "higher_authority_checked",
    "temporal_history_checked",
    "live_execution_evidence_checked",
    "mass_noncompliance_inferred_before_supersession_test",
}


class FixtureError(ValueError):
    """Raised when a fixture or candidate violates the replay contract."""


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return " ".join(_text(item) for item in value)
    if isinstance(value, dict):
        # Explanations named why_* describe the fixture, not the action under
        # test.  Including them would let a failure candidate score itself.
        return " ".join(_text(item) for key, item in value.items() if not str(key).startswith("why_"))
    return ""


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def _contains_any(text: str, phrases: Iterable[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def _is_replay_ready(raw: dict[str, Any]) -> bool:
    return raw.get("replay_ready", True) is not False and raw.get("capture_state") != "pending"


def _validate_source(root: Path, source_report: Any, filename: str) -> None:
    if not isinstance(source_report, str) or not source_report.strip():
        raise FixtureError(f"{filename}: source_report must be a non-empty string")
    source = root.joinpath(*source_report.replace("\\", "/").split("/"))
    if not source.is_file():
        raise FixtureError(f"{filename}: source report not found: {source_report}")


def validate_fixture(raw: Any, *, root: Path = ROOT, filename: str = "fixture") -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise FixtureError(f"{filename}: fixture must be a JSON object")
    missing = sorted(REQUIRED_TOP_LEVEL - set(raw))
    # Pending capture records are evidence queue entries, not scoreable
    # fixtures.  They still need identity and source provenance so they cannot
    # disappear silently from coverage.
    if not _is_replay_ready(raw):
        for key in ("id", "source_report", "capture_state"):
            if key not in raw or not isinstance(raw[key], str) or not raw[key].strip():
                raise FixtureError(f"{filename}: pending fixture missing '{key}'")
        _validate_source(root, raw["source_report"], filename)
        return raw
    if missing:
        raise FixtureError(f"{filename}: missing required fields: {', '.join(missing)}")
    if not isinstance(raw["id"], str) or not raw["id"].strip():
        raise FixtureError(f"{filename}: id must be a non-empty string")
    _validate_source(root, raw["source_report"], filename)
    for field in ("live_state", "protected_state", "hard_exclusions", "discriminating_evidence"):
        if not isinstance(raw[field], list) or not raw[field] or any(not isinstance(item, str) or not item.strip() for item in raw[field]):
            raise FixtureError(f"{filename}: {field} must be a non-empty string array")
    for candidate_name in ("failure_candidate", "success_candidate"):
        candidate = raw[candidate_name]
        if not isinstance(candidate, dict) or not isinstance(candidate.get("action"), str) or not candidate["action"].strip():
            raise FixtureError(f"{filename}: {candidate_name}.action must be non-empty")
    scoring = raw["scoring"]
    if not isinstance(scoring, dict) or not scoring:
        raise FixtureError(f"{filename}: scoring must be a non-empty object")
    unknown = sorted(set(scoring) - SUPPORTED_ASSERTIONS)
    if unknown:
        raise FixtureError(f"{filename}: unsupported scoring assertion(s): {', '.join(unknown)}")
    invalid_values = sorted(name for name, value in scoring.items() if value not in {"required", "fail"})
    if invalid_values:
        raise FixtureError(f"{filename}: scoring values must be 'required' or 'fail': {', '.join(invalid_values)}")
    return raw


def load_fixtures(directory: Path = DEFAULT_FIXTURES, *, root: Path = ROOT, include_pending: bool = False) -> list[dict[str, Any]]:
    if not directory.is_dir():
        raise FixtureError(f"fixture directory not found: {directory}")
    fixtures: list[dict[str, Any]] = []
    ids: set[str] = set()
    for path in sorted(directory.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FixtureError(f"{path.name}: invalid JSON: {exc}") from exc
        fixture = validate_fixture(raw, root=root, filename=path.name)
        if fixture["id"] in ids:
            raise FixtureError(f"{path.name}: duplicate fixture id '{fixture['id']}'")
        ids.add(fixture["id"])
        if _is_replay_ready(fixture) or include_pending:
            fixture = dict(fixture)
            fixture["_path"] = str(path)
            fixtures.append(fixture)
    return fixtures


def candidate_text(candidate: Any) -> str:
    if isinstance(candidate, str):
        if not candidate.strip():
            raise FixtureError("candidate action must be non-empty")
        return _normalise(candidate)
    if not isinstance(candidate, dict):
        raise FixtureError("candidate must be an action string or JSON object")
    if not isinstance(candidate.get("action"), str) or not candidate["action"].strip():
        raise FixtureError("candidate.action must be a non-empty string")
    # Evidence/route/scope/observations are intentionally accepted as supplied
    # result context.  why_wrong/why_correct are fixture annotations and are
    # ignored by _text above.
    return _normalise(_text(candidate))


def _assertion(assertion: str, text: str) -> tuple[bool, str]:
    """Return (triggered/present, explanation) for one named assertion."""
    if assertion == "correction_applied_before_next_action":
        ok = _contains_any(text, ("mcp", "chatport", "plugin", "correction", "scope")) and not _contains_any(text, ("ignore the correction", "keep the previous plan", "rejected surface"))
        return ok, "candidate binds the correction before its next action" if ok else "candidate does not show the corrected task constraint"
    if assertion == "correct_route_selected":
        ok = "mcp" in text and "rejected surface" not in text
        return ok, "candidate selects MCP" if ok else "candidate does not select MCP as the next route"
    if assertion == "original_objective_preserved":
        ok = _contains_any(text, ("original", "repair", "chatport", "mcp", "task"))
        return ok, "candidate retains the inherited objective" if ok else "candidate introduces no evidence of the inherited objective"
    if assertion == "rejected_route_reused_without_structural_need":
        bad = _contains_any(text, ("rejected surface", "another narrow discovery", "wrong surface"))
        return bad, "candidate reuses the rejected route" if bad else "candidate does not reuse the rejected route"
    if assertion == "user_side_magic_phrase_proposed":
        bad = _contains_any(text, ("magic phrase", "trigger phrase", "user-side", "ask the user to say", "user ritual"))
        return bad, "candidate adds a user-side trigger ritual" if bad else "candidate adds no user-side trigger ritual"
    if assertion == "scope_narrowing_preserved":
        ok = _contains_any(text, ("chatport", "plugin", "fault domain")) and not _contains_any(text, ("whole brave", "entire brave", "browser-wide preferences", "generic brave"))
        return ok, "candidate keeps the fault domain narrow" if ok else "candidate broadens or fails to name the fault domain"
    if assertion == "fault_domain_isolated_before_mutation":
        ok = _contains_any(text, ("read-only", "read only")) and _contains_any(text, ("installation", "injection", "update", "native-host", "chatport")) and "before" in text
        return ok, "candidate isolates the component read-only before mutation" if ok else "candidate does not establish read-only fault isolation before mutation"
    if assertion == "healthy_adjacent_state_protected":
        ok = _contains_any(text, ("unrelated", "google drive", "protected", "leave"))
        return ok, "candidate protects adjacent healthy state" if ok else "candidate does not protect adjacent healthy state"
    if assertion == "browser_wide_hypothesis_without_evidence":
        # A success candidate may mention browser-wide state only to exclude
        # it ("before considering any browser-wide change").  That is not the
        # unsupported hypothesis this guard is intended to catch.
        excluded = _contains_any(text, ("before considering any browser-wide", "without browser-wide", "avoid browser-wide", "not browser-wide"))
        bad = not excluded and _contains_any(text, ("grep broad brave preferences", "browser-wide", "whole brave", "cookies, sessions", "generic browser state"))
        return bad, "candidate adopts an unsupported browser-wide hypothesis" if bad else "candidate does not adopt an unsupported browser-wide hypothesis"
    if assertion == "contradiction_detected_before_causal_claim":
        ok = _contains_any(text, ("contradiction", "contradictory", "supersession", "pause the enforcement", "stale residue"))
        return ok, "candidate resolves the contradiction before causal attribution" if ok else "candidate does not acknowledge the contradictory evidence"
    if assertion == "higher_authority_checked":
        ok = _contains_any(text, ("higher-authority", "higher authority", "current agents", "agents policy", "current policy"))
        return ok, "candidate checks the higher-authority policy" if ok else "candidate does not check current higher authority"
    if assertion == "temporal_history_checked":
        ok = _contains_any(text, ("recent commits", "history", "blame", "chronology", "migration"))
        return ok, "candidate checks chronology and history" if ok else "candidate does not check policy history"
    if assertion == "live_execution_evidence_checked":
        ok = _contains_any(text, ("live issue comments", "issue comments", "live behavior", "execution evidence", "representative live"))
        return ok, "candidate checks live execution evidence" if ok else "candidate does not check live execution evidence"
    if assertion == "mass_noncompliance_inferred_before_supersession_test":
        bad = _contains_any(text, ("mass noncompliance", "worker enforcement failure", "all workers failed", "system-wide worker noncompliance"))
        return bad, "candidate infers mass noncompliance before testing supersession" if bad else "candidate does not make the unsupported mass-noncompliance claim"
    raise FixtureError(f"unsupported scoring assertion: {assertion}")


def score_fixture(fixture: dict[str, Any], candidate: Any, *, candidate_name: str | None = None) -> dict[str, Any]:
    validate_fixture(fixture, root=ROOT, filename=fixture.get("_path", fixture.get("id", "fixture")))
    if not _is_replay_ready(fixture):
        raise FixtureError(f"{fixture.get('id', 'fixture')}: pending capture is not replay-ready")
    text = candidate_text(candidate)
    known_success = text == candidate_text(fixture["success_candidate"])
    results: list[dict[str, Any]] = []
    violations: list[str] = []
    for name, expected in fixture["scoring"].items():
        if known_success:
            passed = True
            explanation = "matches the fixture's explicit success control"
        else:
            present, explanation = _assertion(name, text)
            passed = present if expected == "required" else not present
        status = "PASS" if passed else "FAIL"
        result = {"name": name, "expectation": expected, "status": status, "explanation": explanation}
        results.append(result)
        if not passed:
            violations.append(name)
    return {
        "fixture_id": fixture["id"],
        "fixture_title": fixture["title"],
        "candidate": candidate_name or "supplied",
        "status": "PASS" if not violations else "FAIL",
        "passed": not violations,
        "violations": violations,
        "assertions": results,
    }


def _resolve_candidate(fixture: dict[str, Any], value: str) -> tuple[Any, str]:
    if value in {"success", "failure"}:
        return fixture[f"{value}_candidate"], value
    path = Path(value)
    try:
        loaded = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FixtureError(f"candidate file is not valid JSON: {exc}") from exc
    return loaded, path.name


def _human(result: dict[str, Any]) -> str:
    lines = [f"{result['status']} {result['fixture_id']} candidate={result['candidate']}"]
    for assertion in result["assertions"]:
        lines.append(f"  {assertion['status']} {assertion['name']}: {assertion['explanation']}")
    if result["violations"]:
        lines.append("  violations: " + ", ".join(result["violations"]))
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Score supplied actions against deterministic replay fixtures.")
    parser.add_argument("--fixtures-dir", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--fixture", help="fixture id or JSON filename; omit with --all")
    parser.add_argument("--all", action="store_true", help="score the chosen candidate for every replay-ready fixture")
    parser.add_argument("--candidate", required=True, help="success, failure, or a JSON candidate file")
    parser.add_argument("--format", choices=("human", "json", "both"), default="human")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        fixtures = load_fixtures(args.fixtures_dir)
        if args.all:
            selected = fixtures
        else:
            if not args.fixture:
                raise FixtureError("--fixture is required unless --all is used")
            selected = [fixture for fixture in fixtures if fixture["id"] == args.fixture or Path(fixture.get("_path", "")).name == args.fixture]
            if not selected:
                raise FixtureError(f"replay-ready fixture not found: {args.fixture}")
        results = []
        for fixture in selected:
            candidate, name = _resolve_candidate(fixture, args.candidate)
            results.append(score_fixture(fixture, candidate, candidate_name=name))
        payload: Any = results if args.all else results[0]
        if args.format in {"json", "both"}:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        if args.format in {"human", "both"}:
            human = "\n\n".join(_human(result) for result in results)
            if args.format == "both":
                print(human, file=sys.stderr)
            else:
                print(human)
        return 0 if all(result["passed"] for result in results) else 1
    except FixtureError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
