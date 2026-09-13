from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any


def _query_helpers():
    try:
        from tools.timeline_materializer import _minimum_query_matches, _query_concepts, _query_tokens
    except ImportError:
        from timeline_materializer import _minimum_query_matches, _query_concepts, _query_tokens
    return _query_concepts, _query_tokens, _minimum_query_matches


def _semantic_score(query: str, weighted_fields: list[tuple[float, str]]) -> tuple[float, int, int]:
    query_concepts, query_tokens, minimum_query_matches = _query_helpers()
    concepts = query_concepts(query)
    if not concepts:
        return 0.0, 0, 0
    token_fields = [(weight, query_tokens(text)) for weight, text in weighted_fields if text]
    matched = 0
    score = 0.0
    for concept in concepts:
        best = max((weight for weight, tokens in token_fields if tokens & concept), default=0.0)
        if best:
            matched += 1
            score += best
    required = minimum_query_matches(len(concepts))
    if matched < required:
        return 0.0, matched, required
    score *= 0.75 + 1.35 * (matched / min(len(concepts), 6))
    return score, matched, required


def _identity_multiplier(query: str, identity: str) -> float:
    query_concepts, query_tokens, _ = _query_helpers()
    identity_tokens = query_tokens(identity)
    matched = sum(1 for concept in query_concepts(query) if concept & identity_tokens)
    return 1.0 + min(0.7, 0.35 * matched)


def _flag_value(command: list[str], *names: str) -> str | None:
    for name in names:
        try:
            index = command.index(name)
        except ValueError:
            continue
        if index + 1 < len(command):
            return command[index + 1]
    return None


def _gh_repo(command: list[str], context: str) -> str | None:
    repo = _flag_value(command, "--repo", "-R")
    if repo:
        return repo
    match = re.search(r"(?m)^repo=([^\s]+)$", context)
    return match.group(1) if match else None


def _comment_text(comments: Any) -> tuple[str, int]:
    if not isinstance(comments, list):
        return "", 0
    bodies = [str(row.get("body") or "") for row in comments if isinstance(row, dict)]
    return "\n".join(body for body in bodies if body), len(comments)


def _cache_objects(command: list[str], context: str, stdout_text: str) -> list[dict[str, Any]]:
    if len(command) < 2 or command[0] not in {"issue", "pr"} or command[1] not in {"list", "view"}:
        return []
    repo = _gh_repo(command, context)
    if not repo:
        return []
    try:
        payload = json.loads(stdout_text)
    except json.JSONDecodeError:
        return []

    rows: list[dict[str, Any]]
    if command[1] == "list":
        rows = [row for row in payload if isinstance(row, dict)] if isinstance(payload, list) else []
    elif isinstance(payload, dict):
        rows = [payload]
    elif isinstance(payload, list) and len(payload) == 1 and isinstance(payload[0], dict):
        rows = [payload[0]]
    else:
        rows = []

    command_number = str(command[2]).strip() if command[1] == "view" and len(command) >= 3 else ""
    objects: list[dict[str, Any]] = []
    for row in rows:
        number = str(row.get("number") or command_number).strip()
        if not number.isdigit():
            continue
        comments_text, comment_count = _comment_text(row.get("comments"))
        label = str(row.get("title") or "").strip() or None
        rich_text = "\n".join(value for value in (
            label or "",
            str(row.get("body") or ""),
            comments_text,
            str(row.get("state") or ""),
            str(row.get("headRefName") or ""),
            str(row.get("baseRefName") or ""),
        ) if value)
        objects.append({
            "kind": f"github_{command[0]}_cache",
            "reference": f"{repo}#{number}",
            "repo": repo,
            "label": label,
            "rich_text": rich_text,
            "comment_count": comment_count,
            "cache_command": f"{command[0]} {command[1]}",
        })
    return objects


def _exact_issue_numbers(query: str) -> list[str]:
    numbers: list[str] = []
    seen: set[str] = set()
    for number in re.findall(r"#(\d{1,9})\b", query):
        if number in seen:
            continue
        seen.add(number)
        numbers.append(number)
        if len(numbers) >= 3:
            break
    return numbers


