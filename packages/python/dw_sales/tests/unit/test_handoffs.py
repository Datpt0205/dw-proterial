"""A hand-off to PC or QA, pre-filled from a customer's mail: what code keeps of
a model's spans, what it resolves and against whose orders, and what reaches
the template (ticket 33, dw_sales ADR 0005).

The reader over the mock catalogue with a scripted model (`Recorded`), and the
whole flow over the in-memory world: which messages reach the model at all,
under which switch and run; what a span becomes; which PO resolves; that no
destination is carried; and what no usable answer leaves. The live model's
accuracy is the eval lane's (`sales_handoff@1.0.0`).
"""

from __future__ import annotations

import shutil
import uuid
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.budget import BudgetExceededError
from dw_agent_runtime.model.interpretation import (
    ModelUnavailableError,
    estimated_tokens,
)
from dw_agent_runtime.model.prompts import PromptRegistry
from dw_platform.domain.mail_parts import newest_part
from dw_platform.domain.messages import EmailAddress, InboundMessage, MailAuthentication
from dw_platform.domain.notation import notation_of
from dw_sales.adapters.mock import MockSalesCatalog
from dw_sales.adapters.mock.fixtures import ATTACHMENTS_DIR, DATA_DIR
from dw_sales.adapters.policy_files import load_sales_policies
from dw_sales.application.access import SalesScopes
from dw_sales.application.handoffs import (
    PROMPT_TOKENS,
    REQUEST_HANDOFF,
    HandoffCopy,
    HandoffReader,
    render,
)
from dw_sales.application.ports import SalesScope
from dw_sales.application.rules import RuleKey
from dw_sales.domain.catalog import Customer
from dw_sales.domain.handoffs import (
    Handoff,
    HandoffKind,
    carries_contact,
    line_number_of,
    locate,
    quantity_at,
)
from dw_sales.domain.orders import OrderCase
from dw_sales.evals.graders import AN as _AN
from dw_sales.evals.graders import CALLERS, GIANG
from dw_sales.evals.recorded import ByPrompt, Recorded
from dw_sales.evals.world import ALPHA, BETA, SampleSet, open_world
from dw_sales.testing.customer_notations import MemoryCustomerNotations

# An given the set `sales_rules_editor` (`sales.rules.propose`): since
# 2026-10-28 a PIC proposes only when the admin gives them it.
AN = replace(_AN, scopes=_AN.scopes | {SalesScopes.RULES_PROPOSE})

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
COPY = load_sales_policies(REPO / "configs" / "policies", REPO / "configs" / "copy").handoff_copy
CATALOG = MockSalesCatalog.load(ALPHA)
RECEIVED = date(2026, 10, 10)
RUN = RunContext(
    run_id=uuid.UUID(int=0x33),
    tenant_id=ALPHA.tenant_id.value,
    workspace_id=ALPHA.workspace_id.value,
    actor_id=uuid.UUID(int=0xA1),
    worker_id="sales-dw1",
    worker_version="1.0.0",
    channel="web",
    plan_id="professional",
    roles=frozenset(),
    scopes=frozenset(),
    trace_id="t33",
)
# "0,42" and "25/11/2026" are what tell code that this mail's "2.000 m" is two
# thousand metres and its "05/12/2026" the fifth of December (audit 11-13,
# findings 8 and 9); `UNSETTLED` is the same mail without them.
CHANGE = (
    "Chào chị Vy,\n\nĐơn VLX-PO-2608-0102 bên em xin điều chỉnh:\n"
    "- Dòng 2: giảm còn 2.000 m, đơn giá giữ 0,42 USD/m.\n"
    "- Mã VX-C4B22: lùi ngày giao từ 25/11/2026 sang 05/12/2026.\n\nCảm ơn chị"
)
UNSETTLED = CHANGE.replace(", đơn giá giữ 0,42 USD/m", "").replace("từ 25/11/2026 ", "")


class _NoCases:
    async def cases_for_po(
        self, scope: SalesScope, customer_code: str, po_no: str
    ) -> list[OrderCase]:
        return []


