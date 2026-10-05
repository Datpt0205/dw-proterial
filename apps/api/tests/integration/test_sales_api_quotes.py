"""A quotation through the API, as Diệu, Giang and Khoa walk it (spec "Done
when"), and the approval's refusals: the pricer, a holder of the platform's
`approvals.decide` without `sales.quote.approve`, and the generic approvals
path, which never holds a Sales case.
"""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa
from sales_api_harness import AN, DECIDED_PRICE, DIEU, GIANG, KHOA, Api, Persona, user_id
from sales_flow import process, quote
from sqlalchemy.ext.asyncio import AsyncEngine

from dw_platform.testing.seed_env import sid

pytestmark = pytest.mark.integration

_BAND = {"kind": "lme_band", "low_usd_per_tonne": "10500", "high_usd_per_tonne": "11000"}


async def _step(persona: Persona, case: dict[str, Any], step: str, **body: Any) -> dict[str, Any]:
    response = await persona.post(
        f"/quotes/{case['case_id']}/{step}", {"case_version": case["case_version"], **body}
    )
    assert response.status_code == 200, response.text
    return await quote(persona, case["case_id"])


async def replied(pic: Persona, rfq: str, ycbg_no: str, reply: str) -> dict[str, Any]:
    """The request processed, its YCBG recorded and sent, Design's reply taken."""
    opened = await process(pic, rfq)
    assert opened["case_kind"] == "quote", opened
    case = await quote(pic, opened["case_id"])
    case = await _step(pic, case, "ycbg")
    case = await _step(pic, case, "ycbg", ycbg_no=ycbg_no)
    case = await _step(pic, case, "design-sent")
    attached = await process(pic, reply)
    assert (attached["kind"], attached["case_id"]) == ("attached_to_case", case["case_id"])
    return await quote(pic, case["case_id"])


async def submitted(
    pricer: Persona, case: dict[str, Any], price: str = DECIDED_PRICE, quote_no: str = "Q26-0301"
) -> dict[str, Any]:
    priced = await _step(
        pricer,
        case,
        "price",
        lme_month="2026-09",
        lines=[
            {
                "line_no": line["line_no"],
                "unit_price": price,
                "moq": "3000",
                "lead_time_days": 45,
                "copper_basis": _BAND,
            }
            for line in case["lines"]
        ],
    )
    return await _step(pricer, priced, "submit", quote_no=quote_no)


async def _approve(approver: Persona, case: dict[str, Any], **extra: Any) -> Any:
    return await approver.post(
        f"/quotes/{case['case_id']}/approval",
        {
            "case_version": case["case_version"],
            "decision": "approve",
            "document_sha256": case["submission"]["document_sha256"],
            **extra,
        },
    )


async def test_dieu_prices_m10_and_giang_approves_it(api: Api) -> None:
    dieu, giang = api.as_(DIEU), api.as_(GIANG)
    case = await replied(dieu, "M10", "YCBG-2609-030", "M25")
    assert case["assigned_to"] == str(user_id(DIEU))
    assert (case["rules_version"], case["parser_version"]) == (
        "sales_quote_rules@1.1.0",
        "excel_rfq_reader@1.0.0",
    )
    # Diệu holds sales_price_evidence: other customers' prices reach her.
    (evidence,) = case["evidence"]
    assert isinstance(evidence["other_customers"], list) and evidence["other_customers"]

    pending = await submitted(dieu, case)
    assert pending["status"] == "pending_approval"
    assert pending["pricing"]["decided_by"] == str(user_id(DIEU))

    approved = await _approve(giang, pending)
    assert approved.status_code == 200, approved.text
    final = await quote(giang, case["case_id"])
    assert final["approval"]["approved_by"] == str(user_id(GIANG))
    assert final["approval"]["document_sha256"] == pending["submission"]["document_sha256"]
    sent = await _step(dieu, final, "sent")
    recorded = await _step(dieu, sent, "master-list")
    assert recorded["status"] == "master_list_recorded"


