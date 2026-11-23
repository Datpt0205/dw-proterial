"""A PO for an item with no valid quotation opens a quote case (ticket 09),
through the services the API serves and the platform's approval flow.

Over the in-memory world (`dw_sales.evals.world`) with the fictional M03
order (BRN-PO-2609-031): line 2's only quotation expired, so the line raises
`quotation_missing`. "Mở báo giá" opens a quote case for line 2, linked to the
order; the order cannot be prepared while it is open; approving it checks
line 2 again with the approved terms, and the finding is gone.
"""

from __future__ import annotations

import copy
import json
import uuid
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from dw_kernel.errors import ConflictError, NotFoundError, PermissionDeniedError
from dw_platform.domain.messages import Attachment
from dw_sales.application.decisions import QuoteManagerSettlement
from dw_sales.application.po_body_reading import PO_BODY_EXTRACTION
from dw_sales.application.quotes_service import PricedLine
from dw_sales.domain.anchors import SourceAnchor
from dw_sales.domain.catalog import FixedCopper
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.order_quotes import quoted_for_po, request_from_order
from dw_sales.domain.orders import (
    Accepted,
    Actor,
    Capability,
    FindingCode,
    OrderCase,
    OrderStatus,
)
from dw_sales.domain.quotes import (
    DeclineReason,
    DesignReply,
    DesignReplyDocument,
    DesignReplyLine,
    QuoteCase,
    QuoteRequest,
    QuoteStatus,
    RequestReading,
    Sourced,
)
from dw_sales.evals.graders import AN, CALLERS, GIANG, KHOA, OUTSIDER, READER
from dw_sales.evals.recorded import ByPrompt, Recorded
from dw_sales.evals.world import ALPHA, BETA, Caller, SampleSet, SampleWith, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
MISSING = "quotation_missing:2"
# The price line 2 prints: the quote approved at it raises no price finding.
PO_PRICE = Decimal("14500")
# A PIC who prepares orders and opens nothing in quotes.
ORDERS_ONLY = Caller(
    uuid.UUID(int=0x0C),
    "Order Only",
    "order.only@alpha.local",
    frozenset({"sales.case.read", "sales.price.read", "sales.order.prepare"}),
)


def _world() -> World:
    return open_world(REPO, SampleSet.of(REPO, None), (*CALLERS, ORDERS_ONLY))


async def _m03(world: World) -> uuid.UUID:
    """M03 in review: `quotation_missing` on line 2, `missing_noc_esf` open."""
    ((disposition, _),) = (await world.process_each(AN, ["M03"])).values()
    assert disposition.case_id is not None
    case = world.order(disposition.case_id)
    assert case.status is OrderStatus.IN_REVIEW
    assert case.quote_lines() == (2,)
    return case.case_id


async def _open(world: World, case_id: uuid.UUID, caller: Caller = AN) -> uuid.UUID:
    view = await world.services.order_quotes.open(
        caller.context(), case_id, case_version=world.order(case_id).case_version
    )
    return view.quote_case_id


async def _ready_to_prepare(world: World, case_id: uuid.UUID, *keys: str) -> None:
    """`missing_noc_esf` and ``keys`` accepted, then the source opened at the
    version that leaves: what `prepare` needs besides any quote."""
    for key in ("missing_noc_esf:-", *keys):
        await world.services.order_commands.dispose(
            AN.context(),
            case_id,
            key,
            case_version=world.order(case_id).case_version,
            disposition="accepted",
            reason="Đã xem, xác nhận trước khi gửi",
        )
    await world.open_sources(AN, case_id)


def _put(world: World, case: QuoteCase) -> None:
    held = world.store.state(ALPHA).quotes
    held[case.case_id] = replace(held[case.case_id], case=case)


