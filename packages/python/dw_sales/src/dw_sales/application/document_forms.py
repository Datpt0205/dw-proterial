"""A customer's own request form, read by the forms the tenant's
``document-forms`` skill names; code checks every value at its cell (ticket
42 family 3, dw_sales ADR 0014).

The fixed-label reader (`adapters.rfq_excel`) reads one layout by its English
labels, and a request on any other customer's form went to a person, or to
ticket 29's reading (`rfq_reading`), which knows no form. Here the tenant
says in words, per customer, which label or column of its form means which
field (`domain.document_forms`), and a model reads the file by those words:

- **Code chooses the forms shown**: only the sender's customer's own forms
  and those any customer may send (`DocumentForms.of`), the customer being
  the sender domain's in master data, never anything the file or the model
  says. One customer's form never reads another's file.
- **The model answers** which of those forms the file is, or ``none``, and
  the span text of every value, in the schema ticket 29's reading answers in
  (`ModelRfqReading`): the answer's schema is built per call from the forms'
  names plus ``none``, and code reads a name it did not offer as ``none``.
- **Code verifies every value** as ticket 29's reading does (`verify_rfq`):
  each span found once, whole, in the cell of the line it belongs to, parsed
  by code, notation settled by the document or the customer's record
  (ticket 37); a value not found is dropped, never repaired. The request is
  built by the one builder both readings share (`RfqModelReader.request_of`),
  every value flagged ``model_read`` for Sales to confirm. What the model
  still decides is which field a cell fills: the residual risk, which is
  why every value is flagged.
- **Nothing read** (``none`` in any call, two forms named for one file, the
  model down, a version whose forms no longer read, a file shown in part,
  too long, no item or currency verified): `DocumentFormReader.read` returns
  None and the file is read exactly as with the step off. A budget or quota
  refusal propagates, as everywhere.
- **What it opens**: a form names one route, the quotation flow
  (`FORM_ROUTES`). Intake asks this reader where no fixed reader recognised
  a file (`order_intake`, `DocumentFormReader.recognises`: the same calls
  and checks, no request built): a file it reads into a request makes the
  mail a quotation request, beside the ``RFQ No.`` marker, never instead of
  it.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, create_model

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.interpretation import (
    ModelUnavailableError,
    PromptRef,
    estimated_tokens,
)
from dw_agent_runtime.model.skills import Skill
from dw_platform.domain.messages import AttachmentContent, InboundMessage
from dw_sales.application.customer_notations import record_for
from dw_sales.application.mail_kinds import SkillPort
from dw_sales.application.ports import SalesScope
from dw_sales.application.rfq_reading import RequestRead, RfqModelReader, calls_for, unread
from dw_sales.domain.catalog import Customer
from dw_sales.domain.document_forms import (
    DOCUMENT_FORMS,
    MAX_FORMS,
    NO_FORM,
    DocumentForm,
    DocumentForms,
    document_forms_of,
    guidance,
)
from dw_sales.domain.order_checks import OrderRules
from dw_sales.domain.quotes import RfqDocument
from dw_sales.domain.rfq_reading import (
    MAX_ITEMS_PER_CALL,
    ModelRfqItem,
    ModelRfqReading,
    TextPart,
    VerifiedRfq,
    notations,
    verify_rfq,
)

__all__ = [
    "DOCUMENT_FORMS_PROMPT",
    "DocumentFormExample",
    "DocumentFormExamplesPort",
    "DocumentFormReader",
    "DocumentFormReplay",
    "forms_schema",
    "request_values",
    "served_forms",
]

_LOG = logging.getLogger("dw_sales.model")

# The prompt a form is read with (`configs/prompts/sales/document_forms@1.0.0
# .yaml`); the skill's words are one of its contained inputs.
DOCUMENT_FORMS_PROMPT: Final = PromptRef("sales.document_forms", "1.0.0")
# What the prompt costs without the skill's words and the parts, held above
# its rendered size by a test.
PROMPT_TOKENS: Final = 1000
# Room for up to 15 items (about 120 tokens each), the request's own and the
# form's name.
_OUTPUT_TOKENS: Final = 2000
_SPAN = Field(min_length=1, max_length=300)


def forms_schema(names: Sequence[str]) -> type[BaseModel]:
    """The answer's schema for a reading offered the forms ``names``: the
    form first, one of ``names`` or `NO_FORM`, then ticket 29's spans. Built
    per call because the forms are the tenant's and the customer's; the
    gateway sends it as the server's JSON schema."""
    if not 0 < len(names) <= MAX_FORMS:
        raise ValueError("a reading is offered between one and sixty forms")
    allowed: Any = Literal.__getitem__((*names, NO_FORM))
    return create_model(
        "DocumentFormAnswer",
        __config__=ConfigDict(frozen=True, extra="forbid"),
        form=(allowed, ...),
        rfq_no_span=(str | None, _SPAN),
        quote_due_span=(str | None, _SPAN),
        currency_span=(str | None, _SPAN),
        items=(tuple[ModelRfqItem, ...], Field(max_length=MAX_ITEMS_PER_CALL)),
    )


