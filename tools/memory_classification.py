from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    from .memory_lifecycle import is_expired
except ImportError:
    from memory_lifecycle import is_expired

PROJECT_MARKERS = {
    "p3": ("p3",),
    "tiny3d": ("tiny3d",),
    "lowvram": ("lowvram", "lowvram3d"),
}
ROLE_MARKERS = {
    "orchestrator": ("orchestrator",),
    "worker": ("worker", "workers"),
}
SEMANTIC_CATEGORIES = (
    "CORRECTION",
    "PREFERENCE",
    "DECISION",
    "WORKFLOW_POLICY",
    "INCIDENT",
    "PROJECT_STATE",
    "STATE_SNAPSHOT",
    "CHECKPOINT",
    "FACT",
    "PROJECT_LESSON",
    "LESSON",
    "HYPOTHESIS",
)
DOMAINS = (
    "project:p3",
    "project:tiny3d",
    "project:lowvram",
    "cross-project",
    "memory-system",
    "assistant-orchestration",
    "mcp-control-plane",
    "regression-research",
    "machine-ops",
    "chatgpt-personalization",
    "global",
)
DURABILITIES = ("DURABLE", "HISTORICAL", "TIME_BOUNDED", "EPHEMERAL", "REVIEW")
SENSITIVITIES = ("CLEAR", "REVIEW", "EXCLUDE")

_INCIDENT_WORDS = {
    "incident", "security-incident", "slopwall", "red-alert", "redalert", "panic-alert", "recurrence",
}
_POLICY_WORDS = {
    "policy", "rule", "runbook", "workflow", "contract", "guard", "invariant", "authority", "arming",
}
_CHECKPOINT_WORDS = {
    "checkpoint", "snapshot", "change-point", "safepoint", "safe-point", "current-snapshot",
}
_HYPOTHESIS_WORDS = {"hypothesis", "theory", "unproven", "not-proven", "unknown-cause", "causal-test"}
_EPHEMERAL_SCOPE_FRAGMENTS = (
    "tool-availability/checkpoint",
    "assistant-orchestration/current-snapshot",
    "pc-cleanup/disk-recovery",
    "chatgpt-context-checkpoint",
    "chatgpt-context-maintenance",
)
_ENTITY_MARKERS = {
    "p3": ("p3",),
    "tiny3d": ("tiny3d",),
    "lowvram": ("lowvram", "lowvram3d"),
    "mcp": ("mcp",),
    "busycoordinator": ("busycoordinator", "busy-coordinator"),
    "vault": ("vault",),
    "github": ("github",),
    "chatgpt": ("chatgpt",),
    "unreal": ("unreal", "ue5", "ue"),
}
_STRONG_SENSITIVE_PATTERNS = (
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgho_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{10,}\b"),
    re.compile(r"\b(?:password|passwd|api[_ -]?key|token)\s*[:=]\s*\S+", re.I),
    re.compile(r"\b(?:password|passwd)\s+(?:is|was)\s+[\"']?(?=[^\s\"']{8,})(?=[^\s\"']*[A-Za-z])(?=[^\s\"']*\d)[^\s\"']+", re.I),
    re.compile(r"\b(?:api[_ -]?key|access[_ -]?token|auth[_ -]?token|token)\s+(?:is|was)\s+[\"']?[A-Za-z0-9._~+/=-]{16,}", re.I),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}", re.I),
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b\d{4}(?:[\s-]\d{4}){3}\b"),
)
_REVIEW_SENSITIVE_PATTERNS = (
    re.compile(r"\bcredential(?:s)?\b", re.I),
    re.compile(r"\bprivate\s*key\b", re.I),
    re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
)


def _grouped_matchers(patterns: tuple[re.Pattern[str], ...]) -> tuple[re.Pattern[str], ...]:
    """Combine equivalent regex sources by case-sensitivity without changing match semantics."""
    groups: list[re.Pattern[str]] = []
    for ignore_case in (False, True):
        sources = [pattern.pattern for pattern in patterns if bool(pattern.flags & re.IGNORECASE) is ignore_case]
        if not sources:
            continue
        combined = "|".join(f"(?:{source})" for source in sources)
        groups.append(re.compile(combined, re.IGNORECASE if ignore_case else 0))
    return tuple(groups)


_STRONG_SENSITIVE_MATCHERS = _grouped_matchers(_STRONG_SENSITIVE_PATTERNS)
_REVIEW_SENSITIVE_MATCHERS = _grouped_matchers(_REVIEW_SENSITIVE_PATTERNS)


def token_words(value: Any) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", str(value or "").casefold()))


def _descriptor_values(entry: dict[str, Any]) -> list[Any]:
    return [entry.get("scope"), entry.get("title"), *(entry.get("tags") or [])]


