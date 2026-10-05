"""The source route (ADR 0009, spec decision 12): the original, a page or a
sheet at a time, with the anchors drawn on it, recorded as served."""

from __future__ import annotations

import base64

import pytest
from sales_api_harness import AN, DIEU, HA, Api
from sales_flow import order_of, process, quote

pytestmark = pytest.mark.integration


async def test_a_pdf_order_is_served_one_page_with_its_anchor_boxes(api: Api) -> None:
    an = api.as_(AN)
    case = await order_of(an, "M03")

    response = await an.get(f"/orders/{case['case_id']}/source/{case['attachment_id']}", page=1)

    assert response.status_code == 200, response.text
    view = response.json()
    assert (view["kind"], view["page"], view["case_version"]) == ("pdf", 1, case["case_version"])
    assert base64.b64decode(view["pdf_base64"]).startswith(b"%PDF")
    assert view["anchors"] and all(a["anchor"]["page"] == 1 for a in view["anchors"])
    assert all(a["anchor"]["boxes"] for a in view["anchors"])


async def test_a_sheet_is_served_as_its_grid_with_the_hidden_flags(api: Api) -> None:
    an = api.as_(AN)
    case = await order_of(an, "M27")
    flagged = next(line for line in case["lines"] if line["line_no"] == 2)
    sheet = flagged["anchors"]["quantity"]["cell_ref"].rsplit("!", 1)[0]

    view = (
        await an.get(f"/orders/{case['case_id']}/source/{case['attachment_id']}", sheet=sheet)
    ).json()

    assert view["kind"] == "sheet" and sheet in view["sheets"]
    hidden_rows = {cell["row"] for cell in view["grid"]["cells"] if cell["hidden_row"]}
    assert hidden_rows, "the hidden row is shown flagged, not left out"


async def test_a_flagged_value_holds_prepare_until_its_sheet_is_served(api: Api) -> None:
    an = api.as_(AN)
    case = await order_of(an, "M27")
    # Every finding typed, so only the source gate is left.
    for finding in case["findings"]:
        response = await an.post(
            f"/orders/{case['case_id']}/findings/{finding['key']}/disposition",
            {
                "case_version": case["case_version"],
                "disposition": "corrected_by_sales",
                "value": "1000",
                "source": "Đối chiếu bản in",
            },
        )
        assert response.status_code == 200, response.text
        case = (await an.get(f"/orders/{case['case_id']}")).json()
    po_sheet = case["header_anchors"]["po_no"]["cell_ref"].rsplit("!", 1)[0]
    await an.get(f"/orders/{case['case_id']}/source/{case['attachment_id']}", sheet=po_sheet)

    refused = await an.post(
        f"/orders/{case['case_id']}/prepare", {"case_version": case["case_version"]}
    )

    assert refused.status_code == 409
    assert "chưa mở nguồn" in refused.json()["message"]


async def test_a_quote_request_is_served_as_its_sheet(api: Api) -> None:
    dieu = api.as_(DIEU)
    case = await quote(dieu, (await process(dieu, "M10"))["case_id"])
    sheet = next(iter(case["lines"][0]["anchors"].values()))["cell_ref"].rsplit("!", 1)[0]

    response = await dieu.get(
        f"/quotes/{case['case_id']}/source/{case['attachment_id']}", sheet=sheet
    )

    assert response.status_code == 200, response.text
    assert {a["field"] for a in response.json()["anchors"]} >= {"quantity", "target_price"}


async def test_the_source_needs_a_page_or_a_sheet_and_an_attachment_of_the_case(
    api: Api,
) -> None:
    an = api.as_(AN)
    case = await order_of(an, "M01")
    base = f"/orders/{case['case_id']}/source"

    assert (await an.get(f"{base}/{case['attachment_id']}")).status_code == 422
    assert (await an.get(f"{base}/{case['attachment_id']}", page=1, sheet="PO")).status_code == 422
    assert (await an.get(f"{base}/M02-A1", sheet="PO")).status_code == 404
    assert (await api.as_(HA).get(f"{base}/{case['attachment_id']}", sheet="PO")).status_code == 403


async def test_a_replayed_key_never_answers_a_caller_without_the_scope(api: Api) -> None:
    an, ha = api.as_(AN), api.as_(HA)
    case = await order_of(an, "M01")
    po_sheet = case["header_anchors"]["po_no"]["cell_ref"].rsplit("!", 1)[0]
    await an.get(f"/orders/{case['case_id']}/source/{case['attachment_id']}", sheet=po_sheet)
    body = {"case_version": case["case_version"]}
    assert (await an.post(f"/orders/{case['case_id']}/prepare", body, key="k-1")).status_code == 200

    replay = await ha.post(f"/orders/{case['case_id']}/prepare", body, key="k-1")

    # The scope is checked before the key is claimed: no stored answer
    # reaches someone who may not make the request.
    assert replay.status_code == 403
