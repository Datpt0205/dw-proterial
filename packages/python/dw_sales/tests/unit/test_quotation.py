"""The quotation flow over the mock mailbox and master data, policies as shipped.

Golden expectations for the requests and Design replies in the mock mailbox
(`adapters/mock/README.md`, "Quote requests", "Design replies" and "Yearly
screening").
"""

from __future__ import annotations

import hashlib
import io
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml
from openpyxl import load_workbook
from pydantic import ValidationError

from dw_kernel.errors import ConflictError, NotFoundError, PermissionDeniedError
from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.adapters.mock import MockInbox, MockSalesCatalog
from dw_sales.adapters.mock.generate_attachments import load_quote_requests
from dw_sales.adapters.rfq_excel import ExcelDesignReplyReader, ExcelRfqReader
from dw_sales.application.ports import SalesScope
from dw_sales.application.quotation import (
    NotADesignReplyError,
    QuotationService,
    QuoteRules,
    ReplyAttached,
    ReplyUnmatched,
    RequestNotExtractedError,
    ScreeningRow,
)
from dw_sales.domain.catalog import LmeBand, LmeMonth, Quotation
from dw_sales.domain.messages import Attachment, EmailAddress, InboundMessage
from dw_sales.domain.pricing import SalesPricing
from dw_sales.domain.quotes import (
    DeclineReason,
    LinePrice,
    PricingDecision,
    QuoteActor,
    QuoteCapability,
    QuoteCase,
    QuoteFindingCode,
    QuoteStatus,
)

pytestmark = pytest.mark.unit

SCOPE = SalesScope(TenantId(uuid.UUID(int=1)), WorkspaceId(uuid.UUID(int=2)))
OTHER_TENANT = SalesScope(TenantId(uuid.UUID(int=9)), WorkspaceId(uuid.UUID(int=10)))
POLICIES = Path(__file__).resolve().parents[5] / "configs" / "policies"
PRICER = uuid.UUID(int=101)  # the quotation PIC
HEAD = uuid.UUID(int=102)
DEPUTY = uuid.UUID(int=104)
APPROVE = frozenset({QuoteCapability.APPROVE})
AT = datetime(2026, 10, 2, 2, 0, tzinfo=UTC)
ISSUED = date(2026, 10, 2)
BAND = LmeBand(low_usd_per_tonne=Decimal(10500), high_usd_per_tonne=Decimal(11000))
# Sales' price for M10: above the target, and not any other customer's price.
DECIDED = Decimal("0.6890")
# What only Sales may see for M10: the other customers' prices and the reference.
INTERNAL_PRICES = ("0.7120", "0.6980", "0.7050")


