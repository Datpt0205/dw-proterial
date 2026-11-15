"""Retrieval eval harness metrics (B6; made able to fail by Sales ticket 45)."""

from __future__ import annotations

import math
import uuid

import pytest

from dw_knowledge.retrieval_eval import RetrievalCase, RetrievalFloor, evaluate_retrieval

D1 = uuid.uuid4()
D2 = uuid.uuid4()
D3 = uuid.uuid4()
D4 = uuid.uuid4()
FLOOR = RetrievalFloor(top_k=2, min_recall=0.9, min_ndcg=0.9, max_p95_ms=10_000)


def _case(*relevant: uuid.UUID, query: str = "q") -> RetrievalCase:
    return RetrievalCase(query=query, domain="legal", relevant_document_ids=frozenset(relevant))


@pytest.mark.asyncio
async def test_perfect_retrieval_scores_one_and_passes() -> None:
    async def search(query: str, domain: str, top_k: int):
        return [D1, D2]

    report = await evaluate_retrieval(search, [_case(D1)], top_k=2)
    assert report.mean_recall == 1.0
    assert report.mean_ndcg == 1.0
    assert report.mrr == 1.0
    assert report.shortfalls(FLOOR) == []


@pytest.mark.asyncio
async def test_a_document_counts_once_at_its_best_rank() -> None:
    """Three chunks of one document are one answer, not three: without this a
    split document filled the top k and pushed the second relevant one out."""

    async def search(query: str, domain: str, top_k: int):
        return [D1, D1, D1, D2]

    report = await evaluate_retrieval(search, [_case(D1, D2)], top_k=2)
    assert report.cases[0].retrieved == (D1, D2)
    assert report.mean_recall == 1.0


@pytest.mark.asyncio
async def test_ndcg_and_reciprocal_rank_reflect_position() -> None:
    async def search(query: str, domain: str, top_k: int):
        return [D1, D2, D3]  # relevant at rank 3

    report = await evaluate_retrieval(search, [_case(D3)], top_k=3)
    assert report.mean_recall == 1.0
    assert report.mrr == pytest.approx(1 / 3)
    assert report.mean_ndcg == pytest.approx(1 / math.log2(4))


@pytest.mark.asyncio
async def test_a_miss_scores_zero_and_fails_the_floor() -> None:
    async def search(query: str, domain: str, top_k: int):
        return [D2, D3]

    report = await evaluate_retrieval(search, [_case(D1)], top_k=2)
    assert (report.mean_recall, report.mean_ndcg, report.mrr) == (0.0, 0.0, 0.0)
    assert len(report.shortfalls(FLOOR)) == 2


@pytest.mark.asyncio
async def test_aggregates_across_cases() -> None:
    async def search(query: str, domain: str, top_k: int):
        return [D1] if query == "a" else [D3]  # first hits, second misses

    report = await evaluate_retrieval(search, [_case(D1, query="a"), _case(D2, query="b")], top_k=1)
    assert report.mean_recall == 0.5
    assert len(report.cases) == 2


@pytest.mark.asyncio
async def test_no_cases_is_not_a_pass() -> None:
    """The old harness passed whenever it had cases, so it could not fail on
    quality; with none at all it must not pass either."""

    async def search(query: str, domain: str, top_k: int):
        return [D4]

    report = await evaluate_retrieval(search, [], top_k=2)
    assert report.shortfalls(FLOOR) == ["no cases were run"]


@pytest.mark.asyncio
async def test_a_slow_search_fails_the_latency_floor() -> None:
    async def search(query: str, domain: str, top_k: int):
        return [D1]

    report = await evaluate_retrieval(search, [_case(D1)], top_k=1)
    strict = RetrievalFloor(top_k=1, min_recall=0.0, min_ndcg=0.0, max_p95_ms=-1.0)
    assert report.shortfalls(strict) == [f"p95 {report.p95_ms:.1f} ms > -1.0 ms"]
