"""A customer's PO form mapped once by one person and decided by another on a
platform approval, through the API the web calls (ticket 30), against a real
database.

No model is wired: the form is mapped by a person, as on a deployment with the
step off. What PostgreSQL keeps (the layout as tenant data under row
security, bound to its approval in the same workspace, its maker never its
checker), who may map and decide, the decision announced in the outbox and
carried out as the worker carries it out, and that the customer's next PO is
read through the approved layout with every value to confirm, are this file's.
The model pre-fill is the eval lane's (`sales_layout@1.0.0`) and the unit
suite's; the worker's handler is `apps/worker`'s unit suite's.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from sales_api_harness import AN, BAO, BETA, GIANG, HA, Api, Persona
from sales_flow import order, process
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from dw_kernel.ports import SystemClock, Uuid4Generator
from dw_platform.adapters.persistence.repositories import (
    SqlApprovalRepository,
    SqlAuditRepository,
)
from dw_platform.application.access_context import AccessContext
from dw_sales.adapters.assembly import build_layout_settlement
from dw_sales.application.layouts import LAYOUT_DECIDED

pytestmark = pytest.mark.integration

MAPPING: dict[str, Any] = {
    "kind": "pdf",
    "po_no": "Order Number",
    "po_date": "Order Date",
    "currency": "Currency",
    "line_no": "Item",
    "customer_item_code": "Part Number",
    "description": "Part Description",
    "quantity": "Order Qty",
    "uom": "Unit",
    "unit_price": "Price",
    "amount": "Extended",
    "requested_date": "Need By",
    "total_label": "Order Total",
    "thousands_separator": ",",
    "decimal_separator": ".",
    "date_format": "%Y-%m-%d",
}
BODY = {"message_id": "M43", "attachment_id": "M43-A1", "mapping": MAPPING}


async def _carry_out(api: Api, migrator: AsyncEngine, approval_id: str) -> str:
    """What the worker does with the decision's outbox event: the event is
    there, written by the decision, and its settlement applies it."""
    async with migrator.connect() as conn:
        event = (
            await conn.execute(
                sa.text(
                    "SELECT tenant_id, workspace_id, payload FROM platform.outbox_events"
                    " WHERE event_type = :type AND aggregate_id = :id"
                ),
                {"type": LAYOUT_DECIDED, "id": approval_id},
            )
        ).one()
    settlement = build_layout_settlement(
        session_factory=api.sessions,
        audit=SqlAuditRepository,
        approvals=SqlApprovalRepository,
        clock=SystemClock(),
        ids=Uuid4Generator(),
    )
    decider = AccessContext(
        tenant_id=event.tenant_id,
        workspace_id=event.workspace_id,
        principal_id=uuid.UUID(event.payload["decided_by"]),
        roles=frozenset(),
        scopes=frozenset(),
        plan_id="background",
    )
    return (await settlement.settle(uuid.UUID(approval_id), decider)).status


async def _proposed(an: Persona) -> dict[str, Any]:
    proposed = await an.post("/layouts", BODY)
    assert proposed.status_code == 200, proposed.text
    return dict(proposed.json())


async def test_a_form_is_mapped_by_one_person_approved_by_another_and_then_read(
    api: Api, migrator: AsyncEngine
) -> None:
    an, giang = api.as_(AN), api.as_(GIANG)
    routed = await process(an, "M43")
    assert (routed["kind"], routed["reason"]) == ("routed_to_sales", "attachment_unreadable")

    source = await an.get("/layouts/source", message_id="M43", attachment_id="M43-A1")
    assert source.status_code == 200, source.text
    assert {"Order Number", "Need By"} <= {c["text"] for c in source.json()["cells"]}
    preview = (await an.post("/layouts/preview", BODY)).json()
    assert (preview["ok"], preview["po_no"], len(preview["lines"])) == (True, "NRV-PO-26-0502", 3)
    swapped = {**BODY, "mapping": {**MAPPING, "quantity": "Price", "unit_price": "Order Qty"}}
    refused = await an.post("/layouts", swapped)
    assert refused.status_code == 409
    assert "quantity_not_whole:quantity" in str(refused.json()["details"]["problems"])

    layout = await _proposed(an)
    approval_id = layout["approval_id"]
    decision = {"approve": True, "comment": "Mẫu đọc đúng PO", "subject_version": 1}
    # The PIC holds no `sales.layout.approve`, the scope the approval is stamped with.
    assert (await an.decide(approval_id, decision)).status_code == 403
    # Decided on the layouts page only: `/approvals` sends no version.
    unversioned = {k: v for k, v in decision.items() if k != "subject_version"}
    assert (await giang.decide(approval_id, unversioned)).status_code == 422
    approved = await giang.decide(approval_id, decision)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    # Recorded, not yet carried out: the worker applies it.
    listed = {row["layout_id"]: row for row in (await an.get("/layouts")).json()}
    assert listed[layout["layout_id"]]["status"] == "proposed"
    assert await _carry_out(api, migrator, approval_id) == "approved"
    assert await _carry_out(api, migrator, approval_id) == "approved"  # redelivered

    async with migrator.connect() as conn:
        row = (
            await conn.execute(
                sa.text(
                    "SELECT status, proposed_by::text, decided_by::text, approval_id::text"
                    " FROM sales.po_layouts WHERE id = :id"
                ),
                {"id": layout["layout_id"]},
            )
        ).one()
        audited = await conn.scalar(
            sa.text(
                "SELECT count(*) FROM platform.audit_events"
                " WHERE action = 'sales.layout.approved' AND resource_id = :id"
            ),
            {"id": layout["layout_id"]},
        )
    assert row.status == "approved" and row.proposed_by != row.decided_by
    assert (row.decided_by, row.approval_id) == (str(giang.id), approval_id)
    assert audited == 1

    read = await process(an, "M43")
    assert (read["kind"], read["case_kind"]) == ("case_created", "order")
    case = await order(an, read["case_id"])
    uncertain = [f for f in case["findings"] if f["code"] == "value_uncertain"]
    assert {f["line_no"] for f in uncertain} == {None, 1, 2, 3}


async def test_the_maker_is_refused_on_the_approval_and_by_the_database(
    api: Api, migrator: AsyncEngine
) -> None:
    giang = api.as_(GIANG)
    await process(api.as_(AN), "M43")
    # The head maps one: they are its maker, and `sales.` is strict.
    layout = await _proposed(giang)
    mine = await giang.decide(
        layout["approval_id"], {"approve": True, "comment": "Tự duyệt", "subject_version": 1}
    )
    assert mine.status_code == 409
    assert mine.json()["details"]["rule"] == "maker_checker"

    with pytest.raises(IntegrityError, match="ck_po_layouts_checker_not_maker"):
        async with migrator.begin() as conn:
            await conn.execute(
                sa.text(
                    "UPDATE sales.po_layouts SET status = 'approved', decided_by = proposed_by"
                    " WHERE id = :id"
                ),
                {"id": layout["layout_id"]},
            )


async def test_a_layout_cannot_wait_on_another_workspaces_approval(
    api: Api, migrator: AsyncEngine
) -> None:
    an = api.as_(AN)
    await process(an, "M43")
    layout = await _proposed(an)

    with pytest.raises(IntegrityError, match="fk_po_layouts_approval_requests"):
        async with migrator.begin() as conn:
            await conn.execute(
                sa.text("UPDATE sales.po_layouts SET approval_id = :other WHERE id = :id"),
                {"other": uuid.uuid4(), "id": layout["layout_id"]},
            )


async def test_who_may_map_and_another_tenant_sees_no_layout(api: Api) -> None:
    an, ha, bao = api.as_(AN), api.as_(HA), api.as_(BAO, BETA)
    await process(an, "M43")
    layout = await _proposed(an)

    # Leadership reads aggregates only; another tenant's mailbox is its own.
    assert (
        await ha.get("/layouts/source", message_id="M43", attachment_id="M43-A1")
    ).status_code == 403
    assert (await ha.post("/layouts", BODY)).status_code == 403
    assert (
        await bao.get("/layouts/source", message_id="M43", attachment_id="M43-A1")
    ).status_code == 404
    assert (await bao.get("/layouts")).json() == []
    decision = {"approve": True, "comment": "Duyệt", "subject_version": 1}
    assert (await bao.decide(layout["approval_id"], decision)).status_code == 404
    assert [row["layout_id"] for row in (await an.get("/layouts")).json()] == [layout["layout_id"]]
