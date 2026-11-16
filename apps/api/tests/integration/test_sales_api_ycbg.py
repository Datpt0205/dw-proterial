"""Ticket 16 through the API: the YCBG number in Bravo's shape, and Bravo's
YCBG export uploaded for Design's results.

The route refuses another shape before the case sees it (422, the field named,
the value not echoed); the upload is the quote preparer's, refused at the
route for a viewer and for a person outside Sales, and another tenant lists
none of this tenant's exports.
"""

from __future__ import annotations

import base64

import pytest
from sales_api_harness import BAO, BETA, BINH, DIEU, HA, Api
from sales_flow import process, quote, quote_step

from dw_sales.testing.bravo_ycbg_export import ExportRow, ycbg_export_xlsx

pytestmark = pytest.mark.integration

_EXPORT = base64.b64encode(
    ycbg_export_xlsx([ExportRow("RFQ260930-030", None, "PENDING", description="a")])
).decode("ascii")


async def test_a_number_bravo_cannot_have_given_is_refused_and_bravos_is_recorded(
    api: Api,
) -> None:
    dieu = api.as_(DIEU)
    opened = await process(dieu, "M10")
    case = await quote(dieu, opened["case_id"])

    refused = await dieu.post(
        f"/quotes/{case['case_id']}/ycbg",
        {"case_version": case["case_version"], "ycbg_no": "RFQ2611-2"},
    )

    assert refused.status_code == 422, refused.text
    assert "RFQ2611-2" not in refused.text
    assert (await quote(dieu, case["case_id"]))["ycbg_no"] is None
    recorded = await quote_step(dieu, case, "ycbg", ycbg_no="RFQ261110-002")
    assert recorded["ycbg_no"] == "RFQ261110-002"


async def test_the_export_is_the_quote_preparers_and_this_tenants(api: Api) -> None:
    body = {"screen": "ycbg", "file_name": "ycbg.xlsx", "content_b64": _EXPORT}

    queued = await api.as_(DIEU).post("/bravo-exports", body)
    assert queued.status_code == 202, queued.text
    assert queued.json()["status"] == "queued"

    for persona in (api.as_(HA), api.as_(BINH)):
        assert (await persona.post("/bravo-exports", body)).status_code == 403
        assert (await persona.get("/bravo-exports?screen=ycbg")).status_code == 403

    listed = await api.as_(DIEU).get("/bravo-exports?screen=ycbg")
    assert [e["export_id"] for e in listed.json()] == [queued.json()["export_id"]]
    other = await api.as_(BAO, BETA).get("/bravo-exports?screen=ycbg")
    assert other.status_code == 200 and other.json() == []
