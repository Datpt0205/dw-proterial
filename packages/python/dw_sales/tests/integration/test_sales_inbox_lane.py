"""DW1's mailbox lane against PostgreSQL (ticket 16): the two facts the
database owns.

- The message log's key, (workspace, message_id), is the message's
  idempotency key: a disposition on a case is final, whoever recorded it, and
  of two transactions recording one message the second is refused.
- DW1's service account, as the demo seed leaves it, signs in to nothing but
  holds `sales.inbox.process` through the role `sales_dw1`, and nothing else:
  not another Sales scope, not `platform_admin`.
"""

from __future__ import annotations

import asyncio

import pytest
import sqlalchemy as sa
from pg_test_db import DatabaseUrls
from sales_harness import T0, OrderRun
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_kernel.errors import ConflictError
from dw_platform.adapters.persistence import tables
from dw_platform.adapters.persistence.membership_lookup import SqlMembershipLookup
from dw_platform.testing.seed_env import seed_test_env, sid
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.inbox_lane import LANE_CEILING, dw1_subject
from dw_sales.domain.dispositions import (
    SALES_PIC_POOL,
    DispositionKind,
    MessageDisposition,
    RoutingReason,
)
from dw_sales.testing.seed_personas import seed_dw1_accounts

pytestmark = pytest.mark.integration

ISSUER = "https://issuer.test/realms/dw"
ALPHA, BETA = "tenant-alpha", "tenant-beta"


def _routed(message_id: str) -> MessageDisposition:
    return MessageDisposition(
        message_id=message_id,
        kind=DispositionKind.ROUTED_TO_SALES,
        reason=RoutingReason.OTHER,
        owner=SALES_PIC_POOL,
    )


# ------------------------------------------------ the idempotency key --


async def test_a_message_on_a_case_is_never_given_another_disposition(
    uow: SqlSalesUnitOfWorkFactory, small_run: OrderRun
) -> None:
    async with uow(small_run.scope) as work:
        before = await work.messages.get("M01")
        assert before is not None and before.kind is DispositionKind.CASE_CREATED
        with pytest.raises(ConflictError) as refused:
            await work.messages.record(_routed("M01"), T0)
        assert refused.value.details["rule"] == "message_already_processed"
    async with uow(small_run.scope) as work:
        assert await work.messages.get("M01") == before


async def test_a_message_routed_to_sales_may_be_processed_again(
    uow: SqlSalesUnitOfWorkFactory, small_run: OrderRun
) -> None:
    async with uow(small_run.scope) as work:
        assert (await work.messages.get("M11")) is not None
        again = _routed("M11").model_copy(update={"reason": RoutingReason.CUSTOMER_UNKNOWN})
        await work.messages.record(again, T0)
        await work.commit()
    async with uow(small_run.scope) as work:
        assert await work.messages.get("M11") == again


async def test_of_two_transactions_recording_one_new_message_the_second_is_refused(
    uow: SqlSalesUnitOfWorkFactory, small_run: OrderRun
) -> None:
    """A person's "DW xử lý" and the lane racing on one message: the first to
    commit puts it on a case; the second waits on the key, then is refused,
    so its case and its events roll back with it."""
    async with uow(small_run.scope) as work:
        m01 = await work.messages.get("M01")
    assert m01 is not None
    on_case = m01.model_copy(update={"message_id": "M90"})
    first_recorded = asyncio.Event()
    release_first = asyncio.Event()

    async def first() -> None:
        async with uow(small_run.scope) as work:
            await work.messages.record(on_case, T0)
            first_recorded.set()
            await release_first.wait()
            await work.commit()

    async def second() -> None:
        await first_recorded.wait()
        async with uow(small_run.scope) as work:
            # Blocks on the key until the first commits, then is refused.
            await work.messages.record(on_case, T0)
            await work.commit()

    first_task = asyncio.create_task(first())
    second_task = asyncio.create_task(second())
    await first_recorded.wait()
    await asyncio.sleep(0.3)
    assert not second_task.done(), "the second must wait on the first's key"
    release_first.set()
    await first_task
    with pytest.raises(ConflictError) as refused:
        await second_task
    assert refused.value.details["rule"] == "message_already_processed"


# ------------------------------------------------ DW1's service account --


@pytest.fixture
async def seeded(sales_db: DatabaseUrls) -> None:
    await seed_test_env(sales_db.migrator)
    await seed_dw1_accounts(sales_db.migrator)


async def test_dw1s_account_holds_the_inbox_scope_through_its_role_and_nothing_else(
    seeded: None, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Read the way sign-in reads a membership, with no ceiling: what the
    account holds, not what the lane cuts it to."""
    tenant, workspace = sid("tenant", ALPHA), sid("workspace", f"{ALPHA}:main")
    access = await SqlMembershipLookup(app_sessions).find_access(
        dw1_subject(tenant), ISSUER, tenant, workspace
    )

    assert access is not None
    assert access.roles == frozenset({"sales_dw1"})
    assert "platform_admin" not in access.roles
    assert access.scopes == frozenset({"sales.inbox.process"})


async def test_the_lane_resolves_it_in_its_own_tenant_only(
    seeded: None, app_sessions: async_sessionmaker[AsyncSession]
) -> None:
    lookup = SqlMembershipLookup(app_sessions)
    alpha = sid("tenant", ALPHA), sid("workspace", f"{ALPHA}:main")
    beta = sid("tenant", BETA), sid("workspace", f"{BETA}:main")

    access = await lookup.find_service_access(dw1_subject(alpha[0]), *alpha, LANE_CEILING)
    assert access is not None
    assert (access.scopes, access.roles) == (LANE_CEILING, frozenset())
    # No account in beta's mailbox; and alpha's account is nobody there.
    assert await lookup.find_service_access(dw1_subject(beta[0]), *beta, LANE_CEILING) is None
    assert await lookup.find_service_access(dw1_subject(alpha[0]), *beta, LANE_CEILING) is None


async def test_it_has_no_email_and_reseeding_takes_a_hand_added_role_off(
    seeded: None, sales_db: DatabaseUrls, migrator: AsyncEngine
) -> None:
    tenant = sid("tenant", ALPHA)
    subject = dw1_subject(tenant)
    m, u = tables.memberships, tables.users
    account = sa.select(u.c.id).where(u.c.subject == subject).scalar_subquery()
    async with migrator.begin() as conn:
        assert (await conn.execute(sa.select(u.c.email).where(u.c.subject == subject))).one() == (
            None,
        )
        await conn.execute(
            sa.update(m)
            .where(m.c.user_id == account)
            .values(
                role_keys=["sales_dw1", "sales_head"], permission_set_keys=["sales_quote_approver"]
            )
        )

    await seed_dw1_accounts(sales_db.migrator)

    async with migrator.connect() as conn:
        row = (
            await conn.execute(
                sa.select(m.c.role_keys, m.c.permission_set_keys).where(m.c.user_id == account)
            )
        ).one()
    assert (row.role_keys, row.permission_set_keys) == (["sales_dw1"], [])
