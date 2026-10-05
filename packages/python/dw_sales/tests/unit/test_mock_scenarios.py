"""What `adapters/mock/README.md` says each mock email triggers is what the data holds.

Tickets 02 and 03 turn the README into golden tests of the real checks. This is
the other half: it derives each answer from the fixtures with the plainest
reading of every rule, and asserts each margin that makes the answer the same
under any reasonable policy detail (tolerance, which month's LME, calendar or
working days, the denial-list age), so a golden test cannot pass or fail on a
reading the data left open.
"""

from __future__ import annotations

import json
import math
import re
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest
import yaml

from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.adapters.mock import MockInbox, MockSalesCatalog
from dw_sales.adapters.mock.fixtures import DATA_DIR, MOCK_ROOT
from dw_sales.adapters.mock.generate_attachments import (
    DesignReplyDocument,
    OrderLine,
    PurchaseOrderDocument,
    QuoteRequestDocument,
    StatedAttributes,
    load_design_replies,
    load_purchase_orders,
    load_quote_requests,
)
from dw_sales.application.ports import SalesScope
from dw_sales.domain.catalog import (
    BravoOrder,
    Customer,
    Item,
    LmeBand,
    OpenYcbg,
    fiscal_year,
    month_key,
)
from dw_sales.domain.messages import InboundMessage

pytestmark = pytest.mark.unit

SCOPE = SalesScope(TenantId(uuid.UUID(int=1)), WorkspaceId(uuid.UUID(int=2)))
README = (MOCK_ROOT / "README.md").read_text(encoding="utf-8")
PACKAGE = Path(__file__).resolve().parents[2]
GLOSSARY = (PACKAGE / "CONTEXT.md").read_text(encoding="utf-8")
ORDER_RULES = PACKAGE.parents[2] / "configs" / "policies" / "sales_order_rules@1.0.0.yaml"
# The owner of the fiscal year's first month; read, never restated here.
FISCAL_YEAR_START = int(
    yaml.safe_load(ORDER_RULES.read_text(encoding="utf-8"))["fiscal_year_start_month"]
)

# The seller's own domain: Sales forwarding mail, Design replying.
SELLER_DOMAIN = "seller.example"
# The platform seed's persona addresses (`Customer.sales_pic`); `.local` is
# reserved and resolves nowhere.
PERSONA_DOMAIN = "alpha.local"
# Glossary codes no mock message raises, and why.
NOT_RAISED_BY_A_MESSAGE = {
    # Raised by processing M07 before M04, not by the mailbox's own order.
    "revision_without_base",
    # Raised by Sales' price decision; ticket 03's tests script one.
    "price_below_policy_floor",
    "price_floor_unknown",
    "price_basis_mismatch",
    "above_target_price",
}
# A message routed on what its text says: no rule over the data can recompute
# which of these it is, so the oracle checks only that it is one of them.
ROUTED_BY_CONTENT = frozenset({"delivery_change", "complaint", "sample_request", "other"})
# A price that differs from its quotation differs by at least this much.
PRICE_MARGIN = Decimal("0.02")
# A denial-list check no older than this on every message date reads the same
# under any maximum age from this up.
DENIAL_LIST_MARGIN_DAYS = 45
SCREENING_DAY = date(2026, 9, 30)
# No ERP order this close to the start of a 12-month window, so "12 months" may
# be read as 365 days or a calendar year, the start included or not.
WINDOW_EDGE_MARGIN_DAYS = 15

# (finding code, PO line number, or None for the message as a whole)
type Finding = tuple[str, int | None]
# (disposition, routing reason or None)
type Disposition = tuple[str, str | None]

_CODE = re.compile(r"`([^`]+)`")
_FINDING = re.compile(r"`(\w+)`(?:\s*\(line (\d+)\))?")
_QUOTE_NO = re.compile(r"`(Q\d{2}-\d{4})`")
_ORDER_NO = re.compile(r"`(SO\d{2}-\d{4})`")


