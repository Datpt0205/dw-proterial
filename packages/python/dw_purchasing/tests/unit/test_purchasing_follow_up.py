"""DW02 function 5 over the in-memory world: Bravo's number, the supplier's
confirmation read and held to the order, what arrived, and what is late."""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from dw_kernel.errors import (
    ConflictError,
    InfrastructureError,
    NotFoundError,
    PermissionDeniedError,
)
from dw_purchasing.application.access import PurchasingScopes
from dw_purchasing.application.follow_up import ORDER_CONFIRMATION_READING
from dw_purchasing.testing.flows import orders_drafted, sourcing_world
from dw_purchasing.testing.world import ALPHA, BETA, EVERY_SCOPE, World, caller

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
FOLLOW_UP = json.loads(
    (REPO / "evals/fixtures/cases/purchasing_follow_up.json").read_text(encoding="utf-8")
)
# P01's orders, by supplier: Kimura line 1, Bảo Hộ line 2, An Phát line 3.
KIMURA, BAOHO, ANPHAT = "PR-2611-004-03", "PR-2611-004-02", "PR-2611-004-01"


async def _drafted(answers: dict[str, object] | None = None) -> tuple[World, uuid.UUID]:
    world = sourcing_world(REPO)
    world.model.by_schema["ModelConfirmation"] = answers or FOLLOW_UP["answers"]
    return world, await orders_drafted(world)


async def _version(world: World, case_id: uuid.UUID) -> int:
    return (await world.service.case(caller(), case_id)).case_version


async def _numbered(world: World, case_id: uuid.UUID) -> None:
    for po_ref, number in ((KIMURA, "PO-26110007"), (BAOHO, "PO-26110008")):
        await world.follow_up.record_bravo_no(
            caller(), case_id, po_ref, number, case_version=await _version(world, case_id)
        )


async def _read(world: World, case_id: uuid.UUID, message_id: str) -> None:
    await world.follow_up.read_confirmation(
        caller(), case_id, message_id, case_version=await _version(world, case_id)
    )


def _tracked(case: object, po_ref: str):  # type: ignore[no-untyped-def]
    return next(t for t in case.tracking if t.po_ref == po_ref)  # type: ignore[attr-defined]


async def test_bravo_s_number_is_typed_once_stamped_and_audited() -> None:
    world, case_id = await _drafted()
    await _numbered(world, case_id)
    case = await world.service.case(caller(), case_id)
    kimura = _tracked(case, KIMURA)
    assert (kimura.bravo_no, kimura.bravo_by) == ("PO-26110007", caller().principal_id)
    audit = [
        e for e in world.store.rows(*ALPHA).audit if e.action == "purchasing.po.bravo_numbered"
    ]
    assert [e.details["po_ref"] for e in audit] == [KIMURA, BAOHO]
    with pytest.raises(ConflictError) as again:
        await world.follow_up.record_bravo_no(
            caller(), case_id, KIMURA, "PO-1", case_version=case.case_version
        )
    assert again.value.details["rule"] == "bravo_no_set"
    with pytest.raises(NotFoundError):
        await world.follow_up.record_bravo_no(
            caller(), case_id, "PR-0000-001-01", "PO-2", case_version=case.case_version
        )


async def test_a_confirmation_matching_its_order_is_read_with_no_difference() -> None:
    world, case_id = await _drafted()
    await _numbered(world, case_id)
    await _read(world, case_id, "C01")
    confirmation = _tracked(await world.service.case(caller(), case_id), KIMURA).confirmation
    assert confirmation is not None and confirmation.differences == ()
    assert confirmation.source_ref == "C01" and confirmation.accepted_by is None
    (call,) = [c for c in world.model.calls if c[0] == ORDER_CONFIRMATION_READING]
    assert "PO-26110007" in call[1]["mail"]


