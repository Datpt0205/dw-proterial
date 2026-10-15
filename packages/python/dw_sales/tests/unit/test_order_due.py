"""An order's due date on the work list (G22, ticket 08), over the in-memory
world: the requested date of a line whose lead time is short.

The SQL reader's column, index and keyset are held equal to this by
`apps/api/tests/integration/test_sales_overview_sql.py`.
"""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

import pytest

from dw_kernel.pagination import PageQuery, PageRequest
from dw_sales.application.overview_ports import NO_DUE, OpenOrder
from dw_sales.domain.orders import FindingCode
from dw_sales.evals.graders import AN, CALLERS
from dw_sales.evals.world import ALPHA, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]


def _world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), CALLERS)


async def _orders(world: World, *message_ids: str) -> dict[str, uuid.UUID]:
    seen = await world.process_each(AN, list(message_ids))
    ids = {m: seen[m][0].case_id for m in message_ids}
    assert None not in ids.values()
    return ids  # type: ignore[return-value]


async def test_an_order_is_due_on_its_short_lines_requested_date() -> None:
    world = _world()
    ids = await _orders(world, "M01", "M06", "M35")
    # M06: line 3 is requested before its lead time allows; the others are not.
    m06 = world.order(ids["M06"])
    short = [f.line_no for f in m06.findings if f.code is FindingCode.REQUESTED_DATE_SHORT_LT]
    assert short == [3]
    assert m06.due == m06.line(3).effective.requested_date == date(2026, 9, 30)
    # M35: line 2 is split over two schedules, of which only the first is
    # short; the order is due on that one, not on the later delivery.
    m35 = world.order(ids["M35"])
    assert [s.requested_date for s in m35.line(2).effective.schedules] == [
        date(2026, 10, 6),
        date(2026, 11, 30),
    ]
    assert m35.due == date(2026, 10, 6)
    # M01: no line is short, so nothing sets a deadline.
    assert world.order(ids["M01"]).due is None


async def test_an_order_with_several_short_lines_is_due_on_the_earliest() -> None:
    """M06 with line 1 (requested 2026-11-13) short as well as line 3
    (2026-09-30): the order is due on line 3's date, whichever finding comes
    first."""
    world = _world()
    ids = await _orders(world, "M06")
    m06 = world.order(ids["M06"])
    (line_3,) = (f for f in m06.findings if f.code is FindingCode.REQUESTED_DATE_SHORT_LT)
    line_1 = line_3.model_copy(update={"line_no": 1, "actual": "2026-11-13"})
    two_short = m06.model_copy(update={"findings": (line_1, *m06.findings)})
    assert m06.line(1).effective.requested_date == date(2026, 11, 13)
    assert two_short.due == date(2026, 9, 30)


async def test_my_work_carries_an_orders_due_date_and_sorts_by_it() -> None:
    world = _world()
    ids = await _orders(world, "M01", "M35")
    items = (await world.services.overview.my_work(AN.context())).items
    orders = [i for i in items if i.kind == "order"]
    assert [(i.id, i.due) for i in orders] == [
        # M35 came in after M01, and is listed first: it is due.
        (str(ids["M35"]), date(2026, 10, 6)),
        (str(ids["M01"]), None),
    ]


async def test_the_store_pages_an_order_in_its_due_dates_group() -> None:
    """The reader's sort key is the one the SQL index carries: (due date as
    ISO text, or `NO_DUE`; received; id)."""
    world = _world()
    ids = await _orders(world, "M01", "M35")
    async with world.store(ALPHA) as work:
        page = await work.overview.work_page(
            await world.services.overview._wanted(AN.context()),
            PageRequest(limit=50, after=None, query=PageQuery(key="t")),
        )
    groups = {
        entry.row.case_id: (entry.position.group, entry.row.due)
        for entry in page.items
        if isinstance(entry.row, OpenOrder)
    }
    assert groups[ids["M35"]] == ("2026-10-06", date(2026, 10, 6))
    assert groups[ids["M01"]] == (NO_DUE, None)