def _design_replied(quote: QuoteCase, prv_code: str) -> QuoteCase:
    """Design's reply for every requested line, as the reader would attach
    it (synthetic file, synthetic values)."""
    assert quote.ycbg is not None
    sha = "d" * 64

    def at(text: str) -> SourceAnchor:
        return SourceAnchor(attachment_id="D09-A1", attachment_sha256=sha, page=1, quote=text)

    def sourced(value: object, text: str) -> Sourced:  # type: ignore[type-arg]
        return Sourced(value=value, source=at(text))

    document = DesignReplyDocument(
        ycbg_no=sourced(quote.ycbg.ycbg_no, quote.ycbg.ycbg_no),
        reply_date=sourced(date(2026, 10, 3), "03/10/2026"),
        lines=tuple(
            DesignReplyLine(
                line_no=item.line_no,
                bp_code=sourced("BP-0901", "BP-0901"),
                spec_no=sourced("SP-5202", "SP-5202"),
                prv_code=sourced(prv_code, prv_code),
            )
            for item in quote.request.document.items
        ),
    )
    reply = DesignReply(
        message_id="D09",
        received_at=quote.request.received_at,
        attachment=Attachment(
            attachment_id="D09-A1",
            name="reply.pdf",
            media_type="application/pdf",
            size=1,
            sha256=sha,
        ),
        document=document,
    )
    return quote.record_design_reply(reply)


async def _approved(
    world: World,
    quote_id: uuid.UUID,
    *,
    prv_code: str = "CB-2003",
    price: Decimal = PO_PRICE,
    recheck: bool = True,
) -> None:
    """The quote opened from the order, through YCBG, Design, price and
    submission, checked by Khoa and approved by the head as its Manager."""
    reasons = await _submitted(world, quote_id, prv_code=prv_code, price=price)
    await _decided(world, quote_id, reasons, recheck)


async def _submitted(
    world: World, quote_id: uuid.UUID, *, prv_code: str = "CB-2003", price: Decimal = PO_PRICE
) -> dict[str, str]:
    """The quote opened from the order, priced and submitted; the reasons
    its open price findings are accepted with."""
    commands = world.services.quote_commands

    def version() -> int:
        return world.quote(quote_id).case_version

    await commands.ycbg(AN.context(), quote_id, case_version=version(), ycbg_no="RFQ261005-090")
    await commands.design_sent(AN.context(), quote_id, case_version=version())
    _put(world, _design_replied(world.quote(quote_id), prv_code))
    await commands.price(
        AN.context(),
        quote_id,
        case_version=version(),
        lme_month="2026-09",
        lines=[
            PricedLine(
                line_no=item.line_no,
                unit_price=price,
                moq=Decimal(3000),
                lead_time_days=28,
                copper_basis=FixedCopper(kind="fixed"),
            )
            for item in world.quote(quote_id).request.document.items
        ],
        management_guidance=None,
    )
    await world.services.dw1.submit_quote(
        AN.context(), quote_id, case_version=version(), quote_no="Q26-0901"
    )
    return {
        f"{f.code.value}:{f.line_no or '-'}": "Giá theo PO của khách"
        for f in world.quote(quote_id).findings
        if f.is_open
    }


async def _decided(
    world: World, quote_id: uuid.UUID, reasons: dict[str, str], recheck: bool
) -> None:
    await world.decide(
        KHOA, CaseKind.QUOTE, quote_id, approve=True, comment="Đã xem", reasons=reasons or None
    )
    # WIV-03-023 section 4 (ticket 39): opened from an order, it is checked at the
    # first level and approved by a Manager, then the order is checked again
    # ("Kiểm tra lại": the worker carrying out the Manager's decision holds
    # no order intake).
    checked = world.quote(quote_id)
    assert checked.status is QuoteStatus.PENDING_APPROVAL
    assert checked.submission is not None and checked.submission.check is not None
    await world.decide_manager(GIANG, quote_id, approve=True, comment="Manager duyệt")
    assert world.quote(quote_id).status is QuoteStatus.APPROVED
    if recheck:
        case_id = world.quote(quote_id).from_order
        assert case_id is not None
        await world.services.order_quotes.recheck(
            AN.context(), case_id.case_id, case_version=world.order(case_id.case_id).case_version
        )