def _message(body: str, sender: str = "an.trinh@velatrix.example") -> InboundMessage:
    return InboundMessage(
        message_id="H1",
        sender=EmailAddress(address=sender),
        subject="Điều chỉnh đơn",
        received_at=datetime(2026, 10, 10, 2, 0, tzinfo=UTC),
        body_text=body,
        authentication=MailAuthentication(spf="pass", dkim="pass", dmarc="pass"),
    )


async def _customer(code: str) -> Customer:
    customer = (await CATALOG.customer_by_code(ALPHA, code)).data
    assert customer is not None
    return customer


async def _read(
    answer: dict[str, Any] | None,
    body: str,
    kind: HandoffKind = "delivery_change",
    *,
    customer: str = "VLX",
    scope: SalesScope = ALPHA,
    model: Any = None,
    records: MemoryCustomerNotations | None = None,
) -> Handoff:
    scripted = model or Recorded(raw=answer)
    return await HandoffReader(
        scripted, CATALOG, _NoCases(), records or MemoryCustomerNotations()
    ).read(
        scope,
        newest_part(_message(body)),
        await _customer(customer),
        kind,
        received_on=RECEIVED,
        rules_version="sales_order_rules@1.5.2",
        run=RUN,
    )


def _with_intent(handoffs: Recorded) -> ByPrompt:
    """The demo tenant reads a message's intent first (ticket 31): M31 read as
    the complaint it is, the hand-off answered by ``handoffs``."""
    intent = Recorded(raw={"language": "vi", "referenced_number_spans": [], "kind": "complaint"})
    return ByPrompt({"sales.message_intent": intent, "sales.request_handoff": handoffs})


# ----------------------------------------------------------- the reading --


async def test_a_delivery_change_resolves_the_senders_order_and_each_line_against_it() -> None:
    handoff = await _read(
        {
            "po_no_span": "VLX-PO-2608-0102",
            "lines": [
                {"line_or_item_span": "2", "new_quantity_span": "2.000 m", "new_date_span": None},
                {
                    "line_or_item_span": "VX-C4B22",
                    "new_quantity_span": None,
                    "new_date_span": "05/12/2026",
                },
            ],
        },
        CHANGE,
    )

    assert (handoff.outcome, handoff.po_no, handoff.so_no) == (
        "read",
        "VLX-PO-2608-0102",
        "SO26-0812",
    )
    by_line = {line.line_no: line for line in handoff.lines}
    # Line 2 by its number; the customer's code VX-C4B22 is line 1's CB-2007.
    assert (by_line[2].new_quantity, by_line[2].item) == (Decimal("2000"), "HW-1001")
    assert (by_line[1].new_date, by_line[1].item) == (date(2026, 12, 5), "CB-2007")
    assert handoff.refused == {}


async def test_a_value_the_mail_does_not_settle_keeps_the_customers_words_for_sales() -> None:
    """Nothing else in the mail says whether "2.000" is two thousand or two,
    or whether "05/12/2026" is the fifth of December or the twelfth of May:
    neither is read, and the customer's words go into the hand-off instead."""
    handoff = await _read(
        {
            "po_no_span": "VLX-PO-2608-0102",
            "lines": [
                {"line_or_item_span": "2", "new_quantity_span": "2.000 m", "new_date_span": None},
                {
                    "line_or_item_span": "VX-C4B22",
                    "new_quantity_span": None,
                    "new_date_span": "05/12/2026",
                },
            ],
        },
        UNSETTLED,
    )

    by_line = {line.line_no: line for line in handoff.lines}
    assert by_line[2].new_quantity is None and by_line[1].new_date is None
    assert by_line[2].quantity is not None and by_line[2].quantity.text == "2.000 m"
    assert by_line[1].date_span is not None and by_line[1].date_span.text == "05/12/2026"
    assert handoff.refused == {"quantity_unread": 1, "date_unread": 1}
    written = render(handoff, COPY, customer_code="VLX", message_id="H1")
    assert f"số lượng mới {COPY.unknown} «2.000 m»" in written.body
    assert f"ngày giao mới {COPY.unknown} «05/12/2026»" in written.body