def _yaml(name: str) -> dict[str, Any]:
    raw = yaml.safe_load((POLICIES / name).read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


RULES = QuoteRules.model_validate(_yaml("sales_quote_rules@1.0.0.yaml"))
PRICING = SalesPricing.model_validate(_yaml("sales_pricing@1.0.0.yaml"))


class FakeCases:
    """`QuoteCaseLookupPort` over cases held per scope, as the store holds them."""

    def __init__(self) -> None:
        self._cases: dict[tuple[SalesScope, uuid.UUID], QuoteCase] = {}

    def put(self, scope: SalesScope, case: QuoteCase) -> QuoteCase:
        self._cases[(scope, case.case_id)] = case
        return case

    async def cases_for_ycbg(self, scope: SalesScope, ycbg_no: str) -> Sequence[QuoteCase]:
        return [
            case
            for (held_scope, _), case in self._cases.items()
            if held_scope == scope and case.ycbg is not None and case.ycbg.ycbg_no == ycbg_no
        ]


class RefusingLedger:
    """A production ledger before the customer grants write access."""

    async def record(self, scope: SalesScope, rows: Sequence[Quotation]) -> None:
        raise PermissionDeniedError("no write access to the master list")


def _service(
    *,
    catalog: MockSalesCatalog | None = None,
    inbox: MockInbox | None = None,
    cases: FakeCases | None = None,
    ledger: Any = None,
    rules: QuoteRules = RULES,
) -> QuotationService:
    catalog = catalog or MockSalesCatalog.load()
    return QuotationService(
        catalog=catalog,
        inbox=inbox or MockInbox.load(),
        rfq_reader=ExcelRfqReader(),
        reply_reader=ExcelDesignReplyReader(),
        cases=cases or FakeCases(),
        ledger=ledger or catalog,
        rules=rules,
        pricing=PRICING,
    )


async def _awaiting_design(service: QuotationService, message_id: str, ycbg_no: str) -> QuoteCase:
    case = QuoteCase.open(uuid.uuid4(), await service.extract_request(SCOPE, message_id))
    return case.draft_ycbg().record_ycbg(ycbg_no, by=PRICER, at=AT).send_to_design()


async def _m10_replied(service: QuotationService, cases: FakeCases) -> QuoteCase:
    cases.put(SCOPE, await _awaiting_design(service, "M10", "YCBG-2609-030"))
    outcome = await service.take_design_reply(SCOPE, "M25")
    assert isinstance(outcome, ReplyAttached)
    return cases.put(SCOPE, outcome.case)


def _decision(
    price: Decimal = DECIDED,
    *,
    by: uuid.UUID = PRICER,
    basis: Any = BAND,
    guidance: str | None = None,
) -> PricingDecision:
    return PricingDecision(
        decided_by=by,
        decided_at=AT,
        lme=LmeMonth(month="2026-09", usd_per_tonne=Decimal(10870)),
        lines=(
            LinePrice(
                line_no=1,
                unit_price=price,
                moq=Decimal(3000),
                lead_time_days=45,
                copper_basis=basis,
            ),
        ),
        management_guidance=guidance,
    )


# ------------------------------------------------------------- the policy --


def test_the_shipped_policy_is_valid_and_named_for_its_version() -> None:
    assert f"{RULES.version}.yaml" == "sales_quote_rules@1.0.0.yaml"
    assert RULES.copper_basis == "lme_band"
    assert RULES.reference_price is not None


@pytest.mark.parametrize(
    "change",
    [
        {"copper_basis": "floating"},
        {"validity_days": 0},
        {"reference_price": {"band_below_percent": 100, "band_above_percent": 10}},
        {"approval": {"separate_from_pricer": False}},
    ],
)
def test_a_policy_with_an_impossible_or_unknown_rule_is_refused(change: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        QuoteRules.model_validate(_yaml("sales_quote_rules@1.0.0.yaml") | change)


def test_a_policy_says_whether_it_offers_a_reference_rather_than_forgetting_to() -> None:
    raw = _yaml("sales_quote_rules@1.0.0.yaml")
    assert QuoteRules.model_validate(raw | {"reference_price": None}).reference_price is None
    del raw["reference_price"]
    with pytest.raises(ValidationError):
        QuoteRules.model_validate(raw)


# ---------------------------------------------------------- step 1: read --


async def test_m10_is_read_with_every_value_and_the_quote_due_date_anchored() -> None:
    request = await _service().extract_request(SCOPE, "M10")
    document = request.document

    assert (request.customer_code, request.customer_from) == ("KMH", "sender_domain")
    assert document.quote_due is not None
    assert (document.quote_due.value, document.quote_due.source.cell_ref) == (
        date(2026, 10, 7),
        "見積依頼!B5",
    )
    (item,) = document.items
    assert item.target_price is not None and item.target_price.value == Decimal("0.6500")
    assert {a.attachment_sha256 for a in document.anchors()} == {request.attachment.sha256}


async def test_every_quote_request_in_the_mailbox_reads_back_as_its_fixture_says() -> None:
    service = _service()
    for fixture in load_quote_requests():
        request = await service.extract_request(SCOPE, fixture.message_id)
        document = request.document
        assert request.customer_code == fixture.customer_code, fixture.message_id
        assert document.rfq_no.value == fixture.rfq_no
        assert document.quote_due is not None and document.quote_due.value == fixture.quote_due
        assert [(i.line_no, i.quantity.value, i.needed_by.value) for i in document.items] == [
            (line.no, line.quantity, line.required_date) for line in fixture.lines
        ]


async def test_m14_forwarded_by_the_sales_manager_names_its_buyer_and_waits_for_sales() -> None:
    request = await _service().extract_request(SCOPE, "M14")
    case = QuoteCase.open(uuid.uuid4(), request)

    assert (request.customer_code, request.customer_from) == ("VLX", "named_buyer")
    assert [f.code for f in case.findings] == [QuoteFindingCode.CUSTOMER_UNKNOWN]


async def test_m23_with_a_blank_quantity_opens_a_case_with_rfq_incomplete() -> None:
    case = QuoteCase.open(uuid.uuid4(), await _service().extract_request(SCOPE, "M23"))

    (finding,) = case.findings
    assert (finding.code, finding.line_no, finding.missing) == (
        QuoteFindingCode.RFQ_INCOMPLETE,
        1,
        ("quantity",),
    )
    with pytest.raises(ConflictError, match="findings are answered"):
        await _service().design_request(SCOPE, case)


@pytest.mark.parametrize("message_id", ["M01", "M03", "M25"])
async def test_a_message_without_a_request_file_is_not_read_as_a_request(message_id: str) -> None:
    with pytest.raises(RequestNotExtractedError) as refused:
        await _service().extract_request(SCOPE, message_id)

    assert refused.value.reason == "no_request_file"


async def test_a_message_the_mailbox_does_not_hold_is_not_found() -> None:
    with pytest.raises(NotFoundError):
        await _service().extract_request(SCOPE, "M99")


async def _file(message_id: str) -> tuple[str, bytes]:
    inbox = MockInbox.load()
    message = await inbox.get_message(SCOPE, message_id)
    assert message is not None
    (attachment,) = message.attachments
    content = await inbox.read_attachment(SCOPE, message_id, attachment.attachment_id)
    assert content is not None
    return attachment.name, content.data


def _mailbox(sender: str, *files: tuple[str, bytes]) -> MockInbox:
    """A mailbox holding one message, ``X1``, from ``sender`` with ``files``."""
    attachments = tuple(
        Attachment(
            attachment_id=f"X-A{index}",
            name=name,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )
        for index, (name, data) in enumerate(files, start=1)
    )
    message = InboundMessage(
        message_id="X1",
        sender=EmailAddress(address=sender),
        subject="RFQ",
        received_at=datetime(2026, 9, 30, 3, 0, tzinfo=UTC),
        body_text="",
        attachments=attachments,
    )
    contents = {
        ("X1", a.attachment_id): data for a, (_, data) in zip(attachments, files, strict=True)
    }
    return MockInbox([message], contents)


async def test_a_look_alike_sender_is_not_the_customer_the_printed_buyer_may_be() -> None:
    """The domain matches no customer, so the customer is the buyer M10's file
    prints, and Sales must confirm it (`customer_unknown`)."""
    mailbox = _mailbox("buyer@kumohana-mail.example", await _file("M10"))

    request = await _service(inbox=mailbox).extract_request(SCOPE, "X1")

    assert (request.customer_code, request.customer_from) == ("KMH", "named_buyer")


async def test_a_request_whose_sender_and_buyer_name_no_customer_is_routed_not_guessed() -> None:
    name, data = await _file("M10")
    workbook = load_workbook(io.BytesIO(data))
    workbook.worksheets[0]["A1"] = "KUMOHANA DEVICES VIETNAM"  # not the exact name
    buffer = io.BytesIO()
    workbook.save(buffer)
    mailbox = _mailbox("buyer@kumohana-mail.example", (name, buffer.getvalue()))

    with pytest.raises(RequestNotExtractedError) as refused:
        await _service(inbox=mailbox).extract_request(SCOPE, "X1")

    assert refused.value.reason == "customer_unknown"


async def test_a_message_with_two_request_files_is_left_to_a_person() -> None:
    mailbox = _mailbox("purchasing@kumohana.example", await _file("M10"), await _file("M09"))

    with pytest.raises(RequestNotExtractedError) as refused:
        await _service(inbox=mailbox).extract_request(SCOPE, "X1")

    assert refused.value.reason == "several_request_files"


# ------------------------------------------------- steps 2-3: YCBG draft --


async def test_the_design_request_names_the_known_item_and_no_price() -> None:
    service = _service()
    case = QuoteCase.open(uuid.uuid4(), await service.extract_request(SCOPE, "M10"))
    draft = await service.design_request(SCOPE, case)

    (line,) = draft.lines
    assert (line.known_prv_code, line.quantity) == ("CB-2007", Decimal(9000))
    assert draft.quote_due == date(2026, 10, 7)
    assert "0.65" not in draft.model_dump_json()


async def test_a_code_the_convert_list_does_not_know_goes_to_design_as_new() -> None:
    service = _service()
    case = QuoteCase.open(uuid.uuid4(), await service.extract_request(SCOPE, "M09"))

    (line,) = (await service.design_request(SCOPE, case)).lines
    assert line.known_prv_code is None


# --------------------------------------------- step 4: Design's reply --


async def test_design_reply_is_attached_to_the_case_waiting_under_its_ycbg_number() -> None:
    cases = FakeCases()
    case = await _m10_replied(_service(cases=cases), cases)

    assert case.status is QuoteStatus.DESIGN_REPLIED
    assert case.design_reply is not None and case.design_reply.message_id == "M25"


async def test_a_reply_quoting_a_ycbg_no_case_holds_is_routed_to_sales() -> None:
    cases = FakeCases()
    service = _service(cases=cases)
    cases.put(SCOPE, await _awaiting_design(service, "M10", "YCBG-2609-030"))

    outcome = await service.take_design_reply(SCOPE, "M32")

    assert outcome == ReplyUnmatched(message_id="M32", ycbg_no="YCBG-2608-044")
    disposition = outcome.disposition
    assert (disposition.kind, disposition.reason) == ("routed_to_sales", "design_reply_unmatched")
    assert disposition.owner is not None and disposition.case_id is None


async def test_an_attached_reply_is_the_messages_disposition_on_its_quote_case() -> None:
    cases = FakeCases()
    service = _service(cases=cases)
    waiting = cases.put(SCOPE, await _awaiting_design(service, "M10", "YCBG-2609-030"))

    outcome = await service.take_design_reply(SCOPE, "M25")

    assert isinstance(outcome, ReplyAttached)
    disposition = outcome.disposition
    assert (disposition.message_id, disposition.kind, disposition.case_kind) == (
        "M25",
        "attached_to_case",
        "quote",
    )
    assert disposition.case_id == waiting.case_id


async def test_a_reply_answering_other_lines_than_its_case_asked_is_routed_not_an_error() -> None:
    """M25 answers line 1. A case under its YCBG that asked lines 1 and 2 is
    not handed a reply missing line 2: the message is routed, with a reason,
    instead of failing the case's own check and ending with no disposition."""
    cases = FakeCases()
    service = _service(cases=cases)
    waiting = await _awaiting_design(service, "M10", "YCBG-2609-030")
    document = waiting.request.document
    (item,) = document.items
    two_lines = document.model_copy(
        update={"items": (item, item.model_copy(update={"line_no": 2}))}
    )
    request = waiting.request.model_copy(update={"document": two_lines})
    cases.put(SCOPE, waiting.model_copy(update={"request": request}))

    outcome = await service.take_design_reply(SCOPE, "M25")

    assert isinstance(outcome, ReplyUnmatched)
    assert (outcome.disposition.kind, outcome.disposition.reason) == ("routed_to_sales", "other")


async def test_a_reply_is_matched_by_ycbg_number_only_never_by_customer_or_request() -> None:
    """M25 answers KMH's M10. A case for that very request, recorded under
    another YCBG number, is not matched: nothing but the number is compared."""
    cases = FakeCases()
    service = _service(cases=cases)
    cases.put(SCOPE, await _awaiting_design(service, "M10", "YCBG-2609-031"))

    outcome = await service.take_design_reply(SCOPE, "M25")

    assert isinstance(outcome, ReplyUnmatched)


async def test_a_reply_for_a_case_no_longer_waiting_on_design_is_routed() -> None:
    cases = FakeCases()
    service = _service(cases=cases)
    waiting = await _awaiting_design(service, "M10", "YCBG-2609-030")
    cases.put(SCOPE, waiting.decline_request(by=PRICER, at=AT, reason=DeclineReason.COMMERCIAL))

    assert isinstance(await service.take_design_reply(SCOPE, "M25"), ReplyUnmatched)


async def test_another_tenants_case_under_the_same_ycbg_is_never_matched() -> None:
    cases = FakeCases()
    service = _service(cases=cases)
    cases.put(OTHER_TENANT, await _awaiting_design(service, "M10", "YCBG-2609-030"))

    assert isinstance(await service.take_design_reply(SCOPE, "M25"), ReplyUnmatched)


async def test_a_message_without_a_design_reply_file_is_not_taken_as_one() -> None:
    with pytest.raises(NotADesignReplyError):
        await _service().take_design_reply(SCOPE, "M10")


# ---------------------------------------------------- step 7: evidence --


async def test_m10_evidence_holds_every_factor_sales_weighs() -> None:
    cases = FakeCases()
    service = _service(cases=cases)
    case = await _m10_replied(service, cases)

    (evidence,) = await service.price_evidence(
        SCOPE, case, as_of=date(2026, 10, 2), incoterm="CIF", destination="japan"
    )

    assert evidence.prv_code == "CB-2007"
    assert evidence.target_price == Decimal("0.6500")
    assert [q.quote_no for q in evidence.own_history] == ["Q25-0233"]
    assert sorted(r.quotation.quote_no for r in evidence.other_customers) == [
        "Q26-0104",
        "Q26-0122",
    ]
    assert all(r.internal_only for r in evidence.other_customers)
    assert [line.so_no for line in evidence.orders] == ["SO25-1120"]
    assert evidence.lme is not None and evidence.lme.month == "2026-09"
    assert evidence.copper is not None
    assert evidence.copper.usd_per_uom == Decimal("0.132809")
    assert evidence.floor is not None
    assert evidence.freight is not None and evidence.freight.rate is not None
    assert evidence.freight.rate.usd_per_km == Decimal("19.50")
    assert evidence.reference is not None and evidence.reference.price == Decimal("0.7050")
    assert evidence.pricing_policy == "sales_pricing@1.0.0"


async def test_a_lane_the_policy_has_no_freight_rate_for_says_so() -> None:
    cases = FakeCases()
    service = _service(cases=cases)
    case = await _m10_replied(service, cases)

    (evidence,) = await service.price_evidence(
        SCOPE, case, as_of=date(2026, 10, 2), incoterm="DDP", destination="japan"
    )

    assert evidence.freight is not None and evidence.freight.rate is None


async def test_evidence_waits_for_design() -> None:
    service = _service()
    case = await _awaiting_design(service, "M10", "YCBG-2609-030")

    with pytest.raises(ConflictError):
        await service.price_evidence(SCOPE, case, as_of=date(2026, 10, 2))


# --------------------------------------------------- step 7: the price --


@pytest.mark.parametrize(
    ("price", "basis", "raised"),
    [
        (Decimal("0.1500"), BAND, {QuoteFindingCode.PRICE_BELOW_POLICY_FLOOR}),
        (Decimal("0.6400"), {"kind": "fixed"}, {QuoteFindingCode.PRICE_BASIS_MISMATCH}),
        (DECIDED, BAND, {QuoteFindingCode.ABOVE_TARGET_PRICE}),
        (Decimal("0.6400"), BAND, set()),
    ],
    ids=["below_floor", "basis_mismatch", "above_target", "clean"],
)
async def test_a_decided_price_raises_exactly_the_quotation_findings_it_calls_for(
    price: Decimal, basis: Any, raised: set[QuoteFindingCode]
) -> None:
    cases = FakeCases()
    service = _service(cases=cases)
    case = await _m10_replied(service, cases)

    priced = await service.decide_price(SCOPE, case, _decision(price, basis=basis))

    assert priced.status is QuoteStatus.PRICED
    assert {f.code for f in priced.findings} == raised


async def test_a_decision_stating_an_lme_figure_other_than_the_recorded_one_is_refused() -> None:
    """The floor is computed from the figure the decision carries: a lower
    figure for the right month would lower the floor and hide
    `price_below_policy_floor`."""
    cases = FakeCases()
    service = _service(cases=cases)
    case = await _m10_replied(service, cases)
    honest = _decision(Decimal("0.1500"))
    forged = honest.model_copy(
        update={"lme": LmeMonth(month="2026-09", usd_per_tonne=Decimal(1000))}
    )

    with pytest.raises(ConflictError):
        await service.decide_price(SCOPE, case, forged)
    with pytest.raises(ConflictError):
        await service.decide_price(
            SCOPE,
            case,
            honest.model_copy(
                update={
                    "lme": None,
                    "lines": (
                        honest.lines[0].model_copy(update={"copper_basis": {"kind": "fixed"}}),
                    ),
                }
            ),
        )
    priced = await service.decide_price(SCOPE, case, honest)
    assert QuoteFindingCode.PRICE_BELOW_POLICY_FLOOR in {f.code for f in priced.findings}


# ------------------------------------- steps 8-11: document to master list --


async def _submitted(
    service: QuotationService, cases: FakeCases, *, by: uuid.UUID = PRICER, **kw: Any
) -> QuoteCase:
    case = await service.decide_price(
        SCOPE, await _m10_replied(service, cases), _decision(by=by, **kw)
    )
    return await service.submit(SCOPE, case, quote_no="Q26-0301", issued_on=ISSUED, by=by, at=AT)


@pytest.mark.parametrize("price", ["0.1500", "0.6400", "0.6890", "0.7120", "0.9999"])
async def test_another_customers_price_never_reaches_the_customer_document(price: str) -> None:
    """Red if anything internal reaches what the customer receives: the other
    customers' prices, the reference, or the management guidance. A decided
    price equal to another customer's is Sales' decision and is allowed."""
    cases = FakeCases()
    service = _service(cases=cases)
    guidance = "Chỉ đạo nội bộ: không thấp hơn giá khách khác"
    case = await _submitted(service, cases, price=Decimal(price), guidance=guidance)
    assert case.submission is not None

    text = case.submission.document.model_dump_json()
    assert guidance not in text
    for internal in INTERNAL_PRICES:
        if internal != price:
            assert internal not in text, internal


async def test_the_document_carries_every_field_the_quotation_needs() -> None:
    cases = FakeCases()
    case = await _submitted(_service(cases=cases), cases)
    assert case.submission is not None
    document = case.submission.document

    assert (document.addressee.code, document.their_reference) == ("KMH", "KMH-RFQ-260930-02")
    assert [r.address for r in document.recipients] == ["takumi.arai@vn.kumohana.example"]
    assert (document.issued_on, document.valid_to) == (ISSUED, date(2026, 12, 30))
    assert document.lme is not None and document.lme.month == "2026-09"
    (line,) = document.lines
    assert (line.bp_code, line.spec_no, line.prv_code) == ("BP-25-0187", "SP-5406", "CB-2007")
    assert (line.unit_price, line.moq, line.lead_time_days, line.copper_basis) == (
        DECIDED,
        Decimal(3000),
        45,
        BAND,
    )
    assert case.submission.priced_by == PRICER


async def test_the_document_is_written_only_from_a_priced_case() -> None:
    cases = FakeCases()
    service = _service(cases=cases)
    case = await _m10_replied(service, cases)

    with pytest.raises(ConflictError):
        await service.quotation_document(SCOPE, case, quote_no="Q26-0301", issued_on=ISSUED)


async def test_the_quote_to_order_loop_closes_through_the_master_list() -> None:
    """After M10's master-list row is recorded, a later PO line for the item
    finds the quotation through `quotations_valid_on`."""
    catalog = MockSalesCatalog.load()
    cases = FakeCases()
    service = _service(catalog=catalog, cases=cases)
    submitted = await _submitted(service, cases)
    assert submitted.submission is not None
    later = date(2026, 11, 3)
    assert not (await catalog.quotations_valid_on(SCOPE, "KMH", "CB-2007", later)).data

    approved = submitted.approve(
        QuoteActor(user_id=HEAD, capabilities=APPROVE),
        at=AT,
        document_sha256=submitted.submission.document_sha256,
    )
    sent = approved.mark_sent(by=PRICER, at=AT)
    recorded = await service.record_master_list(SCOPE, sent, by=PRICER, at=AT)

    assert recorded.status is QuoteStatus.MASTER_LIST_RECORDED
    (found,) = (await catalog.quotations_valid_on(SCOPE, "KMH", "CB-2007", later)).data
    assert (found.quote_no, found.unit_price) == ("Q26-0301", DECIDED)
    # Recording again changes nothing.
    await catalog.record(SCOPE, sent.master_list_rows())
    assert len((await catalog.quotations_valid_on(SCOPE, "KMH", "CB-2007", later)).data) == 1


async def test_a_deputy_approves_a_quote_the_head_priced() -> None:
    cases = FakeCases()
    submitted = await _submitted(_service(cases=cases), cases, by=HEAD)
    assert submitted.submission is not None

    approved = submitted.approve(
        QuoteActor(user_id=DEPUTY, capabilities=APPROVE),
        at=AT,
        document_sha256=submitted.submission.document_sha256,
    )
    assert approved.approval is not None and approved.approval.approved_by == DEPUTY
    with pytest.raises(ConflictError, match="separation of duties"):
        submitted.approve(
            QuoteActor(user_id=HEAD, capabilities=APPROVE),
            at=AT,
            document_sha256=submitted.submission.document_sha256,
        )


async def test_the_quotation_pic_cannot_approve_without_the_approver_set() -> None:
    cases = FakeCases()
    submitted = await _submitted(_service(cases=cases), cases)
    assert submitted.submission is not None

    with pytest.raises(PermissionDeniedError):
        submitted.approve(
            QuoteActor(user_id=PRICER),
            at=AT,
            document_sha256=submitted.submission.document_sha256,
        )


async def test_a_ledger_that_refuses_leaves_the_case_sent() -> None:
    cases = FakeCases()
    service = _service(cases=cases, ledger=RefusingLedger())
    submitted = await _submitted(service, cases)
    assert submitted.submission is not None
    sent = submitted.approve(
        QuoteActor(user_id=HEAD, capabilities=APPROVE),
        at=AT,
        document_sha256=submitted.submission.document_sha256,
    ).mark_sent(by=PRICER, at=AT)

    with pytest.raises(PermissionDeniedError):
        await service.record_master_list(SCOPE, sent, by=PRICER, at=AT)
    assert sent.status is QuoteStatus.SENT


async def test_the_mock_ledger_refuses_other_terms_under_a_recorded_number() -> None:
    catalog = MockSalesCatalog.load()
    (existing,) = [q for q in (await catalog.quotations(SCOPE)).data if q.quote_no == "Q26-0104"]

    with pytest.raises(ConflictError):
        await catalog.record(SCOPE, [existing.model_copy(update={"unit_price": Decimal("0.1")})])
    with pytest.raises(ConflictError):
        await catalog.record(SCOPE, [existing.model_copy(update={"customer_code": "KMH"})])


# ------------------------------------------------- step 12: screening --


async def test_screening_lists_exactly_what_the_mock_erp_history_implies() -> None:
    rows = await _service().screening(SCOPE, date(2026, 9, 30))

    assert rows == (
        ScreeningRow(customer_code="CVG", prv_code="CB-2008", quote_nos=("Q26-0166",)),
        ScreeningRow(customer_code="NRV", prv_code="CB-2006", quote_nos=("Q26-0123",)),
        ScreeningRow(customer_code="QRL", prv_code="CB-2013", quote_nos=("Q26-0204",)),
    )