# ------------------------------------------------------------- "Mở báo giá" --


async def test_opening_links_a_quote_for_the_lines_without_a_quotation() -> None:
    world = _world()
    case_id = await _m03(world)
    before = world.order(case_id)

    quote_id = await _open(world, case_id)

    order, quote = world.order(case_id), world.quote(quote_id)
    assert order.case_version == before.case_version + 1
    (link,) = order.quote_links
    assert (link.quote_case_id, link.lines, link.by) == (quote_id, (2,), AN.user_id)
    assert order.status is OrderStatus.IN_REVIEW and order.lines == before.lines
    # The quote case: the customer's, line 2 as the PO prints it, the order named.
    assert quote.from_order is not None
    assert (quote.from_order.case_id, quote.from_order.po_no) == (case_id, before.header.po_no)
    assert quote.customer_code == before.customer_code == "BRN"
    (item,) = quote.request.document.items
    po = before.line(2).effective
    assert (item.line_no, item.quantity.value, item.needed_by.value) == (
        2,
        po.quantity,
        po.requested_date,
    )
    assert item.description.source == po.anchors.description
    assert quote.request.attachment is not None
    assert quote.request.attachment.attachment_id == before.document.attachment_id
    # A complete request: DW1 drafts its YCBG at once, as for one from the mailbox.
    assert quote.status is QuoteStatus.YCBG_DRAFTED
    # Assigned to the order's PIC.
    stored = world.store.state(ALPHA)
    assert stored.quotes[quote_id].origin.assigned_to == stored.orders[case_id].origin.assigned_to
    actions = [e.action for e in world.audit()]
    assert "sales.quote.opened_from_order" in actions and "sales.order.quote_opened" in actions


async def test_opening_twice_opens_one() -> None:
    world = _world()
    case_id = await _m03(world)
    quote_id = await _open(world, case_id)

    with pytest.raises(ConflictError) as refused:
        await _open(world, case_id)

    assert refused.value.details["rule"] == "quote_open"
    assert refused.value.details["quote_case_id"] == str(quote_id)
    assert len(world.order(case_id).quote_links) == 1
    assert list(world.store.state(ALPHA).quotes) == [quote_id]


async def test_a_double_click_on_the_same_version_opens_one() -> None:
    world = _world()
    case_id = await _m03(world)
    version = world.order(case_id).case_version
    await world.services.order_quotes.open(AN.context(), case_id, case_version=version)

    with pytest.raises(ConflictError):
        await world.services.order_quotes.open(AN.context(), case_id, case_version=version)

    assert len(world.store.state(ALPHA).quotes) == 1


async def test_an_order_with_every_quotation_valid_opens_none() -> None:
    world = _world()
    ((disposition, _),) = (await world.process_each(AN, ["M04"])).values()
    assert disposition.case_id is not None
    case = world.order(disposition.case_id)
    assert case.quote_lines() == ()

    with pytest.raises(ConflictError) as refused:
        await _open(world, case.case_id)

    assert refused.value.details["rule"] == "no_quotation_missing"
    assert not world.store.state(ALPHA).quotes


async def test_opening_needs_both_the_order_and_the_quote_scope() -> None:
    world = _world()
    case_id = await _m03(world)

    for caller in (ORDERS_ONLY, READER):
        with pytest.raises(PermissionDeniedError):
            await _open(world, case_id, caller)

    assert not world.order(case_id).quote_links
    assert not world.store.state(ALPHA).quotes


async def test_another_tenants_pic_cannot_open_a_quote_from_the_order() -> None:
    world = _world()
    case_id = await _m03(world)

    with pytest.raises(NotFoundError):
        await world.services.order_quotes.open(
            OUTSIDER.context(BETA), case_id, case_version=world.order(case_id).case_version
        )

    assert not world.order(case_id).quote_links
    assert not world.store.state(ALPHA).quotes and not world.store.state(BETA).quotes


