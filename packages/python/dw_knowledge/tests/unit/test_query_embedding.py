"""A question's embedding: its own short deadline, and a cache by tenant.

The embedder's own timeout is sized for a reindex's batches (120 s on the
on-prem profile), so without a deadline of its own a one-line question waits
that long on an embedder in trouble. The cache is keyed by tenant and workspace
although the vector would be the same for anyone: a hit is faster than a miss,
and a cache shared across tenants would time-tell one tenant what another asked.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_kernel.errors import InfrastructureError
from dw_kernel.ports import SequentialIdGenerator, SystemClock
from dw_knowledge.adapters.memory_index import InMemoryVectorIndexAdapter
from dw_knowledge.contracts import SearchQuery
from dw_knowledge.gateway import KnowledgeGateway
from dw_platform.application.access_context import AccessContext

pytestmark = pytest.mark.unit


@dataclass
class CountingEmbedding:
    delay: float = 0.0
    asked: list[str] = field(default_factory=list)

    @property
    def dimension(self) -> int:
        return 2

    @property
    def model(self) -> str:
        return "counting-2"

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.asked.extend(texts)
        await asyncio.sleep(self.delay)
        return [[1.0, 0.0] for _ in texts]


def _gateway(embeddings: CountingEmbedding, **settings: Any) -> KnowledgeGateway:
    return KnowledgeGateway(
        session_factory=cast("async_sessionmaker[AsyncSession]", None),  # search never touches SQL
        vector_index=InMemoryVectorIndexAdapter(),
        embeddings=embeddings,
        object_storage=cast(Any, None),
        clock=SystemClock(),
        id_generator=SequentialIdGenerator(),
        **settings,
    )


def _context(tenant: uuid.UUID | None = None) -> AccessContext:
    return AccessContext(
        tenant_id=tenant or uuid.uuid4(),
        workspace_id=uuid.UUID(int=1),
        principal_id=uuid.uuid4(),
        roles=frozenset({"member"}),
        plan_id="starter",
    )


async def test_a_repeated_question_is_embedded_once_per_tenant() -> None:
    embeddings = CountingEmbedding()
    gateway = _gateway(embeddings)
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()

    await gateway.search(SearchQuery(text="PO-2026-0457"), _context(tenant_a))
    await gateway.search(SearchQuery(text="PO-2026-0457"), _context(tenant_a))
    await gateway.search(SearchQuery(text="PO-2026-0457"), _context(tenant_b))

    assert embeddings.asked == ["PO-2026-0457", "PO-2026-0457"]


async def test_the_cache_keeps_only_the_most_recent_questions() -> None:
    embeddings = CountingEmbedding()
    gateway = _gateway(embeddings, query_vector_cache_size=2)
    context = _context()

    for text in ("a", "b", "c", "a"):
        await gateway.search(SearchQuery(text=text), context)

    assert embeddings.asked == ["a", "b", "c", "a"], "the oldest question was evicted"


async def test_a_slow_query_embedding_fails_fast() -> None:
    gateway = _gateway(CountingEmbedding(delay=5.0), query_embedding_timeout_seconds=0.05)

    started = time.perf_counter()
    with pytest.raises(InfrastructureError, match="query embedding timed out"):
        await gateway.search(SearchQuery(text="q"), _context())

    assert time.perf_counter() - started < 2.0
