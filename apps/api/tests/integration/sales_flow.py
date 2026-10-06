"""Steps the Sales API tests take more than once: processing a message, opening
the sources a decision needs, walking an order or a quote to a state."""

from __future__ import annotations

from typing import Any

import httpx
from sales_api_harness import DECIDED_PRICE, Persona


async def process(persona: Persona, message_id: str) -> dict[str, Any]:
    response = await persona.post(f"/inbox/{message_id}/process")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def order_of(persona: Persona, message_id: str) -> dict[str, Any]:
    """The order case a processed message opened or joined."""
    disposition = await process(persona, message_id)
    assert disposition["case_kind"] == "order", disposition
    return await order(persona, disposition["case_id"])


async def order(persona: Persona, case_id: str) -> dict[str, Any]:
    response = await persona.get(f"/orders/{case_id}")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def quote(persona: Persona, case_id: str) -> dict[str, Any]:
    response = await persona.get(f"/quotes/{case_id}")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _anchors(case: dict[str, Any]) -> list[dict[str, Any]]:
    found = list(case["header_anchors"].values())
    for line in case["lines"]:
        found += list(line["anchors"].values())
    found += [a for a in (case.get("total_anchor"), case.get("buyer_anchor")) if a]
    return found


async def open_sources(persona: Persona, case: dict[str, Any]) -> None:
    """Every page or sheet the order's values were read from, served to
    ``persona`` at the case's current version."""
    seen: set[tuple[str, str, Any]] = set()
    for anchor in _anchors(case):
        if anchor.get("page"):
            region = ("page", anchor["attachment_id"], anchor["page"])
        elif anchor.get("cell_ref"):
            region = ("sheet", anchor["attachment_id"], anchor["cell_ref"].rsplit("!", 1)[0])
        else:
            continue
        if region in seen:
            continue
        seen.add(region)
        kind, attachment, where = region
        response = await persona.get(
            f"/orders/{case['case_id']}/source/{attachment}", **{kind: where}
        )
        assert response.status_code == 200, response.text


async def decide(
    persona: Persona, case: dict[str, Any], step: str, body: dict[str, Any] | None = None
) -> dict[str, Any]:
    """POST a decision on the order at its current version; the fresh case."""
    response = await persona.post(
        f"/orders/{case['case_id']}/{step}", {"case_version": case["case_version"], **(body or {})}
    )
    assert response.status_code == 200, response.text
    return await order(persona, case["case_id"])


async def prepared(pic: Persona, case: dict[str, Any]) -> dict[str, Any]:
    await open_sources(pic, case)
    return await decide(pic, case, "prepare")


async def uploaded(
    pic: Persona, case: dict[str, Any], recorder: Persona | None = None
) -> dict[str, Any]:
    ready = await prepared(pic, case)
    return await decide(
        recorder or pic, ready, "bravo-entry", {"so_no": "SO26-1001", "entry_compared": True}
    )


def dates(case: dict[str, Any], day: str = "2026-11-27") -> list[dict[str, Any]]:
    return [{"line_no": line["line_no"], "confirmed_date": day} for line in case["lines"]]


async def approval_of(persona: Persona, case: dict[str, Any]) -> str:
    """The platform approval the case's DW1 run waits on, as the page finds it."""
    kind = "orders" if "po_no" in case else "quotes"
    response = await persona.get(f"/{kind}/{case['case_id']}")
    assert response.status_code == 200, response.text
    decision = response.json()["decision"]
    assert decision is not None, "the case waits on no decision"
    approval_id: str = decision["approval_id"]
    return approval_id


async def cross_check(
    checker: Persona,
    case: dict[str, Any],
    *,
    approve: bool = True,
    comment: str = "Đã đối chiếu với Bravo",
    via: Persona | None = None,
) -> httpx.Response:
    """The checker's decision on the order's cross-check approval, on the
    version they were shown. ``via`` finds the approval when the checker
    could not read the case."""
    approval_id = await approval_of(via or checker, case)
    return await checker.decide(
        approval_id,
        {"approve": approve, "comment": comment, "subject_version": case["case_version"]},
    )


async def cross_checked(checker: Persona, case: dict[str, Any]) -> dict[str, Any]:
    await open_sources(checker, case)
    response = await cross_check(checker, case)
    assert response.status_code == 200, response.text
    return await order(checker, case["case_id"])


# ------------------------------------------------------------------ quotes --

_BAND = {"kind": "lme_band", "low_usd_per_tonne": "10500", "high_usd_per_tonne": "11000"}


async def quote_step(
    persona: Persona, case: dict[str, Any], step: str, **body: Any
) -> dict[str, Any]:
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
    case = await quote_step(pic, case, "ycbg")
    case = await quote_step(pic, case, "ycbg", ycbg_no=ycbg_no)
    case = await quote_step(pic, case, "design-sent")
    attached = await process(pic, reply)
    assert (attached["kind"], attached["case_id"]) == ("attached_to_case", case["case_id"])
    return await quote(pic, case["case_id"])


async def submitted(
    pricer: Persona, case: dict[str, Any], price: str = DECIDED_PRICE, quote_no: str = "Q26-0301"
) -> dict[str, Any]:
    priced = await quote_step(
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
    return await quote_step(pricer, priced, "submit", quote_no=quote_no)


async def approve(
    approver: Persona,
    case: dict[str, Any],
    *,
    via: Persona | None = None,
    reasons: dict[str, str] | None = None,
    comment: str = "Đã xem tài liệu báo giá",
) -> httpx.Response:
    """The approver's decision on the quote's approval, on the version shown.
    ``via`` finds the approval for an approver who cannot read the case."""
    approval_id = await approval_of(via or approver, case)
    return await approver.decide(
        approval_id,
        {
            "approve": True,
            "comment": comment,
            "reasons": reasons or {},
            "subject_version": case["case_version"],
        },
    )
