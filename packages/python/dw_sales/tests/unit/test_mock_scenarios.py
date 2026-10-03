"""What `adapters/mock/README.md` says each mock email triggers is what the data holds.

Tickets 02 and 03 turn the README into golden tests of the real checks. This is
the other half: it derives each answer from the fixtures with the plainest
reading of every rule, and asserts each margin that makes the answer the same
under any reasonable policy detail (tolerance, which month's LME, calendar or
working days), so a golden test cannot pass or fail on a reading the data left
open.
"""

from __future__ import annotations

import json
import math
import re
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

import pytest

from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.adapters.mock import MockInbox, MockSalesCatalog
from dw_sales.adapters.mock.fixtures import DATA_DIR, MOCK_ROOT
from dw_sales.adapters.mock.generate_attachments import (
    OrderLine,
    PurchaseOrderDocument,
    QuoteRequestDocument,
    StatedAttributes,
    load_purchase_orders,
    load_quote_requests,
)
from dw_sales.application.ports import SalesScope
from dw_sales.domain.catalog import Customer, Item, LmeBand, fiscal_year, month_key
from dw_sales.domain.messages import InboundMessage

pytestmark = pytest.mark.unit

SCOPE = SalesScope(TenantId(uuid.UUID(int=1)), WorkspaceId(uuid.UUID(int=2)))
README = (MOCK_ROOT / "README.md").read_text(encoding="utf-8")

# The findings table of `.claude/plans/sales/dw1-portal-demo/spec.md`. Ticket 02
# gives these codes an owner in code; this copy is what coverage is held to.
SPEC_FINDINGS = frozenset(
    {
        "code_unmapped",
        "code_ambiguous",
        "price_mismatch",
        "quotation_missing",
        "lme_band_mismatch",
        "moq_violation",
        "pack_multiple",
        "requested_date_short_lt",
        "missing_noc_esf",
        "duplicate_po",
        "revised_po",
    }
)
# A price that differs from its quotation differs by at least this much.
PRICE_MARGIN = Decimal("0.02")

# (finding code, PO line number, or None for the message as a whole)
type Finding = tuple[str, int | None]

_CODE = re.compile(r"`([^`]+)`")
_FINDING = re.compile(r"`(\w+)`(?:\s*\(line (\d+)\))?")
_QUOTE_NO = re.compile(r"`(Q\d{2}-\d{4})`")


@dataclass(frozen=True)
class Outcome:
    customer: str
    classification: str
    findings: frozenset[Finding]


@dataclass(frozen=True)
class RequestEvidence:
    customer: str
    item: str  # a PRV code, or "new"
    target_price: Decimal | None
    own_quotations: tuple[str, ...]
    others_valid_quotations: tuple[str, ...]


@pytest.fixture(scope="module")
def catalog() -> MockSalesCatalog:
    return MockSalesCatalog.load()


@pytest.fixture(scope="module")
def inbox() -> MockInbox:
    return MockInbox.load()


# ------------------------------------------------------------ the README --


def _table(heading: str) -> list[list[str]]:
    """The rows of the table under ``## heading``, header and rule excluded."""
    section = README.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0]
    return [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in section.splitlines()
        if line.startswith("| `")
    ]


def _claimed_outcomes() -> dict[str, Outcome]:
    claims: dict[str, Outcome] = {}
    for message, customer, _scenario, _attachment, classification, findings in _table("Messages"):
        claims[_CODE.findall(message)[0]] = Outcome(
            customer=_CODE.findall(customer)[0],
            classification=_CODE.findall(classification)[0],
            findings=frozenset(
                (code, int(line) if line else None) for code, line in _FINDING.findall(findings)
            ),
        )
    return claims


def _claimed_evidence() -> dict[str, RequestEvidence]:
    claims: dict[str, RequestEvidence] = {}
    for message, customer, item, target, own, others in _table("Quote requests"):
        price = re.search(r"\d+\.\d+", target)
        claims[_CODE.findall(message)[0]] = RequestEvidence(
            customer=_CODE.findall(customer)[0],
            item=(_CODE.findall(item) or ["new"])[0],
            target_price=Decimal(price.group()) if price else None,
            own_quotations=tuple(_QUOTE_NO.findall(own)),
            others_valid_quotations=tuple(_QUOTE_NO.findall(others)),
        )
    return claims


