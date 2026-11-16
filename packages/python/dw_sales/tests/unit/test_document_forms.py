"""A customer's own request form read by the forms the tenant's
``document-forms`` skill names; code checks every value at its cell (ticket
42 family 3, dw_sales ADR 0014).

The forms and their words are the tenant's; the route a form opens and every
check of every value are code's. These tests hold: the platform's standard
form says the fixed reader's labels, a version's forms are read and checked
by code (an unknown route or a customer that is no code refused when
proposed, unused when served), a reading is offered the sender's customer's
forms only and held to them, every value is still found at its cell, the
reading stamps the version and the form, intake takes a file the forms read
as a quotation request only where the step may run, and a proposal is
replayed on the platform's example files.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.interpretation import (
    ModelUnavailableError,
    PromptRef,
    estimated_tokens,
)
from dw_agent_runtime.model.prompts import PromptRegistry
from dw_sales.adapters import rfq_excel
from dw_sales.adapters.skill_examples import FixtureDocumentFormExamples
from dw_sales.adapters.skill_files import load_dw1_skills
from dw_sales.application.document_forms import (
    DOCUMENT_FORMS_PROMPT,
    PROMPT_TOKENS,
    DocumentFormExample,
    DocumentFormReplay,
    forms_schema,
)
from dw_sales.application.order_intake import MessageKind
from dw_sales.application.skills import STEP_SKILLS, skill_key
from dw_sales.domain.activity import request_step
from dw_sales.domain.document_forms import (
    DOCUMENT_FORMS,
    FORM_ROUTES,
    NO_FORM,
    document_forms_of,
    guidance,
)
from dw_sales.domain.order_checks import ModelStep
from dw_sales.domain.orders import RegionFlag
from dw_sales.domain.quotes import RequestReading
from dw_sales.evals.document_forms import (
    _below_bar,
    _files_of,
    _intake_for,
    _Switched,
    company_book,
    forms_book,
    forms_reader,
    read_form,
)
from dw_sales.evals.intents import _platform_rules
from dw_sales.evals.requests import rendered
from dw_sales.evals.thread_agent import run_for
from dw_sales.evals.world import ALPHA, BETA, measured_gate

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
SKILLS = REPO / "configs" / "skills" / "dw1"
PLATFORM_FORMS = load_dw1_skills(SKILLS).skills[skill_key(DOCUMENT_FORMS)]
FIXTURE = json.loads(
    (REPO / "evals" / "fixtures" / "cases" / "sales_document_forms.json").read_text("utf-8")
)
BRN, KMH, QRL = FIXTURE["forms"]
BRN_PART = "FORMS-VI-BRN-01-A1!RFQ"
BRN_LINE = "1 | BRN-WR-1102 | Dây đơn 0.5mm2 đỏ | 4 | 2000 | m | 2026-11-20"


@dataclass(frozen=True)
class _Ctx:
    """What the eval's helpers read of a grader context."""

    repo_root: Path = REPO


def _company() -> Any:
    return company_book(_Ctx())  # type: ignore[arg-type]


def _answer(form: str, **overrides: Any) -> dict[str, Any]:
    item = {
        "part": BRN_PART,
        "line_span": BRN_LINE,
        "description_span": "Dây đơn 0.5mm2 đỏ",
        "customer_item_code_span": "BRN-WR-1102",
        "quantity_span": "2000",
        "uom_span": "m",
        "required_date_span": "2026-11-20",
        "target_price_span": None,
        **overrides,
    }
    return {
        "form": form,
        "rfq_no_span": "BRN-DN-2610-07",
        "quote_due_span": "2026-10-09",
        "currency_span": "VND",
        "items": [item],
    }


@dataclass
class Scripted:
    """A door answering ``answer`` (validated against the call's schema
    unless ``validate`` is off), or no usable answer for None; keeps what
    each call allowed and was sent."""

    answer: Mapping[str, Any] | None
    validate: bool = True
    model_profile: str = "onprem"
    route: str = "structured_extraction"
    max_input_tokens: int = 6000
    allowed: list[tuple[str, ...]] = field(default_factory=list)
    inputs: list[dict[str, str]] = field(default_factory=list)

    async def interpret[OutputT: BaseModel](
        self,
        prompt: PromptRef,
        inputs: Mapping[str, str],
        schema: type[OutputT],
        *,
        run: RunContext,
        max_output_tokens: int,
    ) -> OutputT:
        if prompt != DOCUMENT_FORMS_PROMPT:
            raise ModelUnavailableError("not scored here")
        self.inputs.append(dict(inputs))
        self.allowed.append(tuple(schema.model_json_schema()["properties"]["form"]["enum"]))
        if self.answer is None:
            raise ModelUnavailableError("recorded: no usable answer")
        if not self.validate:
            return schema.model_construct(**self.answer)
        return schema.model_validate(self.answer)


