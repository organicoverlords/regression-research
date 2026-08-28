from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Iterable

try:
    from .memory_bank import (
        DEFAULT_HISTORY_LIMIT,
        DEFAULT_RECALL_LIMIT,
        MAX_HISTORY_LIMIT,
        MAX_RECALL_LIMIT,
        _tokens as legacy_tokens,
        load_source_registry,
        search_entries,
        source_relevance,
    )
    from .memory_lifecycle import is_expired
except ImportError:
    from memory_bank import (
        DEFAULT_HISTORY_LIMIT,
        DEFAULT_RECALL_LIMIT,
        MAX_HISTORY_LIMIT,
        MAX_RECALL_LIMIT,
        _tokens as legacy_tokens,
        load_source_registry,
        search_entries,
        source_relevance,
    )
    from memory_lifecycle import is_expired

BM25_K1 = 1.2
BM25_B = 0.75
RRF_K = 60.0
RRF_WEIGHTS = {"legacy": 0.30, "bm25": 0.40, "char": 0.15, "association": 0.15}
MIN_QUERY_COVERAGE = 0.45
MAX_ASSOCIATION_DOC_FRACTION = 0.35
ASSOCIATIONS_PER_QUERY_TERM = 3
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
_WORD_RE = re.compile(r"[\w]+", flags=re.UNICODE)
_NON_ALNUM_RE = re.compile(r"[^\w]+", flags=re.UNICODE)


def _word_tokens(value: str) -> list[str]:
    out: list[str] = []
    for token in _WORD_RE.findall(value.casefold()):
        if token in _STOPWORDS:
            continue
        if len(token) < 2 and not token.isdigit():
            continue
        out.append(token)
    return out


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


def _eligible_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    superseded = {old for entry in entries for old in entry.get("supersedes", [])}
    return [
        entry for entry in entries
        if entry.get("state") != "REJECTED" and entry.get("id") not in superseded and not is_expired(entry)
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


def _legacy_score(entry: dict[str, Any], query: str, scope: str | None, tags: list[str]) -> float:
    query_tokens = legacy_tokens(query)
    text_tokens = legacy_tokens(str(entry.get("text") or ""))
    tag_tokens = {str(tag).casefold() for tag in entry.get("tags", [])}
    relevance = 0.0
    if scope and str(entry.get("scope") or "").casefold() == scope.casefold():
        relevance += 4.0
    relevance += 4.0 * sum(tag.casefold() in tag_tokens for tag in tags)
    relevance += sum(
        token in text_tokens or token in tag_tokens or token == str(entry.get("scope") or "").casefold()
        for token in query_tokens
    )
    return relevance


def _rank_map(scores: list[float], allowed: set[int] | None = None) -> dict[int, int]:
    pairs = [
        (score, idx) for idx, score in enumerate(scores)
        if score > 0.0 and (allowed is None or idx in allowed)
    ]
    pairs.sort(key=lambda item: (-item[0], item[1]))
    return {idx: rank for rank, (_, idx) in enumerate(pairs, start=1)}


def _association_weights(
    query_terms: list[str],
    present_query_terms: set[str],
    doc_sets: list[set[str]],
    descriptor_sets: list[set[str]],
    df: Counter[str],
    descriptor_df: Counter[str],
) -> dict[str, float]:
    if len(present_query_terms) < 2:
        return {}
    total_docs = len(doc_sets)
    result: dict[str, float] = {}
    for query_term in query_terms:
        if query_term not in present_query_terms:
            continue
        qdf = df.get(query_term, 0)
        if not qdf or qdf > total_docs * MAX_ASSOCIATION_DOC_FRACTION:
            continue
        cooccurrence: Counter[str] = Counter()
        for idx, tokens in enumerate(doc_sets):
            if query_term not in tokens:
                continue
            for candidate in descriptor_sets[idx]:
                if candidate == query_term or candidate in present_query_terms or candidate in _STOPWORDS:
                    continue
                cooccurrence[candidate] += 1
        scored: list[tuple[float, str]] = []
        for candidate, co_docs in cooccurrence.items():
            cdf = descriptor_df.get(candidate, 0)
            if not cdf or cdf > total_docs * MAX_ASSOCIATION_DOC_FRACTION:
                continue
            strength = co_docs / math.sqrt(qdf * cdf)
            if strength > 0.0:
                scored.append((strength, candidate))
        scored.sort(key=lambda item: (-item[0], item[1]))
        for strength, candidate in scored[:ASSOCIATIONS_PER_QUERY_TERM]:
            result[candidate] = max(result.get(candidate, 0.0), 0.35 * strength)
    return result


def search_entries_hybrid(
    entries: list[dict[str, Any]],
    query: str,
    *,
    scope: str | None = None,
    tags: list[str] | None = None,
    limit: int | None = None,
    history: bool = False,
    source_registry: dict[str, Any] | None = None,
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

    query_terms = _word_tokens(query)
    query_unique = list(dict.fromkeys(query_terms))
    doc_tokens = [_weighted_document_tokens(entry) for entry in eligible]
    doc_counts = [Counter(tokens) for tokens in doc_tokens]
    doc_lengths = [len(tokens) for tokens in doc_tokens]
    doc_sets = [set(tokens) for tokens in doc_tokens]
    descriptor_sets = [set(_word_tokens(_entry_descriptor(entry))) for entry in eligible]

    df: Counter[str] = Counter()
    descriptor_df: Counter[str] = Counter()
    for tokens in doc_sets:
        df.update(tokens)
    for tokens in descriptor_sets:
        descriptor_df.update(tokens)

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
        if len(matched) >= 2 or coverage >= MIN_QUERY_COVERAGE:
            admitted.add(idx)

    direct_weights = {term: 1.0 for term in query_unique}
    bm25_scores = _bm25_scores(doc_counts, doc_lengths, df, direct_weights)
    legacy_scores = [
        _legacy_score(entry, query, scope, tags) if idx in admitted else 0.0
        for idx, entry in enumerate(eligible)
    ]

    query_grams = _char_ngrams(query)
    char_scores = [
        _dice(query_grams, _char_ngrams(_entry_descriptor(entry))) if idx in admitted else 0.0
        for idx, entry in enumerate(eligible)
    ]

    assoc_weights = _association_weights(
        query_unique, present_query_terms, doc_sets, descriptor_sets, df, descriptor_df,
    )
    association_scores = _bm25_scores(doc_counts, doc_lengths, df, assoc_weights)
    association_candidates = {idx for idx, score in enumerate(association_scores) if score > 0.0}

    candidates = admitted | association_candidates
    if not candidates:
        return []

    ranks = {
        "legacy": _rank_map(legacy_scores, candidates),
        "bm25": _rank_map(bm25_scores, admitted),
        "char": _rank_map(char_scores, admitted),
        "association": _rank_map(association_scores, association_candidates),
    }
    registry = source_registry or load_source_registry()
    ranked: list[tuple[float, int, datetime, str, dict[str, Any]]] = []
    for idx in candidates:
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
    return [entry for _, _, _, _, entry in ranked[:effective_limit]]
