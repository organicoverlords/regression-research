from __future__ import annotations

import math
import re
from collections import Counter
from datetime import datetime
from typing import Any, Iterable

try:
    from .memory_bank import (
        DEFAULT_HISTORY_LIMIT,
        DEFAULT_RECALL_LIMIT,
        MAX_HISTORY_LIMIT,
        MAX_RECALL_LIMIT,
        load_source_registry,
        search_entries,
        source_relevance,
    )
    from .memory_lifecycle import is_expired
    from .memory_classification import classify_entry
except ImportError:
    from memory_bank import (
        DEFAULT_HISTORY_LIMIT,
        DEFAULT_RECALL_LIMIT,
        MAX_HISTORY_LIMIT,
        MAX_RECALL_LIMIT,
        load_source_registry,
        search_entries,
        source_relevance,
    )
    from memory_lifecycle import is_expired
    from memory_classification import classify_entry

BM25_K1 = 1.2
BM25_B = 0.75
RRF_K = 60.0
RRF_WEIGHTS = {"bm25": 0.70, "char": 0.30}
MIN_QUERY_COVERAGE = 0.45
TITLE_WEIGHT = 3
TAG_WEIGHT = 2
SCOPE_WEIGHT = 2
BODY_WEIGHT = 1

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "but", "by", "can", "could",
    "did", "do", "does", "for", "from", "had", "has", "have", "he", "her", "here", "him", "his",
    "how", "i", "if", "in", "into", "is", "it", "its", "just", "may", "me", "more", "most", "my",
    "no", "not", "of", "on", "or", "our", "should", "so", "some", "than", "that", "the", "their",
    "them", "then", "there", "these", "they", "this", "those", "to", "too", "us", "was", "we", "were",
    "what", "when", "where", "which", "who", "why", "will", "with", "without", "would", "you", "your",
}
_STRICT_ADMISSION_GENERIC_TOKENS = {"display", "expose", "image", "library", "route", "share", "show", "transport", "use"}
_WORD_RE = re.compile(r"[\w]+", flags=re.UNICODE)
_NON_ALNUM_RE = re.compile(r"[^\w]+", flags=re.UNICODE)

# Small domain-neutral concept normalization for natural paraphrases.  These
# aliases affect relevance only; they never grant authority.  Keep groups broad
# enough to be useful outside a benchmark case and narrow enough to preserve
# abstention.
_CONCEPT_GROUPS = (
    ("execution", "command", "commands", "job", "jobs", "task", "tasks", "process", "processes", "request", "requests", "turn", "turns"),
    ("loss", "lost", "lose", "losing", "disappear", "disappeared", "disappears", "died", "dead", "drop", "dropped", "disconnect", "disconnected"),
    ("proof", "prove", "proven", "evidence", "demonstrate", "demonstrated", "establish", "established", "verify", "verified"),
    ("retrieve", "retrieval", "reread", "rereading", "reload", "refresh", "refreshing"),
    ("scope", "area", "areas", "unrelated", "adjacent"),
    ("expand", "spread", "widen", "widened", "expansion", "expanded"),
    ("complete", "completed", "completion", "finish", "finished", "done", "ends", "ended"),
    ("persist", "persistence", "store", "stored", "save", "saved", "preserve", "preserved"),
    ("concurrency", "simultaneous", "simultaneously", "parallel", "concurrent"),
    ("worker", "workers", "runner", "runners", "agent", "agents"),
    ("prune", "trim", "trimming", "pruned", "pruning"),
    ("isolate", "isolated", "isolating", "experiment", "experimental", "experimentally"),
    ("investigation", "diagnostic", "diagnostics", "debug", "debugging", "investigate", "investigating"),
    ("route", "routing", "path", "paths"),
    ("correction", "correct", "corrects", "corrected", "correcting"),
    ("continuity", "intact", "unchanged", "unaffected", "remainder", "rest"),
    ("presentation", "wording", "format", "formatting", "phrasing"),
    ("define", "defined", "defines", "dictate", "dictated", "govern", "governed"),
    ("label", "labels", "taxonomy", "classification"),
    ("cause", "causal", "causality", "rootcause"),
    ("internal", "hidden", "underlying"),
    ("acknowledge", "acknowledged", "acknowledging", "acknowledgement", "acknowledgment"),
    ("burden", "walk", "reconstruct", "reconstruction"),
    ("answer", "answering", "conclusion", "deliverable", "response"),
    ("compact", "concise", "compress", "compressed", "compression", "brief"),
    ("report", "reports", "reporting"),
    ("hypothesis", "hypotheses", "theory", "theories"),
    ("agreement", "agree", "agreed", "agreeing", "accept", "accepted", "mirror"),
    ("reset", "resets", "resetting", "restart", "restarts", "restarted", "restarting"),
    ("dimension", "size", "sized", "scale", "scaled", "scaling", "height", "heights", "dimensions"),
)
_CONCEPT_ALIAS = {alias: group[0] for group in _CONCEPT_GROUPS for alias in group}
_NUMBER_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_NUMBER_ONES = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}


