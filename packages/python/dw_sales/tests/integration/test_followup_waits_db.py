"""The follow-ups' new waits against PostgreSQL (tickets 06, 09 and 16,
migration 57bbf61ae6b8): what `SqlFollowupStore.cases` reads, and what the
database admits.

- An order's wait on Design is its oldest request still named
  (`sales.order_cases.design_requests`); none named, none read.
- An order's wait on a quote opened from it is the oldest link whose quote
  case is open by its own status, read at the tick: approved or declined,
  none. A link naming another tenant's quote case reads nothing of it.
- A quote whose Design result was read from Bravo's export says so
  (`body.design_check`).
- The record and the feed's marks take the two new follow-ups, and
  `sales_reminders` is a key a tenant's version may be stored under.

Rows are written by the migrator straight into the columns the domain
writes, so each read is tested on its own, not through the flows (those are
`test_followup_waits.py`'s, over the same domain).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sales_harness import OrderRun, QuoteRun, World
from sqlalchemy.ext.asyncio import AsyncEngine

from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.followups import LOADED, FollowupKey, SentFollowup
from dw_sales.application.ports import SalesScope
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.followups import WaitingCase

pytestmark = pytest.mark.integration

T1 = datetime(2026, 10, 19, 3, 0, tzinfo=UTC)
T2 = T1 + timedelta(hours=5)
BY = str(uuid.UUID(int=0xA1))


def _m01(small_run: OrderRun) -> uuid.UUID:
    case = small_run.outcomes["M01"].case
    assert case is not None
    return case.case_id


async def _set(migrator: AsyncEngine, statement: str, **values: object) -> None:
    async with migrator.begin() as conn:
        await conn.execute(sa.text(statement), values)


async def _read(
    uow: SqlSalesUnitOfWorkFactory, scope: SalesScope, case_id: uuid.UUID
) -> WaitingCase | None:
    async with uow(scope) as work:
        found = await work.followups.cases(LOADED, received_since=T1 - timedelta(days=999))
    return next((c for c in found if c.case_id == case_id), None)


async def test_the_wait_on_design_is_the_oldest_request_still_named(
    uow: SqlSalesUnitOfWorkFactory, migrator: AsyncEngine, world: World, small_run: OrderRun
) -> None:
    order_id = _m01(small_run)
    requests = [
        {"line_no": 2, "by": BY, "at": T2.isoformat()},
        {"line_no": 1, "by": BY, "at": T1.isoformat()},
    ]
    statement = "UPDATE sales.order_cases SET design_requests = CAST(:r AS jsonb) WHERE id = :id"
    await _set(migrator, statement, r=json.dumps(requests), id=order_id)
    read = await _read(uow, world.alpha, order_id)
    assert read is not None and read.design_asked_at == T1

    await _set(migrator, statement, r="[]", id=order_id)
    read = await _read(uow, world.alpha, order_id)
    assert read is not None and read.design_asked_at is None


@pytest.mark.parametrize(
    ("status", "open_"),
    [
        ("priced", True),
        ("pending_approval", True),
        ("approved", False),
        ("sent", False),
        ("master_list_recorded", False),
        ("declined", False),
    ],
)
async def test_the_wait_on_a_quote_is_read_from_the_quotes_own_status(
    uow: SqlSalesUnitOfWorkFactory,
    migrator: AsyncEngine,
    world: World,
    small_run: OrderRun,
    quote_run: QuoteRun,
    status: str,
    open_: bool,
) -> None:
    order_id, quote_id = _m01(small_run), quote_run.steps[-1].case_id
    link = [{"quote_case_id": str(quote_id), "lines": [1], "by": BY, "at": T1.isoformat()}]
    await _set(
        migrator,
        "UPDATE sales.order_cases SET quote_links = CAST(:l AS jsonb) WHERE id = :id",
        l=json.dumps(link),
        id=order_id,
    )
    await _set(
        migrator, "UPDATE sales.quote_cases SET status = :s WHERE id = :id", s=status, id=quote_id
    )

    read = await _read(uow, world.alpha, order_id)

    assert read is not None
    assert read.quote_open_since == (T1 if open_ else None)


async def test_a_link_to_another_tenants_quote_reads_nothing_of_it(
    uow: SqlSalesUnitOfWorkFactory,
    migrator: AsyncEngine,
    world: World,
    small_run: OrderRun,
    quote_run: QuoteRun,
) -> None:
    """Beta holds an open quote case under an id an alpha order names: the
    alpha order waits on nothing (row security and the tenant in the join),
    and beta's tick reads none of alpha's cases."""
    order_id, quote_id = _m01(small_run), quote_run.steps[-1].case_id
    theirs = uuid.uuid4()
    await _set(
        migrator,
        "INSERT INTO sales.quote_cases"
        " (id, tenant_id, workspace_id, case_version, status, body, received_at)"
        " SELECT CAST(:theirs AS uuid), CAST(:tenant AS uuid), CAST(:workspace AS uuid),"
        " case_version, 'priced', body, received_at"
        " FROM sales.quote_cases WHERE id = :id",
        theirs=str(theirs),
        tenant=str(world.beta.tenant_id.value),
        workspace=str(world.beta.workspace_id.value),
        id=quote_id,
    )
    link = [{"quote_case_id": str(theirs), "lines": [1], "by": BY, "at": T1.isoformat()}]
    await _set(
        migrator,
        "UPDATE sales.order_cases SET quote_links = CAST(:l AS jsonb) WHERE id = :id",
        l=json.dumps(link),
        id=order_id,
    )

    read = await _read(uow, world.alpha, order_id)
    assert read is not None and read.quote_open_since is None
    async with uow(world.beta) as work:
        found = await work.followups.cases(LOADED, received_since=T1 - timedelta(days=999))
    assert order_id not in {c.case_id for c in found}
    assert theirs in {c.case_id for c in found if c.kind is CaseKind.QUOTE}


async def test_a_quote_says_whether_designs_result_was_read(
    uow: SqlSalesUnitOfWorkFactory, migrator: AsyncEngine, world: World, quote_run: QuoteRun
) -> None:
    quote_id = quote_run.steps[-1].case_id
    check = {"ycbg_no": "RFQ260930-030", "lines": [{"line_no": 1, "verdict": "quote"}]}
    statement = (
        "UPDATE sales.quote_cases SET body = jsonb_set(body, '{design_check}', CAST(:c AS jsonb))"
        " WHERE id = :id"
    )
    await _set(migrator, statement, c=json.dumps(check), id=quote_id)
    read = await _read(uow, world.alpha, quote_id)
    assert read is not None and read.design_checked

    await _set(migrator, statement, c="null", id=quote_id)
    read = await _read(uow, world.alpha, quote_id)
    assert read is not None and not read.design_checked


@pytest.mark.parametrize("followup", ["waiting_design_code", "waiting_quote"])
async def test_the_record_takes_the_new_followups(
    uow: SqlSalesUnitOfWorkFactory, world: World, followup: str
) -> None:
    key = FollowupKey(followup, "remind", str(uuid.uuid4()), T1)
    async with uow(world.alpha) as work:
        assert await work.followups.record(SentFollowup(key, 1, T2))
        await work.commit()


async def test_a_tenant_version_of_the_reminder_words_is_a_key_the_tables_take(
    migrator: AsyncEngine,
) -> None:
    async with migrator.connect() as conn:
        for check in ("ck_rule_versions_key", "ck_rule_drafts_rule_key"):
            definition = await conn.scalar(
                sa.text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = :c"),
                {"c": check},
            )
            assert "'sales_reminders'" in str(definition), check
