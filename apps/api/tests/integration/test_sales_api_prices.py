"""Prices reach only those allowed to see them (spec decision 8, G2).

After M04 is decided and M10 approved, leadership, tenant IT and a member
without Sales scopes call every Sales route and the platform's audit log, and
no known price string is in anything they get back. The same walk as An,
who may see prices, does find them: the search can fail.
"""

from __future__ import annotations

import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

import pytest
from sales_api_harness import AN, BINH, DIEU, GIANG, HA, TAM, Api, Persona, known_price_strings
from sales_flow import approve, decide, open_sources, order_of, replied, submitted

pytestmark = pytest.mark.integration

PRICES = known_price_strings()
_PRICE_VALUES = {Decimal(p) for p in PRICES}
_PATTERNS = [re.compile(rf"(?<![\d.]){re.escape(p)}(?![\d])") for p in sorted(PRICES)]


def _is_uuid(text: str) -> bool:
    try:
        uuid.UUID(text)
    except ValueError:
        return False
    return True


def leaks(body: Any) -> list[str]:
    """Every known price in a JSON body, matched as a value, never inside an id."""
    found: list[str] = []
    if isinstance(body, dict):
        for value in body.values():
            found += leaks(value)
    elif isinstance(body, list):
        for value in body:
            found += leaks(value)
    elif isinstance(body, bool) or body is None:
        return found
    elif isinstance(body, (int, float)):
        try:
            if Decimal(str(body)) in _PRICE_VALUES:
                found.append(str(body))
        except InvalidOperation:
            pass
    elif isinstance(body, str) and not _is_uuid(body):
        found += [p.pattern for p in _PATTERNS if p.search(body)]
    return found


async def _decided_world(api: Api) -> dict[str, Any]:
    """M04 decided by An, M10 approved by Giang: every price path exercised."""
    an, dieu, giang = api.as_(AN), api.as_(DIEU), api.as_(GIANG)
    m04 = await order_of(an, "M04")
    m04 = await decide(
        an,
        m04,
        "findings/price_mismatch:2/disposition",
        {"disposition": "accepted", "reason": "Khách xác nhận giá"},
    )
    m04 = await decide(an, m04, "lines/3/mapping", {"prv_code": "CB-2007"})
    # Checked again against CB-2007's quotation, the line's price differs too.
    m04 = await decide(
        an,
        m04,
        "findings/price_mismatch:3/disposition",
        {"disposition": "accepted", "reason": "Khách xác nhận giá"},
    )
    await open_sources(an, m04)
    m04 = await decide(an, m04, "prepare")
    m10 = await submitted(dieu, await replied(dieu, "M10", "YCBG-2609-030", "M25"))
    assert (await approve(giang, m10)).status_code == 200
    return {"m04": m04, "m10": m10}


async def _everything(persona: Persona, world: dict[str, Any]) -> list[Any]:
    m04, m10 = world["m04"], world["m10"]
    paths = [
        "/overview",
        "/my-work",
        "/inbox",
        "/orders",
        f"/orders/{m04['case_id']}",
        "/quotes",
        f"/quotes/{m10['case_id']}",
        "/quotes/screening",
        "/master-data/customers",
        "/master-data/items",
        "/master-data/convert-list",
        "/master-data/quotations",
        "/master-data/lme",
        "/master-data/bravo-orders",
        "/master-data/open-ycbg",
    ]
    bodies = [(await persona.get(path)).json() for path in paths]
    sheet = m04["header_anchors"]["po_no"]["cell_ref"].rsplit("!", 1)[0]
    bodies.append(
        (
            await persona.get(
                f"/orders/{m04['case_id']}/source/{m04['attachment_id']}", sheet=sheet
            )
        ).json()
    )
    bodies.append((await persona.platform("/audit/events?limit=200")).json())
    return bodies


@pytest.mark.parametrize("subject", [HA, TAM, BINH])
async def test_no_price_reaches_a_persona_without_the_price_scope(api: Api, subject: str) -> None:
    world = await _decided_world(api)

    bodies = await _everything(api.as_(subject), world)

    assert [found for body in bodies if (found := leaks(body))] == []


async def test_the_same_walk_finds_prices_for_a_pic_who_may_see_them(api: Api) -> None:
    world = await _decided_world(api)

    bodies = await _everything(api.as_(AN), world)

    assert any(leaks(body) for body in bodies), "the search could not have found a leak"


async def test_a_hidden_amount_is_marked_hidden_never_zero_or_absent(api: Api) -> None:
    world = await _decided_world(api)
    an_view = (await api.as_(AN).get(f"/quotes/{world['m10']['case_id']}")).json()

    # An has sales.price.read without other customers': amounts of his own,
    # the others' rows marked hidden.
    (evidence,) = an_view["evidence"]
    assert evidence["other_customers"] == {"hidden": True}
    assert an_view["pricing"]["lines"][0]["unit_price"] == "0.6890"
    ha_view = (await api.as_(HA).get("/overview")).json()
    assert leaks(ha_view) == []


def _hidden(body: Any) -> int:
    if body == {"hidden": True}:
        return 1
    if isinstance(body, dict):
        return sum(_hidden(v) for v in body.values())
    if isinstance(body, list):
        return sum(_hidden(v) for v in body)
    return 0


async def test_a_viewer_of_a_case_without_price_read_gets_each_amount_as_hidden(api: Api) -> None:
    """No persona holds case reading without prices today; the mapper's rule
    is unit-tested (`test_views.py`). Here the API's own shape: An's quote
    view marks the other customers' rows hidden, not empty and not zero."""
    world = await _decided_world(api)
    an_view = (await api.as_(AN).get(f"/quotes/{world['m10']['case_id']}")).json()

    assert _hidden(an_view) >= 2  # other customers' rows and the reference price