async def test_a_quantity_in_another_unit_keeps_the_unit_even_when_the_span_omits_it() -> None:
    """Audit 11-13, finding 4: the model's span "3" of "3 km" reached PC as
    3 m. The unit is read from the whole text right after the number."""
    body = "PO VLX-PO-2608-0102: dòng 2 xin đổi còn 3 km thôi."

    handoff = await _read(
        {
            "po_no_span": "VLX-PO-2608-0102",
            "lines": [{"line_or_item_span": "2", "new_quantity_span": "3", "new_date_span": None}],
        },
        body,
    )

    (line,) = handoff.lines
    assert line.new_quantity is None
    assert line.quantity is not None and line.quantity.text == "3 km"
    assert handoff.refused == {"quantity_unread": 1}
    written = render(handoff, COPY, customer_code="VLX", message_id="H1")
    assert f"số lượng mới {COPY.unknown} «3 km»" in written.body


async def test_a_sample_quantity_in_another_unit_is_kept_as_words_and_read_for_sales() -> None:
    body = "Brennic xin 2 cuộn mẫu cáp hai lõi."

    handoff = await _read(
        {"item_spans": [], "quantity_span": "2"}, body, "sample_request", customer="BRN"
    )

    assert handoff.outcome == "read" and handoff.sample_quantity is None
    assert handoff.quantity is not None and handoff.quantity.text == "2 cuộn"
    written = render(handoff, COPY, customer_code="BRN", message_id="M17")
    assert f"Số lượng khách nêu: {COPY.unknown} «2 cuộn»." in written.body


async def test_another_customers_po_resolves_nothing_and_its_lines_are_dropped() -> None:
    body = CHANGE.replace("VLX-PO-2608-0102", "NRV-PO-26-0190")

    handoff = await _read(
        {
            "po_no_span": "NRV-PO-26-0190",
            "lines": [
                {"line_or_item_span": "2", "new_quantity_span": "2.000 m", "new_date_span": None}
            ],
        },
        body,
    )

    assert (handoff.outcome, handoff.po_no, handoff.lines) == ("nothing_located", None, ())
    assert handoff.refused == {"po_no": 1, "line": 1}


async def test_another_tenant_reads_the_catalogue_empty_and_resolves_nothing() -> None:
    handoff = await _read({"po_no_span": "VLX-PO-2608-0102", "lines": []}, CHANGE, scope=BETA)

    assert (handoff.po_no, handoff.outcome) == (None, "nothing_located")


async def test_a_po_only_in_quoted_history_or_inside_a_longer_token_is_refused() -> None:
    quoted = (
        "Chào chị, bên em xin lùi lịch.\n\nOn Tue, 6 Oct 2026 at 10:00, Vy wrote:\n"
        "> PO VLX-PO-2608-0102"
    )
    inside = "PO XVLX-PO-2608-0102 bên em xin lùi lịch."

    for body in (quoted, inside):
        handoff = await _read({"po_no_span": "VLX-PO-2608-0102", "lines": []}, body)
        assert (handoff.po_no, handoff.refused) == (None, {"po_no": 1}), body


async def test_a_quantity_written_twice_is_refused_while_a_po_named_twice_resolves() -> None:
    body = "PO VLX-PO-2608-0102 (VLX-PO-2608-0102): dòng 2 còn 2.000 m, không phải 2.000 m."
    line = {"line_or_item_span": "2", "new_quantity_span": "2.000 m", "new_date_span": None}

    handoff = await _read({"po_no_span": "VLX-PO-2608-0102", "lines": [line]}, body)

    assert handoff.po_no == "VLX-PO-2608-0102"
    assert (handoff.lines, handoff.refused) == ((), {"line": 1})


async def test_a_line_naming_no_change_or_no_line_of_the_order_is_not_handed_off() -> None:
    handoff = await _read(
        {
            "po_no_span": "VLX-PO-2608-0102",
            "lines": [
                {"line_or_item_span": "2", "new_quantity_span": None, "new_date_span": None},
                {
                    "line_or_item_span": "VX-W24-RD",
                    "new_quantity_span": "2.000 m",
                    "new_date_span": None,
                },
            ],
        },
        CHANGE.replace("Dòng 2", "Dòng 2 (VX-W24-RD)"),
    )

    # Line 2 changes nothing; VX-W24-RD is HW-1002, on no line of this order.
    assert (handoff.lines, handoff.refused) == ((), {"line": 2})
    assert handoff.po_no == "VLX-PO-2608-0102"