# ------------------------------------------------- acceptance 1: the wait --


async def test_the_order_cannot_be_prepared_while_its_quote_is_open() -> None:
    """Acceptance 1, where preparation happens: the self-check is refused
    naming the open quote, even with line 2's finding decided."""
    world = _world()
    case_id = await _m03(world)
    quote_id = await _open(world, case_id)
    await _ready_to_prepare(world, case_id, MISSING)

    with pytest.raises(ConflictError) as refused:
        await world.services.order_commands.prepare(
            AN.context(), case_id, case_version=world.order(case_id).case_version
        )

    assert refused.value.details["quotes_open"] == [str(quote_id)]
    assert refused.value.details["open_findings"] == []
    assert world.order(case_id).status is OrderStatus.IN_REVIEW


async def test_a_declined_quote_ends_the_wait_and_leaves_the_finding() -> None:
    world = _world()
    case_id = await _m03(world)
    quote_id = await _open(world, case_id)
    await world.services.quote_commands.decline(
        AN.context(),
        quote_id,
        case_version=world.quote(quote_id).case_version,
        reason=DeclineReason.COMMERCIAL,
        note=None,
    )
    assert world.order(case_id).finding(MISSING).is_open
    await _ready_to_prepare(world, case_id, MISSING)

    await world.services.order_commands.prepare(
        AN.context(), case_id, case_version=world.order(case_id).case_version
    )

    assert world.order(case_id).status is OrderStatus.PREPARED


# --------------------------------------- acceptance 2: approval clears it --


async def test_approving_the_quote_clears_the_finding_and_the_order_resumes() -> None:
    """Acceptance 2: on approval DW1 checks line 2 again with the approved
    terms; the finding is gone, the check basis names the quotation, and the
    order is prepared."""
    world = _world()
    case_id = await _m03(world)
    quote_id = await _open(world, case_id)

    await _approved(world, quote_id)

    order = world.order(case_id)
    assert FindingCode.QUOTATION_MISSING not in {f.code for f in order.findings}
    basis = order.line(2).basis.quotation
    assert basis is not None and (basis.quote_no, basis.unit_price) == ("Q26-0901", PO_PRICE)
    assert basis.valid_from == order.header.po_date
    rechecked = [e for e in world.audit() if e.action == "sales.order.quote_rechecked"]
    assert len(rechecked) == 1 and rechecked[0].resource_id == str(case_id)
    await _ready_to_prepare(world, case_id)
    await world.services.order_commands.prepare(
        AN.context(), case_id, case_version=world.order(case_id).case_version
    )
    assert world.order(case_id).status is OrderStatus.PREPARED


async def test_an_approved_quote_at_another_price_is_a_price_finding() -> None:
    world = _world()
    case_id = await _m03(world)
    quote_id = await _open(world, case_id)

    await _approved(world, quote_id, price=Decimal("15000"))

    codes = {f.key for f in world.order(case_id).findings}
    assert MISSING not in codes and "price_mismatch:2" in codes


async def test_a_quote_for_another_item_does_not_clear_the_line() -> None:
    """Design named another code: the order's line is not that item."""
    world = _world()
    case_id = await _m03(world)
    quote_id = await _open(world, case_id)

    await _approved(world, quote_id, prv_code="CB-2012")

    assert world.order(case_id).finding(MISSING).is_open


async def test_every_later_check_of_the_line_reads_the_approved_quote() -> None:
    """A person's "Kiểm tra lại" runs the same check: still no finding."""
    world = _world()
    case_id = await _m03(world)
    quote_id = await _open(world, case_id)
    await _approved(world, quote_id)

    await world.services.order_quotes.recheck(
        AN.context(), case_id, case_version=world.order(case_id).case_version
    )

    assert FindingCode.QUOTATION_MISSING not in {f.code for f in world.order(case_id).findings}


