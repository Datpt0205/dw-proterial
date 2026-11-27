"""Taking back a cross-check DW passed on Bravo's read-back (ticket 81),
through the route and the database.

The pass itself is the lane's, tested in `test_cross_check_on_match_lane.py`
over the real approval flow. Here a person's cross-check is turned into the
lane's by the migrator, with the columns the lane writes, so what is tested
is the route: who may take a pass back, and what it leaves.

Negatives: a viewer without `sales.order.cross_check` (403), a maker (409),
another tenant's workspace (404), and a cross-check a person decided (409).
"""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa
from sales_api_harness import AN, BAO, BETA, DIEU, GIANG, HA, Api
from sales_flow import cross_checked, order, order_of, uploaded
from sqlalchemy.ext.asyncio import AsyncEngine

from dw_platform.domain.audit import system_actor
from dw_sales.application.cross_check_on_match import CROSS_CHECK_ON_MATCH_LANE

pytestmark = pytest.mark.integration

DIGEST = "e" * 64


async def _crossed(api: Api) -> dict[str, Any]:
    """M34 prepared and recorded by An, cross-checked by Diệu."""
    an, dieu = api.as_(AN), api.as_(DIEU)
    return await cross_checked(dieu, await uploaded(an, await order_of(an, "M34")))


async def _passed_by_dw(api: Api, migrator: AsyncEngine) -> dict[str, Any]:
    crossed = await _crossed(api)
    async with migrator.begin() as conn:
        await conn.execute(
            sa.text(
                "UPDATE sales.order_cases SET cross_check_on_match = true,"
                " cross_checked_by = :lane, cross_checked_on_read_back = :digest"
                " WHERE id = :id"
            ),
            {
                "lane": system_actor(CROSS_CHECK_ON_MATCH_LANE).value,
                "digest": DIGEST,
                "id": crossed["case_id"],
            },
        )
    passed = await order(api.as_(AN), crossed["case_id"])
    assert (passed["status"], passed["cross_checked_on_read_back"]) == ("cross_checked", DIGEST)
    return passed


def _reopen(case: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    return f"/orders/{case['case_id']}/cross-check/reopen", {"case_version": case["case_version"]}


async def test_a_non_maker_who_may_cross_check_takes_the_pass_back(
    api: Api, migrator: AsyncEngine
) -> None:
    passed = await _passed_by_dw(api, migrator)
    path, body = _reopen(passed)

    assert (await api.as_(HA).post(path, body)).status_code == 403
    maker = await api.as_(AN).post(path, body)
    assert maker.status_code == 409, maker.text
    assert (await api.as_(BAO, BETA).post(path, body)).status_code == 404

    taken = await api.as_(GIANG).post(path, body)
    assert taken.status_code == 200, taken.text
    back = await order(api.as_(GIANG), passed["case_id"])
    assert back["status"] == "uploaded_to_bravo"
    assert (back["cross_checked_by"], back["cross_checked_on_read_back"]) == (None, None)
    assert back["cross_check_on_match"] is False
    # Nothing is raised for it: the recorder or the head raises it again.
    assert back["cross_check_stalled"] is True
    async with migrator.connect() as conn:
        (actor,) = (
            await conn.execute(
                sa.text(
                    "SELECT actor_id FROM platform.audit_events"
                    " WHERE action = 'sales.order.cross_check_reopened' AND resource_id = :id"
                ),
                {"id": passed["case_id"]},
            )
        ).one()
    assert str(actor) == str(api.as_(GIANG).id)


async def test_a_cross_check_a_person_decided_is_not_taken_back(api: Api) -> None:
    crossed = await _crossed(api)
    path, body = _reopen(crossed)

    refused = await api.as_(GIANG).post(path, body)

    assert refused.status_code == 409, refused.text
    assert (await order(api.as_(GIANG), crossed["case_id"]))["status"] == "cross_checked"
