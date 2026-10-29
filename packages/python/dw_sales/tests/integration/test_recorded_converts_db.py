"""`sales.recorded_convert_entries` (migration bbf5aa95bf6f) against a real
database, as `dw_app`: a code Sales confirmed in one process maps the next
PO in another, the first confirmation is kept, under tenant AND workspace
RLS, appended and never changed by the application."""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sales_harness import World, seed_world
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence.tenant_session import TenantScope, bind_tenant
from dw_sales.adapters.mock import MockSalesCatalog
from dw_sales.adapters.persistence.recorded_converts import SqlRecordedConverts
from dw_sales.adapters.persistence.recorded_quotations import SqlRecordedQuotations
from dw_sales.adapters.persistence.recorded_senders import SqlRecordedSenders
from dw_sales.application.ports import SalesScope
from dw_sales.application.snapshot_catalog import SnapshotSalesCatalog
from dw_sales.domain.catalog import ConvertEntry

pytestmark = pytest.mark.integration

WHO, CASE = uuid.UUID(int=0xA1), uuid.UUID(int=0xCA5E)
NEW = ConvertEntry(customer_code="KMH", customer_item_code="KMH-NEW-01", prv_code="CB-2005")


class _NoLists:
    async def approved(self, scope: SalesScope, catalog_list: object) -> None:
        return None


@pytest.fixture
async def world(migrator: AsyncEngine) -> World:
    return await seed_world(migrator)


def _catalog(sessions: async_sessionmaker[AsyncSession], scope: SalesScope) -> SnapshotSalesCatalog:
    return SnapshotSalesCatalog(
        _NoLists(),
        MockSalesCatalog.load(scope),
        SqlRecordedQuotations(sessions),
        SqlRecordedConverts(sessions),
        SqlRecordedSenders(sessions),
    )


async def test_a_code_confirmed_in_one_process_maps_in_the_next(
    world: World, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    api, worker = _catalog(app_sessions, world.alpha), _catalog(app_sessions, world.alpha)
    assert await api.learn_convert(world.alpha, NEW, by=WHO, case_id=CASE)
    other = NEW.model_copy(update={"prv_code": "CB-2008"})
    await api.learn_convert(world.alpha, other, by=WHO, case_id=CASE)

    assert (await worker.convert_entry(world.alpha, "KMH", "KMH-NEW-01")).data == NEW
    store = SqlRecordedConverts(app_sessions)
    assert [c.entry for c in await store.converts(world.alpha)] == [NEW]
    assert await store.converts(world.alpha_other) == []
    assert await store.converts(world.beta) == []


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE sales.recorded_convert_entries SET prv_code = 'CB-2008'",
        "DELETE FROM sales.recorded_convert_entries",
    ],
)
async def test_the_application_never_changes_a_kept_code(
    world: World, app_sessions: async_sessionmaker[AsyncSession], statement: str
) -> None:
    await SqlRecordedConverts(app_sessions).learn(world.alpha, NEW, by=WHO, case_id=CASE)
    async with app_sessions() as session, session.begin():
        await bind_tenant(
            session,
            TenantScope(
                tenant_id=world.alpha.tenant_id.value, workspace_id=world.alpha.workspace_id.value
            ),
        )
        with pytest.raises(DBAPIError, match="permission denied"):
            await session.execute(sa.text(statement))
