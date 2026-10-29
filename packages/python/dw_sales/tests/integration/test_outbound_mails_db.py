"""`sales.outbound_mails` (migration c42ed45c73a2) against a real database, as
`dw_app`: one active mail per send draft, status moved only from pending,
the lane's scopes across tenants by ids alone, under tenant AND workspace
RLS, and never deleted by the application."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sales_harness import World, seed_world
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence.tenant_session import TenantScope, bind_tenant
from dw_sales.adapters.persistence.outbound import SqlOutboundScopes
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.case_store import OutboundMail
from dw_sales.application.ports import SalesScope
from dw_sales.domain.dispositions import CaseKind

pytestmark = pytest.mark.integration

AT = datetime(2026, 10, 29, 3, 0, tzinfo=UTC)
CASE, DRAFT, WHO = uuid.uuid4(), uuid.uuid4(), uuid.UUID(int=0x61)


@pytest.fixture
async def world(migrator: AsyncEngine) -> World:
    return await seed_world(migrator)


def _mail(mail_id: uuid.UUID | None = None) -> OutboundMail:
    return OutboundMail(
        mail_id=mail_id or uuid.uuid4(),
        case_kind=CaseKind.QUOTE,
        case_id=CASE,
        artifact_id=DRAFT,
        requested_by=WHO,
        mailbox="giang.do@alpha.local",
        status="queued",
        queued_at=AT,
    )


async def _add(
    uow: SqlSalesUnitOfWorkFactory, scope: SalesScope, mail: OutboundMail
) -> OutboundMail:
    async with uow(scope) as work:
        held = await work.outbound.add(mail)
        await work.commit()
    return held


async def test_one_active_mail_per_draft_and_a_failed_one_may_go_again(
    world: World, uow: SqlSalesUnitOfWorkFactory
) -> None:
    first = await _add(uow, world.alpha, _mail())
    again = await _add(uow, world.alpha, _mail())
    assert again.mail_id == first.mail_id

    async with uow(world.alpha) as work:
        assert await work.outbound.settle(first.mail_id, "written", AT)
        assert await work.outbound.settle(first.mail_id, "failed", AT, "flow_failed")
        # Settled once: a second receipt changes nothing.
        assert not await work.outbound.settle(first.mail_id, "sent", AT)
        await work.commit()
    retry = await _add(uow, world.alpha, _mail())
    assert retry.mail_id != first.mail_id
    async with uow(world.alpha) as work:
        assert [m.mail_id for m in await work.outbound.pending()] == [retry.mail_id]


async def test_the_lane_finds_each_pending_workspace_and_rls_keeps_them_apart(
    world: World,
    uow: SqlSalesUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    mail = await _add(uow, world.alpha, _mail())
    await _add(uow, world.beta, _mail())
    scopes = await SqlOutboundScopes(app_sessions).scopes()
    assert {world.alpha, world.beta} <= set(scopes)
    assert world.alpha_other not in scopes
    async with uow(world.alpha_other) as work:
        assert await work.outbound.get(mail.mail_id) is None
        assert not await work.outbound.settle(mail.mail_id, "sent", AT)
    async with uow(world.beta) as work:
        assert await work.outbound.get(mail.mail_id) is None


async def test_a_status_outside_the_set_or_an_error_without_failure_is_refused(
    world: World, uow: SqlSalesUnitOfWorkFactory
) -> None:
    mail = await _add(uow, world.alpha, _mail())
    for status, error in (("delivered", None), ("failed", None), ("sent", "flow_failed")):
        with pytest.raises(DBAPIError, match="check constraint"):
            async with uow(world.alpha) as work:
                await work.outbound.settle(
                    mail.mail_id,
                    status,
                    AT + timedelta(minutes=1),
                    error,  # type: ignore[arg-type]
                )
                await work.commit()


async def test_the_application_never_deletes_a_mail(
    world: World, uow: SqlSalesUnitOfWorkFactory, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    await _add(uow, world.alpha, _mail())
    async with app_sessions() as session, session.begin():
        await bind_tenant(
            session,
            TenantScope(
                tenant_id=world.alpha.tenant_id.value, workspace_id=world.alpha.workspace_id.value
            ),
        )
        with pytest.raises(DBAPIError, match="permission denied"):
            await session.execute(sa.text("DELETE FROM sales.outbound_mails"))