@dataclass(frozen=True)
class Outcome:
    customer: str | None
    classification: str
    disposition: Disposition
    findings: frozenset[Finding]


@dataclass(frozen=True)
class RequestEvidence:
    customer: str
    item: str  # a PRV code, or "new"
    target_price: Decimal | None
    own_quotations: tuple[str, ...]
    others_valid_quotations: tuple[str, ...]
    own_orders: tuple[str, ...]


@dataclass(frozen=True)
class ReplyMatch:
    ycbg_no: str
    answers: str | None  # the request's message id
    prv_code: str | None


@pytest.fixture(scope="module")
def catalog() -> MockSalesCatalog:
    return MockSalesCatalog.load(SCOPE)


@pytest.fixture(scope="module")
def inbox() -> MockInbox:
    return MockInbox.load(SCOPE)


# ------------------------------------------------------------ the README --


def _tables(heading: str, text: str = README) -> list[list[list[str]]]:
    """The tables under ``## heading``, each as its data rows (header and rule
    excluded: a data row starts with a backticked code)."""
    section = text.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0]
    return [
        [
            [cell.strip() for cell in line.strip().strip("|").split("|")]
            for line in block.splitlines()
            if line.startswith("| `")
        ]
        for block in (part.strip() for part in section.split("\n\n"))
        if block.startswith("|")
    ]


def _table(heading: str, text: str = README) -> list[list[str]]:
    return _tables(heading, text)[0]


def _second_table(heading: str) -> list[list[str]]:
    return _tables(heading)[1]


def _comparable(disposition: Disposition) -> Disposition:
    kind, reason = disposition
    return (kind, "by_content" if reason in ROUTED_BY_CONTENT else reason)


def _claimed_outcomes() -> dict[str, Outcome]:
    claims: dict[str, Outcome] = {}
    for message, customer, _scenario, _attachment, classification, disposition, findings in _table(
        "Messages"
    ):
        kind, *reason = _CODE.findall(disposition)
        claims[_CODE.findall(message)[0]] = Outcome(
            customer=(_CODE.findall(customer) or [None])[0],
            classification=_CODE.findall(classification)[0],
            disposition=(kind, reason[0] if reason else None),
            findings=frozenset(
                (code, int(line) if line else None) for code, line in _FINDING.findall(findings)
            ),
        )
    return claims


def _claimed_evidence() -> dict[str, RequestEvidence]:
    claims: dict[str, RequestEvidence] = {}
    for message, customer, item, target, own, others, orders in _table("Quote requests"):
        price = re.search(r"\d+\.\d+", target)
        claims[_CODE.findall(message)[0]] = RequestEvidence(
            customer=_CODE.findall(customer)[0],
            item=(_CODE.findall(item) or ["new"])[0],
            target_price=Decimal(price.group()) if price else None,
            own_quotations=tuple(_QUOTE_NO.findall(own)),
            others_valid_quotations=tuple(_QUOTE_NO.findall(others)),
            own_orders=tuple(_ORDER_NO.findall(orders)),
        )
    return claims


def _glossary_codes(heading: str) -> set[str]:
    return {_CODE.findall(row[0])[0] for row in _table(heading, GLOSSARY)}


def _glossary_routing_reasons() -> set[str]:
    paragraph = GLOSSARY.split("Routing reasons:", 1)[1].split("\n\n", 1)[0]
    return set(re.findall(r"`(\w+)`\s+\(", paragraph))


# ------------------------------------------- the rules, read plainly ------


def _states(stated: StatedAttributes, item: Item) -> bool:
    """Every attribute the line states is the item's."""
    known = StatedAttributes.of_item(item)
    return all(value is None or getattr(known, name) == value for name, value in stated)


