"""Tenant-aware LangGraph store backed by platform.agent_store.

The store holds an agent's cross-thread memory. LangGraph
takes one store instance at compile time and never passes tenancy per call, so
the tenant has to travel in the namespace: every namespace starts with the
tenant id, supplied by the composition root from the verified RunContext and
never by the model. A namespace without one is refused rather than served as a
cross-tenant scan, and RLS backs that up in the database.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from datetime import UTC
from typing import Any

import sqlalchemy as sa
from langgraph.store.base import BaseStore, GetOp, Item, Op, PutOp, Result, SearchItem, SearchOp
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_agent_runtime.adapters.runtime_tables import agent_store
from dw_kernel.errors import TenantContextMissingError
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session


def tenant_namespace(tenant_id: uuid.UUID, *parts: str) -> tuple[str, ...]:
    """Build the namespace the store requires; use this instead of literals."""
    return (str(tenant_id), *parts)


def _tenant_of(namespace: Sequence[str]) -> uuid.UUID:
    try:
        return uuid.UUID(namespace[0])
    except (IndexError, ValueError) as exc:
        raise TenantContextMissingError(
            "store namespace must start with the tenant id",
            details={"namespace": list(namespace)},
        ) from exc


class SqlAlchemyAgentStore(BaseStore):
    """Async cross-thread memory with per-transaction RLS context."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def batch(self, ops: Iterable[Op]) -> list[Result]:
        raise NotImplementedError("the platform runs async; use abatch")

    async def abatch(self, ops: Iterable[Op]) -> list[Result]:
        return [await self._run(op) for op in ops]

    async def _run(self, op: Op) -> Result:
        if isinstance(op, GetOp):
            return await self._get(op)
        if isinstance(op, PutOp):
            await self._put(op)
            return None
        if isinstance(op, SearchOp):
            return await self._search(op)
        raise NotImplementedError(f"unsupported store operation: {type(op).__name__}")

    async def _get(self, op: GetOp) -> Item | None:
        scope = TenantScope(_tenant_of(op.namespace))
        async with tenant_session(self._session_factory, scope) as session:
            row = (
                await session.execute(
                    sa.select(agent_store).where(
                        agent_store.c.namespace == list(op.namespace),
                        agent_store.c.key == op.key,
                    )
                )
            ).first()
        return _to_item(row) if row is not None else None

    async def _put(self, op: PutOp) -> None:
        tenant_id = _tenant_of(op.namespace)
        namespace = list(op.namespace)
        async with tenant_session(self._session_factory, TenantScope(tenant_id)) as session:
            if op.value is None:
                await session.execute(
                    sa.delete(agent_store).where(
                        agent_store.c.namespace == namespace, agent_store.c.key == op.key
                    )
                )
                return
            insert = sa.dialects.postgresql.insert(agent_store).values(
                tenant_id=tenant_id,
                namespace=namespace,
                key=op.key,
                value=op.value,
                created_at=sa.func.now(),
                updated_at=sa.func.now(),
            )
            await session.execute(
                insert.on_conflict_do_update(
                    index_elements=["tenant_id", "namespace", "key"],
                    set_={"value": insert.excluded.value, "updated_at": sa.func.now()},
                )
            )

    async def _search(self, op: SearchOp) -> list[SearchItem]:
        prefix = list(op.namespace_prefix)
        tenant_id = _tenant_of(prefix)
        query = (
            sa.select(agent_store)
            .where(agent_store.c.namespace[1 : len(prefix)] == prefix)
            .order_by(agent_store.c.namespace, agent_store.c.key)
            .limit(op.limit)
            .offset(op.offset)
        )
        if op.filter:
            query = query.where(agent_store.c.value.contains(op.filter))

        async with tenant_session(self._session_factory, TenantScope(tenant_id)) as session:
            rows = (await session.execute(query)).all()
        return [_to_search_item(row) for row in rows]


def _to_item(row: Any) -> Item:
    return Item(
        value=dict(row.value),
        key=row.key,
        namespace=tuple(row.namespace),
        created_at=row.created_at.astimezone(UTC),
        updated_at=row.updated_at.astimezone(UTC),
    )


def _to_search_item(row: Any) -> SearchItem:
    return SearchItem(
        namespace=tuple(row.namespace),
        key=row.key,
        value=dict(row.value),
        created_at=row.created_at.astimezone(UTC),
        updated_at=row.updated_at.astimezone(UTC),
    )
