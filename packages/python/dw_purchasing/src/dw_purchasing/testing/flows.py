"""A case taken through DW2's flow over the in-memory world, for what comes
after it: mock mail P01 read, approved, sourced from the three demo
suppliers' replies (Q01-Q03), one supplier chosen per line, orders drafted.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from dw_purchasing.domain.sourcing import Choice
from dw_purchasing.testing.world import ALPHA, World, caller, open_world

HEAD: Final = uuid.UUID(int=0x4EAD)
CHOICES: Final = (
    Choice(line_no=1, supplier_code="KIMURA"),
    Choice(line_no=2, supplier_code="BAOHO"),
    Choice(line_no=3, supplier_code="ANPHAT"),
)


def sourcing_world(repo: Path) -> World:
    """The world, its model answering the mock mail and the suppliers' replies."""
    fixtures = repo / "evals" / "fixtures" / "cases"
    intake = json.loads((fixtures / "purchasing_pr_intake.json").read_text(encoding="utf-8"))
    sourcing = json.loads((fixtures / "purchasing_sourcing.json").read_text(encoding="utf-8"))
    world = open_world(repo, intake["answers"])
    world.model.by_schema = {
        "ModelOffer": sourcing["answers"],
        "RfqWording": {"PR-2611-004": sourcing["rfq_words"]["good"]},
    }
    return world


async def _version(world: World, case_id: uuid.UUID) -> int:
    return (await world.service.case(caller(), case_id)).case_version


async def orders_drafted(world: World) -> uuid.UUID:
    """P01's case with its three orders drafted (`po_drafted`)."""
    item = await world.service.read_mail(caller(), "P01")
    case_id = item.case_id
    assert case_id is not None
    await world.approvals.submit(caller(), case_id, case_version=1)
    case = await world.service.case(caller(), case_id)
    assert case.approval is not None
    world.store.decide(
        case.approval.approval_id,
        tenant_id=ALPHA[0],
        workspace_id=ALPHA[1],
        approved=True,
        decided_by=HEAD,
        at=datetime(2026, 11, 2, 9, tzinfo=UTC),
    )
    await world.settlement.settle(case.approval.approval_id, caller(principal=HEAD))
    await world.sourcing.draft_rfq(caller(), case_id, case_version=3)
    for message_id in ("Q01", "Q02", "Q03"):
        await world.sourcing.read_offer_mail(
            caller(), case_id, message_id, case_version=await _version(world, case_id)
        )
    await world.sourcing.select(
        caller(), case_id, CHOICES, case_version=await _version(world, case_id)
    )
    await world.orders.draft(caller(), case_id, case_version=await _version(world, case_id))
    return case_id
