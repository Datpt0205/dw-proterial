"""A model reads what a message no reader accepted is about; code routes it
(ticket 31, dw_sales ADR 0005, Đạt's §6).

`OrderIntake` over crafted messages with a scripted model (`Recorded`): which
messages reach the model at all, under which switch and run; what each kind
becomes; which numbers are taken; and what no usable answer leaves.
"""

from __future__ import annotations

import hashlib
import itertools
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, get_args

import pytest
from pydantic import ValidationError

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.budget import BudgetExceededError
from dw_agent_runtime.model.prompts import PromptRegistry
from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.adapters.mock import MockInbox, MockSalesCatalog
from dw_sales.adapters.mock.fixtures import ATTACHMENTS_DIR, DATA_DIR
from dw_sales.adapters.order_rules import PlatformOrderRules, load_tenant_order_rules
from dw_sales.adapters.policy_files import load_sales_policies
from dw_sales.adapters.readers import mock_po_readers
from dw_sales.adapters.rfq_excel import ExcelQuoteForms
from dw_sales.application.message_intent import MESSAGE_INTENT, PROMPT_TOKENS, IntentReader
from dw_sales.application.model_reading import ModelUnavailableError, estimated_tokens
from dw_sales.application.order_intake import (
    INTENT_ROUTES,
    NOT_UNDERSTOOD,
    MessageKind,
    OrderIntake,
)
from dw_sales.application.ports import SalesScope
from dw_sales.domain.dispositions import DispositionKind, RoutingReason
from dw_sales.domain.message_intent import IntentKind, ModelMessageIntent, located_numbers
from dw_sales.domain.messages import Attachment, EmailAddress, InboundMessage, MailAuthentication
from dw_sales.domain.order_checks import OrderRules
from dw_sales.domain.orders import OrderCase
from dw_sales.evals.recorded import Recorded

pytestmark = pytest.mark.unit

SCOPE = SalesScope(TenantId(uuid.UUID(int=1)), WorkspaceId(uuid.UUID(int=2)))
CATALOG = MockSalesCatalog.load(SCOPE)
REPO = Path(__file__).resolve().parents[5]
PLATFORM = load_sales_policies(REPO / "configs" / "policies", REPO / "configs" / "copy").order_rules
DEMO = load_tenant_order_rules(DATA_DIR / "policies")
RECEIVED = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
RUN = RunContext(
    run_id=uuid.UUID(int=0x31),
    tenant_id=SCOPE.tenant_id.value,
    workspace_id=SCOPE.workspace_id.value,
    actor_id=uuid.UUID(int=0xA1),
    worker_id="sales-dw1",
    worker_version="1.0.0",
    channel="web",
    plan_id="professional",
    roles=frozenset(),
    scopes=frozenset(),
    trace_id="t31",
)
M01_PO = (ATTACHMENTS_DIR / "M01_VLX-PO-2609-0118.xlsx").read_bytes()


def _says(kind: str, *numbers: str, language: str = "vi") -> Recorded:
    return Recorded(
        raw={"language": language, "referenced_number_spans": list(numbers), "kind": kind}
    )


def _message(
    subject: str,
    body: str,
    *,
    sender: str = "an.trinh@velatrix.example",
    files: tuple[bytes, ...] = (),
    received: datetime = RECEIVED,
    verified: bool = True,
) -> tuple[InboundMessage, MockInbox]:
    attachments = tuple(
        Attachment(
            attachment_id=f"T1-A{n}",
            name="attachment.dat",
            media_type="application/octet-stream",
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )
        for n, data in enumerate(files, start=1)
    )
    result = "pass" if verified else "fail"
    message = InboundMessage(
        message_id="T1",
        sender=EmailAddress(address=sender),
        subject=subject,
        received_at=received,
        body_text=body,
        attachments=attachments,
        authentication=MailAuthentication(spf=result, dkim=result, dmarc=result),
    )
    contents = {("T1", a.attachment_id): data for a, data in zip(attachments, files, strict=True)}
    return message, MockInbox([message], contents, scope=SCOPE)


class _Cases:
    def __init__(self, cases: list[OrderCase] | None = None) -> None:
        self.cases = cases or []

    async def cases_for_po(self, scope: SalesScope, customer_code: str, po_no: str) -> list[Any]:
        return [
            c for c in self.cases if (c.customer_code, c.header.po_no) == (customer_code, po_no)
        ]


def _intake(inbox: MockInbox, model: Any, rules: OrderRules | None = DEMO) -> OrderIntake:
    assert rules is not None
    ids = itertools.count(1)
    return OrderIntake(
        catalog=CATALOG,
        inbox=inbox,
        reader=mock_po_readers(),
        quote_forms=ExcelQuoteForms(),
        rules=PlatformOrderRules(rules),
        cases=_Cases(),
        new_case_id=lambda: uuid.UUID(int=next(ids)),
        intents=None if model is None else IntentReader(model, CATALOG, _Cases()),
    )


