"""Integration: the memory ranker against a real Qdrant.

An adapter that has never run against the thing it adapts is the failure this
repository has counted twice: what a library actually does is a fact about the
outside world, and only running it settles them. Two of those facts here — that
a payload filter on three keyword fields discriminates, and that `query_points`
returns ids in similarity order — are both things the documentation asserts and
neither is worth believing untested.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
from qdrant_client import AsyncQdrantClient

from dw_knowledge.adapters.hash_embedding import HashEmbeddingAdapter
from dw_memory.adapters.qdrant_ranker import QdrantMemoryRanker

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

TENANT = uuid.UUID(int=0xDD00)
OTHER_TENANT = uuid.UUID(int=0xDD01)
WORKSPACE = uuid.UUID(int=0xDD02)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def ranker() -> AsyncIterator[QdrantMemoryRanker]:
    url = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333")
    client = AsyncQdrantClient(url=url)
    # Its own collection per run: these tests write points, and a leftover from
    # a previous run would make the ranking assertions read someone else's data.
    collection = f"dw_memory_test_{uuid.uuid4().hex[:8]}"
    built = QdrantMemoryRanker(
        client=client, embedder=HashEmbeddingAdapter(), collection=collection
    )
    try:
        await built.ensure_ready()
    except Exception as exc:  # pragma: no cover - environment, not logic
        pytest.skip(f"Qdrant unreachable at {url}: {exc}")
    try:
        yield built
    finally:
        await client.delete_collection(collection)
        await client.close()


async def _remember(ranker: QdrantMemoryRanker, content: str, *, tenant: uuid.UUID) -> uuid.UUID:
    memory_id = uuid.uuid4()
    await ranker.index(
        memory_id=memory_id,
        content=content,
        tenant_id=tenant,
        workspace_id=WORKSPACE,
        worker_id="demo",
    )
    return memory_id


async def test_the_closest_memory_comes_first(ranker: QdrantMemoryRanker) -> None:
    await _remember(ranker, "Khách muốn gặp vào buổi sáng thứ Hai", tenant=TENANT)
    contract = await _remember(ranker, "Hợp đồng sẽ ký trước ngày 20 tháng 10", tenant=TENANT)

    order = await ranker.nearest(
        "bao giờ ký hợp đồng",
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        worker_id="demo",
        limit=10,
    )

    assert order, "the store returned nothing at all"
    assert order[0] == contract


async def test_another_tenants_memory_is_never_returned(ranker: QdrantMemoryRanker) -> None:
    """The SQL is the real boundary; this is the depth behind it. A filter that
    can be forgotten is one that will be, so it is asserted here too."""
    theirs = await _remember(ranker, "Hợp đồng sẽ ký trước ngày 20 tháng 10", tenant=OTHER_TENANT)

    order = await ranker.nearest(
        "bao giờ ký hợp đồng",
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        worker_id="demo",
        limit=10,
    )

    assert theirs not in order
    assert order == ()


async def test_another_workers_memory_is_never_returned(ranker: QdrantMemoryRanker) -> None:
    await _remember(ranker, "Hợp đồng sẽ ký trước ngày 20 tháng 10", tenant=TENANT)

    order = await ranker.nearest(
        "bao giờ ký hợp đồng",
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        worker_id="another_worker",
        limit=10,
    )

    assert order == ()


async def test_indexing_a_store_that_is_down_does_not_raise() -> None:
    """A vector store that is down must not undo a fact already committed."""
    broken = QdrantMemoryRanker(
        client=AsyncQdrantClient(url="http://127.0.0.1:1"),
        embedder=HashEmbeddingAdapter(),
        collection="never",
    )

    await broken.index(
        memory_id=uuid.uuid4(),
        content="gì đó",
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        worker_id="demo",
    )


async def test_a_width_mismatch_refuses_rather_than_dropping_everyones_vectors(
    ranker: QdrantMemoryRanker,
) -> None:
    """Recreating would be triggered by nothing more than a config value, and
    during a rolling deploy two processes would delete each other's collection."""
    wider = QdrantMemoryRanker(
        client=ranker.client,
        embedder=HashEmbeddingAdapter(_dimension=128),
        collection=ranker.collection,
    )

    with pytest.raises(ValueError, match="reindex"):
        await wider.ensure_ready()