def _gh_buffer_proxy() -> str | None:
    executable = shutil.which("gh")
    if not executable:
        return None
    normalized = executable.replace("\\", "/").casefold()
    return executable if "/gh-buffer-proxy/" in normalized else None


def _cached_references(rows: list[tuple[Any, ...]]) -> set[str]:
    references: set[str] = set()
    for _, _, returncode, stdout, _, command_json, context in rows:
        if int(returncode or 0) != 0:
            continue
        try:
            command = json.loads(str(command_json or "[]"))
        except json.JSONDecodeError:
            continue
        if not isinstance(command, list) or not all(isinstance(value, str) for value in command):
            continue
        stdout_text = bytes(stdout or b"").decode("utf-8", "replace") if not isinstance(stdout, str) else stdout
        for obj in _cache_objects(command, str(context or ""), stdout_text):
            references.add(str(obj["reference"]).casefold())
    return references


def _hydrate_exact_gh_buffer_refs(
    query: str,
    repo_hints: list[str],
    known_references: set[str],
) -> tuple[list[tuple[Any, ...]], dict[str, Any]]:
    numbers = _exact_issue_numbers(query)
    repos: list[str] = []
    seen_repos: set[str] = set()
    for repo in repo_hints:
        normalized = str(repo or "").strip().strip("/")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", normalized):
            continue
        folded = normalized.casefold()
        if folded in seen_repos:
            continue
        seen_repos.add(folded)
        repos.append(normalized)
        if len(repos) >= 2:
            break
    if not numbers or not repos:
        return [], {"status": "NOT_NEEDED", "attempted": 0, "hits": 0}

    proxy = _gh_buffer_proxy()
    if not proxy:
        return [], {"status": "UNAVAILABLE", "attempted": 0, "hits": 0, "reason": "gh-buffer-proxy_not_on_path"}

    folded_query = query.casefold()
    if re.search(r"\b(?:pr|pull request)\b", folded_query):
        kinds = ["pr"]
    elif re.search(r"\bissue\b", folded_query):
        kinds = ["issue"]
    else:
        kinds = ["issue", "pr"]

    attempted = 0
    hydrated_rows: list[tuple[Any, ...]] = []
    for repo in repos:
        for number in numbers:
            reference = f"{repo}#{number}".casefold()
            if reference in known_references:
                continue
            for kind in kinds:
                attempted += 1
                logical_command = [kind, "view", number, "--repo", repo, "--json", "number,title,body,comments,state"]
                try:
                    completed = subprocess.run(
                        [proxy, *logical_command],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=3.0,
                        check=False,
                    )
                except (OSError, subprocess.TimeoutExpired):
                    continue
                if completed.returncode != 0:
                    continue
                if not _cache_objects(logical_command, f"host=github.com\nrepo={repo}", completed.stdout):
                    continue
                now = time.time()
                hydrated_rows.append((
                    now,
                    now + 60.0,
                    0,
                    completed.stdout.encode("utf-8"),
                    completed.stderr.encode("utf-8"),
                    json.dumps(logical_command),
                    f"host=github.com\nrepo={repo}",
                ))
                known_references.add(reference)
                break
    return hydrated_rows, {
        "status": "USED" if attempted else "NOT_NEEDED",
        "attempted": attempted,
        "hits": len(hydrated_rows),
        "max_repositories": 2,
        "max_numbers": 3,
        "proxy": "gh-buffer-proxy",
    }


