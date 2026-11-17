"""Ticket 05's wait against PostgreSQL (migration b01dba5d0433): what
`SqlFollowupStore.cases` reads of a quote marked pcs, and what the database
admits.

- A quote marked pcs with no GM price recorded waits from when it was marked
  (`body.production_type_set.at`); with the price, or marked mass, none.
- The record takes `waiting_pcs_price`.

Rows are written by the migrator straight into the body the domain writes,
so the read is tested on its own (the flow is `test_pcs_followup.py`'s).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sales_harness import QuoteRun, World
from sqlalchemy.ext.asyncio import AsyncEngine

from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.followups import LOADED, FollowupKey, SentFollowup
from dw_sales.application.ports import SalesScope
from dw_sales.domain.followups import WaitingCase

pytestmark = pytest.mark.integration

T1 = datetime(2026, 11, 16, 3, 0, tzinfo=UTC)
BY = str(uuid.UUID(int=0xD1))
_SET = (
    "UPDATE sales.quote_cases SET body = body"
    " || jsonb_build_object('production_type', CAST(:kind AS jsonb),"
    " 'production_type_set', CAST(:stamp AS jsonb), 'pcs_price', CAST(:price AS jsonb))"
    " WHERE id = :id"
)


async def _mark(
    migrator: AsyncEngine, quote_id: uuid.UUID, kind: str | None, price: object = None
) -> None:
    stamp = None if kind is None else {"by": BY, "at": T1.isoformat()}
    async with migrator.begin() as conn:
        await conn.execute(
            sa.text(_SET),
            {
                "kind": json.dumps(kind),
                "stamp": json.dumps(stamp),
                "price": json.dumps(price),
                "id": quote_id,
            },
        )


async def _read(
    uow: SqlSalesUnitOfWorkFactory, scope: SalesScope, case_id: uuid.UUID
) -> WaitingCase | None:
    async with uow(scope) as work:
        found = await work.followups.cases(LOADED, received_since=T1 - timedelta(days=999))
    return next((c for c in found if c.case_id == case_id), None)


async def test_a_pcs_quote_waits_from_its_mark_until_the_gm_price_is_recorded(
    uow: SqlSalesUnitOfWorkFactory, migrator: AsyncEngine, world: World, quote_run: QuoteRun
) -> None:
    quote_id = quote_run.steps[-1].case_id

    await _mark(migrator, quote_id, "pcs")
    read = await _read(uow, world.alpha, quote_id)
    assert read is not None and read.pcs_price_asked_at == T1

    price = {
        "lines": [{"line_no": 1, "unit_price": "12.40"}],
        "recorded_by": BY,
        "recorded_at": T1.isoformat(),
    }
    await _mark(migrator, quote_id, "pcs", price)
    read = await _read(uow, world.alpha, quote_id)
    assert read is not None and read.pcs_price_asked_at is None

    for kind in ("mass", None):
        await _mark(migrator, quote_id, kind)
        read = await _read(uow, world.alpha, quote_id)
        assert read is not None and read.pcs_price_asked_at is None


async def test_the_record_takes_the_pcs_wait(uow: SqlSalesUnitOfWorkFactory, world: World) -> None:
    key = FollowupKey("waiting_pcs_price", "remind", str(uuid.uuid4()), T1)
    async with uow(world.alpha) as work:
        assert await work.followups.record(SentFollowup(key, 1, T1))
        await work.commit()