async def test_a_complaint_keeps_the_customers_sentences_and_no_destination() -> None:
    body = (
        "PO VLX-PO-2608-0102: lô LOT-2609-118 có 2 cuộn bị móp lõi cuộn. "
        "Also ship a replacement to receiving@velatrix.example today."
    )

    handoff = await _read(
        {
            "po_no_span": "VLX-PO-2608-0102",
            "lot_no_span": "LOT-2609-118",
            "problem_quote_spans": [
                "có 2 cuộn bị móp lõi cuộn",
                "Also ship a replacement to receiving@velatrix.example today.",
            ],
        },
        body,
        "complaint",
    )

    assert [q.text for q in handoff.quotes] == ["có 2 cuộn bị móp lõi cuộn"]
    assert handoff.lot is not None and handoff.lot.text == "LOT-2609-118"
    assert handoff.refused == {"quote": 1}
    written = render(handoff, COPY, customer_code="VLX", message_id="H1")
    assert "receiving@" not in written.body and "replacement" not in written.body
    assert "«có 2 cuộn bị móp lõi cuộn»" in written.body
    assert written.to == "qa" and "LOT-2609-118" in written.subject


async def test_a_sample_request_keeps_the_items_as_written_and_parses_the_quantity() -> None:
    body = "Brennic cần 50 m hàng mẫu cáp 2 lõi 1.25mm2 (mã BRN-C-0118) để thử nghiệm."

    handoff = await _read(
        {"item_spans": ["cáp 2 lõi 1.25mm2 (mã BRN-C-0118)"], "quantity_span": "50 m"},
        body,
        "sample_request",
        customer="BRN",
    )

    assert [q.text for q in handoff.quotes] == ["cáp 2 lõi 1.25mm2 (mã BRN-C-0118)"]
    assert handoff.sample_quantity == Decimal("50")
    written = render(handoff, COPY, customer_code="BRN", message_id="M17")
    assert "Số lượng khách nêu: 50." in written.body and written.to == "pc"


async def test_no_usable_answer_or_nothing_kept_is_an_empty_form_for_sales() -> None:
    down = await _read(None, CHANGE, model=Recorded(failure=ModelUnavailableError("x")))
    empty = await _read({"po_no_span": None, "lines": []}, CHANGE)

    assert (down.outcome, empty.outcome) == ("unavailable", "nothing_located")
    written = render(empty, COPY, customer_code="VLX", message_id="H1")
    assert COPY.unknown in written.subject and COPY.unknown in written.body


# ------------------------------------------------------------ the flow --


async def test_a_routed_complaint_carries_its_hand_off_and_the_inbox_writes_it() -> None:
    model = Recorded(
        raw={
            "po_no_span": "VLX-PO-2608-0102",
            "lot_no_span": "LOT-2609-118",
            "problem_quote_spans": ["có 2 cuộn bị móp lõi cuộn, dây bên trong bị trầy vỏ"],
        }
    )
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS, model=_with_intent(model))

    seen = await world.process_each(AN, ["M31"])

    disposition, _ = seen["M31"]
    assert (disposition.kind, disposition.reason) == ("routed_to_sales", "complaint")
    handoff = disposition.handoff
    assert handoff is not None and (handoff.kind, handoff.po_no) == (
        "complaint",
        "VLX-PO-2608-0102",
    )
    ((_, run, inputs),) = [c for c in model.calls if c[0] == REQUEST_HANDOFF]
    assert (inputs["kind"], run.tenant_id) == ("complaint", ALPHA.tenant_id.value)
    listed = {m.message_id: m for m in await world.services.inbox.messages(AN.context())}
    draft = listed["M31"].handoff_draft
    assert draft is not None and draft.to == "qa"
    assert draft.template_ref == "sales_handoffs@1.1.0#complaint"
    assert "VLX-PO-2608-0102" in draft.subject and "LOT-2609-118" in draft.subject