async def _resolve(
    catalog: MockSalesCatalog, customer: Customer, code: str, stated: StatedAttributes | None
) -> Item | str:
    """The item a line names, or the finding code that says why it names none."""
    entry = (await catalog.convert_entry(SCOPE, customer.code, code)).data
    if entry is not None:
        item = (await catalog.item_by_prv_code(SCOPE, entry.prv_code)).data
        assert item is not None
        assert stated is None or _states(stated, item), f"{code} describes another item"
        return item
    assert stated is not None, f"{code} has no convert entry and states nothing"
    candidates = [item for item in (await catalog.items(SCOPE)).data if _states(stated, item)]
    if not candidates:
        return "code_unmapped"
    if len(candidates) > 1:
        return "code_ambiguous"
    return candidates[0]


async def _attribute(
    catalog: MockSalesCatalog, message: InboundMessage, named_buyer: str | None
) -> tuple[Customer | None, bool]:
    """The customer a message is attributed to, and whether it was taken from
    the document's named buyer rather than the sender's domain."""
    by_domain = (await catalog.customer_by_email_domain(SCOPE, message.sender.domain)).data
    if by_domain is not None:
        assert named_buyer is None or named_buyer.casefold() == by_domain.name.casefold(), (
            f"{message.message_id}: the document names another buyer than the sender's"
        )
        return by_domain, False
    if named_buyer is None:
        return None, False
    matches = [
        c
        for c in (await catalog.customers(SCOPE)).data
        if c.name.casefold() == named_buyer.casefold()
    ]
    assert len(matches) <= 1, f"{message.message_id}: the buyer's name fits two customers"
    return (matches[0], True) if matches else (None, False)


def _unverified(message: InboundMessage) -> bool:
    results = {
        message.authentication.spf,
        message.authentication.dkim,
        message.authentication.dmarc,
    }
    assert results == {"pass"} or "pass" not in results, (
        f"{message.message_id}: verified or not depends on which result is read"
    )
    return results != {"pass"}


async def _line_findings(
    catalog: MockSalesCatalog,
    customer: Customer,
    po: PurchaseOrderDocument,
    received: date,
    line: OrderLine,
    item: Item,
) -> set[str]:
    found: set[str] = set()
    label = f"{po.message_id} line {line.no}"
    valid = (
        await catalog.quotations_valid_on(SCOPE, customer.code, item.prv_code, po.po_date)
    ).data
    on_arrival = (
        await catalog.quotations_valid_on(SCOPE, customer.code, item.prv_code, received)
    ).data
    assert valid == on_arrival, f"{label}: validity depends on which date is read"
    assert len(valid) <= 1, f"{label}: two valid quotations, a check would have to choose"
    quotation = valid[0] if valid else None
    if quotation is None:
        found.add("quotation_missing")
    else:
        if quotation.currency != po.currency:
            found.add("currency_mismatch")
        elif line.unit_price != quotation.unit_price:
            gap = abs(line.unit_price - quotation.unit_price)
            assert gap >= quotation.unit_price * PRICE_MARGIN, f"{label}: within any tolerance"
            found.add("price_mismatch")
        if isinstance(quotation.copper_basis, LmeBand):
            month_before = po.po_date.replace(day=1) - timedelta(days=1)
            verdicts = set()
            for month in (month_key(po.po_date), month_key(month_before)):
                lme = (await catalog.lme_for_month(SCOPE, month)).data
                assert lme is not None, f"{label}: no LME for {month}"
                verdicts.add(quotation.copper_basis.contains(lme.usd_per_tonne))
            assert len(verdicts) == 1, f"{label}: the band verdict depends on the month"
            if verdicts == {False}:
                found.add("lme_band_mismatch")
    minimums = [item.moq] + ([quotation.moq] if quotation else [])
    if line.quantity < min(minimums):
        found.add("moq_violation")
    else:
        assert line.quantity >= max(minimums), f"{label}: depends on whose MOQ"
    if line.quantity % item.pack_multiple:
        found.add("pack_multiple")
    lead_times = [item.standard_lead_time_days] + ([quotation.lead_time_days] if quotation else [])
    if line.requested_date < po.po_date + timedelta(days=min(lead_times)):
        found.add("requested_date_short_lt")
    else:
        working_days = math.ceil(max(lead_times) * 7 / 5) + 3
        clear = max(po.po_date, received) + timedelta(days=working_days)
        assert line.requested_date >= clear, f"{label}: depends on how lead time is counted"
    units = {item.uom} | ({quotation.uom} if quotation else set())
    if units != {line.uom}:
        # Whether the other checks run on a line in another unit is the
        # policy's; the data leaves them nothing to raise either way.
        assert not found, f"{label}: other findings depend on the unit's reading"
        found.add("uom_mismatch")
    return found


