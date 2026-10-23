"""The activity page's drill-down through the API, against PostgreSQL (slice 3).

A count on `GET /sales/activity` carries the case list filter it stands for;
`GET /sales/orders` and `GET /sales/quotes` take those parameters as they are
serialised and keep the cases a matching row of `sales.step_outcomes` names,
read under the caller's RLS after the caller's scope. A filter that names too
little is refused (422), not read as "any".
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sales_api_harness import AN, HA, Api
from sales_flow import order_of

from dw_kernel.ids import TenantId, WorkspaceId
from dw_platform.adapters.persistence.repositories import (
    SqlApprovalRepository,
    SqlAuditRepository,
)
from dw_platform.testing.seed_env import sid
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.ports import SalesScope
from dw_sales.domain.activity import StepOutcome
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.order_checks import SALES_TIME_ZONE, ModelStep

pytestmark = pytest.mark.integration

ALPHA = SalesScope(
    TenantId(sid("tenant", "tenant-alpha")), WorkspaceId(sid("workspace", "tenant-alpha:main"))
)
STEP = ModelStep.DESCRIPTION_ATTRIBUTES


def _row(case_id: str, *, automatic: bool, at: datetime) -> StepOutcome:
    return StepOutcome(
        outcome_id=uuid.uuid4(),
        occurred_at=at,
        message_id="M01",
        lane=CaseKind.ORDER,
        case_id=uuid.UUID(case_id),
        line_no=1,
        step=STEP,
        result="accepted" if automatic else "refused",
        automatic=automatic,
        reason_code=None if automatic else "text_uncovered",
        refusals={},
        prompt="sales.description_attributes@1.0.0",
        model_profile="onprem",
        model="qwen3.5-9b-dw",
        calls=1,
        duration_ms=500,
    )


async def _written(api: Api) -> tuple[str, str, str]:
    """Two orders, one carried by DW1 and one left to a person at the
    description step today; the local day the rows fall on."""
    an = api.as_(AN)
    carried, left = await order_of(an, "M01"), await order_of(an, "M04")
    now = datetime.now(UTC)
    uow = SqlSalesUnitOfWorkFactory(
        api.sessions, audit=SqlAuditRepository, approvals=SqlApprovalRepository
    )
    async with uow(ALPHA) as work:
        await work.step_activity.append(
            [
                _row(carried["case_id"], automatic=True, at=now),
                _row(left["case_id"], automatic=False, at=now),
            ]
        )
        await work.commit()
    return carried["case_id"], left["case_id"], now.astimezone(SALES_TIME_ZONE).date().isoformat()


async def test_a_count_on_the_activity_page_opens_the_cases_it_counts(api: Api) -> None:
    carried, left, today = await _written(api)
    an = api.as_(AN)

    summary = (await an.get("/activity", **{"from": today, "to": today})).json()
    (step,) = [s for s in summary["steps"] if s["step"] == STEP.value]
    assert (step["automatic"]["count"], step["to_person"]["count"]) == (1, 1)
    linked: dict[str, Any] = {k: v for k, v in step["to_person"]["filter"].items() if v}

    listed = await an.get("/orders", **linked)
    assert listed.status_code == 200, listed.text
    assert [o["case_id"] for o in listed.json()] == [left]
    carried_only = await an.get("/orders", **{**linked, "handled_by": "dw1"})
    assert [o["case_id"] for o in carried_only.json()] == [carried]
    # No filter: the whole list, as before.
    assert {carried, left} <= {o["case_id"] for o in (await an.get("/orders")).json()}
    # The quote list reads its own lane: no quote case has a row here.
    assert (await an.get("/quotes", **linked)).json() == []


@pytest.mark.parametrize(
    "asked",
    [
        {"handled_by": "dw1"},
        {"step": STEP.value, "from": "2026-10-01"},
        {"step": STEP.value, "from": "2026-10-01", "to": "2026-10-01", "lane": "quote"},
        {"step": STEP.value, "from": "2026-09-01", "to": "2026-10-23"},
    ],
    ids=["no_step", "no_end", "other_lane", "over_31_days"],
)
async def test_a_filter_that_names_too_little_is_refused(api: Api, asked: dict[str, str]) -> None:
    refused = await api.as_(AN).get("/orders", **asked)
    assert refused.status_code == 422, refused.text


async def test_a_caller_who_may_not_read_cases_is_refused_before_the_filter(api: Api) -> None:
    """The viewer reads the overview only: forbidden, whatever the filter."""
    for asked in ({}, {"handled_by": "dw1"}):
        assert (await api.as_(HA).get("/orders", **asked)).status_code == 403