def search_gh_buffer_cache(
    query: str,
    limit: int = 5,
    *,
    cache_path: Path | None = None,
    repo_hints: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    started = time.perf_counter()
    path = cache_path or (Path(os.path.expandvars(r"%LOCALAPPDATA%")) / "gh-buffer" / "cache.sqlite3")
    coverage: dict[str, Any] = {
        "authority": "LOCAL_GH_BUFFER_CACHE_DISCOVERY",
        "read_mode": "READ_ONLY_SQLITE_CACHE",
        "network_fanout": False,
        "repo_content_scan": False,
        "path": str(path),
    }
    if not path.is_file():
        coverage.update({"status": "UNAVAILABLE", "latency_ms": round((time.perf_counter() - started) * 1000, 1)})
        return [], coverage
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=0.25)
        try:
            rows = connection.execute(
                "SELECT created_at, expires_at, returncode, stdout, stderr, command_json, context FROM cache_entries"
            ).fetchall()
        finally:
            connection.close()
    except (sqlite3.Error, OSError) as exc:
        coverage.update({"status": "ERROR", "error": str(exc), "latency_ms": round((time.perf_counter() - started) * 1000, 1)})
        return [], coverage

    exact_rows, exact_lookup = _hydrate_exact_gh_buffer_refs(
        query, list(repo_hints or []), _cached_references(rows)
    )
    rows.extend(exact_rows)

    now = time.time()
    exact_references = {
        f"{str(repo).strip().strip('/')}#{number}".casefold()
        for repo in (repo_hints or [])
        if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", str(repo or "").strip().strip("/"))
        for number in _exact_issue_numbers(query)
    }
    ranked: list[tuple[float, float, str, dict[str, Any]]] = []
    objects_seen = 0
    for created_at, expires_at, returncode, stdout, stderr, command_json, context in rows:
        if int(returncode or 0) != 0:
            continue
        try:
            command = json.loads(str(command_json or "[]"))
        except json.JSONDecodeError:
            continue
        if not isinstance(command, list) or not all(isinstance(value, str) for value in command):
            continue
        stdout_text = bytes(stdout or b"").decode("utf-8", "replace") if not isinstance(stdout, str) else stdout
        stderr_text = bytes(stderr or b"").decode("utf-8", "replace") if not isinstance(stderr, str) else stderr
        command_text = " ".join(command)
        context_text = str(context or "")
        for obj in _cache_objects(command, context_text, stdout_text):
            objects_seen += 1
            score, matched, required = _semantic_score(query, [
                (4.0, obj["rich_text"]),
                (2.2, f"github gh cache buffer ghbuf {obj['repo']} {obj['reference']} {context_text}"),
                (1.2, command_text),
                (0.7, stderr_text),
            ])
            exact_reference_match = str(obj["reference"]).casefold() in exact_references
            if score <= 0 and not exact_reference_match:
                continue
            score *= _identity_multiplier(query, obj["repo"])
            if exact_reference_match:
                score = max(score, 100.0)
            age = max(0.0, now - float(created_at or now))
            hit = {
                "kind": obj["kind"],
                "reference": obj["reference"],
                "authority": "LOCAL_GH_BUFFER_CACHE_DISCOVERY",
                "live_truth_required": True,
                "score": round(score, 3),
                "matched_concepts": matched,
                "required_concepts": required,
                "cached_age_seconds": round(age, 1),
                "cache_expired": float(expires_at or 0.0) < now,
                "cached_comment_count": obj["comment_count"],
                "cached_content": "title_body_comments",
                "cache_command": obj["cache_command"],
                "exact_reference_match": exact_reference_match,
            }
            if obj["label"]:
                hit["label"] = obj["label"][:180]
            stable = f"{obj['kind']}:{obj['reference'].casefold()}"
            ranked.append((score, -age, stable, hit))

    ranked.sort(key=lambda row: (-row[0], -row[1], row[2]))
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _, _, stable, hit in ranked:
        if stable in seen:
            continue
        seen.add(stable)
        deduped.append(hit)
        if len(deduped) >= max(1, int(limit)):
            break
    coverage.update({
        "status": "OK",
        "cache_entries": len(rows),
        "objects_seen": objects_seen,
        "matching_identity_count": len(seen),
        "exact_lookup": exact_lookup,
        "read_mode": (
            "READ_ONLY_SQLITE_CACHE_PLUS_BOUNDED_EXACT_GH_BUFFER_LOOKUP"
            if exact_lookup.get("status") == "USED"
            else "READ_ONLY_SQLITE_CACHE"
        ),
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
    })
    return deduped, coverage