async def test_the_inbox_writes_a_hand_off_in_the_tenants_own_copy() -> None:
    """Ticket 36: a hand-off copy the tenant proposed and its head approved
    writes the draft, and the draft names that version."""
    model = Recorded(
        raw={
            "po_no_span": "VLX-PO-2608-0102",
            "lot_no_span": "LOT-2609-118",
            "problem_quote_spans": ["có 2 cuộn bị móp lõi cuộn, dây bên trong bị trầy vỏ"],
        }
    )
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS, model=_with_intent(model))
    await world.process_each(AN, ["M31"])
    document = COPY.model_dump(mode="json")
    document["templates"]["complaint"]["subject"] = "[Khiếu nại] {customer} {po} lô {lot}"
    proposed = await world.services.rules.propose(
        AN.context(), RuleKey.HANDOFFS, {**document, "version": "9.0.1"}
    )
    await world.decide_rules(GIANG, proposed.version_id, approve=True, comment="Đồng ý")

    listed = {m.message_id: m for m in await world.services.inbox.messages(AN.context())}

    draft = listed["M31"].handoff_draft
    assert draft is not None and draft.template_ref == "sales_handoffs@9.0.1#complaint"
    assert draft.subject == "[Khiếu nại] VLX VLX-PO-2608-0102 lô LOT-2609-118"


@pytest.mark.parametrize(
    ("field", "text"),
    [
        ("line", "{line_no:>999999999}"),
        ("line", "{line_no.__class__}"),
        ("line", "{line_no!r}"),
        ("quote", "{secret}"),
        ("quote", "{0}"),
        ("subject", "{customer[0]}"),
        ("body", "{po:{lot}}"),
    ],
)
def test_a_hand_off_copy_names_only_its_placeholders_bare(field: str, text: str) -> None:
    """A tenant's version is filled with `str.format`: a format spec builds a
    string as long as it asks for, an attribute or an index reaches past the
    value. Each is refused before the copy can be proposed (ticket 36)."""
    document = COPY.model_dump(mode="json")
    if field in ("subject", "body"):
        document["templates"]["complaint"][field] = text
    else:
        document[field] = text

    with pytest.raises(ValidationError, match="placeholder"):
        HandoffCopy.model_validate(document)


async def test_with_the_switch_off_no_model_is_asked_and_the_message_routes_as_before(
    tmp_path: Path,
) -> None:
    model = Recorded(failure=AssertionError("asked with the step off"))
    shutil.copytree(DATA_DIR, tmp_path / "data", ignore=shutil.ignore_patterns("policies"))
    world = open_world(REPO, SampleSet(tmp_path / "data", ATTACHMENTS_DIR), CALLERS, model=model)

    seen = await world.process_each(AN, ["M11", "M17", "M31"])

    # No keyword table gives a reason (audit finding 6): a person reads each.
    assert {d.reason for d, _ in seen.values()} == {"other"}
    assert all(d.handoff is None for d, _ in seen.values())
    assert not model.calls


async def test_the_model_down_routes_as_before_with_an_empty_form() -> None:
    down = Recorded(failure=ModelUnavailableError("x"))
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS, model=_with_intent(down))

    seen = await world.process_each(AN, ["M31"])

    disposition, _ = seen["M31"]
    assert (disposition.kind, disposition.reason) == ("routed_to_sales", "complaint")
    assert disposition.handoff is not None and disposition.handoff.outcome == "unavailable"


async def test_a_spent_budget_stops_the_run() -> None:
    spent = Recorded(failure=BudgetExceededError("ceiling"))
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS, model=_with_intent(spent))

    with pytest.raises(BudgetExceededError):
        await world.process_each(AN, ["M31"])


# ------------------------------------------------------------- the rules --


def test_spans_quantities_lines_and_contacts_are_read_by_code() -> None:
    part = "Đơn VLX-PO-2608-0102 dòng 2 giảm còn 2.000 m; VLX-PO-2608-01022 khác."
    assert locate(part, "VLX-PO-2608-0102", bounded=True) is not None
    assert locate(part, "2.000", bounded=True) is not None
    assert locate(part, "000", bounded=True) is None
    named = ("2", "Dòng 1 (VX-C4B22)", "Line 12", "2行目", "VX-C4B22", "12 cuộn")
    assert [line_number_of(s) for s in named] == [2, 1, 12, 2, None, None]
    assert carries_contact("send it to qa@velatrix.example")
    assert carries_contact("see https://example.test/form")
    assert carries_contact("call +84 28 3812 3456")
    assert not carries_contact("lô LOT-2609-118 giao ngày 2026-09-25 bị trầy vỏ")