async def test_a_quote_declined_after_approval_is_no_quotation() -> None:
    """A declined case keeps its approval as history: its terms no longer
    count, and the order's next check says so."""
    world = _world()
    case_id = await _m03(world)
    quote_id = await _open(world, case_id)
    await _approved(world, quote_id)
    await world.services.quote_commands.decline(
        AN.context(),
        quote_id,
        case_version=world.quote(quote_id).case_version,
        reason=DeclineReason.COMMERCIAL,
        note=None,
    )
    assert world.quote(quote_id).approval is not None

    with pytest.raises(ConflictError):
        await world.services.order_quotes.recheck(
            AN.context(), case_id, case_version=world.order(case_id).case_version
        )
    order = world.order(case_id)
    assert (
        quoted_for_po(
            [world.quote(quote_id)],
            customer_code="BRN",
            prv_code="CB-2003",
            po_date=order.header.po_date,
        )
        is None
    )


async def test_a_quote_priced_again_after_approval_is_open_again() -> None:
    world = _world()
    case_id = await _m03(world)
    quote_id = await _open(world, case_id)
    await _approved(world, quote_id)
    await world.services.quote_commands.price(
        AN.context(),
        quote_id,
        case_version=world.quote(quote_id).case_version,
        lme_month="2026-09",
        lines=[
            PricedLine(
                line_no=2,
                unit_price=PO_PRICE,
                moq=Decimal(3000),
                lead_time_days=28,
                copper_basis=FixedCopper(kind="fixed"),
            )
        ],
        management_guidance=None,
    )
    assert world.quote(quote_id).status is QuoteStatus.PRICED
    await _ready_to_prepare(world, case_id)

    with pytest.raises(ConflictError) as refused:
        await world.services.order_commands.prepare(
            AN.context(), case_id, case_version=world.order(case_id).case_version
        )

    assert refused.value.details["quotes_open"] == [str(quote_id)]


# ------------------------------------------------- the domain, directly --


def _quote_link_case(case: OrderCase, quote_id: uuid.UUID) -> OrderCase:
    actor = Actor(user_id=AN.user_id)
    return case.open_quote(quote_id, actor, case.received_at)


async def test_the_case_refuses_prepare_for_a_link_its_caller_did_not_settle() -> None:
    world = _world()
    case_id = await _m03(world)
    quote_id = uuid.uuid4()
    case = _quote_link_case(world.order(case_id), quote_id)
    actor = Actor(user_id=AN.user_id)
    decided = case.dispose(
        "missing_noc_esf:-",
        _accepted(actor, case),
        actor.model_copy(
            update={"capabilities": frozenset({Capability.ACKNOWLEDGE_EXPORT_CONTROL})}
        ),
    ).dispose(MISSING, _accepted(actor, case), actor)

    with pytest.raises(ConflictError) as refused:
        decided.prepare(actor, case.received_at)
    assert refused.value.details["quotes_open"] == [str(quote_id)]

    prepared = decided.prepare(actor, case.received_at, settled_quotes=frozenset({quote_id}))
    assert prepared.status is OrderStatus.PREPARED


def _accepted(actor: Actor, case: OrderCase) -> Accepted:
    return Accepted(reason="đã xem", by=actor.user_id, at=case.received_at)


async def test_another_customers_approved_quote_is_never_this_orders_quotation() -> None:
    world = _world()
    case_id = await _m03(world)
    quote_id = await _open(world, case_id)
    await _approved(world, quote_id)
    quote = world.quote(quote_id)
    order = world.order(case_id)

    assert (
        quoted_for_po(
            [quote], customer_code="NRV", prv_code="CB-2003", po_date=order.header.po_date
        )
        is None
    )
    found = quoted_for_po(
        [quote], customer_code="BRN", prv_code="CB-2003", po_date=order.header.po_date
    )
    assert found is not None and found.quote_no == "Q26-0901"