async def test_a_confirmation_that_differs_says_where_and_waits_for_the_buyer() -> None:
    world, case_id = await _drafted()
    await _numbered(world, case_id)
    await _read(world, case_id, "C02")
    confirmation = _tracked(await world.service.case(caller(), case_id), BAOHO).confirmation
    assert confirmation is not None
    assert [(d.field, d.ordered, d.confirmed) for d in confirmation.differences] == [
        ("quantity", "50", "40"),
        ("delivery_on", "2026-11-20", "2026-11-22"),
    ]
    # The lane accepts only a confirmation that differs in nothing.
    with pytest.raises(ConflictError) as differs:
        await world.follow_up.accept_confirmation(
            caller(), case_id, BAOHO, case_version=await _version(world, case_id), only_if_same=True
        )
    assert differs.value.details["rule"] == "differs"
    await world.follow_up.accept_confirmation(
        caller(), case_id, BAOHO, case_version=await _version(world, case_id)
    )
    accepted = _tracked(await world.service.case(caller(), case_id), BAOHO).confirmation
    assert accepted is not None and accepted.accepted_by == caller().principal_id


async def test_a_mail_that_names_no_order_of_its_supplier_is_not_read() -> None:
    world, case_id = await _drafted()
    # No Bravo number recorded yet: C01 names nothing the case holds.
    with pytest.raises(ConflictError) as unnamed:
        await _read(world, case_id, "C01")
    assert unnamed.value.details["rule"] == "order_not_named"
    # A quote is no confirmation of an order.
    await _numbered(world, case_id)
    with pytest.raises(ConflictError):
        await _read(world, case_id, "Q01")
    assert not [c for c in world.model.calls if c[0] == ORDER_CONFIRMATION_READING]


async def test_an_unverified_mail_in_a_supplier_s_name_is_not_read() -> None:
    world, case_id = await _drafted()
    await _numbered(world, case_id)
    message = await world.service.inbox.get_message(caller(), "C01")
    assert message is not None
    forged = message.model_copy(
        update={
            "message_id": "C99",
            "authentication": message.authentication.model_copy(
                update={"spf": "fail", "dkim": "fail", "dmarc": "fail"}
            ),
        }
    )
    world.service.inbox._messages.append(forged)  # type: ignore[attr-defined]
    listed = await world.follow_up.confirmation_mails(caller(), case_id)
    assert "C99" not in [m.message_id for m in listed]
    with pytest.raises(ConflictError) as refused:
        await _read(world, case_id, "C99")
    assert refused.value.details["rule"] == "sender_unverified"


async def test_a_confirmation_is_read_once_and_a_model_s_invention_is_refused() -> None:
    world, case_id = await _drafted()
    await _numbered(world, case_id)
    await _read(world, case_id, "C01")
    with pytest.raises(ConflictError) as again:
        await _read(world, case_id, "C01")
    assert again.value.details["rule"] == "read"
    invented, invented_case = await _drafted(FOLLOW_UP["variants"]["invented_price"])
    await _numbered(invented, invented_case)
    with pytest.raises(ConflictError) as refused:
        await _read(invented, invented_case, "C01")
    assert refused.value.details["rule"] == "line_unreadable"
    assert (
        _tracked(await invented.service.case(caller(), invented_case), KIMURA).confirmation is None
    )


async def test_no_model_reads_nothing_and_records_nothing() -> None:
    world, case_id = await _drafted()
    await _numbered(world, case_id)
    world.follow_up = world.follow_up.__class__(**{**world.follow_up.__dict__, "model": None})
    version = await _version(world, case_id)
    with pytest.raises(InfrastructureError):
        await _read(world, case_id, "C01")
    assert await _version(world, case_id) == version


async def test_what_arrived_is_recorded_never_past_what_is_owed() -> None:
    world, case_id = await _drafted()
    receive = world.follow_up.record_receipt
    await receive(
        caller(),
        case_id,
        BAOHO,
        line_no=2,
        quantity=Decimal(40),
        received_on=date(2026, 11, 22),
        case_version=await _version(world, case_id),
    )
    with pytest.raises(ConflictError) as over:
        await receive(
            caller(),
            case_id,
            BAOHO,
            line_no=2,
            quantity=Decimal(11),
            received_on=date(2026, 11, 23),
            case_version=await _version(world, case_id),
        )
    assert over.value.details["rule"] == "over_receipt"
    with pytest.raises(NotFoundError):
        await receive(
            caller(),
            case_id,
            BAOHO,
            line_no=1,
            quantity=Decimal(1),
            received_on=date(2026, 11, 23),
            case_version=await _version(world, case_id),
        )