def served_forms(skill: Skill) -> DocumentForms | None:
    """The forms ``skill``'s words name, or None for words that do not read:
    checked again whenever the skill is served, so a version no longer
    holding is not used (the file is read as with the step off)."""
    try:
        return document_forms_of(skill.body)
    except ValueError as exc:
        # Which version and why; never the words.
        _LOG.warning("document forms of %s not used: %s", skill.ref, type(exc).__name__)
        return None


def _words(skill: Skill, forms: Sequence[DocumentForm]) -> str:
    """What a reading is told: the skill's guidance and the forms offered,
    never another customer's."""
    blocks = "\n\n".join(form.block() for form in forms)
    return f"{guidance(skill.body)}\n\n{blocks}"


@dataclass(frozen=True)
class DocumentFormReader:
    """Reads a customer's file by the tenant's document forms (module
    docstring), on ticket 29's reader's model, texts, notation records and
    request builder."""

    requests: RfqModelReader
    skills: SkillPort

    async def read(
        self,
        scope: SalesScope,
        message: InboundMessage,
        contents: Sequence[AttachmentContent],
        customer: Customer,
        rules: OrderRules,
        *,
        received_on: date,
        run: RunContext,
    ) -> RequestRead | None:
        """The request the files read as, by the run's tenant's skill, or
        None for nothing read. ``customer``: the sender domain's."""
        skill = await self.skills.skill(run, DOCUMENT_FORMS)
        try:
            return await self.reading(
                skill, scope, message, contents, customer, rules, received_on=received_on, run=run
            )
        except ModelUnavailableError:
            return None

    async def recognises(
        self,
        scope: SalesScope,
        contents: Sequence[AttachmentContent],
        customer: Customer,
        rules: OrderRules,
        *,
        received_on: date,
        run: RunContext,
    ) -> bool:
        """Whether the files read into a request by one of the customer's
        forms: what `read` would read, by the same calls and checks, without
        building the request (no item's description is read for it)."""
        skill = await self.skills.skill(run, DOCUMENT_FORMS)
        try:
            found = await self._verdict(
                skill, scope, contents, customer, rules, received_on=received_on, run=run
            )
        except ModelUnavailableError:
            return False
        return found is not None and unread(found[0]) is None

    async def reading(
        self,
        skill: Skill,
        scope: SalesScope,
        message: InboundMessage,
        contents: Sequence[AttachmentContent],
        customer: Customer,
        rules: OrderRules,
        *,
        received_on: date,
        run: RunContext,
    ) -> RequestRead | None:
        """`read` under ``skill`` (the version served, or a proposal its
        replay reads, `DocumentFormReplay`), raising `ModelUnavailableError`
        where a call gave no usable answer, so a replay can count it apart
        from a file read as no form."""
        found = await self._verdict(
            skill, scope, contents, customer, rules, received_on=received_on, run=run
        )
        if found is None:
            return None
        verdict, calls, form = found
        read = await self.requests.request_of(
            scope,
            message,
            contents,
            customer,
            rules,
            verdict,
            run,
            calls,
            prompt=DOCUMENT_FORMS_PROMPT,
        )
        if isinstance(read, str):
            return None
        stamp = read.reading.model_copy(update={"skill": skill.ref, "form": form.name})
        return dataclasses.replace(read, reading=stamp)

    async def _verdict(
        self,
        skill: Skill,
        scope: SalesScope,
        contents: Sequence[AttachmentContent],
        customer: Customer,
        rules: OrderRules,
        *,
        received_on: date,
        run: RunContext,
    ) -> tuple[VerifiedRfq, list[list[TextPart]], DocumentForm] | None:
        """What code accepted of the calls under ``skill``, the calls, and
        the one form every call named; None for nothing read (module
        docstring)."""
        forms = served_forms(skill)
        held = () if forms is None else forms.of(customer.code)
        if not held:
            return None
        words = _words(skill, held)
        parts: list[TextPart] = []
        for content in contents:
            text = await self.requests.texts.text_parts(content, rules.intake)
            if text.unshown:
                # A file read in part would miss lines nobody knows are
                # missing (audit finding 10): a person reads it whole.
                return None
            parts.extend(text.parts)
        if not parts:
            return None
        model = self.requests.model
        calls = calls_for(parts, model.max_input_tokens - PROMPT_TOKENS - estimated_tokens(words))
        if calls is None:
            return None
        schema = forms_schema([form.name for form in held])
        verdict = VerifiedRfq()
        documents = notations(parts)
        record = await record_for(self.requests.records, scope, customer.code)
        read_as: DocumentForm | None = None
        for call in calls:
            inputs = {
                "forms": words,
                # Code-built JSON inside the untrusted block: a cell cannot
                # close its string and pose as another part.
                "parts": json.dumps(
                    [{"part": part.part_id, "text": part.text} for part in call],
                    ensure_ascii=False,
                ),
            }
            answer = await model.interpret(
                DOCUMENT_FORMS_PROMPT, inputs, schema, run=run, max_output_tokens=_OUTPUT_TOKENS
            )
            # Code's reading of the name: one it did not offer is no form,
            # whatever the decoder let through; one file is one form.
            name = str(getattr(answer, "form"))  # noqa: B009 - a schema built per call
            form = next((f for f in held if f.name == name), None)
            if form is None or (read_as is not None and form != read_as):
                return None
            read_as = form
            spans = ModelRfqReading.model_validate(answer.model_dump(exclude={"form"}))
            verify_rfq(call, spans, received_on, into=verdict, documents=documents, record=record)
        assert read_as is not None  # every call named it
        return verdict, calls, read_as