def _po_total_findings(po: PurchaseOrderDocument) -> set[Finding]:
    numbers = [line.no for line in po.lines]
    step = Decimal("0.01") if po.currency == "USD" else Decimal(1)
    lines_sum = sum(
        ((line.quantity * line.unit_price).quantize(step, ROUND_HALF_UP) for line in po.lines),
        Decimal(0),
    )
    if po.printed_total is not None:
        assert po.printed_total != lines_sum, f"{po.message_id}: printed_total changes nothing"
    if numbers != list(range(1, len(numbers) + 1)) or po.printed_total is not None:
        return {("line_total_mismatch", None)}
    return set()


def _uncertain_lines(po: PurchaseOrderDocument) -> set[Finding]:
    on_hidden_pages = {
        line.no
        for number, page in enumerate(po.pages(), start=1)
        if number in po.hidden_pages
        for line in page
    }
    return {("value_uncertain", no) for no in set(po.hidden_lines) | on_hidden_pages}


async def _history(
    catalog: MockSalesCatalog,
    customer: Customer,
    po: PurchaseOrderDocument,
    resolved: dict[int, Item],
    revisions: dict[tuple[str, str], list[int]],
) -> tuple[str, set[Finding]]:
    """The classification, and the history finding: a DW1 case or an ERP order
    for the same PO decides between new, revised and duplicate."""
    earlier = revisions.setdefault((customer.code, po.po_no), [])
    in_erp = (await catalog.orders_for_po(SCOPE, customer.code, po.po_no)).data
    found: set[Finding] = set()
    classification = "po"
    if any(revision < po.revision for revision in earlier):
        classification = "revised_po"
        found.add(("revised_po", None))
    elif po.revision in earlier:
        found.add(("duplicate_po", None))
    else:
        assert not any(order.po_revision != po.revision for order in in_erp), (
            f"{po.message_id}: the ERP holds another revision; no fixture exercises it"
        )
        keyed = [order for order in in_erp if order.po_revision == po.revision]
        if keyed:
            (order,) = keyed
            assert _same_lines(po, resolved, order), f"{po.message_id}: differs from {order.so_no}"
            found.add(("duplicate_po", None))
        else:
            assert po.revision == 0, f"{po.message_id}: a revision with no earlier PO"
    earlier.append(po.revision)
    return classification, found


def _same_lines(po: PurchaseOrderDocument, resolved: dict[int, Item], order: BravoOrder) -> bool:
    printed = [
        (line.no, resolved[line.no].prv_code, line.quantity, line.unit_price, line.requested_date)
        for line in po.lines
    ]
    keyed = [
        (line.line_no, line.prv_code, line.quantity, line.unit_price, line.delivery_date)
        for line in order.lines
    ]
    return order.currency == po.currency and printed == keyed


def _compliance_findings(customer: Customer, po_date: date, received: date) -> set[Finding]:
    year = fiscal_year(po_date, start_month=FISCAL_YEAR_START)
    assert year == fiscal_year(received, start_month=FISCAL_YEAR_START), customer.code
    compliance = customer.compliance
    checked = compliance.denial_list_checked_on
    if checked is not None:
        for day in (po_date, received):
            assert 0 <= (day - checked).days <= DENIAL_LIST_MARGIN_DAYS, (
                f"{customer.code}: the denial-list verdict depends on the maximum age"
            )
    if not compliance.noc_confirmed or compliance.esf_fiscal_year != year or checked is None:
        return {("missing_noc_esf", None)}
    return set()