async def test_late_lists_each_line_past_its_date_with_what_is_owed() -> None:
    world, case_id = await _drafted()
    await _numbered(world, case_id)
    await _read(world, case_id, "C02")  # Bảo Hộ: 22/11 for line 2
    await world.follow_up.record_receipt(
        caller(),
        case_id,
        BAOHO,
        line_no=2,
        quantity=Decimal(40),
        received_on=date(2026, 11, 22),
        case_version=await _version(world, case_id),
    )
    late = await world.follow_up.late(caller(), today=date(2026, 11, 23))
    # Every line needed by 20/11; line 2's date is the supplier's 22/11 and
    # 10 pairs are still owed; line 3 had no date and is never late.
    assert [(x.po_ref, x.line_no, x.due_on, x.owed) for x in late] == [
        (KIMURA, 1, date(2026, 11, 20), Decimal(4)),
        (BAOHO, 2, date(2026, 11, 22), Decimal(10)),
    ]
    assert await world.follow_up.late(caller(), today=date(2026, 11, 20)) == []


async def test_following_an_order_is_the_buyer_s_and_the_tenant_s_own() -> None:
    world, case_id = await _drafted()
    version = await _version(world, case_id)
    viewer = caller(scopes=EVERY_SCOPE - {PurchasingScopes.PO_PREPARE.value})
    with pytest.raises(PermissionDeniedError):
        await world.follow_up.record_bravo_no(viewer, case_id, KIMURA, "PO-1", case_version=version)
    with pytest.raises(PermissionDeniedError):
        await world.follow_up.late(viewer, today=date(2026, 11, 30))
    # Another tenant, every scope held: no such case, and nothing late.
    with pytest.raises(NotFoundError):
        await world.follow_up.record_bravo_no(
            caller(BETA), case_id, KIMURA, "PO-1", case_version=version
        )
    assert await world.follow_up.late(caller(BETA), today=date(2026, 11, 30)) == []
    assert await _version(world, case_id) == version


async def test_the_mails_that_confirm_an_order_are_listed_by_code_until_read() -> None:
    world, case_id = await _drafted()
    # Before Bravo's numbers: no mail names an order of the case.
    assert await world.follow_up.confirmation_mails(caller(), case_id) == []
    await _numbered(world, case_id)
    listed = await world.follow_up.confirmation_mails(caller(), case_id)
    assert [(m.message_id, m.po_ref) for m in listed] == [("C02", BAOHO), ("C01", KIMURA)]
    await _read(world, case_id, "C01")
    listed = await world.follow_up.confirmation_mails(caller(), case_id)
    assert [m.message_id for m in listed] == ["C02"]
    with pytest.raises(NotFoundError):
        await world.follow_up.confirmation_mails(caller(BETA), case_id)


async def test_a_supplier_cannot_confirm_another_supplier_s_order() -> None:
    """Bảo Hộ's verified mail naming Kimura's order is about no order of
    Bảo Hộ's: not listed, not read, and no model asked."""
    world, case_id = await _drafted()
    await _numbered(world, case_id)
    message = await world.service.inbox.get_message(caller(), "C02")
    assert message is not None
    other = message.model_copy(
        update={
            "message_id": "C98",
            "subject": "Xác nhận đơn PO-26110007",
            "body_text": "Xác nhận đơn PO-26110007: DC-200, 4 cái",
        }
    )
    world.service.inbox._messages.append(other)  # type: ignore[attr-defined]
    listed = await world.follow_up.confirmation_mails(caller(), case_id)
    assert "C98" not in [m.message_id for m in listed]
    with pytest.raises(ConflictError) as refused:
        await _read(world, case_id, "C98")
    assert refused.value.details["rule"] == "order_not_named"
    assert not [c for c in world.model.calls if c[0] == ORDER_CONFIRMATION_READING]
