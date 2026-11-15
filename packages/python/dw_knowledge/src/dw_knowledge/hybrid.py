"""What a hybrid search is, stated once for both vector indexes.

A search runs two rankings under one trusted filter: the dense vector (meaning)
and BM25 over the chunk text (exact words: a PO number, an item code, which a
dense vector matches poorly). Reciprocal rank fusion joins them by position, so
neither scale has to be calibrated against the other.

The Qdrant adapter asks the server to do this in one Query API call; the
in-memory adapter does the same arithmetic here. Both read the constants below,
so a test or an eval run against the in-memory index measures the ranking
Qdrant serves, not a cousin of it (failure-modes #3).
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Hashable, Iterable, Sequence

# Reciprocal rank fusion's k: score = sum over rankings of 1 / (k + rank), rank
# counted from zero (Qdrant's own formula, docs "Hybrid Queries", read
# 2026-11-15). Qdrant's default, and measured on the labelled set
# (`evals/fixtures/cases/pf_retrieval.json`, 2026-11-15): nDCG@5 0.76 at k=2
# against 0.71 at 10 and at 60 (Cormack et al.'s constant), recall@5 1.0 at
# all three. A small k lets the point one leg ranks first stay near the top,
# which is what an exact PO number found only by BM25 needs.
RRF_K = 2

# How many points each leg hands the fusion. A point one leg ranks below this is
# fused as if that leg never saw it, so it is the depth a lexical match can be
# found at while dense search ranks it nowhere. The review proposed ~40.
PREFETCH_FLOOR = 40

# BM25's own two parameters, Qdrant's defaults (k is its name for k1).
BM25_K = 1.2
BM25_B = 0.75

_LEGS = 2  # dense and lexical


def prefetch_limit(top_k: int) -> int:
    """Each leg's depth: never shallower than what the search will return."""
    return max(top_k, PREFETCH_FLOOR)


def relevance_from_fused(score: float) -> float:
    """A fused score on [0, 1]: 1.0 is first in both rankings.

    `SearchQuery.min_relevance` and `EvidenceRef.relevance_score` are on [0, 1].
    A raw RRF score is at most 2/k, the score of a point first in both
    rankings; this is the score over that maximum, so it stays on [0, 1]
    whatever k is (at k=2 the two are the same number).
    """
    return max(0.0, min(1.0, score * RRF_K / _LEGS))


# Qdrant's `word` tokenizer splits on spaces, punctuation and special
# characters and keeps digits and letters together; lowercased. Measured on
# 1.20.1 (2026-11-15): `PO-2026-0457` is `po`, `2026`, `0457`, and a run of
# Japanese with no spaces is one token. `\w+` does the same here.
_TOKEN = re.compile(r"\w+", re.UNICODE)


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def bm25_scores(query: str, corpus: Sequence[tuple[Hashable, str]]) -> dict[Hashable, float]:
    """BM25 of `query` against every document of `corpus`, by its key.

    The statistics (document count, document frequency, average length) come
    from `corpus` alone: the caller passes exactly what this caller may read,
    as the Qdrant adapter scopes its `idf` corpus, so another tenant's words
    weigh nothing here. A document with no query term is absent, as in Qdrant.
    """
    terms = set(tokens(query))
    if not terms or not corpus:
        return {}
    bags = [(key, Counter(tokens(text))) for key, text in corpus]
    lengths = [sum(bag.values()) for _, bag in bags]
    average = (sum(lengths) / len(lengths)) or 1.0
    count = len(bags)
    frequency = {term: sum(1 for _, bag in bags if term in bag) for term in terms}
    scores: dict[Hashable, float] = {}
    for (key, bag), length in zip(bags, lengths, strict=True):
        score = 0.0
        for term in terms:
            tf = bag.get(term, 0)
            if not tf:
                continue
            idf = math.log(1 + (count - frequency[term] + 0.5) / (frequency[term] + 0.5))
            norm = tf + BM25_K * (1 - BM25_B + BM25_B * length / average)
            score += idf * tf * (BM25_K + 1) / norm
        if score > 0:
            scores[key] = score
    return scores


def reciprocal_rank_fusion(rankings: Iterable[Sequence[Hashable]]) -> list[tuple[Hashable, float]]:
    """Keys by fused score, best first; ties keep the order they were first seen."""
    fused: dict[Hashable, float] = {}
    for ranking in rankings:
        for rank, key in enumerate(ranking):
            fused[key] = fused.get(key, 0.0) + 1.0 / (RRF_K + rank)
    return sorted(fused.items(), key=lambda pair: -pair[1])
