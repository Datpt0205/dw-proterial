"""Decided description lines read back as examples (ticket 43 part 2), on a
real database as `dw_app`: the description is the order line's own, joined
through the revision the labelled case names; only a kept value of the
newest decision on a line is an example; and acceptance 1 at the reading: an
id another tenant's (or workspace's) index might hand back reads as nothing,
because the read runs under the caller's RLS.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sales_harness import OrderRun, World
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_sales.adapters.persistence.labelled_examples import SqlDescriptionExamples
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.ports import SalesScope
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.labelled_cases import LabelledCase
from dw_sales.domain.order_checks import ModelStep
from dw_sales.domain.orders import OrderCase

pytestmark = pytest.mark.integration

_AT = datetime.now(UTC).replace(microsecond=0)


def _described(run: OrderRun) -> tuple[OrderCase, int, str]:
    """A stored case and a line of it with a description."""
    for case in run.latest().values():
        for line in case.lines:
            if line.po_line.description.strip():
                return case, line.po_line.line_no, line.po_line.description
    raise AssertionError("the mock mailbox holds no described line")


def _label(
    case: OrderCase, line_no: int, kept: list[str] | None, *, at: datetime = _AT
) -> LabelledCase:
    return LabelledCase(
        label_id=uuid.uuid4(),
        decided_at=at,
        step=ModelStep.DESCRIPTION_ATTRIBUTES,
        lane=CaseKind.ORDER,
        case_id=case.case_id,
        customer_code=case.customer_code,
        message_id=case.message_id,
        attachment_id=case.document.attachment_id,
        line_no=line_no,
        field="prv_code",
        proposed=["HW-1001", "HW-1009"],
        kept=kept,
        prompt="sales.description_attributes@1.1.0",
        model_profile="onprem",
        rules="sales_order_rules@1.13.0",
        decided_by=uuid.UUID(int=0xA1),
    )


async def _write(uow: SqlSalesUnitOfWorkFactory, scope: SalesScope, *cases: LabelledCase) -> None:
    async with uow(scope) as work:
        await work.labelled_cases.append(cases)
        await work.commit()


async def test_a_kept_code_reads_back_with_its_lines_description_in_its_own_scope_only(
    uow: SqlSalesUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
    world: World,
    order_run: OrderRun,
) -> None:
    case, line_no, description = _described(order_run)
    label = _label(case, line_no, ["HW-1001"])
    await _write(uow, world.alpha, label)
    examples = SqlDescriptionExamples(app_sessions)

    (example,) = await examples.by_ids(world.alpha, [label.label_id])
    assert (example.description, example.prv_code, example.case_id) == (
        description,
        "HW-1001",
        case.case_id,
    )
    assert example.customer_code == case.customer_code
    # Another tenant, another workspace of the same tenant: the same id
    # reads as nothing, whatever an index handed back.
    for scope in (world.beta, world.alpha_other):
        assert await examples.by_ids(scope, [label.label_id]) == []
        assert await examples.after(scope, None, 10) == []
    assert [e.label_id for e in await examples.after(world.alpha, None, 10)] == [label.label_id]
    assert await examples.after(world.alpha, (label.decided_at, label.label_id), 10) == []


async def test_only_the_newest_kept_decision_on_a_line_is_an_example(
    uow: SqlSalesUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
    world: World,
    order_run: OrderRun,
) -> None:
    case, line_no, _ = _described(order_run)
    confirmed = _label(case, line_no, ["HW-1001"], at=_AT - timedelta(hours=2))
    undone = _label(case, line_no, None, at=_AT - timedelta(hours=1))
    await _write(uow, world.alpha, confirmed, undone)
    examples = SqlDescriptionExamples(app_sessions)

    # Undone since: neither the confirmation nor the rejection is one.
    assert await examples.by_ids(world.alpha, [confirmed.label_id, undone.label_id]) == []

    corrected = _label(case, line_no, ["HW-1009"])
    await _write(uow, world.alpha, corrected)
    found = await examples.by_ids(world.alpha, [confirmed.label_id, corrected.label_id])
    assert [(e.label_id, e.prv_code) for e in found] == [(corrected.label_id, "HW-1009")]


async def _store_reading(
    sessions: async_sessionmaker[AsyncSession],
    scope: SalesScope,
    case: OrderCase,
    line_no: int,
    reading: dict[str, object],
) -> None:
    """Stamp a model's reading on the stored line, as the intake does."""
    statement = sa.text(
        "UPDATE sales.order_lines AS l"
        " SET check_basis = jsonb_set(l.check_basis, '{description_reading}', CAST(:r AS jsonb))"
        " FROM sales.order_revisions AS r"
        " WHERE r.id = l.revision_id AND r.case_id = :case AND r.message_id = :message"
        " AND l.line_no = :line"
    )
    async with tenant_session(
        sessions, TenantScope(scope.tenant_id.value, scope.workspace_id.value)
    ) as session:
        await session.execute(
            statement,
            {
                "r": json.dumps(reading),
                "case": case.case_id,
                "message": case.message_id,
                "line": line_no,
            },
        )
        await session.commit()


def _reading(description: str, outcome: str = "read") -> dict[str, object]:
    word = description.split()[0]
    start = description.index(word)
    spans = [
        {
            "attribute": "colour",
            "span": word,
            "start": start,
            "end": start + len(word),
            "value": "black",
            "read_by": "model",
        }
    ]
    return {
        "prompt": "sales.description_attributes@1.2.0",
        "model_profile": "onprem",
        "route": "structured_extraction",
        "outcome": outcome,
        "reason": None if outcome == "read" else "text_uncovered",
        "spans": spans if outcome == "read" else [],
    }


async def test_a_lines_accepted_reading_comes_with_its_example_and_no_other_does(
    uow: SqlSalesUnitOfWorkFactory,
    app_sessions: async_sessionmaker[AsyncSession],
    world: World,
    order_run: OrderRun,
) -> None:
    """Ticket 43, 2026-11-22: the spans go with the example for
    `shown_lines` to show as the answer they were; a reading code refused,
    or none, gives none."""
    case, line_no, description = _described(order_run)
    label = _label(case, line_no, ["HW-1001"])
    await _write(uow, world.alpha, label)
    examples = SqlDescriptionExamples(app_sessions)

    await _store_reading(app_sessions, world.alpha, case, line_no, _reading(description))
    (example,) = await examples.by_ids(world.alpha, [label.label_id])
    assert [(s.attribute, s.span) for s in example.spans] == [("colour", description.split()[0])]

    refused = _reading(description, "not_understood")
    await _store_reading(app_sessions, world.alpha, case, line_no, refused)
    (example,) = await examples.by_ids(world.alpha, [label.label_id])
    assert example.spans == ()