def test_a_hand_off_keeps_lines_only_on_a_resolved_order() -> None:
    stamp = {
        "kind": "delivery_change",
        "prompt": "sales.request_handoff@1.0.0",
        "model_profile": "onprem",
        "route": "structured_extraction",
        "rules": "sales_order_rules@1.5.2",
    }
    line = {"reference": {"text": "2", "start": 0, "end": 1}, "line_no": 2, "new_quantity": "5"}
    with pytest.raises(ValidationError):
        Handoff.model_validate({**stamp, "outcome": "read", "lines": [line]})
    with pytest.raises(ValidationError):
        Handoff.model_validate({**stamp, "outcome": "read"})


def test_the_prompt_file_is_the_one_the_step_names_and_fits_its_room() -> None:
    prompts = PromptRegistry()
    prompts.load_directory(REPO / "configs" / "prompts")

    rendered = prompts.render(
        REQUEST_HANDOFF.prompt_id,
        REQUEST_HANDOFF.version,
        {"kind": "delivery_change", "subject": "", "body": ""},
        tenant_id=RUN.tenant_id,
    )

    assert estimated_tokens(rendered.system + rendered.user) < PROMPT_TOKENS


async def test_a_body_too_long_for_the_route_is_never_cut_but_left_to_sales() -> None:
    """The finding batch B left: a cut text loses its later lines with no one
    told, and a value is verified against less than the mail says."""
    model = Recorded(raw={"po_no_span": None, "lot_no_span": None, "problem_quote_spans": []})

    handoff = await _read(None, "Dây bị trầy vỏ. " * 3000, "complaint", model=model)

    assert model.calls == []
    assert (handoff.outcome, handoff.refused) == ("unavailable", {"too_long": 1})


async def test_a_body_that_fits_is_sent_whole() -> None:
    model = Recorded(raw={"po_no_span": None, "lot_no_span": None, "problem_quote_spans": []})

    await _read(None, CHANGE, "complaint", model=model)

    ((_, _, inputs),) = model.calls
    assert inputs["body"] == newest_part(_message(CHANGE)).body


@pytest.mark.parametrize(
    ("text", "span", "value", "words"),
    [
        ("giảm còn 2.000 m, giá 0,42", "2.000 m", Decimal("2000"), "2.000 m"),
        ("thêm 500 m nữa", "500", Decimal("500"), "500 m"),
        ("500 mét", "500 mét", Decimal("500"), "500 mét"),
        ("1,200 metres @ 1,250.00", "1,200", Decimal("1200"), "1,200 metres"),
        ("各50m", "50m", Decimal("50"), "50m"),
        # Another unit than the line's metres, or none: never converted,
        # never assumed. The words, unit included, are kept for Sales.
        ("đổi còn 3 km", "3", None, "3 km"),
        ("3km", "3km", None, "3km"),
        ("4 cuộn", "4", None, "4 cuộn"),
        ("4 cuon", "4 cuon", None, "4 cuon"),
        ("2 reels", "2", None, "2 reels"),
        ("1000 ft", "1000", None, "1000 ft"),
        ("200 yards", "200", None, "200 yards"),
        ("50 kgs", "50", None, "50 kgs"),
        ("3 spools", "3", None, "3 spools"),
        ("2 tấn", "2", None, "2 tấn"),
        ("5 thùng", "5", None, "5 thùng"),
        ("50 mm", "50", None, "50 mm"),
        ("\uff12巻", "\uff12", None, "2巻"),
        ("thêm 500", "500", None, "500"),
        ("500 m/cuộn", "500", None, "500 m"),
        # "2.000" alone in the mail: two thousand or two.
        ("giảm còn 2.000 m", "2.000 m", None, "2.000 m"),
    ],
)
def test_a_quantity_is_read_only_in_metres_from_the_word_after_its_number(
    text: str, span: str, value: Decimal | None, words: str
) -> None:
    located = locate(text, span, bounded=True)
    assert located is not None

    read = quantity_at(text, located, notation_of(text))

    assert read is not None and read[0] == value and read[1].text == words


def test_a_quantity_span_with_no_number_or_two_is_no_quantity() -> None:
    for text in ("3 cuộn x 500 m", "giảm bớt"):
        located = locate(text, text, bounded=True)
        assert located is not None and quantity_at(text, located, notation_of(text)) is None