def _descriptor_text(entry: dict[str, Any]) -> str:
    return " ".join(str(value or "") for value in _descriptor_values(entry)).casefold()


def projects_from_text(value: Any) -> set[str]:
    words = token_words(value)
    found: set[str] = set()
    for project, markers in PROJECT_MARKERS.items():
        if any(marker in words for marker in markers):
            found.add(project)
    return found


def roles_from_text(value: Any) -> set[str]:
    words = token_words(value)
    found: set[str] = set()
    for role, markers in ROLE_MARKERS.items():
        if any(marker in words for marker in markers):
            found.add(role)
    return found


def entry_projects(entry: dict[str, Any]) -> set[str]:
    explicit = str(entry.get("project") or "").strip().casefold()
    if explicit:
        # A single primary project remains authoritative over incidental title/body
        # mentions, but structured scope/tags may explicitly declare a cross-project
        # memory. This preserves a primary owner without erasing deliberate secondary
        # project descriptors such as `p3-tiny3d-*` or a `tiny3d` tag.
        found = {explicit}
        if explicit in PROJECT_MARKERS:
            for value in (entry.get("scope"), *(entry.get("tags") or [])):
                found.update(projects_from_text(value))
        return found
    found: set[str] = set()
    for value in _descriptor_values(entry):
        found.update(projects_from_text(value))
    return found


def entry_roles(entry: dict[str, Any]) -> set[str]:
    found: set[str] = set()
    for value in _descriptor_values(entry):
        found.update(roles_from_text(value))
    return found


def infer_single_project(entry: dict[str, Any]) -> str | None:
    projects = entry_projects(entry)
    return next(iter(projects)) if len(projects) == 1 else None


def _contains_any(text: str, markers: set[str]) -> bool:
    normalized = text.replace("_", "-").replace("/", "-").replace(":", "-")
    words = set(re.findall(r"[a-z0-9-]+", normalized))
    return any(marker in normalized or marker in words for marker in markers)


def _domain(entry: dict[str, Any], projects: set[str]) -> str:
    if len(projects) == 1:
        return f"project:{next(iter(projects))}"
    if len(projects) > 1:
        return "cross-project"
    desc = _descriptor_text(entry)
    words = token_words(desc)
    if any(x in desc for x in ("memory", "corpus", "vault-memory")):
        return "memory-system"
    if any(x in desc for x in ("assistant-orchestration", "response-quality", "slopwall", "panic-alert", "chatgpt-context")):
        return "assistant-orchestration"
    if any(x in desc for x in ("mcp", "control-plane", "busy", "connector", "tool-routing")):
        return "mcp-control-plane"
    if "regression-research" in desc:
        return "regression-research"
    if any(x in desc for x in ("pc-cleanup", "disk-recovery", "machine", "headroom")):
        return "machine-ops"
    if any(x in desc for x in ("personal-instructions", "personalization")):
        return "chatgpt-personalization"
    return "global"


def _semantic_category(entry: dict[str, Any], projects: set[str]) -> str:
    kind = str(entry.get("kind") or "lesson").casefold()
    desc = _descriptor_text(entry)
    body_hint = str(entry.get("text") or "")[:600].casefold()
    joined = f"{desc} {body_hint}"
    if kind == "correction":
        return "CORRECTION"
    if kind == "preference":
        return "PREFERENCE"
    if kind == "decision":
        return "DECISION"
    if kind == "status":
        return "CHECKPOINT" if _contains_any(joined, _CHECKPOINT_WORDS) else ("PROJECT_STATE" if projects else "STATE_SNAPSHOT")
    if kind == "fact":
        return "PROJECT_STATE" if projects and _contains_any(joined, _CHECKPOINT_WORDS | {"status", "state"}) else "FACT"
    if str(entry.get("state") or "").upper() == "PROVISIONAL" and _contains_any(joined, _HYPOTHESIS_WORDS):
        return "HYPOTHESIS"
    if _contains_any(joined, _INCIDENT_WORDS):
        return "INCIDENT"
    # Lessons encode reusable interpretation/guidance. Policy/authority language must
    # win over checkpoint vocabulary so a lesson *about* a historical snapshot is
    # not demoted to HISTORICAL and silently removed from ordinary recall. Actual
    # status records still take the explicit checkpoint path above.
    if _contains_any(joined, _POLICY_WORDS):
        return "WORKFLOW_POLICY"
    if _contains_any(joined, _CHECKPOINT_WORDS):
        return "CHECKPOINT"
    if projects:
        return "PROJECT_LESSON"
    return "LESSON"


