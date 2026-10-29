"""`sales.recorded_quotations` (migration c1c192e011e1) against a real
database, as `dw_app`: a quotation one process records is valid for a PO the
next process checks, a restart included, under tenant AND workspace RLS,
appended and never changed by the application."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal

import pytest
import sqlalchemy as sa
from pg_test_db import DatabaseUrls
from sales_harness import World, seed_world
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from dw_kernel.errors import ConflictError
from dw_platform.adapters.persistence.tenant_session import TenantScope, bind_tenant
from dw_sales.adapters.mock import MockSalesCatalog
from dw_sales.adapters.persistence.recorded_quotations import SqlRecordedQuotations
from dw_sales.application.ports import SalesScope
from dw_sales.application.snapshot_catalog import SnapshotSalesCatalog
from dw_sales.domain.catalog import Quotation

pytestmark = pytest.mark.integration

DAY = date(2026, 11, 3)


class _NoLists:
    async def approved(self, scope: SalesScope, catalog_list: object) -> None:
        return None


@pytest.fixture
async def world(migrator: AsyncEngine) -> World:
    return await seed_world(migrator)


@pytest.fixture
async def worker_sessions(
    sales_db: DatabaseUrls,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A second engine: the worker's own pool, beside the API's."""
    engine = create_async_engine(sales_db.app, poolclass=NullPool)
    try:
        yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    finally:
        await engine.dispose()


def _catalog(sessions: async_sessionmaker[AsyncSession], scope: SalesScope) -> SnapshotSalesCatalog:
    # A process of its own: its own mock, loaded from the sample files.
    return SnapshotSalesCatalog(
        _NoLists(), MockSalesCatalog.load(scope), SqlRecordedQuotations(sessions)
    )


async def _sent(scope: SalesScope) -> Quotation:
    """KMH's first quotation for an item the sample quotes VLX."""
    (sample,) = [
        q
        for q in (await MockSalesCatalog.load(scope).quotations(scope)).data
        if q.quote_no == "Q26-0104"
    ]
    return sample.model_copy(
        update={
            "quote_no": "Q26-0999",
            "customer_code": "KMH",
            "unit_price": Decimal("1.2345"),
            "valid_from": date(2026, 10, 29),
            "valid_to": date(2027, 3, 31),
        }
    )


async def test_what_the_api_records_the_worker_checks_against(
    world: World,
    app_sessions: async_sessionmaker[AsyncSession],
    worker_sessions: async_sessionmaker[AsyncSession],
) -> None:
    api, worker = _catalog(app_sessions, world.alpha), _catalog(worker_sessions, world.alpha)
    sent = await _sent(world.alpha)
    assert not (await worker.quotations_valid_on(world.alpha, "KMH", sent.prv_code, DAY)).data

    await api.record(world.alpha, [sent])

    found = await worker.quotations_valid_on(world.alpha, "KMH", sent.prv_code, DAY)
    assert found.data == (sent,)
    # A restart: a catalog built afresh still finds it.
    restarted = _catalog(worker_sessions, world.alpha)
    assert (await restarted.quotations_valid_on(world.alpha, "KMH", sent.prv_code, DAY)).data == (
        sent,
    )
    # And recording again writes nothing more.
    await api.record(world.alpha, [sent])
    assert len(await SqlRecordedQuotations(app_sessions).recorded(world.alpha)) == 1


async def test_other_terms_under_a_recorded_number_are_refused_by_the_store(
    world: World, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Asked of the store itself, past the catalog's own check: a second
    request racing the first with other terms is refused, all or none."""
    store = SqlRecordedQuotations(app_sessions)
    sent = await _sent(world.alpha)
    await store.add(world.alpha, [sent])
    fresh = sent.model_copy(update={"quote_no": "Q26-0998"})

    with pytest.raises(ConflictError):
        await store.add(world.alpha, [fresh, sent.model_copy(update={"moq": Decimal(7)})])

    assert [r.quotation for r in await store.recorded(world.alpha)] == [sent]


async def test_another_workspace_or_tenant_reads_none_of_it(
    world: World, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    store = SqlRecordedQuotations(app_sessions)
    await store.add(world.alpha, [await _sent(world.alpha)])
    assert await store.recorded(world.alpha_other) == []
    assert await store.recorded(world.beta) == []


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE sales.recorded_quotations SET customer_code = 'VLX'",
        "DELETE FROM sales.recorded_quotations",
    ],
)
async def test_the_application_never_changes_a_recorded_quotation(
    world: World, app_sessions: async_sessionmaker[AsyncSession], statement: str
) -> None:
    await SqlRecordedQuotations(app_sessions).add(world.alpha, [await _sent(world.alpha)])
    async with app_sessions() as session, session.begin():
        await bind_tenant(
            session,
            TenantScope(
                tenant_id=world.alpha.tenant_id.value, workspace_id=world.alpha.workspace_id.value
            ),
        )
        with pytest.raises(DBAPIError, match="permission denied"):
            await session.execute(sa.text(statement))


async def test_the_key_columns_are_the_documents_own(world: World, migrator: AsyncEngine) -> None:
    sent = await _sent(world.alpha)
    async with migrator.connect() as conn:
        with pytest.raises(IntegrityError, match="ck_recorded_quotations_quotation"):
            await conn.execute(
                sa.text(
                    "INSERT INTO sales.recorded_quotations (tenant_id, workspace_id,"
                    " quote_no, prv_code, customer_code, quotation)"
                    " VALUES (:t, :w, 'Q26-0997', :p, 'KMH', CAST(:q AS jsonb))"
                ),
                {
                    "t": world.alpha.tenant_id.value,
                    "w": world.alpha.workspace_id.value,
                    "p": sent.prv_code,
                    "q": json.dumps(sent.model_dump(mode="json")),
                },
            )