def _normalise_number_words(tokens: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in _NUMBER_TENS and i + 1 < len(tokens) and tokens[i + 1] in _NUMBER_ONES:
            out.append(str(_NUMBER_TENS[token] + _NUMBER_ONES[tokens[i + 1]]))
            i += 2
            continue
        out.append(token)
        i += 1
    return out


def _word_tokens(value: str) -> list[str]:
    out: list[str] = []
    raw_tokens = _normalise_number_words(_WORD_RE.findall(value.casefold()))
    for token in raw_tokens:
        if token in _STOPWORDS:
            continue
        if len(token) < 2 and not token.isdigit():
            continue
        out.append(_CONCEPT_ALIAS.get(token, token))
    return out


_PROOF_VISUAL_QUERY_ALIASES = {
    "picture": "image",
    "pictures": "image",
    "photo": "image",
    "photos": "image",
    "screenshot": "image",
    "screenshots": "image",
}


def _query_word_tokens(value: str) -> list[str]:
    tokens = _word_tokens(value)
    if "proof" not in tokens:
        return tokens
    return [_PROOF_VISUAL_QUERY_ALIASES.get(token, token) for token in tokens]


def _entry_descriptor(entry: dict[str, Any]) -> str:
    return " ".join([
        str(entry.get("title") or ""),
        " ".join(str(tag) for tag in entry.get("tags", [])),
        str(entry.get("scope") or ""),
    ]).strip()


def _weighted_document_tokens(entry: dict[str, Any]) -> list[str]:
    tokens: list[str] = []
    tokens.extend(_word_tokens(str(entry.get("title") or "")) * TITLE_WEIGHT)
    tokens.extend(_word_tokens(" ".join(str(tag) for tag in entry.get("tags", []))) * TAG_WEIGHT)
    tokens.extend(_word_tokens(str(entry.get("scope") or "")) * SCOPE_WEIGHT)
    tokens.extend(_word_tokens(str(entry.get("text") or "")) * BODY_WEIGHT)
    return tokens


def _source_evidence_text(entry: dict[str, Any]) -> str:
    parts = [
        str(entry.get("turn_task") or ""),
        str(entry.get("interpretation") or ""),
        " ".join(str(message) for message in entry.get("source_messages") or []),
    ]
    return " ".join(part for part in parts if part).strip()


def _source_evidence_tokens(entry: dict[str, Any]) -> list[str]:
    # Preserved task/correction wording is searchable evidence, but it must not
    # perturb the canonical lesson corpus or its established BM25 ranking.
    return _word_tokens(_source_evidence_text(entry))


def _eligible_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    superseded = {old for entry in entries for old in entry.get("supersedes", [])}
    return [
        entry for entry in entries
        if entry.get("state") != "REJECTED"
        and entry.get("id") not in superseded
        and not is_expired(entry)
        and classify_entry(entry)["sensitivity"] != "EXCLUDE"
        and classify_entry(entry)["durability"] not in {"EPHEMERAL", "HISTORICAL"}
    ]


def _idf(total_docs: int, document_frequency: int) -> float:
    return math.log(1.0 + (total_docs - document_frequency + 0.5) / (document_frequency + 0.5))


def _bm25_scores(
    doc_counts: list[Counter[str]],
    doc_lengths: list[int],
    df: Counter[str],
    query_weights: dict[str, float],
) -> list[float]:
    if not doc_counts or not query_weights:
        return [0.0] * len(doc_counts)
    total_docs = len(doc_counts)
    avgdl = sum(doc_lengths) / total_docs if total_docs else 1.0
    scores = [0.0] * total_docs
    for term, query_weight in query_weights.items():
        term_df = df.get(term, 0)
        if term_df == 0:
            continue
        term_idf = _idf(total_docs, term_df)
        for idx, counts in enumerate(doc_counts):
            tf = counts.get(term, 0)
            if not tf:
                continue
            dl = doc_lengths[idx]
            norm = BM25_K1 * (1.0 - BM25_B + BM25_B * (dl / avgdl if avgdl else 1.0))
            scores[idx] += query_weight * term_idf * ((tf * (BM25_K1 + 1.0)) / (tf + norm))
    return scores


def _char_ngrams(value: str) -> set[str]:
    normalized = _NON_ALNUM_RE.sub(" ", value.casefold()).strip()
    if not normalized:
        return set()
    padded = f"  {normalized}  "
    grams: set[str] = set()
    for size in (3, 4, 5):
        if len(padded) < size:
            continue
        grams.update(padded[i:i + size] for i in range(len(padded) - size + 1))
    return grams


def _dice(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return (2.0 * len(left & right)) / (len(left) + len(right))


def _rank_map(scores: list[float], allowed: set[int] | None = None) -> dict[int, int]:
    pairs = [
        (score, idx) for idx, score in enumerate(scores)
        if score > 0.0 and (allowed is None or idx in allowed)
    ]
    pairs.sort(key=lambda item: (-item[0], item[1]))
    return {idx: rank for rank, (_, idx) in enumerate(pairs, start=1)}


def _rank_eligible_entries(
    eligible: list[dict[str, Any]],
    query: str,
    *,
    token_builder,
    descriptor_builder,
    source_registry: dict[str, Any] | None = None,
    strict_admission: bool = False,
) -> list[dict[str, Any]]:
    query_terms = _query_word_tokens(query)
    query_unique = list(dict.fromkeys(query_terms))
    doc_tokens = [token_builder(entry) for entry in eligible]
    doc_counts = [Counter(tokens) for tokens in doc_tokens]
    doc_lengths = [len(tokens) for tokens in doc_tokens]
    doc_sets = [set(tokens) for tokens in doc_tokens]
    df: Counter[str] = Counter()
    for tokens in doc_sets:
        df.update(tokens)

    total_docs = len(eligible)
    present_query_terms = {term for term in query_unique if df.get(term, 0) > 0}
    if not present_query_terms:
        return []

    oov_idf = _idf(total_docs, 0)
    query_weight_total = sum(_idf(total_docs, df.get(term, 0)) if df.get(term, 0) else oov_idf for term in query_unique)
    admitted: set[int] = set()
    for idx, tokens in enumerate(doc_sets):
        matched = present_query_terms & tokens
        coverage = (
            sum(_idf(total_docs, df[term]) for term in matched) / query_weight_total
            if query_weight_total else 0.0
        )
        ordinary_admission = len(matched) >= 2 or coverage >= MIN_QUERY_COVERAGE
        if strict_admission:
            meaningful_matched = matched - _STRICT_ADMISSION_GENERIC_TOKENS
            if ordinary_admission and meaningful_matched:
                admitted.add(idx)
        elif ordinary_admission:
            admitted.add(idx)

    if not admitted:
        return []

    direct_weights = {term: 1.0 for term in query_unique}
    bm25_scores = _bm25_scores(doc_counts, doc_lengths, df, direct_weights)
    query_grams = _char_ngrams(query)
    char_scores = [
        _dice(query_grams, _char_ngrams(descriptor_builder(entry))) if idx in admitted else 0.0
        for idx, entry in enumerate(eligible)
    ]
    ranks = {
        "bm25": _rank_map(bm25_scores, admitted),
        "char": _rank_map(char_scores, admitted),
    }
    registry = source_registry or load_source_registry()
    ranked: list[tuple[float, int, datetime, str, dict[str, Any]]] = []
    for idx in admitted:
        score = 0.0
        for component, weight in RRF_WEIGHTS.items():
            rank = ranks[component].get(idx)
            if rank is not None:
                score += weight / (RRF_K + rank)
        if score <= 0.0:
            continue
        entry = eligible[idx]
        source_score = source_relevance(entry, registry)
        stamp = datetime.fromisoformat(str(entry["timestamp"]).replace("Z", "+00:00"))
        ranked.append((score, source_score, stamp, str(entry["id"]), entry))

    ranked.sort(key=lambda item: (-item[0], -item[1], -item[2].timestamp(), item[3]))
    return [entry for _, _, _, _, entry in ranked]


def search_entries_hybrid(
    entries: list[dict[str, Any]],
    query: str,
    *,
    scope: str | None = None,
    tags: list[str] | None = None,
    limit: int | None = None,
    history: bool = False,
    source_registry: dict[str, Any] | None = None,
    strict_admission: bool = False,
) -> list[dict[str, Any]]:
    tags = list(tags or [])
    # Preserve history and metadata-only semantics exactly; hybridization is for textual recall.
    if history or not _word_tokens(query):
        return search_entries(
            entries, query, scope=scope, tags=tags, limit=limit, history=history,
            source_registry=source_registry,
        )

    default_limit = DEFAULT_RECALL_LIMIT
    effective_limit = min(MAX_RECALL_LIMIT, max(0, default_limit if limit is None else limit))
    if effective_limit == 0:
        return []

    eligible = _eligible_entries(entries)
    if not eligible:
        return []

    registry = source_registry or load_source_registry()
    canonical = _rank_eligible_entries(
        eligible,
        query,
        token_builder=_weighted_document_tokens,
        descriptor_builder=_entry_descriptor,
        source_registry=registry,
        strict_admission=strict_admission,
    )
    evidence = _rank_eligible_entries(
        eligible,
        query,
        token_builder=_source_evidence_tokens,
        descriptor_builder=_source_evidence_text,
        source_registry=registry,
        strict_admission=strict_admission,
    )

    # Canonical lesson wording keeps its established ordering. Preserved source
    # language fills otherwise unused recall slots, or becomes the primary lane
    # when the canonical lesson text has no match.
    merged = list(canonical)
    seen = {str(entry["id"]) for entry in merged}
    merged.extend(entry for entry in evidence if str(entry["id"]) not in seen)
    return merged[:effective_limit]
