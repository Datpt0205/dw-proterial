"""The quotation flow reads a request no reader reads through a model, where
it may, and every value it read is Sales' to confirm (ticket 29, dw_sales
ADR 0005).

`QuotationService` over the mock mailbox (M37: the mail body, M38: a text
PDF, M39: the customer's own sheet) with a scripted model (`Recorded`).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.budget import BudgetExceededError
from dw_agent_runtime.model.prompts import PromptRegistry
from dw_kernel.errors import ConflictError, DomainError
from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.adapters.assembly import model_requests
from dw_sales.adapters.mock import MockInbox, MockSalesCatalog
from dw_sales.adapters.mock.fixtures import DATA_DIR
from dw_sales.adapters.order_rules import PlatformOrderRules, load_tenant_order_rules
from dw_sales.adapters.policy_files import load_sales_policies
from dw_sales.adapters.readers.text_parts import AttachmentTexts
from dw_sales.adapters.rfq_excel import ExcelDesignReplyReader, ExcelRfqReader
from dw_sales.application.model_reading import ModelUnavailableError, estimated_tokens
from dw_sales.application.ports import SalesScope
from dw_sales.application.quotation import QuotationService, RequestNotExtractedError
from dw_sales.application.rfq_reading import PROMPT_TOKENS, RFQ_EXTRACTION
from dw_sales.domain.orders import RegionFlag
from dw_sales.domain.quotes import (
    DesignReply,
    LinePrice,
    PricingDecision,
    QuoteCase,
    QuoteFindingCode,
    price_findings,
)
from dw_sales.evals.recorded import Recorded
from dw_sales.evals.world import MemoryStore

pytestmark = pytest.mark.unit

SCOPE = SalesScope(TenantId(uuid.UUID(int=1)), WorkspaceId(uuid.UUID(int=2)))
REPO = Path(__file__).resolve().parents[5]
POLICIES = load_sales_policies(REPO / "configs" / "policies", REPO / "configs" / "copy")
DEMO = load_tenant_order_rules(DATA_DIR / "policies")
PERSON = uuid.UUID(int=0xA1)
AT = datetime(2026, 10, 3, 2, 0, tzinfo=UTC)
RUN = RunContext(
    run_id=uuid.UUID(int=0x29),
    tenant_id=SCOPE.tenant_id.value,
    workspace_id=SCOPE.workspace_id.value,
    actor_id=PERSON,
    worker_id="sales-dw1",
    worker_version="1.0.0",
    channel="web",
    plan_id="professional",
    roles=frozenset(),
    scopes=frozenset(),
    trace_id="t29",
)
M37_LINE_1 = "1. Cáp 2C AWG24 BLK, 1.200 m, cần trước 15/11"
M37_LINE_2 = "2. Dây điện AWG22 màu đỏ lõi xoắn, 3.000 m, cần trước 30/11"
NULLS = {
    "customer_item_code_span": None,
    "quantity_span": None,
    "uom_span": None,
    "required_date_span": None,
    "target_price_span": None,
}
M37 = {
    "rfq_no_span": None,
    "quote_due_span": "20/10/2026",
    "currency_span": "USD",
    "items": [
        NULLS
        | {
            "part": "body",
            "line_span": M37_LINE_1,
            "description_span": "Cáp 2C AWG24 BLK",
            "quantity_span": "1.200 m",
            "required_date_span": "15/11",
        },
        NULLS
        | {
            "part": "body",
            "line_span": M37_LINE_2,
            "description_span": "Dây điện AWG22 màu đỏ lõi xoắn",
            "quantity_span": "3.000 m",
            "required_date_span": "30/11",
        },
    ],
}
M38_LINE_1 = (
    "1. NRV-77-0012 MULTI-CORE CABLE 4C AWG22 BRAID SHIELD GREY - 2,000 m"
    " - by 30 Nov 2026 - target USD 0.95"
)
M38 = {
    "rfq_no_span": "NRV-RFQ-26-0130",
    "quote_due_span": "16 Oct 2026",
    "currency_span": "USD",
    "items": [
        NULLS
        | {
            "part": "M38-A1#p1",
            "line_span": M38_LINE_1,
            "description_span": "MULTI-CORE CABLE 4C AWG22 BRAID SHIELD GREY",
            "customer_item_code_span": "NRV-77-0012",
            "quantity_span": "2,000 m",
            "required_date_span": "30 Nov 2026",
            "target_price_span": "USD 0.95",
        }
    ],
}


class _Down:
    model_profile = "onprem"
    route = "structured_extraction"
    max_input_tokens = 6000

    async def interpret(self, *args: Any, **kwargs: Any) -> Any:
        raise ModelUnavailableError("descriptions are ticket 28's")


def _service(model: Any, *, on: bool = True, inbox: MockInbox | None = None) -> QuotationService:
    assert DEMO is not None
    catalog = MockSalesCatalog.load(SCOPE)
    rules = PlatformOrderRules(DEMO if on else POLICIES.order_rules)
    requests = model_requests(model, catalog, rules)
    # Descriptions are read by ticket 28's reader; here it is down, so a
    # line's candidates say so and nothing else moves.
    reader = requests.reader
    requests = type(requests)(
        reader=type(reader)(
            reader.model, AttachmentTexts(), catalog, type(reader.descriptions)(_Down())
        ),
        rules=rules,
    )
    return QuotationService(
        catalog=catalog,
        inbox=inbox or MockInbox.load(SCOPE),
        rfq_reader=ExcelRfqReader(),
        reply_reader=ExcelDesignReplyReader(),
        cases=MemoryStore(),
        ledger=catalog,
        rules=POLICIES.quote_rules,
        pricing=POLICIES.pricing,
        requests=requests,
    )


async def _open(message_id: str, answer: dict[str, Any], **kwargs: Any) -> QuoteCase:
    return await _service(Recorded(raw=answer), **kwargs).open_case(
        SCOPE, message_id, uuid.UUID(int=7), run=RUN
    )


# ------------------------------------------------------------- reading --


async def test_a_request_in_the_mail_body_opens_a_case_with_every_value_flagged() -> None:
    case = await _open("M37", M37)

    request = case.request
    assert (request.attachment, request.customer_code, request.customer_from) == (
        None,
        "VLX",
        "sender_domain",
    )
    assert request.reading is not None and request.reading.prompt == str(RFQ_EXTRACTION)
    assert request.document.parser_version == "sales.rfq_extraction@1.0.0"
    first, second = request.document.items
    assert (first.quantity.value, str(first.needed_by.value)) == (Decimal(1200), "2026-11-15")
    assert (second.quantity.value, str(second.needed_by.value)) == (Decimal(3000), "2026-11-30")
    for item in request.document.items:
        assert item.model_read == {"description", "quantity", "uom", "needed_by"}
        assert {f.flag for f in item.flags} == {RegionFlag.MODEL_READ}
    assert request.document.model_read == {"currency", "quote_due"}
    # Every value a model read is Sales' to confirm before the YCBG.
    uncertain = {f.line_no: f.flagged for f in case.findings}
    assert uncertain == {
        None: ("currency", "quote_due"),
        1: ("description", "needed_by", "quantity", "uom"),
        2: ("description", "needed_by", "quantity", "uom"),
    }
    assert all(f.blocking and f.code is QuoteFindingCode.VALUE_UNCERTAIN for f in case.findings)
    # The body anchor points at the text the case keeps.
    assert request.body is not None
    chars = first.quantity.source.chars
    assert chars is not None and request.body.text[chars.start : chars.end] == "1.200 m"


async def test_the_quoted_offer_below_m37_is_never_shown_to_the_model() -> None:
    model = Recorded(raw=M37)

    await _service(model).open_case(SCOPE, "M37", uuid.UUID(int=7), run=RUN)

    ((_, _, inputs),) = model.calls
    assert "5.000" not in inputs["parts"] and "01/10" not in inputs["parts"]


async def test_a_stated_target_price_is_the_customers_words_and_never_the_forms() -> None:
    case = await _open("M38", M38)

    (item,) = case.request.document.items
    assert item.target_price is None
    assert item.stated_target_price is not None
    assert item.stated_target_price.value == Decimal("0.95")
    assert item.stated_target_price.source.page == 1


async def test_a_hidden_row_is_never_shown_to_the_model() -> None:
    model = Recorded(raw={**M37, "items": []})

    with pytest.raises(RequestNotExtractedError, match="model_not_understood"):
        await _service(model).open_case(SCOPE, "M39", uuid.UUID(int=7), run=RUN)

    ((_, _, inputs),) = model.calls
    assert "KMH-21-0077" in inputs["parts"] and "KMH-21-0099" not in inputs["parts"]


# ----------------------------------------------------------- the switch --


async def test_with_the_switch_off_no_model_is_asked_and_the_request_is_routed() -> None:
    model = Recorded(raw=M37)

    with pytest.raises(RequestNotExtractedError, match="no_request_file"):
        await _service(model, on=False).open_case(SCOPE, "M37", uuid.UUID(int=7), run=RUN)

    assert model.calls == []


async def test_the_fixed_label_form_is_read_first_and_its_values_are_not_flagged() -> None:
    model = Recorded(failure=AssertionError("a model was asked"))

    case = await _service(model).open_case(SCOPE, "M09", uuid.UUID(int=7), run=RUN)

    assert model.calls == [] and case.request.reading is None
    assert all(not item.flags for item in case.request.document.items)
    assert not any(f.code is QuoteFindingCode.VALUE_UNCERTAIN for f in case.findings)


async def test_a_request_forwarded_by_an_internal_sender_is_customer_unknown_unread() -> None:
    m37 = await MockInbox.load(SCOPE).get_message(SCOPE, "M37")
    assert m37 is not None
    forwarded = m37.model_copy(
        update={"sender": m37.sender.model_copy(update={"address": "sales.manager@seller.example"})}
    )
    model = Recorded(raw=M37)
    service = _service(model, inbox=MockInbox([forwarded], {}, scope=SCOPE))

    with pytest.raises(RequestNotExtractedError, match="customer_unknown"):
        await service.open_case(SCOPE, "M37", uuid.UUID(int=7), run=RUN)
    assert model.calls == []


# ------------------------------------------------------------ degrading --


@pytest.mark.parametrize(
    ("model", "reason"),
    [
        (Recorded(failure=ModelUnavailableError("InfrastructureError")), "model_unavailable"),
        (Recorded(raw={"items": [{"part": "body"}]}), "model_unavailable"),
        (Recorded(raw={**M37, "currency_span": None}), "currency_missing"),
        (
            Recorded(
                raw={
                    **M37,
                    "items": [
                        NULLS | {"part": "body", "line_span": "nowhere", "description_span": "x"}
                    ],
                }
            ),
            "model_not_understood",
        ),
    ],
    ids=["down", "outside_the_schema", "no_currency", "nothing_located"],
)
async def test_no_usable_reading_routes_the_request_as_today(model: Recorded, reason: str) -> None:
    with pytest.raises(RequestNotExtractedError, match=reason):
        await _service(model).open_case(SCOPE, "M37", uuid.UUID(int=7), run=RUN)


async def test_a_spent_budget_stops_the_run() -> None:
    model = Recorded(failure=BudgetExceededError("run reached its input-token ceiling"))

    with pytest.raises(BudgetExceededError):
        await _service(model).open_case(SCOPE, "M37", uuid.UUID(int=7), run=RUN)


async def test_a_request_too_long_for_three_calls_is_not_sent_at_all() -> None:
    m37 = await MockInbox.load(SCOPE).get_message(SCOPE, "M37")
    assert m37 is not None
    long_body = "\n".join(f"Line {n}: please also quote item {n} in USD." for n in range(400))
    message = m37.model_copy(update={"body_text": long_body})
    model = Recorded(failure=AssertionError("sent"))
    service = _service(model, inbox=MockInbox([message], {}, scope=SCOPE))

    with pytest.raises(RequestNotExtractedError, match="request_too_long"):
        await service.open_case(SCOPE, "M37", uuid.UUID(int=7), run=RUN)
    assert model.calls == []


def test_the_prompt_file_is_the_one_the_step_names_and_fits_its_room() -> None:
    prompts = PromptRegistry()
    prompts.load_directory(REPO / "configs" / "prompts")

    rendered = prompts.render(
        RFQ_EXTRACTION.prompt_id, RFQ_EXTRACTION.version, {"parts": ""}, tenant_id=RUN.tenant_id
    )

    assert estimated_tokens(rendered.system + rendered.user) < PROMPT_TOKENS


# ---------------------------------------------------------- confirming --


async def test_sales_confirms_each_value_and_the_finding_is_corrected_at_the_last() -> None:
    case = await _open("M37", M37)

    case = case.confirm_value(1, "quantity", "1250", by=PERSON, at=AT)
    item = case.request.document.item(1)
    assert item.quantity.value == Decimal(1250)
    (finding,) = [f for f in case.findings if f.key == (QuoteFindingCode.VALUE_UNCERTAIN, 1)]
    assert [(c.field, c.read, c.value) for c in finding.confirmed] == [("quantity", "1200", "1250")]
    assert finding.is_open
    for field, value in (
        ("description", "Cáp 2C AWG24 BLK"),
        ("uom", "m"),
        ("needed_by", "2026-11-15"),
    ):
        case = case.confirm_value(1, field, value, by=PERSON, at=AT)
    (finding,) = [f for f in case.findings if f.key == (QuoteFindingCode.VALUE_UNCERTAIN, 1)]
    assert not finding.is_open and finding.disposition.kind == "corrected_by_sales"
    # The flag stays: it says how the value was first read.
    assert "quantity" in case.request.document.item(1).model_read


@pytest.mark.parametrize(
    ("line_no", "field", "value", "error"),
    [
        (1, "quantity", "a lot", DomainError),
        (1, "quantity", "-5", DomainError),
        (1, "needed_by", "15/11", DomainError),
        (1, "uom", "reel", DomainError),
        (None, "currency", "EUR", DomainError),
        (1, "customer_item_code", "X", ConflictError),  # not flagged on M37's line 1
        (3, "quantity", "1", ConflictError),  # no such finding
    ],
)
async def test_a_typed_value_that_is_not_one_of_the_field_is_refused(
    line_no: int | None, field: str, value: str, error: type[Exception]
) -> None:
    case = await _open("M37", M37)

    with pytest.raises(error):
        case.confirm_value(line_no, field, value, by=PERSON, at=AT)


async def test_a_case_with_a_value_to_confirm_cannot_leave_received() -> None:
    case = await _open("M37", M37)

    with pytest.raises(ValueError, match="answered its findings"):
        case.draft_ycbg()


# ----------------------------------------------------- the target price --


async def test_a_stated_target_never_reaches_price_evidence_or_its_finding() -> None:
    """The quotation flow's price evidence and `above_target_price` read the
    form's target price only. Remove the line between the two (a stated
    target copied into ``target_price``) and this goes red."""
    case = await _open("M38", M38)
    for finding in [f for f in case.findings if f.code is QuoteFindingCode.VALUE_UNCERTAIN]:
        for field in finding.flagged:
            current = (
                getattr(case.request.document, field)
                if finding.line_no is None
                else getattr(case.request.document.item(finding.line_no), field)
            )
            value = (
                current.value.isoformat()
                if hasattr(current.value, "isoformat")
                else str(current.value)
            )
            case = case.confirm_value(finding.line_no, field, value, by=PERSON, at=AT)
    replied = (
        case.draft_ycbg()
        .record_ycbg("YCBG-2610-099", by=PERSON, at=AT)
        .send_to_design()
        .record_design_reply(_reply())
    )
    service = _service(Recorded(raw=M38))
    evidence = await service.price_evidence(SCOPE, replied, as_of=AT.date())
    decision = PricingDecision(
        decided_by=PERSON,
        decided_at=AT,
        lme=None,
        lines=(
            LinePrice(
                line_no=1,
                unit_price=Decimal("2.50"),
                moq=Decimal(1000),
                lead_time_days=30,
                copper_basis={"kind": "fixed"},
            ),
        ),
    )
    raised = price_findings(
        replied,
        decision,
        latest_lme=None,
        pricing=POLICIES.pricing,
        prescribed_basis="fixed",
        quote_rules_version=POLICIES.quote_rules.version,
    )

    assert [e.target_price for e in evidence] == [None]
    assert QuoteFindingCode.ABOVE_TARGET_PRICE not in {f.code for f in raised}


def _reply() -> DesignReply:
    sha = "d" * 64

    def at(cell: str) -> dict[str, Any]:
        return {"attachment_id": "R1-A1", "attachment_sha256": sha, "cell_ref": f"YCBG!{cell}"}

    return DesignReply.model_validate(
        {
            "message_id": "R1",
            "received_at": AT,
            "attachment": {
                "attachment_id": "R1-A1",
                "name": "reply.xlsx",
                "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "size": 10,
                "sha256": sha,
            },
            "document": {
                "ycbg_no": {"value": "YCBG-2610-099", "source": at("B4")},
                "reply_date": {"value": "2026-10-03", "source": at("E4")},
                "lines": [
                    {
                        "line_no": 1,
                        "bp_code": {"value": "BP-26-0001", "source": at("B10")},
                        "spec_no": {"value": "SP-5406", "source": at("C10")},
                        "prv_code": {"value": "CB-2007", "source": at("D10")},
                    }
                ],
            },
        }
    )


# ---------------------------------------------------------------- the view --


async def test_the_mail_text_and_a_stated_target_are_shown_only_with_prices() -> None:
    """The mail a model read may state a price; it is shown as a source is,
    to a holder of `sales.price.read`, and so is the stated target."""
    from dw_sales.application.access import PriceView
    from dw_sales.application.views import HIDDEN, quote_case

    m38 = await _open("M38", M38)
    m37 = await _open("M37", M37)

    def view(case: QuoteCase, amounts: bool) -> Any:
        return quote_case(
            case,
            assigned_to=None,
            release_manifest_ref=None,
            today=AT.date(),
            prices=PriceView(amounts=amounts, other_customers=False),
            evidence_rows=None,
        )

    hidden, shown = view(m38, False), view(m38, True)
    assert hidden.lines[0].stated_target_price == HIDDEN
    assert "stated_target_price" not in hidden.lines[0].anchors
    assert shown.lines[0].stated_target_price == Decimal("0.95")
    assert view(m37, False).message_text == HIDDEN
    text = view(m37, True).message_text
    assert isinstance(text, str) and text.startswith("Yêu cầu báo giá")
