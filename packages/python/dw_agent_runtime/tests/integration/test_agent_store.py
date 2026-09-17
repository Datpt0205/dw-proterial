"""Integration: cross-thread agent memory is tenant-scoped by construction."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from langgraph.store.base import GetOp, PutOp, SearchOp
from runtime_harness import TENANT_A, TENANT_B, RuntimeUrls
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from dw_agent_runtime.adapters.store import SqlAlchemyAgentStore, tenant_namespace
from dw_kernel.errors import TenantContextMissingError

pytestmark = pytest.mark.integration


@pytest.fixture
async def store(urls: RuntimeUrls) -> AsyncIterator[SqlAlchemyAgentStore]:
    engine = create_async_engine(urls.app, poolclass=NullPool)
    yield SqlAlchemyAgentStore(
        async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    )
    await engine.dispose()


async def test_put_then_get_round_trips(store: SqlAlchemyAgentStore) -> None:
    namespace = tenant_namespace(TENANT_A, "memories")
    await store.aput(namespace, "profile.md", {"content": "Khách thích gọi buổi sáng"})

    item = await store.aget(namespace, "profile.md")
    assert item is not None
    assert item.value["content"] == "Khách thích gọi buổi sáng"


async def test_put_overwrites_and_none_deletes(store: SqlAlchemyAgentStore) -> None:
    namespace = tenant_namespace(TENANT_A, "memories")
    await store.aput(namespace, "note.md", {"content": "v1"})
    await store.aput(namespace, "note.md", {"content": "v2"})
    item = await store.aget(namespace, "note.md")
    assert item is not None and item.value["content"] == "v2"

    await store.adelete(namespace, "note.md")
    assert await store.aget(namespace, "note.md") is None


async def test_search_matches_the_namespace_prefix(store: SqlAlchemyAgentStore) -> None:
    await store.aput(tenant_namespace(TENANT_A, "prefix", "leads"), "alpha.md", {"n": 1})
    await store.aput(tenant_namespace(TENANT_A, "prefix", "leads"), "beta.md", {"n": 2})
    await store.aput(tenant_namespace(TENANT_A, "prefix-other"), "tmp.md", {"n": 3})

    found = await store.asearch(tenant_namespace(TENANT_A, "prefix"))
    assert sorted(item.key for item in found) == ["alpha.md", "beta.md"]


async def test_another_tenant_cannot_read_or_search(store: SqlAlchemyAgentStore) -> None:
    await store.aput(tenant_namespace(TENANT_A, "memories"), "secret.md", {"content": "bí mật A"})

    assert await store.aget(tenant_namespace(TENANT_B, "memories"), "secret.md") is None
    assert await store.asearch(tenant_namespace(TENANT_B, "memories")) == []


async def test_namespace_without_a_tenant_is_refused(store: SqlAlchemyAgentStore) -> None:
    for op in (
        GetOp(namespace=("memories",), key="x.md", refresh_ttl=False),
        PutOp(namespace=("memories",), key="x.md", value={"n": 1}, index=None, ttl=None),
        SearchOp(
            namespace_prefix=(), filter=None, limit=10, offset=0, query=None, refresh_ttl=False
        ),
    ):
        with pytest.raises(TenantContextMissingError):
            await store.abatch([op])