# ------------------------------------------------------- the platform --


def test_the_standard_form_says_every_label_the_fixed_reader_reads() -> None:
    """One layout, two readers: the platform's standard form names, in its
    words, each label `rfq_excel` reads a request by, so they cannot drift
    apart unseen."""
    forms = document_forms_of(PLATFORM_FORMS.instructions)
    standard = next(f for f in forms.forms if f.name == "standard_rfq")
    rfq_labels = rfq_excel._RFQ_COLUMNS | {
        rfq_excel._RFQ_NO,
        rfq_excel._RFQ_DATE,
        rfq_excel._QUOTE_DUE,
        rfq_excel._CURRENCY,
    }
    for label in rfq_labels:
        assert f'"{label}"' in standard.means, label
    assert {f.route for f in forms.forms} <= FORM_ROUTES
    assert all(f.customer is None for f in forms.forms)


def test_the_prompt_file_is_the_one_the_step_names_and_fits_its_room() -> None:
    registry = PromptRegistry()
    registry.load_directory(REPO / "configs" / "prompts")
    rendered_prompt = registry.render(
        DOCUMENT_FORMS_PROMPT.prompt_id,
        DOCUMENT_FORMS_PROMPT.version,
        {"forms": "", "parts": ""},
        tenant_id=None,
    )
    assert estimated_tokens(rendered_prompt.system + rendered_prompt.user) < PROMPT_TOKENS


def test_the_skill_is_read_at_a_fixed_step_never_picked() -> None:
    assert DOCUMENT_FORMS in STEP_SKILLS


# ------------------------------------------------------- the words --


def test_a_form_opening_a_route_the_platform_lacks_is_refused() -> None:
    with pytest.raises(ValueError, match="route po"):
        document_forms_of("- kind: brn_po\n  customer: BRN\n  route: po\n  means: an order")


@pytest.mark.parametrize(
    "words",
    [
        "no form at all",
        "- kind: a\n  customer: any\n  route: quote_request\n  means: x\n\n"
        "- kind: a\n  customer: any\n  route: quote_request\n  means: y",
        "- kind: a\n  customer: Brennic Ltd\n  route: quote_request\n  means: x",
        "- kind: a\n  customer: any\n  route: quote_request\n  owner: x\n  means: x",
        "- kind: none\n  customer: any\n  route: quote_request\n  means: x",
        "- kind: a\n  route: quote_request\n  means: no customer",
        "- kind: a\n  customer: any\n  means: no route",
        "- kind: a\n  customer: any\n  route: quote_request",
    ],
)
def test_a_set_of_forms_that_does_not_hold_is_refused(words: str) -> None:
    with pytest.raises(ValueError):
        document_forms_of(words)


def test_a_customers_forms_are_its_own_and_those_any_customer_sends() -> None:
    forms = document_forms_of(f"{PLATFORM_FORMS.instructions}\n\n{FIXTURE['company_forms']}")
    assert [f.name for f in forms.of("BRN")] == [
        "standard_rfq",
        "customer_request",
        "brennic_de_nghi",
    ]
    assert "brennic_de_nghi" not in {f.name for f in forms.of("KMH")}


def test_the_guidance_leaves_every_form_out() -> None:
    words = guidance(f"{PLATFORM_FORMS.instructions}\n\n{FIXTURE['company_forms']}")
    assert "## Rules" in words and "# Reading a customer's request form" in words
    assert "- kind:" not in words and "Brennic" not in words


def test_the_schema_offers_the_forms_and_none_only() -> None:
    schema = forms_schema(("standard_rfq", "brennic_de_nghi"))
    assert schema.model_json_schema()["properties"]["form"]["enum"] == [
        "standard_rfq",
        "brennic_de_nghi",
        NO_FORM,
    ]
    with pytest.raises(ValidationError):
        schema.model_validate({**_answer("approved_order")})


# ------------------------------------------------------- the reading --


