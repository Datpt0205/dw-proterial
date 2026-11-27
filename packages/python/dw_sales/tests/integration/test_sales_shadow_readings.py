"""`sales.shadow_readings` (migration a201f3d7ad6f, ticket 67) against a real
database, as `dw_app` wherever isolation is the question.

What a step read in shadow: kept in its own unit of work (the first reading
of an item stands), taken by the decision's unit of work as it is labelled
(read and deleted at once), dropped past its term by the scope's own
DELETE, read under tenant AND workspace RLS only, never rewritten by the
application role, and its step held to the domain's steps.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sales_harness import World
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.ports import SalesScope
from dw_sales.domain.order_checks import ModelStep
from dw_sales.domain.shadow import ShadowReading, item_key

pytestmark = pytest.mark.integration

_AT = datetime.now(UTC).replace(microsecond=0)
_STEP = ModelStep.DESCRIPTION_ATTRIBUTES


def _reading(line_no: int = 1, *, at: datetime = _AT, proposed: Any = None) -> ShadowReading:
    return ShadowReading(
        reading_id=uuid.uuid4(),
        step=_STEP,
        item_key=item_key("M36", "M36-A1", line_no, _STEP),
        message_id="M36",
        attachment_id="M36-A1",
        line_no=line_no,
        field="prv_code",
        proposed=["HW-1002"] if proposed is None else proposed,
        prompt="sales.description_attributes@1.2.0",
        model_profile="onprem",
        rules="sales_order_rules@1.16.0",
        confidence=0.91,
        read_at=at,
    )


async def _keep(uow: SqlSalesUnitOfWorkFactory, scope: SalesScope, *readings: ShadowReading) -> int:
    async with uow(scope) as work:
        kept = await work.shadow_readings.keep(readings)
        await work.commit()
    return kept


async def _take(
    uow: SqlSalesUnitOfWorkFactory, scope: SalesScope, key: str
) -> ShadowReading | None:
    async with uow(scope) as work:
        taken = await work.shadow_readings.take(_STEP, key)
        await work.commit()
    return taken


async def test_the_step_check_holds_exactly_the_domains_steps(migrator: AsyncEngine) -> None:
    async with migrator.connect() as conn:
        definition = await conn.scalar(
            sa.text(
                "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c"
                " JOIN pg_namespace n ON n.oid = c.connamespace"
                " WHERE n.nspname = 'sales' AND c.conname = 'ck_shadow_readings_step'"
            )
        )
    assert set(re.findall(r"'([a-z_]+)'::text", str(definition))) == {s.value for s in ModelStep}


async def test_a_reading_is_kept_once_taken_once_and_read_back_as_written(
    uow: SqlSalesUnitOfWorkFactory, world: World
) -> None:
    first, again = _reading(), _reading(proposed=["HW-1001"])
    assert await _keep(uow, world.alpha, first) == 1
    # The first reading of an item stands: a mail processed again reads it again.
    assert await _keep(uow, world.alpha, again) == 0
    assert await _take(uow, world.alpha, first.item_key) == first
    assert await _take(uow, world.alpha, first.item_key) is None


async def test_a_take_that_rolls_back_leaves_the_reading(
    uow: SqlSalesUnitOfWorkFactory, world: World
) -> None:
    reading = _reading(line_no=2)
    await _keep(uow, world.alpha, reading)
    async with uow(world.alpha) as work:
        assert await work.shadow_readings.take(_STEP, reading.item_key) == reading
        # No commit: the decision failed, so nothing was labelled.
    assert await _take(uow, world.alpha, reading.item_key) == reading


async def test_another_tenant_or_workspace_never_takes_it(
    uow: SqlSalesUnitOfWorkFactory, world: World
) -> None:
    reading = _reading(line_no=3)
    await _keep(uow, world.alpha, reading)
    for scope in (world.beta, world.alpha_other):
        assert await _take(uow, scope, reading.item_key) is None
    assert await _take(uow, world.alpha, reading.item_key) == reading


async def test_a_connection_that_never_scopes_itself_reads_nothing(
    uow: SqlSalesUnitOfWorkFactory, sales_app_engine: AsyncEngine, world: World
) -> None:
    await _keep(uow, world.alpha, _reading(line_no=4))
    async with sales_app_engine.connect() as conn:
        assert await conn.scalar(sa.text("SELECT count(*) FROM sales.shadow_readings")) == 0


async def test_the_application_cannot_rewrite_a_reading(
    uow: SqlSalesUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
    world: World,
) -> None:
    await _keep(uow, world.alpha, _reading(line_no=5))
    async with app_sessions() as session, session.begin():
        for key, value in (
            ("app.tenant_id", world.alpha.tenant_id.value),
            ("app.workspace_id", world.alpha.workspace_id.value),
        ):
            await session.execute(
                sa.text("SELECT set_config(:k, :v, true)"), {"k": key, "v": str(value)}
            )
        with pytest.raises(DBAPIError, match="permission denied"):
            await session.execute(
                sa.text("UPDATE sales.shadow_readings SET proposed = '[\"X\"]'::jsonb")
            )


async def test_the_term_drops_old_readings_of_the_scope_only(
    uow: SqlSalesUnitOfWorkFactory, world: World
) -> None:
    old = _reading(line_no=6, at=_AT - timedelta(days=61))
    young = _reading(line_no=7)
    await _keep(uow, world.alpha, old, young)
    await _keep(uow, world.beta, _reading(line_no=6, at=_AT - timedelta(days=61)))
    async with uow(world.alpha) as work:
        assert await work.shadow_readings.prune(_AT - timedelta(days=60)) == 1
        await work.commit()
    assert await _take(uow, world.alpha, old.item_key) is None
    assert await _take(uow, world.alpha, young.item_key) == young
    assert await _take(uow, world.beta, old.item_key) is not None


async def test_a_case_s_reply_readings_are_taken_together_by_its_scope_only(
    uow: SqlSalesUnitOfWorkFactory, world: World
) -> None:
    case_id = uuid.uuid4()
    readings = [
        ShadowReading(
            reading_id=uuid.uuid4(),
            step=step,
            item_key=item_key("R42", None, None, step),
            message_id="R42",
            attachment_id=None,
            line_no=None,
            field="next_step",
            proposed="resume_review",
            prompt="sales.reply_intent@2.0.0",
            model_profile="onprem",
            rules="sales_order_rules@1.16.0",
            confidence=None,
            read_at=_AT,
            case_id=case_id,
        )
        for step in (ModelStep.REPLY_INTENT, ModelStep.SKILL_INTENTS)
    ]
    await _keep(uow, world.alpha, *readings)
    async with uow(world.beta) as work:
        assert await work.shadow_readings.take_for_case(list(ModelStep), case_id) == []
        await work.commit()
    async with uow(world.alpha) as work:
        taken = await work.shadow_readings.take_for_case(
            [ModelStep.REPLY_INTENT, ModelStep.SKILL_INTENTS], case_id
        )
        await work.commit()
    assert sorted(taken, key=lambda r: r.step.value) == sorted(readings, key=lambda r: r.step.value)
    async with uow(world.alpha) as work:
        assert await work.shadow_readings.take_for_case(list(ModelStep), case_id) == []


async def test_a_po_read_in_shadow_is_taken_by_its_match_key_in_its_scope_only(
    uow: SqlSalesUnitOfWorkFactory, world: World
) -> None:
    step = ModelStep.PO_BODY_EXTRACTION
    reading = ShadowReading(
        reading_id=uuid.uuid4(),
        step=step,
        item_key=item_key("MB1", None, None, step),
        message_id="MB1",
        attachment_id=None,
        line_no=None,
        field="po",
        proposed={"header": {"po_date": "2026-11-20"}, "lines": {"1": {"quantity": "100"}}},
        prompt="sales.po_body_extraction@1.2.0",
        model_profile="onprem",
        rules=None,
        confidence=None,
        read_at=_AT,
        match_key="KMH:po-77",
    )
    await _keep(uow, world.alpha, reading)
    async with uow(world.beta) as work:
        assert await work.shadow_readings.take_matching(step, "KMH:po-77") == []
        await work.commit()
    async with uow(world.alpha) as work:
        assert await work.shadow_readings.take_matching(step, "KMH:po-78") == []
        assert await work.shadow_readings.take_matching(step, "KMH:po-77") == [reading]
        await work.commit()
    async with uow(world.alpha) as work:
        assert await work.shadow_readings.take_matching(step, "KMH:po-77") == []
