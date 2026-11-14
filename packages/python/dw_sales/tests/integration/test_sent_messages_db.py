"""Ticket 25 against real Postgres: the record of a message Sales sent that
DW1 took up (`sales.sent_messages`, migration 7f3def432f82).

Written once per message in its workspace, read back with its reading, never
seen from another workspace or tenant, never updated or deleted by `dw_app`,
and refused where the row's reading is not an object.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from sales_harness import T0, World
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from dw_kernel.errors import ConflictError
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.case_store import SentRead
from dw_sales.domain.reply_intent import ReplyReading

pytestmark = pytest.mark.integration

READING = ReplyReading.model_validate(
    {
        "prompt": "sales.reply_intent@2.0.0",
        "model_profile": "onprem",
        "route": "structured_extraction",
        "rules": "sales_order_rules@1.14.0",
        "outcome": "read",
        "intents": [
            {"intent": "asks", "quotes": [{"text": "Could you confirm?", "start": 0, "end": 18}]}
        ],
    }
)


async def test_a_sent_message_is_recorded_once_and_read_back_in_its_workspace_only(
    uow: SqlSalesUnitOfWorkFactory, world: World
) -> None:
    async with uow(world.alpha) as work:
        await work.sent.record(SentRead("S-1", T0, READING))
        await work.sent.record(SentRead("S-2", T0, None))
        await work.commit()

    async with uow(world.alpha) as work:
        assert await work.sent.get("S-1") == SentRead("S-1", T0, READING)
        assert {s.message_id for s in await work.sent.list_all()} == {"S-1", "S-2"}
    with pytest.raises(ConflictError) as refused:
        async with uow(world.alpha) as work:
            await work.sent.record(SentRead("S-1", T0, None))
    assert refused.value.details["rule"] == "sent_message_already_read"
    # Another workspace and another tenant find none of it, and may record
    # the same message id as their own.
    for other in (world.alpha_other, world.beta):
        async with uow(other) as work:
            assert await work.sent.get("S-1") is None
            assert await work.sent.list_all() == []
            await work.sent.record(SentRead("S-1", T0, None))
            await work.commit()


async def test_the_application_may_neither_update_nor_delete_a_record(
    migrator: AsyncEngine, uow: SqlSalesUnitOfWorkFactory, world: World
) -> None:
    async with migrator.connect() as conn:
        held = {
            row.verb
            for row in await conn.execute(
                sa.text(
                    "SELECT v.verb"
                    " FROM unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE']) AS v(verb)"
                    " WHERE has_table_privilege('dw_app', 'sales.sent_messages', v.verb)"
                )
            )
        }
    assert held == {"SELECT", "INSERT"}
    with pytest.raises(DBAPIError):
        async with migrator.begin() as conn:
            await conn.execute(
                sa.text(
                    "INSERT INTO sales.sent_messages"
                    " (tenant_id, workspace_id, message_id, processed_at, reading)"
                    " VALUES (:t, :w, 'S-X', now(), '[]'::jsonb)"
                ),
                {"t": world.alpha.tenant_id.value, "w": world.alpha.workspace_id.value},
            )