async def _order_outcome(
    catalog: MockSalesCatalog,
    customer: Customer,
    forwarded: bool,
    message: InboundMessage,
    po: PurchaseOrderDocument,
    revisions: dict[tuple[str, str], list[int]],
) -> Outcome:
    received = message.received_at.date()
    findings: set[Finding] = set()
    resolved: dict[int, Item] = {}
    for line in po.lines:
        item = await _resolve(catalog, customer, line.customer_item_code, line.attributes)
        if isinstance(item, str):
            findings.add((item, line.no))
            continue
        resolved[line.no] = item
        found = await _line_findings(catalog, customer, po, received, line, item)
        findings |= {(code, line.no) for code in found}
    classification, history = await _history(catalog, customer, po, resolved, revisions)
    findings |= history
    findings |= _compliance_findings(customer, po.po_date, received)
    findings |= _po_total_findings(po)
    findings |= _uncertain_lines(po)
    if forwarded:
        findings.add(("customer_unknown", None))
    if customer.status == "temporary":
        findings.add(("customer_temporary", None))
    if _unverified(message):
        findings.add(("sender_unverified", None))
    disposition = (
        ("attached_to_case", None) if classification == "revised_po" else ("case_created", None)
    )
    return Outcome(customer.code, classification, disposition, frozenset(findings))


def _buyer_name(catalog_customers: dict[str, Customer], po: PurchaseOrderDocument) -> str:
    if po.customer_code is not None:
        return catalog_customers[po.customer_code].name
    assert po.buyer_name is not None
    return po.buyer_name


async def _outcomes(catalog: MockSalesCatalog, inbox: MockInbox) -> dict[str, Outcome]:
    orders = {po.message_id: po for po in load_purchase_orders()}
    requests = {rfq.message_id: rfq for rfq in load_quote_requests()}
    replies = {reply.message_id: reply for reply in load_design_replies()}
    customers = {c.code: c for c in (await catalog.customers(SCOPE)).data}
    open_ycbg = {y.ycbg_no: y for y in (await catalog.open_ycbg(SCOPE)).data}
    revisions: dict[tuple[str, str], list[int]] = {}
    seen_requests: dict[tuple[str, str], str] = {}
    outcomes: dict[str, Outcome] = {}
    for message in await inbox.list_messages(SCOPE):
        mid = message.message_id
        if (po := orders.get(mid)) is not None:
            customer, forwarded = await _attribute(catalog, message, _buyer_name(customers, po))
            if po.layout == "pdf_image":
                outcome = Outcome(
                    customer.code if customer else None,
                    "po",
                    ("routed_to_sales", "attachment_unreadable"),
                    frozenset(),
                )
            elif customer is None:
                outcome = Outcome(None, "po", ("routed_to_sales", "customer_unknown"), frozenset())
            else:
                outcome = await _order_outcome(catalog, customer, forwarded, message, po, revisions)
        elif (rfq := requests.get(mid)) is not None:
            customer, forwarded = await _attribute(
                catalog, message, customers[rfq.customer_code].name
            )
            assert customer is not None and customer.code == rfq.customer_code, mid
            findings: set[Finding] = {
                ("rfq_incomplete", line.no) for line in rfq.lines if line.quantity is None
            }
            if forwarded:
                findings.add(("customer_unknown", None))
            if _unverified(message):
                findings.add(("sender_unverified", None))
            seen_requests[(customer.code, rfq.rfq_no)] = mid
            outcome = Outcome(
                customer.code, "quote_request", ("case_created", None), frozenset(findings)
            )
        elif (reply := replies.get(mid)) is not None:
            assert message.sender.domain == SELLER_DOMAIN, mid
            ycbg = open_ycbg.get(reply.ycbg_no)
            answered = seen_requests.get((ycbg.customer_code, ycbg.rfq_no)) if ycbg else None
            if ycbg is not None and answered is not None:
                outcome = Outcome(
                    ycbg.customer_code, "design_reply", ("attached_to_case", None), frozenset()
                )
            else:
                outcome = Outcome(
                    None, "design_reply", ("routed_to_sales", "design_reply_unmatched"), frozenset()
                )
        else:
            assert not message.attachments, f"{mid} carries no known document"
            customer, _ = await _attribute(catalog, message, None)
            assert customer is not None, f"{mid}: routed by its text, from nobody known"
            outcome = Outcome(
                customer.code, "other", ("routed_to_sales", "by_content"), frozenset()
            )
        outcomes[mid] = outcome
    return outcomes