async def test_a_po_whose_file_is_gone_from_its_message_opens_no_quote() -> None:
    world = _world()
    case_id = await _m03(world)
    order = world.order(case_id)
    message = await world.inbox.get_message(ALPHA, order.message_id)
    assert message is not None

    with pytest.raises(ConflictError) as refused:
        request_from_order(order, (2,), message.model_copy(update={"attachments": ()}))

    assert refused.value.details["rule"] == "quote_po_not_a_file"


# ----------------------------------------------- a PO written in the mail --

# The fictional Velatrix PO written in the mail (`sales_po_body.json`), dated
# after every quotation its items have: both lines raise `quotation_missing`.
_PO_BODY = json.loads(
    (REPO / "evals" / "fixtures" / "cases" / "sales_po_body.json").read_text(encoding="utf-8")
)["golden"][0]


async def _po_in_the_mail() -> tuple[World, uuid.UUID]:
    spec, answer = copy.deepcopy(_PO_BODY["message"]), copy.deepcopy(_PO_BODY["answer"])
    spec["body"] = spec["body"].replace("ngày 01/10/2026", "ngày 01/10/2029")
    answer["po_date_span"] = "01/10/2029"
    intent = Recorded(raw={"language": "vi", "referenced_number_spans": [], "kind": "po"})
    model = ByPrompt(
        {"sales.message_intent": intent, PO_BODY_EXTRACTION.prompt_id: Recorded(raw=answer)}
    )
    with SampleWith([spec]) as sample:
        world = open_world(REPO, sample, CALLERS, model=model)
        ((_, case),) = (await world.process_each(AN, [spec["message_id"]])).values()
    assert isinstance(case, OrderCase) and case.document.from_message
    assert case.quote_lines() == (1, 2)
    return world, case.case_id


async def test_a_po_written_in_the_mail_opens_a_quote_whose_model_values_sales_confirms() -> None:
    world, case_id = await _po_in_the_mail()
    order = world.order(case_id)
    # Sales typed line 1's quantity on the order: settled, so not asked again.
    await world.services.order_commands.correct_value(
        AN.context(),
        case_id,
        "value_uncertain:1",
        case_version=order.case_version,
        field="quantity",
        value="6200",
    )

    quote_id = await _open(world, case_id)

    request = world.quote(quote_id).request
    assert request.attachment is None and request.body == order.document.body
    assert request.order_reader == order.document.parser_version and request.reading is None
    first, second = request.document.items
    assert first.quantity.value == Decimal(6200)
    assert first.model_read == {"customer_item_code", "description", "needed_by"}
    assert second.model_read == {"customer_item_code", "description", "quantity", "needed_by"}
    # A price a model read is the customer's statement, never a target.
    assert (first.target_price, first.stated_target_price is not None) == (None, True)
    # Flagged values wait for Sales: no YCBG is drafted before they are confirmed.
    assert world.quote(quote_id).ycbg is None


async def test_a_request_is_read_from_the_mail_or_taken_from_an_order_not_both() -> None:
    world, case_id = await _po_in_the_mail()
    order = world.order(case_id)
    message = await world.inbox.get_message(ALPHA, order.message_id)
    assert message is not None
    taken = dict(request_from_order(order, (1,), message))
    reading = RequestReading(
        prompt="sales.rfq_extraction@1.0.0",
        model_profile="p",
        route="r",
        rules="sales_quote_rules@1.0.0",
        calls=1,
    )

    with pytest.raises(ValidationError, match="not both"):
        QuoteRequest.model_validate({**taken, "reading": reading})
    with pytest.raises(ValidationError, match="says how"):
        QuoteRequest.model_validate({**taken, "order_reader": None})


# ----------------------------------------------- both case views name it --


