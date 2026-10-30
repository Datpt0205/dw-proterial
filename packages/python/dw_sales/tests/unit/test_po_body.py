"""A PO the customer wrote in the mail body (the AI list, item 4): what code
accepts of a model's reading, how intake opens a case from it, and that the
mail's text is the source `prepare` asks to have been opened."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from dw_agent_runtime.model.prompts import PromptRegistry
from dw_kernel.errors import ConflictError, NotFoundError, PermissionDeniedError
from dw_sales.application.case_store import MESSAGE_TEXT
from dw_sales.application.model_reading import ModelUnavailableError, estimated_tokens
from dw_sales.application.order_intake import NO_DOCUMENT
from dw_sales.application.po_body_reading import PO_BODY_EXTRACTION, PROMPT_TOKENS
from dw_sales.application.source import required_regions
from dw_sales.domain.anchors import MessageText
from dw_sales.domain.mail_parts import newest_part
from dw_sales.domain.messages import EmailAddress, InboundMessage, MailAuthentication
from dw_sales.domain.orders import FindingCode, OrderCase, PoDocument, RegionFlag
from dw_sales.domain.po_body_reading import ModelPoBody, parse_amount, read_po_body
from dw_sales.domain.rfq_reading import normalised, parse_number
from dw_sales.evals.graders import AN, CALLERS, OUTSIDER, READER
from dw_sales.evals.recorded import ByPrompt, Recorded
from dw_sales.evals.world import BETA, SampleWith, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
FIXTURE = json.loads(
    (REPO / "evals" / "fixtures" / "cases" / "sales_po_body.json").read_text(encoding="utf-8")
)
VI = FIXTURE["golden"][0]
RECEIVED = date(2026, 10, 2)
PARSER = str(PO_BODY_EXTRACTION)


def _text(spec: dict[str, Any]) -> str:
    message = InboundMessage(
        message_id=spec["message_id"],
        sender=EmailAddress(address=spec["sender"]),
        subject=spec["subject"],
        received_at=datetime.fromisoformat(spec["received_at"]),
        body_text=spec["body"],
        authentication=MailAuthentication(**spec["authentication"]),
    )
    return normalised(newest_part(message).text)


def _read(answer: dict[str, Any], spec: dict[str, Any] = VI["message"]) -> Any:
    return read_po_body(
        _text(spec), ModelPoBody.model_validate(answer), RECEIVED, parser_version=PARSER
    )


def _answer(**line_change: Any) -> dict[str, Any]:
    answer = copy.deepcopy(VI["answer"])
    answer["lines"][0].update(line_change)
    return answer


# ------------------------------------------------------------ the reading --


def test_the_right_reading_is_a_po_from_the_mail_with_every_value_flagged() -> None:
    verdict = _read(VI["answer"])
    document = verdict.document
    assert document is not None and verdict.not_read is None
    assert document.from_message and document.attachment_id is None
    assert document.parser_version == PARSER and document.regions == ("message_text",)
    header = document.header
    assert (header.po_no, header.po_date, header.currency) == (
        "VLX-PO-2610-0201",
        date(2026, 10, 1),
        "USD",
    )
    first = document.lines[0]
    assert (first.customer_item_code, first.quantity, first.uom, first.unit_price) == (
        "VX-W24-BK",
        Decimal(6100),
        "m",
        Decimal("0.0420"),
    )
    assert first.requested_date == date(2026, 10, 20)
    assert document.body is not None
    text = document.body.text
    for anchor in document.anchors():
        assert anchor.in_message and anchor.chars is not None
        assert anchor.quote == text[anchor.chars.start : anchor.chars.end]
    for holder in (header, *document.lines):
        flagged = {f.field for f in holder.flags if f.flag is RegionFlag.MODEL_READ}
        assert flagged == set(type(holder.anchors).model_fields)


def test_what_the_mail_does_not_write_is_what_it_implies_anchored_where_it_comes_from() -> None:
    no_date = copy.deepcopy(VI["answer"]) | {"po_date_span": None}
    document = _read(no_date).document
    assert document is not None
    header, first = document.header, document.lines[0]
    assert header.revision == 0 and header.anchors.revision == header.anchors.po_no
    assert header.po_date == RECEIVED and header.anchors.po_date == header.anchors.po_no
    assert first.amount == first.quantity * first.unit_price
    assert first.anchors.amount == first.anchors.unit_price
    bare = _read(_answer(description_span=None, requested_date_span=None)).document
    assert bare is not None
    line = bare.lines[0]
    assert line.description == "" and line.anchors.description == line.anchors.customer_item_code
    assert line.requested_date is None and line.anchors.requested_date == line.anchors.line_no


def test_a_value_from_outside_its_line_refuses_the_whole_po() -> None:
    # The second line's price, given for the first: not inside the first line.
    verdict = _read(_answer(unit_price_span="0.4850"))
    assert verdict.document is None and verdict.not_read == "line_refused"
    assert verdict.refused["unit_price_not_found"] == 1


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"customer_item_code_span": None}, "line_refused"),
        ({"quantity_span": None}, "line_refused"),
        ({"unit_price_span": None}, "line_refused"),
        ({"quantity_span": "6.100", "uom_span": None}, "line_refused"),
    ],
)
def test_a_line_without_its_code_quantity_unit_or_price_refuses_the_po(
    change: dict[str, Any], reason: str
) -> None:
    assert _read(_answer(**change)).not_read == reason


def test_no_number_no_currency_or_no_line_is_no_po() -> None:
    assert _read(VI["answer"] | {"po_no_span": None}).not_read == "no_po_number"
    assert _read(VI["answer"] | {"currency_span": None}).not_read == "currency_missing"
    assert _read(VI["answer"] | {"currency_span": "EUR"}).not_read == "currency_missing"
    assert _read(VI["answer"] | {"lines": []}).not_read == "no_lines"


def test_the_same_line_twice_refuses_the_po() -> None:
    answer = copy.deepcopy(VI["answer"])
    answer["lines"].append(copy.deepcopy(answer["lines"][0]))
    verdict = _read(answer)
    assert verdict.not_read == "line_refused" and verdict.refused["line_repeated"] == 1


def test_the_injected_and_the_missing_answers_read_no_po() -> None:
    injection, missing = FIXTURE["injection"], FIXTURE["missing"]
    assert _read(injection["obeyed"], injection["message"]).document is None
    assert _read(missing["claimed"], missing["message"]).document is None


def test_an_amount_with_cents_reads_with_both_separators_and_nothing_else_does() -> None:
    assert parse_amount("2,792.00") == Decimal("2792.00")
    assert parse_amount("2.792,00 USD") == Decimal("2792.00")
    assert parse_amount("1,234,567.50") == Decimal("1234567.50")
    assert parse_amount("408.00") == Decimal("408.00")
    assert parse_amount("1,234.567,89") is None
    # A quantity or a price written so stays unread, as before (ticket 29).
    assert parse_amount("1.200,5") is None
    assert parse_number("1.200,5") is None


# ---------------------------------------------------- the document's rules --


def test_a_po_from_the_mail_holds_its_text_and_points_only_into_it() -> None:
    document = _read(VI["answer"]).document
    assert document is not None and document.body is not None
    dumped = document.model_dump()
    with pytest.raises(ValidationError, match="one attachment or from the message's text"):
        PoDocument.model_validate({**dumped, "body": None})
    with pytest.raises(ValidationError, match="one attachment or from the message's text"):
        PoDocument.model_validate({**dumped, "attachment_id": "PB-VI-A1"})
    shorter = document.body.text[:10]
    cut = MessageText(text=shorter, sha256=hashlib.sha256(shorter.encode()).hexdigest())
    with pytest.raises(ValidationError, match="points outside"):
        PoDocument.model_validate(
            {**dumped, "body": cut.model_dump(), "attachment_sha256": cut.sha256}
        )


# ------------------------------------------------------------- the intake --


def _model(answer: dict[str, Any] | None, *, down: bool = False) -> ByPrompt:
    intent = Recorded(raw={"language": "vi", "referenced_number_spans": [], "kind": "po"})
    reader = Recorded(failure=ModelUnavailableError("down")) if down else Recorded(raw=answer)
    return ByPrompt({"sales.message_intent": intent, PO_BODY_EXTRACTION.prompt_id: reader})


async def _process(model: Any, spec: dict[str, Any] = VI["message"], **kw: Any) -> Any:
    with SampleWith([spec]) as sample:
        world = open_world(REPO, sample, CALLERS, model=model, **kw)
        disposition, case = (await world.process_each(AN, [spec["message_id"]]))[spec["message_id"]]
        return world, disposition, case


async def test_a_po_in_the_mail_opens_a_case_whose_every_value_sales_confirms() -> None:
    _, disposition, case = await _process(_model(VI["answer"]))
    assert disposition.kind == "case_created"
    assert isinstance(case, OrderCase) and case.document.from_message
    uncertain = {f.line_no for f in case.findings if f.code is FindingCode.VALUE_UNCERTAIN}
    assert uncertain == {None, 1, 2}
    assert required_regions(case) == {MESSAGE_TEXT}


async def test_a_model_down_sends_the_mail_to_sales_with_why() -> None:
    _, disposition, case = await _process(_model(None, down=True))
    assert case is None and disposition.kind == "routed_to_sales"
    assert disposition.reason == "other"
    assert disposition.detail == f"{NO_DOCUMENT}; DW1 did not read a PO from the mail (unavailable)"


async def test_a_step_not_measured_at_its_bar_asks_no_model() -> None:
    reader = Recorded(raw=VI["answer"])
    intent = Recorded(raw={"language": "vi", "referenced_number_spans": [], "kind": "po"})
    model = ByPrompt({"sales.message_intent": intent, PO_BODY_EXTRACTION.prompt_id: reader})
    _, disposition, case = await _process(model, measured=False)
    assert case is None and disposition.kind == "routed_to_sales"
    assert reader.calls == []


async def test_no_model_routes_the_mail_as_before() -> None:
    _, disposition, case = await _process(None)
    assert case is None and disposition.kind == "routed_to_sales"


async def test_a_sender_no_customer_owns_is_not_read() -> None:
    spec = VI["message"] | {"message_id": "PB-UNKNOWN", "sender": "buyer@unknown.example"}
    reader = Recorded(raw=VI["answer"])
    model = ByPrompt(
        {
            "sales.message_intent": Recorded(
                raw={"language": "vi", "referenced_number_spans": [], "kind": "po"}
            ),
            PO_BODY_EXTRACTION.prompt_id: reader,
        }
    )
    _, disposition, case = await _process(model, spec)
    assert case is None and disposition.reason == "customer_unknown"
    assert reader.calls == []


# ------------------------------------------------------- the source gate --


async def _opened(world: World, case: OrderCase) -> None:
    await world.services.sources.order_message_text(AN.context(), case.case_id)


async def test_prepare_waits_until_the_mail_text_was_opened() -> None:
    world, _, case = await _process(_model(VI["answer"]))
    assert isinstance(case, OrderCase)
    with pytest.raises(ConflictError) as refused:
        await world.services.order_commands.prepare(
            AN.context(), case.case_id, case_version=world.order(case.case_id).case_version
        )
    assert refused.value.details["rule"] == "source_not_served"
    assert refused.value.details["missing"] == ["message_text"]
    view = await world.services.sources.order_message_text(AN.context(), case.case_id)
    assert view.sha256 == case.document.attachment_sha256
    with pytest.raises(ConflictError) as still:
        await world.services.order_commands.prepare(
            AN.context(), case.case_id, case_version=world.order(case.case_id).case_version
        )
    # Opened: what still holds it is the values Sales has not confirmed.
    assert still.value.details.get("rule") != "source_not_served"


async def test_another_tenant_finds_neither_the_case_nor_its_mail() -> None:
    world, _, case = await _process(_model(VI["answer"]))
    assert isinstance(case, OrderCase)
    with pytest.raises(NotFoundError):
        await world.services.sources.order_message_text(OUTSIDER.context(BETA), case.case_id)


async def test_a_reader_who_may_not_see_amounts_is_refused_the_mail() -> None:
    """The mail may state a price: the text is a price reader's only."""
    world, _, case = await _process(_model(VI["answer"]))
    assert isinstance(case, OrderCase)
    with pytest.raises(PermissionDeniedError):
        await world.services.sources.order_message_text(READER.context(), case.case_id)


async def test_an_order_read_from_a_file_has_no_mail_text_to_serve() -> None:
    with SampleWith([]) as sample:
        world = open_world(REPO, sample, CALLERS)
        _, case = (await world.process_each(AN, ["M01"]))["M01"]
        assert isinstance(case, OrderCase)
        with pytest.raises(NotFoundError):
            await world.services.sources.order_message_text(AN.context(), case.case_id)


async def test_the_case_view_says_the_po_has_no_file() -> None:
    world, _, case = await _process(_model(VI["answer"]))
    assert isinstance(case, OrderCase)
    view = await world.services.orders.get(AN.context(), case.case_id)
    assert view.attachment_id is None
    assert view.attachment_sha256 == case.document.attachment_sha256


def test_the_prompt_file_is_the_one_the_step_names_and_fits_its_room() -> None:
    prompts = PromptRegistry()
    prompts.load_directory(REPO / "configs" / "prompts")
    rendered = prompts.render(
        PO_BODY_EXTRACTION.prompt_id,
        PO_BODY_EXTRACTION.version,
        {"mail": ""},
        tenant_id=None,
    )
    assert estimated_tokens(rendered.system + rendered.user) < PROMPT_TOKENS
