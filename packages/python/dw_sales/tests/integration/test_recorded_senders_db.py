"""`sales.recorded_customer_senders` (migration 7f94b09d1905) against a real
database, as `dw_app`: a sender Sales confirmed in one process finds its
customer in the next, the address and not its domain, the first confirmation
kept, under tenant AND workspace RLS, appended and never changed."""

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

pytestmark = pytest.mark.integration

WHO = uuid.UUID(int=0xA1)
SENDER = "Tran.Minh@freemail.example"


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


async def test_a_sender_confirmed_in_one_process_finds_its_customer_in_the_next(
    world: World, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    api, worker = _catalog(app_sessions, world.alpha), _catalog(app_sessions, world.alpha)
    assert await api.learn_sender(world.alpha, SENDER, "BRN", by=WHO, message_id="S01")
    await api.learn_sender(world.alpha, SENDER, "VLX", by=WHO, message_id="S02")

    found = await worker.customer_by_sender(world.alpha, SENDER.lower())
    assert found.data is not None and found.data.code == "BRN"
    # The address, never its domain.
    assert (await worker.customer_by_sender(world.alpha, "other@freemail.example")).data is None
    other_workspace = _catalog(app_sessions, world.alpha_other)
    assert (await other_workspace.customer_by_sender(world.alpha_other, SENDER)).data is None
    beta = _catalog(app_sessions, world.beta)
    assert (await beta.customer_by_sender(world.beta, SENDER)).data is None


async def test_a_sender_on_a_customers_domain_is_not_recorded(
    world: World, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    catalog = _catalog(app_sessions, world.alpha)
    assert not await catalog.learn_sender(
        world.alpha, "buyer@brennic.example", "VLX", by=WHO, message_id="S01"
    )
    found = await catalog.customer_by_sender(world.alpha, "buyer@brennic.example")
    assert found.data is not None and found.data.code == "BRN"


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE sales.recorded_customer_senders SET customer_code = 'VLX'",
        "DELETE FROM sales.recorded_customer_senders",
    ],
)
async def test_the_application_never_changes_a_kept_sender(
    world: World, app_sessions: async_sessionmaker[AsyncSession], statement: str
) -> None:
    await SqlRecordedSenders(app_sessions).learn(
        world.alpha, SENDER.lower(), "BRN", by=WHO, message_id="S01"
    )
    async with app_sessions() as session, session.begin():
        await bind_tenant(
            session,
            TenantScope(
                tenant_id=world.alpha.tenant_id.value, workspace_id=world.alpha.workspace_id.value
            ),
        )
        with pytest.raises(DBAPIError, match="permission denied"):
            await session.execute(sa.text(statement))
