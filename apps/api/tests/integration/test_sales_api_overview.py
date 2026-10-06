"""The overview (counts and times only) and each persona's work list."""

from __future__ import annotations

from typing import Any

import pytest
from sales_api_harness import AN, DIEU, GIANG, HA, KHOA, Api, user_id
from sales_flow import order_of, replied, submitted, uploaded

pytestmark = pytest.mark.integration


def _step(overview: dict[str, Any], step_id: str) -> int:
    (row,) = [s for s in overview["steps"] if s["step_id"] == step_id]
    count: int = row["cases"]
    return count


async def test_the_overview_counts_the_mailbox_and_the_steps(api: Api) -> None:
    an, ha = api.as_(AN), api.as_(HA)
    before = (await ha.get("/overview")).json()
    assert before["messages"]["total"] == 32
    assert before["messages"]["without_disposition"] == 32
    assert before["messages"]["oldest_waiting_seconds"] > 0
    assert before["kpi_policy"] == "sales_kpi@1.0.0"
    assert before["quotation_time"]["target_seconds"] == 86400.0

    processed = await an.post("/inbox/process-all")
    assert processed.status_code == 200, processed.text
    after = (await ha.get("/overview")).json()

    assert after["messages"]["without_disposition"] == 0
    assert after["messages"]["routed_without_owner"] == 0
    assert after["messages"]["routed_to_sales"] >= 1
    # Every order case is handed to the PIC's self-check (O6), and every
    # surveyed step is listed, the ones DW1 does not do included.
    assert _step(after, "O6") >= 10
    assert len(after["steps"]) == 23
    assert after["lines_read"] <= after["lines_printed"]
    # M04's price mismatch was corrected by M07, its revision: M06's MOQ stands.
    assert after["findings_by_code"]["moq_violation"] >= 1
    assert after["times"]["dw"]["cases"] >= 10
    assert after["times"]["pc"] is None
    # An export row per surveyed step for the month processed, beside its baseline.
    months = {row["month"] for row in after["export"]}
    assert len(after["export"]) == 23 * len(months)
    o1 = [row for row in after["export"] if row["step_id"] == "O1"]
    assert sum(row["times"] for row in o1) >= 10
    assert all(row["manual_baseline_minutes"] == 5 for row in o1)


async def test_the_a3_shadow_counts_clean_originals_only(api: Api) -> None:
    an, ha = api.as_(AN), api.as_(HA)
    await order_of(an, "M01")  # clean: every line exact, no finding
    await order_of(an, "M04")  # findings

    overview = (await ha.get("/overview")).json()

    assert overview["a3_shadow"] == 1


async def test_my_work_routes_each_step_to_who_may_take_it(api: Api) -> None:
    an, dieu, giang, khoa = api.as_(AN), api.as_(DIEU), api.as_(GIANG), api.as_(KHOA)
    up = await uploaded(an, await order_of(an, "M01"))
    pending = await submitted(dieu, await replied(dieu, "M10", "YCBG-2609-030", "M25"))

    def ids(items: list[dict[str, Any]], action: str) -> set[str]:
        return {i["id"] for i in items if i["action"] == action}

    an_work = (await an.get("/my-work")).json()
    dieu_work = (await dieu.get("/my-work")).json()
    giang_work = (await giang.get("/my-work")).json()
    khoa_work = (await khoa.get("/my-work")).json()

    # The cross-check is for a PIC who made none of the order, not its maker.
    assert up["case_id"] in ids(dieu_work, "cross_check")
    assert up["case_id"] not in ids(an_work, "cross_check")
    # The approval is for an approver who did not price it.
    assert pending["case_id"] in ids(giang_work, "approve")
    assert pending["case_id"] in ids(khoa_work, "approve")
    assert pending["case_id"] not in ids(dieu_work, "approve")
    assert all(
        i["assigned_to"] in (None, str(user_id(AN)))
        for i in an_work
        if i["kind"] == "order" and i["action"] != "cross_check"
    )


async def test_the_viewer_has_no_work_list(api: Api) -> None:
    assert (await api.as_(HA).get("/my-work")).status_code == 403