async def test_a_new_customers_form_is_read_at_its_cells_flagged_and_stamped() -> None:
    model = Scripted(_answer("brennic_de_nghi"))
    read = await read_form(model, BRN, _company())
    assert read is not None
    document = read.document
    (item,) = document.items
    assert (str(item.quantity.value), str(item.needed_by.value)) == ("2000", "2026-11-20")
    assert item.quantity.source.cell_ref == "RFQ!E6"
    assert document.currency.value == "VND" and document.rfq_no is not None
    assert {f.field for f in item.flags if f.flag is RegionFlag.MODEL_READ} >= {
        "description",
        "quantity",
        "needed_by",
    }
    assert (read.reading.prompt, read.reading.form, read.reading.skill) == (
        str(DOCUMENT_FORMS_PROMPT),
        "brennic_de_nghi",
        "sales_skill_document_forms@1.1.0",
    )
    assert set(model.inputs[0]) == {"forms", "parts"}


async def test_a_value_the_file_does_not_hold_is_dropped() -> None:
    model = Scripted(_answer("brennic_de_nghi", quantity_span="5000"))
    read = await read_form(model, BRN, _company())
    assert read is not None
    assert read.document.items[0].quantity.value is None
    assert read.reading.refused


async def test_another_customers_form_is_never_offered_nor_its_words_shown() -> None:
    model = Scripted(_answer("brennic_de_nghi"), validate=False)
    assert await read_form(model, KMH, _company()) is None
    assert "brennic_de_nghi" not in model.allowed[0]
    assert "Brennic" not in model.inputs[0]["forms"]
    assert "kumohana_mitsumori" in model.allowed[0]


async def test_another_tenant_is_offered_the_platforms_forms_only() -> None:
    model = Scripted(_answer(NO_FORM) | {"items": []})
    assert await read_form(model, BRN, _company(), BETA) is None
    assert model.allowed[0] == ("standard_rfq", "customer_request", NO_FORM)


@pytest.mark.parametrize(
    ("answer", "validate"),
    [(_answer(NO_FORM), True), (_answer("approved_order"), False), (None, True)],
)
async def test_no_form_a_name_not_offered_or_no_usable_answer_reads_nothing(
    answer: Any, validate: bool
) -> None:
    assert await read_form(Scripted(answer, validate), BRN, _company()) is None


async def test_a_version_whose_forms_no_longer_read_is_not_used() -> None:
    bad = "- kind: brn_po\n  customer: BRN\n  route: po\n  means: an order"
    model = Scripted(_answer("brennic_de_nghi"))
    assert await read_form(model, BRN, forms_book((ALPHA, "1.1.0", bad))) is None
    assert model.inputs == []


# ------------------------------------------------------- the doors --


async def _classified(answer: Any, *, rules: Any = None, gate: Any = None, spec: Any = BRN) -> Any:
    model = Scripted(answer)
    message, contents = rendered(spec)
    from dw_sales.adapters.mock import MockInbox

    intake = _intake_for(
        rules or _Switched(_platform_rules(), ALPHA),
        gate or measured_gate(REPO, ALPHA)[0],
        forms_reader(model, _company()),
        MockInbox([message], _files_of(message, contents), scope=ALPHA),
    )
    return await intake.classify(ALPHA, message, run=run_for(ALPHA)), model


async def test_intake_takes_a_file_the_forms_read_as_a_quotation_request() -> None:
    classified, model = await _classified(_answer("brennic_de_nghi"))
    assert classified.kind is MessageKind.QUOTE_REQUEST and len(model.inputs) == 1


@pytest.mark.parametrize("why", ["off", "below_bar", "no_form"])
async def test_intake_classifies_as_before_where_the_forms_may_not_or_do_not_read(
    why: str,
) -> None:
    rules = _Switched(_platform_rules(), ALPHA, forms=why != "off")
    gate = _below_bar() if why == "below_bar" else None
    answer = _answer(NO_FORM) | {"items": []} if why == "no_form" else _answer("brennic_de_nghi")
    classified, model = await _classified(answer, rules=rules, gate=gate)
    assert classified.kind is not MessageKind.QUOTE_REQUEST
    assert bool(model.inputs) is (why == "no_form")


def test_a_request_read_by_the_forms_counts_under_their_step() -> None:
    base: dict[str, Any] = {
        "prompt": "sales.rfq_extraction@1.0.0",
        "model_profile": "onprem",
        "route": "structured_extraction",
        "rules": "sales_order_rules@1.5.2",
        "calls": 1,
    }
    assert request_step(RequestReading(**base)) is ModelStep.RFQ_EXTRACTION
    by_forms = RequestReading(
        **{**base, "prompt": str(DOCUMENT_FORMS_PROMPT)},
        skill="sales_skill_document_forms@1.0.0",
        form="standard_rfq",
    )
    assert request_step(by_forms) is ModelStep.SKILL_DOCUMENT_FORMS