# ----------------------------------------------------------- the switch --


def test_the_demo_tenant_has_the_step_on_and_the_platform_has_it_off() -> None:
    assert DEMO is not None and DEMO.model_assist.message_intent
    assert not PLATFORM.model_assist.message_intent


async def test_with_the_switch_off_the_keyword_tables_decide_and_no_model_is_asked() -> None:
    message, inbox = _message("Đề nghị lùi ngày nhận hàng", "Bên em xin lùi ngày nhận hàng.")
    model = _says("delivery_change")

    classified = await _intake(inbox, model, PLATFORM).classify(SCOPE, message, run=RUN)

    assert classified.kind is MessageKind.OTHER and classified.reading is None
    assert model.calls == []


async def test_outside_a_dw1_run_no_model_is_asked() -> None:
    message, inbox = _message("Đề nghị lùi ngày nhận hàng", "Bên em xin lùi ngày nhận hàng.")
    model = _says("delivery_change")

    await _intake(inbox, model).classify(SCOPE, message)

    assert model.calls == []


# ------------------------------------------------------ content decides --


async def test_a_readable_po_titled_quote_request_is_a_po_and_no_model_is_asked() -> None:
    message, inbox = _message(
        "Quote request / request for quotation", "Please quote.", files=(M01_PO,)
    )
    model = _says("quote_request")

    classified = await _intake(inbox, model).classify(SCOPE, message, run=RUN)

    assert classified.kind is MessageKind.PO
    assert model.calls == []


# ---------------------------------------------------------- kind → route --


def test_every_kind_the_model_may_give_has_one_route_and_revised_po_is_none() -> None:
    kinds = set(get_args(IntentKind))

    assert set(INTENT_ROUTES) == kinds
    assert "revised_po" not in kinds
    with pytest.raises(ValidationError):
        ModelMessageIntent.model_validate(
            {"language": "en", "referenced_number_spans": [], "kind": "revised_po"}
        )
    with pytest.raises(ValidationError):
        ModelMessageIntent.model_validate(
            {"language": "en", "referenced_number_spans": [], "kind": "po", "route": "case"}
        )


@pytest.mark.parametrize(
    ("kind", "reason"),
    [
        ("delivery_change", RoutingReason.DELIVERY_CHANGE),
        ("complaint", RoutingReason.COMPLAINT),
        ("sample_request", RoutingReason.SAMPLE_REQUEST),
        ("reply_to_case", RoutingReason.REPLY_TO_CASE),
        ("other", RoutingReason.OTHER),
        # A message about a PO is not a PO: it has to carry one.
        ("po", RoutingReason.OTHER),
    ],
)
async def test_each_kind_is_routed_to_the_customers_pic_with_its_reason(
    kind: str, reason: RoutingReason
) -> None:
    message, inbox = _message("Hỏi chút", "Chị ơi cho em hỏi.")

    outcome = await _intake(inbox, _says(kind)).process(SCOPE, message, run=RUN, now=RECEIVED)

    disposition = outcome.disposition
    assert disposition is not None and outcome.case is None
    assert (disposition.kind, disposition.reason) == (DispositionKind.ROUTED_TO_SALES, reason)
    assert disposition.owner == "an.nguyen@alpha.local"
    reading = disposition.reading
    assert reading is not None and (reading.kind, reading.outcome) == (kind, "read")
    assert (reading.prompt, reading.model_profile, reading.route, reading.rules) == (
        "sales.message_intent@1.0.0",
        "onprem",
        "structured_extraction",
        "sales_order_rules@1.4.1",
    )


@pytest.mark.parametrize("kind", ["quote_request", "design_reply"])
async def test_a_quotation_kind_is_handed_to_the_quotation_flow(kind: str) -> None:
    message, inbox = _message("Hỏi giá", "Chị ơi báo giá giúp em.")

    outcome = await _intake(inbox, _says(kind)).process(SCOPE, message, run=RUN, now=RECEIVED)

    assert outcome.kind is MessageKind(kind) and outcome.disposition is None


# ------------------------------------------------------- referenced numbers --


@pytest.mark.parametrize(
    ("part", "spans", "found"),
    [
        ("Về PO VLX-PO-2608-0102 ạ", ("VLX-PO-2608-0102",), ("VLX-PO-2608-0102",)),
        ("Về PO vlx-po-2608-0102 ạ", ("VLX-PO-2608-0102",), ("VLX-PO-2608-0102",)),
        ("Về đơn tuần trước", ("VLX-PO-2608-0102",), ()),
        ("Mã XVLX-PO-2608-0102", ("VLX-PO-2608-0102",), ()),
        ("Số lượng 1200 m", ("1200 m",), ()),
    ],
)
def test_a_number_is_taken_only_as_a_whole_token_of_the_newest_part(
    part: str, spans: tuple[str, ...], found: tuple[str, ...]
) -> None:
    assert located_numbers(part, spans) == found


