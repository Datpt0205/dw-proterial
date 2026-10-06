"""DW1 on the runtime (ticket 10): who may decide a Sales approval, who sees
one, what an approval and a run carry, the plan's run allowance, and the
context-side decide routes gone.

The negatives the ticket names: the purchasing manager deciding a quote
(403), the maker deciding (409), Diệu with `approver_boost` approving a quote
she priced (403), and a viewer seeing no Sales approval payload.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Any

import pytest
import sqlalchemy as sa
from pg_test_db import DatabaseUrls
from sales_api_harness import (
    AN,
    BAO,
    BETA,
    BINH,
    DIEU,
    GIANG,
    HA,
    Api,
    build_app,
    known_price_strings,
)
from sales_flow import (
    approval_of,
    approve,
    cross_check,
    open_sources,
    order_of,
    process,
    replied,
    submitted,
    uploaded,
)
from sqlalchemy.ext.asyncio import AsyncEngine

from dw_platform.testing.seed_env import sid

pytestmark = pytest.mark.integration

ALPHA_TENANT = sid("tenant", "tenant-alpha")


async def _pending_quote(api: Api) -> dict[str, Any]:
    dieu = api.as_(DIEU)
    return await submitted(dieu, await replied(dieu, "M10", "YCBG-2609-030", "M25"))


async def test_the_purchasing_manager_cannot_decide_a_sales_quote(api: Api) -> None:
    giang, binh = api.as_(GIANG), api.as_(BINH)
    pending = await _pending_quote(api)
    approval_id = await approval_of(giang, pending)

    # Bình holds approvals.decide (manager), not sales.quote.approve.
    refused = await binh.decide(
        approval_id,
        {"approve": True, "comment": "ok", "subject_version": pending["case_version"]},
    )

    assert refused.status_code == 403
    assert refused.json()["details"]["action"] == "sales.quote.approve"
    # Nor is it in his inbox, nor readable by id.
    assert (await binh.platform("/approvals")).json()["items"] == []
    assert (await binh.platform(f"/approvals/{approval_id}")).status_code == 404


async def test_a_viewer_sees_no_sales_approval_payload(api: Api) -> None:
    giang, ha = api.as_(GIANG), api.as_(HA)
    pending = await _pending_quote(api)
    approval_id = await approval_of(giang, pending)

    listed = await ha.platform("/approvals")
    single = await ha.platform(f"/approvals/{approval_id}")

    assert listed.status_code == 200 and listed.json()["items"] == []
    assert single.status_code == 404
    assert pending["case_id"] not in listed.text + single.text


async def test_another_tenant_neither_sees_nor_decides_a_sales_approval(api: Api) -> None:
    giang = api.as_(GIANG)
    pending = await _pending_quote(api)
    approval_id = await approval_of(giang, pending)
    # Bảo is a Sales PIC in tenant beta: every Sales scope, the wrong tenant.
    bao = api.as_(BAO, BETA)

    listed = await bao.platform("/approvals")
    single = await bao.platform(f"/approvals/{approval_id}")
    decided = await bao.decide(
        approval_id, {"approve": True, "comment": "ok", "subject_version": 1}
    )

    assert listed.status_code == 200 and listed.json()["items"] == []
    assert single.status_code == 404
    assert decided.status_code == 404
    assert (await giang.platform(f"/approvals/{approval_id}")).json()["status"] == "pending"


async def test_the_approver_and_the_requester_see_the_approval(api: Api) -> None:
    dieu, giang = api.as_(DIEU), api.as_(GIANG)
    pending = await _pending_quote(api)
    approval_id = await approval_of(giang, pending)

    for persona in (giang, dieu):
        items = (await persona.platform("/approvals")).json()["items"]
        assert [item["id"] for item in items] == [approval_id], persona.subject
    shown = (await giang.platform(f"/approvals/{approval_id}")).json()
    assert shown["approval_type"] == "sales.quote"
    assert shown["requires_comment"] is True


async def test_the_maker_cannot_decide_and_the_approval_names_every_maker(
    api: Api, migrator: AsyncEngine
) -> None:
    an, dieu, giang = api.as_(AN), api.as_(DIEU), api.as_(GIANG)
    up = await uploaded(an, await order_of(an, "M01"), recorder=giang)
    approval_id = await approval_of(an, up)

    async with migrator.connect() as conn:
        row = (
            await conn.execute(
                sa.text(
                    "SELECT requested_by, payload FROM platform.approval_requests WHERE id = :id"
                ),
                {"id": approval_id},
            )
        ).one()
    # Requested by whoever recorded the Bravo entry (a maker), and naming the
    # preparer too: both are refused.
    assert row.requested_by == giang.id
    assert set(row.payload["makers"]) == {str(an.id), str(giang.id)}
    for maker in (an, giang):
        await open_sources(maker, up)
        refused = await cross_check(maker, up)
        assert refused.status_code == 409, maker.subject
        assert refused.json()["details"]["rule"] == "maker_checker"

    await open_sources(dieu, up)
    assert (await cross_check(dieu, up)).status_code == 200


async def test_approvals_and_runs_carry_ids_a_version_and_a_hash_never_an_amount(
    api: Api, migrator: AsyncEngine
) -> None:
    giang = api.as_(GIANG)
    pending = await _pending_quote(api)
    assert (await approve(giang, pending)).status_code == 200

    async with migrator.connect() as conn:
        approvals = (
            await conn.execute(
                sa.text("SELECT payload FROM platform.approval_requests WHERE tenant_id = :t"),
                {"t": ALPHA_TENANT},
            )
        ).all()
        runs = (
            await conn.execute(
                sa.text(
                    "SELECT input, result, worker_id, worker_version, graph_version"
                    " FROM platform.worker_runs WHERE tenant_id = :t"
                ),
                {"t": ALPHA_TENANT},
            )
        ).all()
        audit = (
            await conn.execute(
                sa.text(
                    "SELECT details FROM platform.audit_events"
                    " WHERE tenant_id = :t AND resource_id = :id"
                ),
                {"t": ALPHA_TENANT, "id": pending["case_id"]},
            )
        ).all()

    (approval,) = approvals
    assert set(approval.payload) == {
        "approval_type",
        "decide_scope",
        "reason",
        "case_kind",
        "case_id",
        "case_version",
        "document_sha256",
        "makers",
    }
    assert approval.payload["document_sha256"] == pending["submission"]["document_sha256"]
    # Every run is DW1's, on the pinned graph.
    assert {(r.worker_id, r.worker_version, r.graph_version) for r in runs} == {
        ("sales-dw1", "1.0.0", "1.0.0")
    }
    text = json.dumps(
        [a.payload for a in approvals]
        + [{"input": r.input, "result": r.result} for r in runs]
        + [a.details for a in audit],
        ensure_ascii=False,
    )
    prices = known_price_strings()
    assert [p for p in prices if p in text] == []
    # The search can find one: the quote itself carries the decided price.
    assert any(p in json.dumps(pending) for p in prices)


async def test_the_plans_run_allowance_is_checked_where_processing_starts(
    sales_api_db: DatabaseUrls, clean_sales: None
) -> None:
    """ "DW xử lý" is a run, and the runner refuses one the plan has no
    allowance left for: the check is where every run begins, so any door
    that starts DW1 (a button today, a mailbox consumer later) passes it."""

    class OneRunADay:
        def runs_per_day(self, plan_id: str) -> int | None:
            return 1

        def spend_usd_per_day(self, plan_id: str) -> Decimal | None:
            return None

    async with build_app(sales_api_db.app, allowance=OneRunADay()) as api:
        an = api.as_(AN)
        await process(an, "M01")

        one = await an.post("/inbox/M02/process")
        every = await an.post("/inbox/process-all")

        assert one.status_code == 429, one.text
        assert one.json()["details"]["quota"] == "runs_per_day"
        assert every.status_code == 429
        inbox = (await an.get("/inbox")).json()
        done = [m["message_id"] for m in inbox if m["disposition"]["kind"] != "not_yet_processed"]
        assert done == ["M01"]


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/quotes/{id}/approval", {"case_version": 1, "decision": "approve"}),
        ("/orders/{id}/cross-check", {"case_version": 1, "decision": "accept"}),
    ],
)
async def test_the_context_side_decide_routes_are_gone(
    api: Api, path: str, body: dict[str, Any]
) -> None:
    giang = api.as_(GIANG)

    response = await giang.post(path.format(id=uuid.uuid4()), body)

    assert response.status_code in (404, 405)