# ------------------------------------------- the rules, read plainly ------


def _states(stated: StatedAttributes, item: Item) -> bool:
    """Every attribute the line states is the item's."""
    known = StatedAttributes.of_item(item)
    return all(value is None or getattr(known, name) == value for name, value in stated)


async def _resolve(
    catalog: MockSalesCatalog, customer: Customer, code: str, stated: StatedAttributes | None
) -> Item | str:
    """The item a line names, or the finding code that says why it names none."""
    entry = await catalog.convert_entry(SCOPE, customer.code, code)
    if entry is not None:
        item = await catalog.item_by_prv_code(SCOPE, entry.prv_code)
        assert item is not None
        assert stated is None or _states(stated, item), f"{code} describes another item"
        return item
    assert stated is not None, f"{code} has no convert entry and states nothing"
    candidates = [item for item in await catalog.items(SCOPE) if _states(stated, item)]
    if not candidates:
        return "code_unmapped"
    if len(candidates) > 1:
        return "code_ambiguous"
    return candidates[0]


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
    valid = await catalog.quotations_valid_on(SCOPE, customer.code, item.prv_code, po.po_date)
    on_arrival = await catalog.quotations_valid_on(SCOPE, customer.code, item.prv_code, received)
    assert valid == on_arrival, f"{label}: validity depends on which date is read"
    assert len(valid) <= 1, f"{label}: two valid quotations, a check would have to choose"
    quotation = valid[0] if valid else None
    if quotation is None:
        found.add("quotation_missing")
    else:
        assert quotation.currency == po.currency, label
        if line.unit_price != quotation.unit_price:
            gap = abs(line.unit_price - quotation.unit_price)
            assert gap >= quotation.unit_price * PRICE_MARGIN, f"{label}: within any tolerance"
            found.add("price_mismatch")
        if isinstance(quotation.copper_basis, LmeBand):
            month_before = po.po_date.replace(day=1) - timedelta(days=1)
            verdicts = set()
            for month in (month_key(po.po_date), month_key(month_before)):
                lme = await catalog.lme_for_month(SCOPE, month)
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
    return found


async def _order_outcome(
    catalog: MockSalesCatalog,
    customer: Customer,
    message: InboundMessage,
    po: PurchaseOrderDocument,
    revisions: dict[tuple[str, str], list[int]],
) -> Outcome:
    received = message.received_at.date()
    findings: set[Finding] = set()
    earlier = revisions.setdefault((customer.code, po.po_no), [])
    classification = "po"
    if any(revision < po.revision for revision in earlier):
        classification = "revised_po"
        findings.add(("revised_po", None))
    elif po.revision in earlier:
        findings.add(("duplicate_po", None))
    else:
        assert po.revision == 0, f"{message.message_id}: a revision with no earlier PO"
    earlier.append(po.revision)

    assert fiscal_year(po.po_date) == fiscal_year(received), message.message_id
    compliance = customer.compliance
    if not compliance.noc_confirmed or compliance.esf_fiscal_year != fiscal_year(po.po_date):
        findings.add(("missing_noc_esf", None))

    for line in po.lines:
        resolved = await _resolve(catalog, customer, line.customer_item_code, line.attributes)
        if isinstance(resolved, str):
            findings.add((resolved, line.no))
            continue
        line_findings = await _line_findings(catalog, customer, po, received, line, resolved)
        findings |= {(code, line.no) for code in line_findings}
    return Outcome(customer.code, classification, frozenset(findings))


async def _outcomes(catalog: MockSalesCatalog, inbox: MockInbox) -> dict[str, Outcome]:
    orders = {po.message_id: po for po in load_purchase_orders()}
    requests = {rfq.message_id: rfq for rfq in load_quote_requests()}
    revisions: dict[tuple[str, str], list[int]] = {}
    outcomes: dict[str, Outcome] = {}
    for message in await inbox.list_messages(SCOPE):
        customer = await catalog.customer_by_email_domain(SCOPE, message.sender.domain)
        assert customer is not None, f"{message.message_id} comes from no customer's domain"
        po = orders.get(message.message_id)
        rfq = requests.get(message.message_id)
        if po is not None:
            assert po.customer_code == customer.code, message.message_id
            outcome = await _order_outcome(catalog, customer, message, po, revisions)
        elif rfq is not None:
            assert rfq.customer_code == customer.code, message.message_id
            outcome = Outcome(customer.code, "quote_request", frozenset())
        else:
            assert not message.attachments, f"{message.message_id} carries no known document"
            outcome = Outcome(customer.code, "other", frozenset())
        outcomes[message.message_id] = outcome
    return outcomes