# ------------------------------------------------------- the replay --


@dataclass
class _ByWords:
    """Reads the BRN form where the served words name it, else no form; an
    order read as a request where the words open a door for one."""

    model_profile: str = "onprem"
    route: str = "structured_extraction"
    max_input_tokens: int = 6000

    async def interpret[OutputT: BaseModel](
        self,
        prompt: PromptRef,
        inputs: Mapping[str, str],
        schema: type[OutputT],
        *,
        run: RunContext,
        max_output_tokens: int,
    ) -> OutputT:
        if prompt != DOCUMENT_FORMS_PROMPT:
            raise ModelUnavailableError("not scored here")
        if "brennic_de_nghi" in inputs["forms"] and "BRN-WR-1102" in inputs["parts"]:
            return schema.model_validate(_answer("brennic_de_nghi"))
        if "any_order" in inputs["forms"] and "ĐƠN ĐẶT HÀNG" in inputs["parts"]:
            return schema.model_validate(
                _answer(
                    "any_order",
                    part="PO-1-A1!RFQ",
                    line_span="1 | BRN-WR-1102 | Dây đơn 0.5mm2 đỏ | 2000 | m",
                    customer_item_code_span=None,
                    required_date_span=None,
                )
                | {"rfq_no_span": None, "quote_due_span": None, "currency_span": "VND"}
            )
        return schema.model_validate(_answer(NO_FORM) | {"items": []})


class _Examples:
    def __init__(self, customer: Any) -> None:
        self.customer = customer

    def examples(self) -> list[DocumentFormExample]:
        message, contents = rendered(BRN)
        order = {
            **BRN,
            "id": "po-1",
            "rows": [
                ["BRENNIC - ĐƠN ĐẶT HÀNG"],
                ["Tiền tệ", "VND"],
                [1, "BRN-WR-1102", "Dây đơn 0.5mm2 đỏ", 2000, "m"],
            ],
        }
        po_message, po_contents = rendered(order)
        day = message.received_at.date()
        # The one line the scripted reading reads, as the file states it.
        gold = {**BRN["gold"], "items": BRN["gold"]["items"][:1]}
        return [
            DocumentFormExample("EX-1", message, tuple(contents), self.customer, day, gold),
            DocumentFormExample("SEC-1", po_message, tuple(po_contents), self.customer, day, None),
        ]


class _Rules:
    async def rules(self, scope: Any) -> Any:
        return _platform_rules()


async def test_a_document_forms_proposal_is_replayed_on_files_and_its_doors_graded() -> None:
    from dw_sales.adapters.mock import MockSalesCatalog

    customer = (await MockSalesCatalog.load(ALPHA).customer_by_code(ALPHA, "BRN")).data
    replay = DocumentFormReplay(
        forms_reader(_ByWords(), forms_book()), _Examples(customer), _Rules()
    )
    in_force = PLATFORM_FORMS.skill()
    forgotten: list[uuid.UUID] = []

    def proposed(forms: str) -> Any:
        body = in_force.body.replace("\n\n## Rules", f"\n\n{forms}\n\n## Rules", 1)
        return replace(in_force, body=body, ref="sales_skill_document_forms@1.1.0")

    brn_only = "\n\n".join(FIXTURE["company_forms"].split("\n\n")[:1])
    counts = await replay.counts(
        ALPHA,
        proposed(brn_only),
        in_force,
        new_run=lambda: run_for(ALPHA),
        forget_run=forgotten.append,
    )
    # The proposal reads the BRN file as stated; the version in force reads
    # it as no form. Three readings, three runs freed.
    assert counts == (1, 1, 0, 0, ())
    assert len(forgotten) == 3
    door = "- kind: any_order\n  customer: any\n  route: quote_request\n  means: an order."
    counts = await replay.counts(
        ALPHA, proposed(door), in_force, new_run=lambda: run_for(ALPHA), forget_run=forgotten.append
    )
    assert counts[4] == ("SEC-1",)


def test_the_replay_examples_are_the_request_files_and_the_forms_fixture() -> None:
    examples = FixtureDocumentFormExamples.load(REPO).examples()
    golden = [e for e in examples if e.gold is not None]
    security = [e for e in examples if e.gold is None]
    assert len(golden) == 10 + 3 + 1 and len(security) == 2
    assert {e.example_id for e in security} == {"forms-vi-vlx-po", "forms-en-qrl-invoice"}
    assert all(e.customer.code in ("VLX", "QRL") for e in security)