async def test_a_number_resolves_only_against_the_senders_own_records() -> None:
    reader = IntentReader(_says("reply_to_case"), CATALOG, _Cases())
    velatrix = (await CATALOG.customer_by_code(SCOPE, "VLX")).data

    own = await reader.resolve(SCOPE, velatrix, ("VLX-PO-2608-0102",))
    others = await reader.resolve(SCOPE, velatrix, ("NRV-PO-26-0190",))
    nobody = await reader.resolve(SCOPE, None, ("VLX-PO-2608-0102",))

    assert [(r.number, r.record) for r in own] == [("VLX-PO-2608-0102", "purchase_order")]
    assert others == () and nobody == ()


async def test_a_number_found_only_in_quoted_history_is_not_taken() -> None:
    message, inbox = _message(
        "Re: lịch giao",
        "Chị ơi em cảm ơn ạ.\n\nOn Mon, 5 Oct 2026 at 09:12, Vy wrote:\n> PO VLX-PO-2608-0102.",
    )

    outcome = await _intake(inbox, _says("reply_to_case", "VLX-PO-2608-0102")).process(
        SCOPE, message, run=RUN, now=RECEIVED
    )

    assert outcome.disposition is not None and outcome.disposition.reading is not None
    assert outcome.disposition.reading.references == ()


# ------------------------------------------------------------ no answer --


async def test_a_young_message_with_no_usable_answer_waits_for_a_retry() -> None:
    message, inbox = _message("Hỏi chút", "Chị ơi cho em hỏi.")
    down = Recorded(failure=ModelUnavailableError("InfrastructureError"))

    classified = await _intake(inbox, down).classify(
        SCOPE, message, run=RUN, now=RECEIVED + timedelta(hours=1)
    )

    assert classified.retry
    with pytest.raises(ValueError, match="retry"):
        await _intake(inbox, down).process(SCOPE, message, run=RUN, classified=classified)


async def test_an_old_message_with_no_usable_answer_goes_to_sales_as_not_understood() -> None:
    message, inbox = _message("Hỏi chút", "Chị ơi cho em hỏi.")
    down = Recorded(raw={"language": "vi", "kind": "po"})  # outside the schema

    outcome = await _intake(inbox, down).process(
        SCOPE, message, run=RUN, now=RECEIVED + timedelta(hours=25)
    )

    disposition = outcome.disposition
    assert disposition is not None
    assert (disposition.reason, disposition.detail) == (RoutingReason.OTHER, NOT_UNDERSTOOD)
    assert disposition.reading is not None and disposition.reading.outcome == "unavailable"


async def test_a_spent_budget_stops_the_run_rather_than_reading_as_not_understood() -> None:
    message, inbox = _message("Hỏi chút", "Chị ơi cho em hỏi.")
    spent = Recorded(failure=BudgetExceededError("run reached its input-token ceiling"))

    with pytest.raises(BudgetExceededError):
        await _intake(inbox, spent).process(
            SCOPE, message, run=RUN, now=RECEIVED + timedelta(days=3)
        )


async def test_a_readable_po_goes_through_with_the_model_down() -> None:
    message, inbox = _message("Gửi đơn", "Chị ơi em gửi file.", files=(M01_PO,))
    down = Recorded(failure=ModelUnavailableError("InfrastructureError"))

    outcome = await _intake(inbox, down).process(SCOPE, message, run=RUN, now=RECEIVED)

    assert outcome.case is not None and down.calls == []


# ------------------------------------------------------------- the prompt --


def test_the_prompt_file_is_the_one_the_step_names_and_fits_its_room() -> None:
    prompts = PromptRegistry()
    prompts.load_directory(REPO / "configs" / "prompts")

    rendered = prompts.render(
        MESSAGE_INTENT.prompt_id,
        MESSAGE_INTENT.version,
        {"subject": "", "body": ""},
        tenant_id=RUN.tenant_id,
    )

    assert estimated_tokens(rendered.system + rendered.user) < PROMPT_TOKENS


async def test_a_long_body_is_cut_to_the_routes_room_before_it_is_sent() -> None:
    message, inbox = _message("Hỏi chút", "Chị ơi cho em hỏi về đơn hàng. " * 2000)
    model = _says("other")

    await _intake(inbox, model).classify(SCOPE, message, run=RUN, now=RECEIVED)

    ((_, _, inputs),) = model.calls
    assert estimated_tokens(inputs["body"]) <= model.max_input_tokens - PROMPT_TOKENS