def _persisted_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _persisted_strings(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _persisted_strings(item)


def _sensitivity(entry: dict[str, Any]) -> tuple[str, list[str]]:
    tags = {str(tag).casefold() for tag in entry.get("tags", [])}
    if tags & {"sensitive", "private", "secret", "pii"} or entry.get("sensitive") is True or entry.get("private") is True:
        return "EXCLUDE", ["explicit_sensitive_marker"]
    persisted = list(_persisted_strings(entry))
    if any(matcher.search(text) for text in persisted for matcher in _STRONG_SENSITIVE_MATCHERS):
        return "EXCLUDE", ["secret_like_value"]
    if any(matcher.search(text) for text in persisted for matcher in _REVIEW_SENSITIVE_MATCHERS):
        return "REVIEW", ["sensitivity_pattern_requires_review"]
    return "CLEAR", []


def _durability(entry: dict[str, Any], category: str, domain: str) -> str:
    scope = str(entry.get("scope") or "").casefold()
    if is_expired(entry):
        return "HISTORICAL"
    if any(fragment in scope for fragment in _EPHEMERAL_SCOPE_FRAGMENTS):
        return "EPHEMERAL"
    if category in {"CHECKPOINT", "STATE_SNAPSHOT"}:
        return "HISTORICAL"
    if entry.get("expires_at"):
        return "TIME_BOUNDED"
    if str(entry.get("state") or "").upper() == "PROVISIONAL":
        return "REVIEW"
    return "DURABLE"


def _entities(entry: dict[str, Any], projects: set[str]) -> list[str]:
    # Entities are secondary retrieval labels, so they may use the full body. Unlike
    # projects/roles they never re-scope or grant authority to the record.
    haystack = " ".join([_descriptor_text(entry), str(entry.get("text") or "").casefold()])
    words = token_words(haystack)
    found = set(projects)
    for entity, markers in _ENTITY_MARKERS.items():
        if any(marker in words for marker in markers):
            found.add(entity)
    return sorted(found)


def classify_entry(entry: dict[str, Any]) -> dict[str, Any]:
    projects = entry_projects(entry)
    roles = entry_roles(entry)
    domain = _domain(entry, projects)
    category = _semantic_category(entry, projects)
    sensitivity, sensitivity_reasons = _sensitivity(entry)
    durability = _durability(entry, category, domain)
    review_reasons: list[str] = list(sensitivity_reasons)
    if len(projects) > 1:
        review_reasons.append("multiple_project_descriptors")
    if str(entry.get("state") or "").upper() == "PROVISIONAL":
        review_reasons.append("claim_state_provisional")
    if category == "HYPOTHESIS" and str(entry.get("state") or "").upper() == "PROVEN":
        review_reasons.append("proven_record_classifies_as_hypothesis")
    confidence = "HIGH"
    if review_reasons:
        confidence = "REVIEW"
    elif domain == "global" and category in {"LESSON", "FACT"}:
        confidence = "MEDIUM"
    return {
        "schema_version": 1,
        "semantic_category": category,
        "primary_domain": domain,
        "projects": sorted(projects),
        "roles": sorted(roles),
        "entities": _entities(entry, projects),
        "durability": durability,
        "sensitivity": sensitivity,
        "expired": is_expired(entry),
        "confidence": confidence,
        "review_reasons": sorted(set(review_reasons)),
    }


def _load_bank_entry(path: Path, memory_id: str) -> dict[str, Any]:
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        if isinstance(raw, dict) and raw.get("id") == memory_id:
            return raw
    raise SystemExit(f"memory id not found: {memory_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify one memory entry using the bounded deterministic #87 taxonomy.")
    parser.add_argument("entry", type=Path, nargs="?", help="JSON file containing one memory entry")
    parser.add_argument("--bank", type=Path, help="JSONL memory bank to classify from")
    parser.add_argument("--id", dest="memory_id", help="memory id when --bank is used")
    args = parser.parse_args()
    if args.entry is not None:
        if args.bank is not None or args.memory_id is not None:
            parser.error("use either ENTRY or --bank/--id")
        raw = json.loads(args.entry.read_text(encoding="utf-8-sig"))
    else:
        if args.bank is None or not args.memory_id:
            parser.error("ENTRY or both --bank and --id are required")
        raw = _load_bank_entry(args.bank, args.memory_id)
    if not isinstance(raw, dict):
        raise SystemExit("entry must be one JSON object")
    payload = json.dumps({"id": raw.get("id"), "classification": classify_entry(raw)}, ensure_ascii=False, indent=2) + "\n"
    stream = getattr(__import__("sys").stdout, "buffer", None)
    if stream is None:
        print(json.dumps({"id": raw.get("id"), "classification": classify_entry(raw)}, ensure_ascii=True, indent=2))
    else:
        stream.write(payload.encode("utf-8", "backslashreplace"))
        stream.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