async def _request_evidence(
    catalog: MockSalesCatalog, rfq: QuoteRequestDocument
) -> RequestEvidence:
    customer = (await catalog.customer_by_code(SCOPE, rfq.customer_code)).data
    assert customer is not None
    (line,) = rfq.lines
    resolved = await _resolve(catalog, customer, line.customer_item_code, line.attributes)
    if isinstance(resolved, str):
        assert resolved == "code_unmapped", f"{rfq.message_id}: {resolved}"
        return RequestEvidence(customer.code, "new", line.target_price, (), (), ())
    quotations = (await catalog.quotations_for_item(SCOPE, resolved.prv_code)).data
    own = [q for q in quotations if q.customer_code == customer.code]
    assert not any(q.is_valid_on(rfq.rfq_date) for q in own), (
        f"{rfq.message_id}: the requester already holds a valid price"
    )
    since = rfq.rfq_date - timedelta(days=365)
    history = [
        order
        for order in (await catalog.orders_since(SCOPE, since)).data
        if order.customer_code == customer.code
        and order.order_date <= rfq.rfq_date
        and any(entry.prv_code == resolved.prv_code for entry in order.lines)
    ]
    assert all((order.order_date - since).days >= WINDOW_EDGE_MARGIN_DAYS for order in history), (
        f"{rfq.message_id}: the order history depends on where 12 months start"
    )
    return RequestEvidence(
        customer=customer.code,
        item=resolved.prv_code,
        target_price=line.target_price,
        own_quotations=tuple(q.quote_no for q in own),
        others_valid_quotations=tuple(
            q.quote_no
            for q in quotations
            if q.customer_code != customer.code and q.is_valid_on(rfq.rfq_date)
        ),
        own_orders=tuple(order.so_no for order in history),
    )


async def _reply_match(
    catalog: MockSalesCatalog,
    reply: DesignReplyDocument,
    open_ycbg: dict[str, OpenYcbg],
    requests: dict[tuple[str, str], QuoteRequestDocument],
) -> ReplyMatch:
    (line,) = reply.lines
    ycbg = open_ycbg.get(reply.ycbg_no)
    rfq = requests.get((ycbg.customer_code, ycbg.rfq_no)) if ycbg else None
    if rfq is None:
        return ReplyMatch(reply.ycbg_no, None, line.prv_code)
    customer = (await catalog.customer_by_code(SCOPE, rfq.customer_code)).data
    assert customer is not None
    (requested,) = rfq.lines
    assert requested.no == line.no, reply.message_id
    item = await _resolve(catalog, customer, requested.customer_item_code, requested.attributes)
    if isinstance(item, str):
        assert line.prv_code is None, f"{reply.message_id}: a code for a design the catalogue lacks"
    else:
        assert line.prv_code == item.prv_code, f"{reply.message_id}: names another item"
        assert line.spec_no == item.attributes.spec_no, f"{reply.message_id}: another spec"
    return ReplyMatch(reply.ycbg_no, rfq.message_id, line.prv_code)


# ---------------------------------------------------------------- tests --


async def test_each_message_triggers_what_the_readme_says_and_nothing_else(
    catalog: MockSalesCatalog, inbox: MockInbox
) -> None:
    claimed = {
        mid: Outcome(o.customer, o.classification, _comparable(o.disposition), o.findings)
        for mid, o in _claimed_outcomes().items()
    }

    assert await _outcomes(catalog, inbox) == claimed


