"""The head reassigns a case (ticket 17), through the routes and the database.

`sales.case.assign` is the head's alone (migration 934101cde272); who may be
given a case is who holds the scope that works it in its workspace, read by
the platform's `holding`, the function the access context is built from.

Negatives: a PIC (403), an assignee from another tenant or without the
working scope (422), a stale version (409).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from sales_api_harness import AN, BAO, DIEU, GIANG, HA, KHOA, Api, Persona
from sales_flow import order, order_of, process, quote
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.integration


async def _give(
    head: Persona, kind: str, case: dict[str, Any], assignee: uuid.UUID | None, **kw: Any
) -> Any:
    return await head.put(
        f"/{kind}/{case['case_id']}/assignee",
        {"assignee": assignee, "case_version": case["case_version"]},
        **kw,
    )


async def test_the_head_gives_an_order_to_another_pic(api: Api, migrator: AsyncEngine) -> None:
    an, dieu, giang = api.as_(AN), api.as_(DIEU), api.as_(GIANG)
    case = await order_of(an, "M01")
    assert case["assigned_to"] == str(an.id)

    offered = await giang.get(f"/orders/{case['case_id']}/assignees")
    assert offered.status_code == 200, offered.text
    ids = {m["user_id"] for m in offered.json()}
    assert {str(an.id), str(dieu.id)} <= ids
    assert str(api.as_(HA).id) not in ids

    given = await _give(giang, "orders", case, dieu.id)

    assert given.status_code == 200, given.text
    now = await order(giang, case["case_id"])
    assert now["assigned_to"] == str(dieu.id)
    assert now["case_version"] == case["case_version"] + 1
    # My work follows the new assignee.
    mine = {i["id"] for i in (await dieu.get("/my-work")).json()["items"]}
    assert case["case_id"] in mine
    assert case["case_id"] not in {i["id"] for i in (await an.get("/my-work")).json()["items"]}
    async with migrator.connect() as conn:
        (row,) = (
            await conn.execute(
                sa.text(
                    "SELECT actor_id, details FROM platform.audit_events"
                    " WHERE action = 'sales.order.reassigned' AND resource_id = :id"
                ),
                {"id": case["case_id"]},
            )
        ).all()
        told = (
            await conn.execute(
                sa.text(
                    "SELECT recipient_user_id, link FROM platform.notifications"
                    " WHERE source_key = :k"
                ),
                {"k": f"sales.case.assigned:{case['case_id']}:{now['case_version']}"},
            )
        ).all()
    assert row.actor_id == giang.id
    assert (row.details["assigned_from"], row.details["assigned_to"]) == (
        str(an.id),
        str(dieu.id),
    )
    assert [(t.recipient_user_id, t.link) for t in told] == [
        (dieu.id, f"/sales/orders/{case['case_id']}")
    ]


async def test_a_replay_with_the_same_key_reassigns_once(api: Api) -> None:
    an, dieu, giang = api.as_(AN), api.as_(DIEU), api.as_(GIANG)
    case = await order_of(an, "M01")
    key = str(uuid.uuid4())

    first = await _give(giang, "orders", case, dieu.id, key=key)
    again = await _give(giang, "orders", case, dieu.id, key=key)

    assert first.status_code == again.status_code == 200
    assert again.json() == first.json()
    assert (await order(giang, case["case_id"]))["case_version"] == case["case_version"] + 1


async def test_null_unassigns_and_a_quote_is_reassigned_too(api: Api) -> None:
    an, dieu, giang, khoa = api.as_(AN), api.as_(DIEU), api.as_(GIANG), api.as_(KHOA)
    case = await order_of(an, "M01")
    assert (await _give(giang, "orders", case, None)).status_code == 200
    assert (await order(giang, case["case_id"]))["assigned_to"] is None

    opened = await process(dieu, "M10")
    rfq = await quote(dieu, opened["case_id"])
    given = await _give(giang, "quotes", rfq, khoa.id)
    assert given.status_code == 200, given.text
    assert (await quote(giang, rfq["case_id"]))["assigned_to"] == str(khoa.id)


async def test_a_pic_may_neither_reassign_nor_list_who_may_be_given_it(api: Api) -> None:
    an, dieu = api.as_(AN), api.as_(DIEU)
    case = await order_of(an, "M01")

    refused = await _give(an, "orders", case, dieu.id)
    listed = await an.get(f"/orders/{case['case_id']}/assignees")

    assert refused.status_code == 403, refused.text
    assert listed.status_code == 403
    assert (await order(an, case["case_id"]))["assigned_to"] == str(an.id)


@pytest.mark.parametrize("who", [BAO, HA])
async def test_an_assignee_from_another_tenant_or_without_the_working_scope_is_refused(
    api: Api, who: str
) -> None:
    an, giang = api.as_(AN), api.as_(GIANG)
    case = await order_of(an, "M01")

    refused = await _give(giang, "orders", case, api.as_(who).id)

    assert refused.status_code == 422, refused.text
    assert refused.json()["details"]["field"] == "assignee"
    assert (await order(giang, case["case_id"]))["assigned_to"] == str(an.id)


async def test_a_stale_version_is_refused(api: Api) -> None:
    an, dieu, giang = api.as_(AN), api.as_(DIEU), api.as_(GIANG)
    case = await order_of(an, "M01")

    refused = await _give(giang, "orders", {**case, "case_version": 1_000}, dieu.id)

    assert refused.status_code == 409, refused.text