async def test_both_case_views_name_the_link() -> None:
    world = _world()
    case_id = await _m03(world)
    quote_id = await _open(world, case_id)

    order_view = await world.services.orders.get(AN.context(), case_id)
    quote_view = await world.services.quotes.get(AN.context(), quote_id)

    (link,) = order_view.quote_links
    assert (link.quote_case_id, link.lines, link.waiting) == (quote_id, [2], True)
    assert link.status == "ycbg_drafted"
    assert quote_view.from_order is not None
    assert quote_view.from_order.case_id == case_id

    await _approved(world, quote_id)
    (link,) = (await world.services.orders.get(AN.context(), case_id)).quote_links
    assert (link.status, link.waiting) == ("approved", False)


# --------------------------- two levels for a quotation with an order (39) --


async def _checked(world: World, checker: Caller = KHOA) -> uuid.UUID:
    """M03's quote, priced, submitted and checked at the first level."""
    case_id = await _m03(world)
    quote_id = await _open(world, case_id)
    reasons = await _submitted(world, quote_id)
    await world.decide(
        checker, CaseKind.QUOTE, quote_id, approve=True, comment="Đã kiểm", reasons=reasons or None
    )
    return quote_id


async def test_the_check_keeps_it_waiting_on_a_manager_naming_three_makers() -> None:
    """WIV-03-023 section 4: the first level keeps the quotation waiting and opens
    a Manager's approval whose makers are the pricer, the submitter and the
    checker, so the strict check refuses each of them."""
    world = _world()
    quote_id = await _checked(world)
    checked = world.quote(quote_id)
    assert checked.status is QuoteStatus.PENDING_APPROVAL
    assert checked.submission is not None and checked.submission.check is not None
    (request,) = [
        r for r in world.runtime.approvals.rows.values() if r.approval_type == "sales.quote.manager"
    ]
    assert request.required_scope == "sales.quote.manager_approve"
    makers = request.payload["makers"]
    assert isinstance(makers, list)
    assert set(makers) == {str(AN.user_id), str(KHOA.user_id)}
    assert request.payload["case_id"] == str(quote_id)
    assert "sales.quote.checked" in {e.action for e in world.audit()}


async def test_the_checker_never_decides_the_managers_approval() -> None:
    """Giang checks it and holds the Manager's scope too: refused."""
    world = _world()
    quote_id = await _checked(world, checker=GIANG)
    with pytest.raises(ConflictError):
        await world.decide_manager(GIANG, quote_id, approve=True, comment="Tự duyệt")
    assert world.quote(quote_id).status is QuoteStatus.PENDING_APPROVAL


async def test_a_manager_without_the_scope_is_refused() -> None:
    """The platform shows a Manager's approval only to a holder of its
    scope: anyone else finds no such request, and nothing is decided."""
    world = _world()
    quote_id = await _checked(world, checker=GIANG)
    with pytest.raises(NotFoundError):
        await world.decide_manager(KHOA, quote_id, approve=True, comment="Không có quyền")
    assert world.quote(quote_id).status is QuoteStatus.PENDING_APPROVAL


async def test_the_manager_returns_it_to_the_pricer_and_the_check_goes() -> None:
    world = _world()
    quote_id = await _checked(world)
    await world.decide_manager(GIANG, quote_id, approve=False, comment="Giá chưa hợp lý")
    returned = world.quote(quote_id)
    assert returned.status is QuoteStatus.RETURNED and returned.submission is None
    assert returned.returns[-1].returned_by == GIANG.user_id


async def test_a_manager_decision_delivered_twice_is_carried_out_once() -> None:
    world = _world()
    quote_id = await _checked(world)
    await world.decide_manager(GIANG, quote_id, approve=True, comment="Duyệt")
    version = world.quote(quote_id).case_version
    (request,) = [
        r for r in world.runtime.approvals.rows.values() if r.approval_type == "sales.quote.manager"
    ]
    settlement = QuoteManagerSettlement(
        world.store, world.layout_settlement.clock, world.layout_settlement.ids, world.notifications
    )
    again = await settlement.settle(request.id, GIANG.context())
    assert again == "quote.approved" and world.quote(quote_id).case_version == version