async def test_dieu_cannot_approve_her_own_quote_whatever_approver_boost_gives(
    api: Api, migrator: AsyncEngine
) -> None:
    dieu = api.as_(DIEU)
    pending = await submitted(dieu, await replied(dieu, "M10", "YCBG-2609-030", "M25"))

    refused = await _approve(dieu, pending)

    # 403, not 409: she lacks sales.quote.approve, and the platform's
    # approvals.decide she holds decides nothing here.
    assert refused.status_code == 403
    assert refused.json()["details"]["action"] == "sales.quote.approve"
    # Nothing a Sales step does reaches the platform's generic approvals: no
    # request exists there for a decide-holder to act on.
    async with migrator.connect() as conn:
        requests = await conn.scalar(
            sa.text("SELECT count(*) FROM platform.approval_requests WHERE tenant_id = :t"),
            {"t": sid("tenant", "tenant-alpha")},
        )
    assert requests == 0
    assert (await quote(dieu, pending["case_id"]))["status"] == "pending_approval"


async def test_giang_cannot_approve_a_quote_he_priced_and_khoa_can(api: Api) -> None:
    dieu, giang, khoa = api.as_(DIEU), api.as_(GIANG), api.as_(KHOA)
    case = await replied(dieu, "M09", "YCBG-2609-028", "M18")
    pending = await submitted(giang, case, price="1.2500", quote_no="Q26-0302")

    own = await _approve(giang, pending)
    assert own.status_code == 409
    assert "separation of duties" in own.json()["message"]

    deputy = await _approve(khoa, pending)
    assert deputy.status_code == 200, deputy.text


async def test_an_approval_is_bound_to_the_document_the_approver_saw(api: Api) -> None:
    dieu, giang = api.as_(DIEU), api.as_(GIANG)
    pending = await submitted(dieu, await replied(dieu, "M10", "YCBG-2609-030", "M25"))

    other = await _approve(giang, pending, document_sha256="f" * 64)

    assert other.status_code == 409


async def test_the_approver_returns_the_price_to_the_pricer(api: Api) -> None:
    dieu, giang = api.as_(DIEU), api.as_(GIANG)
    pending = await submitted(dieu, await replied(dieu, "M10", "YCBG-2609-030", "M25"))

    returned = await giang.post(
        f"/quotes/{pending['case_id']}/approval",
        {"case_version": pending["case_version"], "decision": "return", "comment": "Giá cao"},
    )

    assert returned.status_code == 200, returned.text
    case = await quote(dieu, pending["case_id"])
    assert case["status"] == "returned"
    assert case["returns"][0]["returned_by"] == str(user_id(GIANG))


async def test_a_pic_without_sales_price_evidence_sees_no_other_customers_price(
    api: Api,
) -> None:
    dieu, an = api.as_(DIEU), api.as_(AN)
    case = await replied(dieu, "M10", "YCBG-2609-030", "M25")

    seen_by_an = await quote(an, case["case_id"])

    (evidence,) = seen_by_an["evidence"]
    assert evidence["other_customers"] == {"hidden": True}
    assert evidence["reference_price"] == {"hidden": True}
    # His own customer's history is his to see.
    assert isinstance(evidence["own_history"], list)


async def test_a_price_is_stamped_by_the_server_not_the_request(api: Api) -> None:
    dieu = api.as_(DIEU)
    case = await replied(dieu, "M10", "YCBG-2609-030", "M25")

    smuggled = await dieu.post(
        f"/quotes/{case['case_id']}/price",
        {
            "case_version": case["case_version"],
            "decided_by": str(user_id(GIANG)),
            "decided_at": "2020-01-01T00:00:00Z",
            "lines": [],
        },
    )

    # The body has no field for who or when: refused, not taken.
    assert smuggled.status_code == 422
