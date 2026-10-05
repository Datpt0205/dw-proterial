"""Steps the Sales API tests take more than once: processing a message, opening
the sources a decision needs, walking an order or a quote to a state."""

from __future__ import annotations

from typing import Any

from sales_api_harness import Persona


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