# ------------------------------------------------------------- replay --


def request_values(document: RfqDocument) -> dict[str, Any]:
    """The values a request states, as an example's gold writes them: the
    request's number, due date and currency, and each line's description,
    customer code, quantity and required date, as text."""

    def text(value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return format(value.normalize(), "f")
        return " ".join(str(value).split())

    return {
        "rfq_no": text(document.rfq_no.value if document.rfq_no else None),
        "quote_due": text(document.quote_due.value if document.quote_due else None),
        "currency": text(document.currency.value),
        "items": [
            {
                "description": text(item.description.value),
                "customer_item_code": text(
                    item.customer_item_code.value if item.customer_item_code else None
                ),
                "quantity": text(item.quantity.value),
                "needed_by": text(item.needed_by.value),
            }
            for item in document.items
        ],
    }


@dataclass(frozen=True, slots=True)
class DocumentFormExample:
    """One example file a proposed version is replayed on: the customer it
    is from, and the values it states; None for a security case, a file
    that must never read as a request (an order, an injection)."""

    example_id: str
    message: InboundMessage
    contents: tuple[AttachmentContent, ...]
    customer: Customer
    received_on: date
    gold: Mapping[str, Any] | None


class DocumentFormExamplesPort(Protocol):
    """The platform's example files a document-forms proposal is replayed on."""

    def examples(self) -> Sequence[DocumentFormExample]: ...


class _RulesPort(Protocol):
    async def rules(self, scope: SalesScope) -> OrderRules: ...


# (files, right with the proposal, right with the version in force,
# readings with no usable answer, the security cases the proposal failed).
ReplayCounts = tuple[int, int, int, int, tuple[str, ...]]


@dataclass(frozen=True)
class DocumentFormReplay:
    """A proposed version of the ``document-forms`` skill read on the
    platform's example files beside the version in force
    (`skill_replay.SkillReplayer` asks it for that skill). A golden file is
    right when every value it states is read as stated and nothing else is
    (`request_values`); one not read is not right. A security case fails
    when the proposal reads it into a request at all."""

    reader: DocumentFormReader
    examples: DocumentFormExamplesPort
    rules: _RulesPort

    async def counts(
        self,
        scope: SalesScope,
        proposed: Skill,
        in_force: Skill,
        *,
        new_run: Callable[[], RunContext],
        forget_run: Callable[[uuid.UUID], object],
    ) -> ReplayCounts:
        """Every example read with ``proposed`` and, the golden ones, with
        ``in_force``; each reading a run of its own (``new_run``), freed from
        the spend ledger after (``forget_run``). A reading with no request is
        an answer (the file read as with the step off); one a call gave no
        usable answer to is counted apart."""
        rules = await self.rules.rules(scope)
        files = right_with = right_without = unanswered = 0
        failed: list[str] = []
        for example in self.examples.examples():
            with_it = await self._read(scope, proposed, example, rules, new_run, forget_run)
            unanswered += with_it == "unanswered"
            if example.gold is None:
                if isinstance(with_it, dict):
                    failed.append(example.example_id)
                continue
            without = await self._read(scope, in_force, example, rules, new_run, forget_run)
            files += 1
            unanswered += without == "unanswered"
            right_with += with_it == example.gold
            right_without += without == example.gold
        return files, right_with, right_without, unanswered, tuple(failed)

    async def _read(
        self,
        scope: SalesScope,
        skill: Skill,
        example: DocumentFormExample,
        rules: OrderRules,
        new_run: Callable[[], RunContext],
        forget_run: Callable[[uuid.UUID], object],
    ) -> dict[str, Any] | Literal["unanswered"] | None:
        """The values ``example`` reads as under ``skill``: None for no
        request, ``unanswered`` where a call gave no usable answer."""
        run = new_run()
        try:
            read = await self.reader.reading(
                skill,
                scope,
                example.message,
                example.contents,
                example.customer,
                rules,
                received_on=example.received_on,
                run=run,
            )
        except ModelUnavailableError:
            return "unanswered"
        finally:
            forget_run(run.run_id)
        return None if read is None else request_values(read.document)
