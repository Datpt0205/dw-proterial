"""A quotation through the API, as Diệu, Giang and Khoa walk it (spec "Done
when"), and the approval's refusals: the pricer, and a holder of the
platform's `approvals.decide` without `sales.quote.approve`. The approval is
the platform's (`/api/v1/approvals`), raised by DW1's run on submit.
"""

from __future__ import annotations

import pytest
from sales_api_harness import AN, DIEU, GIANG, KHOA, Api, user_id
from sales_flow import approval_of, approve, quote, quote_step, replied, submitted

pytestmark = pytest.mark.integration


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

    assert pending["decision"]["approval_type"] == "sales.quote"
    approved = await approve(giang, pending)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    final = await quote(giang, case["case_id"])
    assert final["approval"]["approved_by"] == str(user_id(GIANG))
    assert final["approval"]["document_sha256"] == pending["submission"]["document_sha256"]
    sent = await quote_step(dieu, final, "sent")
    recorded = await quote_step(dieu, sent, "master-list")
    assert recorded["status"] == "master_list_recorded"


async def test_dieu_cannot_approve_her_own_quote_whatever_approver_boost_gives(
    api: Api,
) -> None:
    dieu = api.as_(DIEU)
    pending = await submitted(dieu, await replied(dieu, "M10", "YCBG-2609-030", "M25"))

    refused = await approve(dieu, pending)

    # 403, not 409: she lacks sales.quote.approve, the scope the approval was
    # raised under, and the platform's approvals.decide she holds
    # (approver_boost) decides nothing here.
    assert refused.status_code == 403
    assert refused.json()["details"]["action"] == "sales.quote.approve"
    after = await quote(dieu, pending["case_id"])
    assert after["status"] == "pending_approval"
    assert after["decision"] == pending["decision"]


async def test_giang_cannot_approve_a_quote_he_priced_and_khoa_can(api: Api) -> None:
    dieu, giang, khoa = api.as_(DIEU), api.as_(GIANG), api.as_(KHOA)
    case = await replied(dieu, "M09", "YCBG-2609-028", "M18")
    pending = await submitted(giang, case, price="1.2500", quote_no="Q26-0302")

    own = await approve(giang, pending)
    assert own.status_code == 409
    assert "tách nhiệm" in own.json()["message"]
    assert own.json()["details"]["rule"] == "maker_checker"

    deputy = await approve(khoa, pending)
    assert deputy.status_code == 200, deputy.text
    assert (await quote(khoa, case["case_id"]))["approval"]["approved_by"] == str(user_id(KHOA))


async def test_a_quotation_priced_again_withdraws_its_approval(api: Api) -> None:
    dieu, giang = api.as_(DIEU), api.as_(GIANG)
    pending = await submitted(dieu, await replied(dieu, "M10", "YCBG-2609-030", "M25"))
    first = await approval_of(giang, pending)

    # A change to the price after submitting withdraws the document the
    # approver was asked about, and the approval with it.
    again = await submitted(dieu, pending, price="0.7000", quote_no="Q26-0301")
    second = await approval_of(giang, again)
    assert second != first

    stale = await giang.decide(
        first, {"approve": True, "comment": "ok", "subject_version": again["case_version"]}
    )
    assert stale.status_code == 409
    listed = await giang.platform("/approvals")
    assert [a["id"] for a in listed.json()["items"]] == [second]
    assert (await giang.platform(f"/approvals/{first}")).json()["status"] == "cancelled"


async def test_a_decision_on_a_version_the_approver_was_not_shown_is_refused(api: Api) -> None:
    dieu, giang = api.as_(DIEU), api.as_(GIANG)
    pending = await submitted(dieu, await replied(dieu, "M10", "YCBG-2609-030", "M25"))
    approval_id = await approval_of(giang, pending)

    stale = await giang.decide(
        approval_id,
        {"approve": True, "comment": "ok", "subject_version": pending["case_version"] - 1},
    )
    unnamed = await giang.decide(approval_id, {"approve": True, "comment": "ok"})

    assert stale.status_code == 409
    assert unnamed.status_code == 422
    # Refused before it was recorded: the approval is still Giang's to decide.
    assert (await giang.platform(f"/approvals/{approval_id}")).json()["status"] == "pending"


async def test_the_approver_returns_the_price_to_the_pricer(api: Api) -> None:
    dieu, giang = api.as_(DIEU), api.as_(GIANG)
    pending = await submitted(dieu, await replied(dieu, "M10", "YCBG-2609-030", "M25"))

    returned = await giang.decide(
        await approval_of(giang, pending),
        {"approve": False, "comment": "Giá cao", "subject_version": pending["case_version"]},
    )

    assert returned.status_code == 200, returned.text
    case = await quote(dieu, pending["case_id"])
    assert case["status"] == "returned"
    assert case["returns"][0]["returned_by"] == str(user_id(GIANG))
    assert case["returns"][0]["reason"] == "Giá cao"
    assert case["decision"] is None


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
