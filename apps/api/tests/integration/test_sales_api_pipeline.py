"""The pipeline board and a case's history: every case by status, each
person's own next step on it, and who may read either."""

from __future__ import annotations

from typing import Any

import pytest
from sales_api_harness import AN, BAO, BETA, BINH, DIEU, GIANG, HA, KHOA, Api, user_id
from sales_flow import order_of, replied, submitted, uploaded

pytestmark = pytest.mark.integration


def _card(board: dict[str, Any], case_id: str) -> dict[str, Any]:
    (card,) = [c for c in board["cards"] if c["case_id"] == case_id]
    return card


def _column(board: dict[str, Any], kind: str, status: str) -> dict[str, Any]:
    (column,) = [c for c in board["columns"] if c["kind"] == kind and c["status"] == status]
    return column


async def test_the_board_lays_out_cases_by_status_with_each_persons_step(api: Api) -> None:
    an, dieu, giang, khoa = api.as_(AN), api.as_(DIEU), api.as_(GIANG), api.as_(KHOA)
    up = await uploaded(an, await order_of(an, "M01"))
    pending = await submitted(dieu, await replied(dieu, "M10", "YCBG-2609-030", "M25"))

    boards = {}
    for name, persona in {"an": an, "dieu": dieu, "giang": giang, "khoa": khoa}.items():
        response = await persona.get("/pipeline")
        assert response.status_code == 200, response.text
        boards[name] = response.json()

    # One column per status of each kind, in the order a case moves, each
    # with whose turn it is and the surveyed steps it stands for.
    order_columns = [c["status"] for c in boards["an"]["columns"] if c["kind"] == "order"]
    assert order_columns[:3] == ["received", "checked", "in_review"]
    assert len(order_columns) == 10
    review = _column(boards["an"], "order", "in_review")
    assert review["holder"] == "sales"
    assert review["steps"] == ["O6"]
    assert _column(boards["an"], "quote", "pending_approval")["holder"] == "approver"
    assert _column(boards["an"], "order", "confirmed")["holder"] is None

    order = _card(boards["an"], up["case_id"])
    assert order["status"] == "uploaded_to_bravo"
    assert order["reference"] == up["po_no"]
    assert order["assigned_to"] == str(user_id(AN))
    assert order["awaits_cross_check"] is True
    assert order["status_since"] >= order["received_at"]
    assert _column(boards["an"], "order", "uploaded_to_bravo")["cases"] >= 1

    # The same case, a different next step per person (the work list's rule):
    # the cross-check is for a PIC who made none of it, never its maker.
    assert order["my_action"] is None
    assert _card(boards["dieu"], up["case_id"])["my_action"] == "cross_check"
    # The approval is for an approver who did not price the quote.
    assert _card(boards["giang"], pending["case_id"])["my_action"] == "approve"
    assert _card(boards["khoa"], pending["case_id"])["my_action"] == "approve"
    assert _card(boards["dieu"], pending["case_id"])["my_action"] is None


async def test_a_cases_history_is_its_events_oldest_first(api: Api) -> None:
    an = api.as_(AN)
    up = await uploaded(an, await order_of(an, "M01"))

    response = await an.get(f"/orders/{up['case_id']}/history")

    assert response.status_code == 200, response.text
    history = response.json()
    assert [h["occurred_at"] for h in history] == sorted(h["occurred_at"] for h in history)
    assert history[-1]["to_status"] == "uploaded_to_bravo"
    # DW1 read the order; An prepared it and recorded the Bravo entry.
    assert history[0]["actor_kind"] == "worker"
    assert history[0]["worker_id"]
    assert history[0]["actor_user_id"] is None
    prepared = [h for h in history if h["action"] == "order.prepared"]
    assert prepared
    assert prepared[0]["actor_user_id"] == str(user_id(AN))


@pytest.mark.parametrize("persona", [HA, BINH])
async def test_who_may_not_read_cases_reads_neither(api: Api, persona: str) -> None:
    an = api.as_(AN)
    case = await order_of(an, "M01")
    other = api.as_(persona)

    assert (await other.get("/pipeline")).status_code == 403
    assert (await other.get(f"/orders/{case['case_id']}/history")).status_code == 403


async def test_another_tenant_sees_none_of_the_cases(api: Api) -> None:
    an, bao = api.as_(AN), api.as_(BAO, BETA)
    case = await order_of(an, "M01")

    board = (await bao.get("/pipeline")).json()
    assert case["case_id"] not in {c["case_id"] for c in board["cards"]}
    assert all(c["cases"] == 0 for c in board["columns"])
    # Not found, never an empty history: the case's existence is not leaked.
    assert (await bao.get(f"/orders/{case['case_id']}/history")).status_code == 404
    assert (await bao.get(f"/quotes/{case['case_id']}/history")).status_code == 404