def test_a_message_routed_by_its_text_names_a_reason_text_can_give() -> None:
    for mid, outcome in _claimed_outcomes().items():
        kind, reason = outcome.disposition
        if outcome.classification == "other":
            assert kind == "routed_to_sales", mid
            assert reason in ROUTED_BY_CONTENT, mid


async def test_each_quote_request_has_the_evidence_the_readme_lists(
    catalog: MockSalesCatalog,
) -> None:
    observed = {
        rfq.message_id: await _request_evidence(catalog, rfq) for rfq in load_quote_requests()
    }

    assert observed == _claimed_evidence()


async def test_each_design_reply_answers_the_request_the_readme_names(
    catalog: MockSalesCatalog,
) -> None:
    open_ycbg = {y.ycbg_no: y for y in (await catalog.open_ycbg(SCOPE)).data}
    requests = {(r.customer_code, r.rfq_no): r for r in load_quote_requests()}
    observed = {
        reply.message_id: await _reply_match(catalog, reply, open_ycbg, requests)
        for reply in load_design_replies()
    }
    claimed = {
        _CODE.findall(message)[0]: ReplyMatch(
            ycbg_no=_CODE.findall(ycbg)[0],
            answers=(_CODE.findall(answers) or [None])[0],
            prv_code=(_CODE.findall(prv) or [None])[0],
        )
        for message, ycbg, answers, prv in _table("Design replies")
    }

    assert observed == claimed


async def test_the_ycbg_still_waiting_are_the_open_ones_no_reply_quotes(
    catalog: MockSalesCatalog,
) -> None:
    replied = {reply.ycbg_no for reply in load_design_replies()}
    waiting = {
        (y.ycbg_no, y.customer_code)
        for y in (await catalog.open_ycbg(SCOPE)).data
        if y.ycbg_no not in replied
    }
    claimed = {
        (_CODE.findall(ycbg)[0], _CODE.findall(customer)[0])
        for ycbg, customer in _second_table("Design replies")
    }

    assert waiting == claimed


async def test_the_yearly_screening_is_what_the_erp_export_implies(
    catalog: MockSalesCatalog,
) -> None:
    since = SCREENING_DAY - timedelta(days=365)
    orders = (await catalog.orders_since(SCOPE, since)).data
    ordered = {
        (order.customer_code, line.prv_code)
        for order in orders
        if order.order_date <= SCREENING_DAY
        for line in order.lines
    }
    assert all(
        abs((order.order_date - since).days) >= WINDOW_EDGE_MARGIN_DAYS
        for order in (await catalog.orders_since(SCOPE, date(2000, 1, 1))).data
    ), "an order sits on the edge of the screening window"
    quotations = (await catalog.quotations(SCOPE)).data
    pairs = {(q.customer_code, q.prv_code) for q in quotations}
    valid = {
        (q.customer_code, q.prv_code): q.quote_no
        for q in quotations
        if q.is_valid_on(SCREENING_DAY)
    }
    only_expired = pairs - valid.keys()
    assert only_expired <= ordered, "screening depends on whether expired quotations count"
    observed = {(c, p, quote_no) for (c, p), quote_no in valid.items() if (c, p) not in ordered}
    claimed = {
        (_CODE.findall(customer)[0], _CODE.findall(item)[0], _CODE.findall(quote_no)[0])
        for customer, item, quote_no in _table("Yearly screening")
    }

    assert observed == claimed


async def test_each_message_carries_the_attachment_the_readme_names(inbox: MockInbox) -> None:
    claimed = {_CODE.findall(row[0])[0]: tuple(_CODE.findall(row[3])) for row in _table("Messages")}
    carried = {
        message.message_id: tuple(attachment.name for attachment in message.attachments)
        for message in await inbox.list_messages(SCOPE)
    }

    assert carried == claimed