async def _request_evidence(
    catalog: MockSalesCatalog, rfq: QuoteRequestDocument
) -> RequestEvidence:
    customer = await catalog.customer_by_code(SCOPE, rfq.customer_code)
    assert customer is not None
    (line,) = rfq.lines
    resolved = await _resolve(catalog, customer, line.customer_item_code, line.attributes)
    if isinstance(resolved, str):
        assert resolved == "code_unmapped", f"{rfq.message_id}: {resolved}"
        return RequestEvidence(customer.code, "new", line.target_price, (), ())
    quotations = await catalog.quotations_for_item(SCOPE, resolved.prv_code)
    own = [q for q in quotations if q.customer_code == customer.code]
    assert not any(q.is_valid_on(rfq.rfq_date) for q in own), (
        f"{rfq.message_id}: the requester already holds a valid price"
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
    )


# ---------------------------------------------------------------- tests --


async def test_each_message_triggers_what_the_readme_says_and_nothing_else(
    catalog: MockSalesCatalog, inbox: MockInbox
) -> None:
    assert await _outcomes(catalog, inbox) == _claimed_outcomes()


async def test_each_quote_request_has_the_evidence_the_readme_lists(
    catalog: MockSalesCatalog,
) -> None:
    observed = {
        rfq.message_id: await _request_evidence(catalog, rfq) for rfq in load_quote_requests()
    }

    assert observed == _claimed_evidence()


async def test_each_message_carries_the_attachment_the_readme_names(inbox: MockInbox) -> None:
    claimed = {
        _CODE.findall(message)[0]: tuple(_CODE.findall(attachment))
        for message, _customer, _scenario, attachment, _class, _findings in _table("Messages")
    }
    carried = {
        message.message_id: tuple(attachment.name for attachment in message.attachments)
        for message in await inbox.list_messages(SCOPE)
    }

    assert carried == claimed


def test_every_finding_in_the_spec_is_triggered_by_a_mock_email() -> None:
    claimed = {code for outcome in _claimed_outcomes().values() for code, _ in outcome.findings}

    assert sorted(SPEC_FINDINGS - claimed) == [], "no mock email triggers these"
    assert sorted(claimed - SPEC_FINDINGS) == [], "the README names findings the spec lacks"


def test_the_master_data_counts_in_the_readme_are_the_fixtures() -> None:
    rows = _table("Master data")

    assert rows
    for file_cell, records, _what in rows:
        name = _CODE.findall(file_cell)[0]
        assert len(json.loads((DATA_DIR / name).read_text(encoding="utf-8"))) == int(records), name


async def test_every_sender_is_a_contact_of_the_customer_its_domain_names(
    catalog: MockSalesCatalog, inbox: MockInbox
) -> None:
    """A reply can go back to the sender without leaving the customer's contacts."""
    for message in await inbox.list_messages(SCOPE):
        customer = await catalog.customer_by_email_domain(SCOPE, message.sender.domain)
        assert customer is not None
        assert message.sender.address in {c.address for c in customer.contacts}, message.message_id


async def test_every_address_and_domain_in_the_fixtures_is_fictional(
    catalog: MockSalesCatalog,
) -> None:
    """The repository is public: no real domain, and no customer document."""
    # The JSON, and the generator: its constants (the seller's name, every
    # label) are printed into every attachment.
    sources = [*sorted(DATA_DIR.glob("*.json")), MOCK_ROOT / "generate_attachments.py"]
    text = "\n".join(path.read_text(encoding="utf-8") for path in sources)
    domains = set(re.findall(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)", text))
    # A customer may list a domain no address in the fixtures uses.
    domains |= {domain for c in await catalog.customers(SCOPE) for domain in c.email_domains}

    assert domains
    assert sorted(d for d in domains if not d.endswith(".example")) == []
    assert "proterial" not in text.lower()