def test_every_finding_in_the_glossary_is_triggered_by_a_mock_email() -> None:
    expected = _glossary_codes("Finding codes") - NOT_RAISED_BY_A_MESSAGE
    claimed = {code for outcome in _claimed_outcomes().values() for code, _ in outcome.findings}

    assert sorted(expected - claimed) == [], "no mock email triggers these"
    assert sorted(claimed - expected) == [], "the README names findings the glossary lacks"


def test_every_routing_reason_but_other_and_every_disposition_is_given() -> None:
    reasons = _glossary_routing_reasons()
    dispositions = _glossary_codes("Message dispositions")
    claimed = [outcome.disposition for outcome in _claimed_outcomes().values()]

    assert reasons >= {"customer_unknown", "complaint", "other"}, "the glossary was misread"
    assert {kind for kind, _ in claimed} <= dispositions
    assert {reason for _, reason in claimed if reason} == reasons - {"other"}
    # Not one message is left without a decision.
    assert "not_yet_processed" not in {kind for kind, _ in claimed}


async def test_the_sample_request_comes_from_a_customer_without_noc(
    catalog: MockSalesCatalog,
) -> None:
    (sample,) = [o for o in _claimed_outcomes().values() if o.disposition[1] == "sample_request"]
    assert sample.customer is not None
    customer = (await catalog.customer_by_code(SCOPE, sample.customer)).data

    assert customer is not None
    assert not customer.compliance.noc_confirmed


def test_the_master_data_counts_in_the_readme_are_the_fixtures() -> None:
    rows = _table("Master data")

    assert rows
    for file_cell, records, _what in rows:
        name = _CODE.findall(file_cell)[0]
        assert len(json.loads((DATA_DIR / name).read_text(encoding="utf-8"))) == int(records), name


async def test_a_sender_on_a_customers_domain_is_one_of_its_contacts(
    catalog: MockSalesCatalog, inbox: MockInbox
) -> None:
    """A reply can go back to such a sender without leaving the customer's
    contacts. Anyone else is the seller's own address or nobody known."""
    for message in await inbox.list_messages(SCOPE):
        customer = (await catalog.customer_by_email_domain(SCOPE, message.sender.domain)).data
        if customer is not None:
            assert message.sender.address in {c.address for c in customer.contacts}, (
                message.message_id
            )


async def test_every_address_and_domain_in_the_fixtures_is_fictional(
    catalog: MockSalesCatalog,
) -> None:
    """The repository is public: no real domain, and no customer document."""
    # The JSON, and the generator: its constants (the seller's name, every
    # label) are printed into every attachment.
    sources = [*sorted(DATA_DIR.glob("*.json")), MOCK_ROOT / "generate_attachments.py"]
    text = "\n".join(path.read_text(encoding="utf-8") for path in sources)
    addresses = re.findall(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)", text)
    domains = set(addresses)
    # A customer may list a domain no address in the fixtures uses.
    customers = (await catalog.customers(SCOPE)).data
    domains |= {domain for c in customers for domain in c.email_domains}
    pics = [c.sales_pic for c in customers if c.sales_pic is not None]

    assert domains
    assert sorted(d for d in domains if not d.endswith(".example") and d != PERSONA_DOMAIN) == []
    # The persona domain names a Sales PIC and nothing else.
    assert addresses.count(PERSONA_DOMAIN) == len(pics)
    assert {pic.rpartition("@")[2] for pic in pics} == {PERSONA_DOMAIN}
    assert "proterial" not in text.lower()


async def test_the_snapshot_was_taken_after_the_last_message_arrived(
    catalog: MockSalesCatalog, inbox: MockInbox
) -> None:
    """The README's claim, and what keeps the open-YCBG list honest: a YCBG
    Design already answered by mail is still open in this snapshot, because
    it closes when its quotation is issued, not when the reply arrives."""
    *_, last = await inbox.list_messages(SCOPE)

    assert (await catalog.open_ycbg(SCOPE)).as_of > last.received_at
