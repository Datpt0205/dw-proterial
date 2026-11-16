"""A model copies a delivery change, complaint or sample request into a
hand-off; code locates, parses and resolves every value, and writes it.

Ticket 33, dw_sales ADR 0005 (the rules: `domain.handoffs`). Asked only for a
message already routed to Sales with one of those three reasons, from a
sender on a customer's domain, where the tenant's rules turn it on and a DW1
run is processing. `HandoffReader.read` sends the subject and the newest part
(`mail_parts.newest_part`, history cut by structure) under prompt
`sales.request_handoff`, with the kind the routing decided and its schema, and
returns what code keeps:

- every span located exactly once in the newest part, as a whole token where
  it is a number, a date, a PO, a line or a lot;
- the PO resolved against the sender's customer's ERP orders, else the one
  live order case DW1 holds for it; another customer's PO, or another
  tenant's, is not there to resolve;
- each line resolved exactly against that order: by its number, by the
  PRV code or the customer's code the convert list maps to the line's item;
- each quantity and date parsed from its span, as the mail's own values
  settle "2.000" and "05/11", else as the sender's customer's notation
  record does (ticket 37, `NotationRecordPort`; marked `from_record`), a
  quantity only in metres: words code does not read are kept, flagged, for
  Sales to fill from; each quote that names no destination
  (`carries_contact`).

A message that does not fit the model's input whole is not cut: it is an
``unavailable`` hand-off counted ``too_long``, for Sales, as before.

No usable answer is an ``unavailable`` hand-off, and an answer code keeps
nothing of is ``nothing_located``: either is an empty form for Sales, the
message routed as before. A budget or quota refusal propagates: the run stops.

`render` writes the hand-off's subject and body from the versioned template
(`HandoffCopy`, `configs/copy/sales_handoffs@<version>.yaml`): the template's
words, the values code kept, and the customer's sentences in quotation marks.

With the tenant's hand-off skill served (ticket 42 family 5,
`handoff_kinds`), the same reading runs under prompt `sales.handoff_kinds`
with the skill's words: the kind is the skill's, its fields and its team come
from the platform's closed sets as the skill maps them, and every check above
is unchanged.
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from string import Formatter
from typing import Any, Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.interpretation import (
    InterpretationPort,
    ModelUnavailableError,
    PromptRef,
    estimated_tokens,
)
from dw_agent_runtime.model.skills import Skill
from dw_platform.domain.mail_parts import MessagePart
from dw_platform.domain.notation import Notation, notation_of, settle
from dw_sales.application.customer_notations import NotationRecordPort, record_for
from dw_sales.application.order_ports import OrderCaseLookupPort
from dw_sales.application.ports import CatalogNotConnectedError, SalesCatalogPort, SalesScope
from dw_sales.domain.catalog import Customer
from dw_sales.domain.handoff_kinds import HandoffKindSpec
from dw_sales.domain.handoffs import (
    MAX_ITEMS,
    MAX_QUOTES,
    MODEL_SCHEMAS,
    FromRecord,
    Handoff,
    HandoffKind,
    HandoffLine,
    HandoffTeam,
    Located,
    ModelComplaint,
    ModelDeliveryChange,
    ModelSampleRequest,
    QuantityRead,
    carries_contact,
    line_number_of,
    locate,
    locate_identifier,
    quantity_at,
)
from dw_sales.domain.rfq_reading import parse_date, parse_document_no

# The prompt the spans are copied with. Its file is
# `configs/prompts/sales/request_handoff@1.0.0.yaml`; a test holds the two
# together, and a new wording is a new version here and a new file there.
REQUEST_HANDOFF: Final = PromptRef("sales.request_handoff", "1.0.0")
# A handful of short spans, or three sentences: about 200 tokens measured.
_OUTPUT_TOKENS: Final = 800
# What the prompt itself costs, held above its rendered size by a test.
PROMPT_TOKENS: Final = 1800
# The same copying by the kinds the tenant's hand-off skill names (ticket 42
# family 5, `configs/prompts/sales/handoff_kinds@1.0.0.yaml`); its cost is
# held under `PROMPT_TOKENS` without the skill's words, which are counted
# beside it.
HANDOFF_KINDS_PROMPT: Final = PromptRef("sales.handoff_kinds", "1.0.0")


_TOO_LONG: Final = "too_long"


@dataclass(frozen=True, slots=True)
class Copied:
    """What a model copied of a mail, located by code, no order resolved:
    the PO number, the lot, the located sentences or items (casefolded) and
    how many lines name a located new quantity or date."""

    po_no: str | None
    lot: str | None
    quotes: tuple[str, ...]
    lines: int


@dataclass(frozen=True, slots=True)
class ServedKind:
    """The tenant's hand-off skill as served, and the kind of it a message
    is read as (`handoff_kinds`)."""

    skill: Skill
    kind: HandoffKindSpec


@dataclass(frozen=True, slots=True)
class _OrderLine:
    line_no: int
    prv_code: str | None
    # Every code the line is known by: its PRV code, the customer's code.
    codes: frozenset[str]


@dataclass(frozen=True, slots=True)
class _Order:
    """The one order of the sender's customer a PO number resolved to."""

    po_no: str
    so_no: str | None
    order_case_id: uuid.UUID | None
    lines: tuple[_OrderLine, ...]


@dataclass(frozen=True)
class HandoffReader:
    """Reads a routed message's hand-off through a model (module docstring)."""

    model: InterpretationPort
    catalog: SalesCatalogPort
    cases: OrderCaseLookupPort
    # The sender's customer's notation record (ticket 37).
    records: NotationRecordPort

    async def read(
        self,
        scope: SalesScope,
        part: MessagePart,
        customer: Customer,
        kind: HandoffKind,
        *,
        received_on: date,
        rules_version: str,
        run: RunContext,
        served: ServedKind | None = None,
    ) -> Handoff:
        """The hand-off of ``kind``'s fields. ``served``: the tenant's
        hand-off skill and the kind of it read (ticket 42 family 5), whose
        words are the model's to read by and whose team and label the
        hand-off carries; None, read as ticket 33 reads it."""
        stamp: dict[str, object] = {
            "kind": kind,
            "prompt": str(REQUEST_HANDOFF if served is None else HANDOFF_KINDS_PROMPT),
            "model_profile": self.model.model_profile,
            "route": self.model.route,
            "rules": rules_version,
        }
        if served is not None:
            stamp |= {
                "skill": served.skill.ref,
                "skill_kind": served.kind.name,
                "kind_label": served.kind.label,
                "to": served.kind.to,
            }
        answer = await self._answer(part, kind, served, run)
        if answer is None or answer == _TOO_LONG:
            # Too long is never a cut: spans are located in the whole text,
            # and a line past a cut would be left out with no one told.
            too_long = {"too_long": 1} if answer == _TOO_LONG else {}
            return Handoff.model_validate({**stamp, "outcome": "unavailable", "refused": too_long})
        assert isinstance(answer, BaseModel)
        refused: Counter[str] = Counter()
        kept = await self._kept(scope, part.text, customer, answer, received_on, refused)
        located = any(
            kept.get(name)
            for name in ("po_no", "lines", "lot", "quotes", "sample_quantity", "quantity")
        )
        return Handoff.model_validate(
            {
                **stamp,
                **kept,
                "outcome": "read" if located else "nothing_located",
                "refused": dict(refused),
            }
        )

    async def _answer(
        self, part: MessagePart, kind: HandoffKind, served: ServedKind | None, run: RunContext
    ) -> BaseModel | Literal["too_long"] | None:
        """The model's spans for ``kind``'s fields, under the skill where
        one is ``served``: ``too_long`` for a mail that does not fit whole,
        None for no usable answer."""
        inputs = {"kind": kind, "subject": part.subject, "body": part.body}
        prompt, budget = REQUEST_HANDOFF, PROMPT_TOKENS
        if served is not None:
            inputs = {
                "skill": served.skill.body,
                "kind": served.kind.name,
                "fields": served.kind.asks,
                "subject": part.subject,
                "body": part.body,
            }
            prompt = HANDOFF_KINDS_PROMPT
            budget = PROMPT_TOKENS + estimated_tokens(served.skill.body)
        if estimated_tokens(part.text) > self.model.max_input_tokens - budget:
            return _TOO_LONG
        try:
            return await self.model.interpret(
                prompt,
                inputs,
                MODEL_SCHEMAS[kind],
                run=run,
                max_output_tokens=_OUTPUT_TOKENS,
            )
        except ModelUnavailableError:
            return None

    async def located(
        self, part: MessagePart, served: ServedKind, *, run: RunContext
    ) -> Copied | None:
        """What the model copies of ``part`` under ``served``, as code
        locates it with no order resolved: what a replay of a skill version
        compares (`handoff_kinds.HandoffKindReplay`), which holds none of the
        tenant's orders. None for no usable answer, or a mail too long."""
        answer = await self._answer(part, served.kind.shape, served, run)
        if not isinstance(answer, BaseModel):
            return None
        text, ignored = part.text, Counter[str]()
        po = lot = None
        quotes: tuple[Located, ...] = ()
        lines = 0
        if isinstance(answer, ModelDeliveryChange | ModelComplaint):
            found = locate_identifier(text, answer.po_no_span)
            po = parse_document_no(found.text) if found else None
        if isinstance(answer, ModelComplaint):
            at = locate(text, answer.lot_no_span, bounded=True)
            lot = at.text if at else None
            quotes = _quotes(text, answer.problem_quote_spans, MAX_QUOTES, ignored, "quote")
        elif isinstance(answer, ModelSampleRequest):
            quotes = _quotes(text, answer.item_spans, MAX_ITEMS, ignored, "item")
        elif isinstance(answer, ModelDeliveryChange):
            lines = sum(
                1
                for line in answer.lines
                if locate(text, line.line_or_item_span, bounded=True)
                and (
                    locate(text, line.new_quantity_span, bounded=True)
                    or locate(text, line.new_date_span, bounded=True)
                )
            )
        return Copied(po, lot, tuple(q.text.casefold() for q in quotes), lines)

    async def _kept(
        self,
        scope: SalesScope,
        text: str,
        customer: Customer,
        answer: BaseModel,
        received_on: date,
        refused: Counter[str],
    ) -> dict[str, Any]:
        # The mail's own notation, and the customer's record for what the
        # mail leaves open: never another customer's.
        notation = _Notations(
            notation_of(text), await record_for(self.records, scope, customer.code)
        )
        if isinstance(answer, ModelSampleRequest):
            quantity = self._quantity(text, answer.quantity_span, notation, refused)
            return {
                "quotes": _quotes(text, answer.item_spans, MAX_ITEMS, refused, "item"),
                "sample_quantity": quantity.value if quantity else None,
                "quantity": quantity.words if quantity else None,
                "quantity_from_record": bool(quantity and quantity.by_record),
            }
        assert isinstance(answer, ModelDeliveryChange | ModelComplaint)
        located_po, order = await self._order(scope, text, customer, answer.po_no_span, refused)
        kept: dict[str, Any] = {}
        if order is not None:
            kept |= {
                "po_no": order.po_no,
                "po": located_po,
                "so_no": order.so_no,
                "order_case_id": order.order_case_id,
            }
        if isinstance(answer, ModelComplaint):
            lot = locate(text, answer.lot_no_span, bounded=True)
            if answer.lot_no_span is not None and lot is None:
                refused["lot"] += 1
            return kept | {
                "lot": lot,
                "quotes": _quotes(text, answer.problem_quote_spans, MAX_QUOTES, refused, "quote"),
            }
        lines: dict[int, HandoffLine] = {}
        for asked in answer.lines:
            line = None
            if order is not None:
                line = await self._line(
                    scope, text, customer, order, asked, received_on, notation, refused
                )
            if line is None or line.line_no in lines:
                refused["line"] += 1
                continue
            lines[line.line_no] = line
        return kept | {"lines": tuple(lines.values())}

    async def _order(
        self,
        scope: SalesScope,
        text: str,
        customer: Customer,
        span: str | None,
        refused: Counter[str],
    ) -> tuple[Located | None, _Order | None]:
        """The located PO span, and the one order of ``customer`` it names."""
        located = locate_identifier(text, span)
        number = parse_document_no(located.text) if located else None
        if span is not None and number is None:
            refused["po_no"] += 1
        if number is None:
            return None, None
        order = await self.order_of(scope, customer, number)
        if order is None:
            refused["po_no"] += 1
        return located, order

    async def order_of(self, scope: SalesScope, customer: Customer, po_no: str) -> _Order | None:
        """The order ``po_no`` is for ``customer``: the ERP's sales order keyed
        from it (its latest revision), else the one live order case DW1 holds
        for it; None when it is neither, or when two cases hold it. With
        Bravo not connected, only DW1's own case answers: a number it does
        not hold is refused, for a person (never a guess)."""
        try:
            erp = (await self.catalog.orders_for_po(scope, customer.code, po_no)).data
        except CatalogNotConnectedError:
            erp = ()
        cases = await self.cases.cases_for_po(scope, customer.code, po_no)
        live = [case for case in cases if case.superseded_by_case is None]
        case_id = live[0].case_id if len(live) == 1 else None
        if erp:
            latest = erp[-1]
            lines = tuple(
                _OrderLine(line.line_no, line.prv_code, frozenset({line.prv_code}))
                for line in latest.lines
            )
            return _Order(po_no, latest.so_no, case_id, lines)
        if len(live) != 1:
            return None
        return _Order(
            po_no,
            None,
            case_id,
            tuple(
                _OrderLine(
                    line.line_no,
                    line.mapping.checked_against,
                    frozenset(
                        code
                        for code in (
                            line.po_line.customer_item_code,
                            line.mapping.checked_against,
                        )
                        if code
                    ),
                )
                for line in live[0].lines
            ),
        )

    async def _line(
        self,
        scope: SalesScope,
        text: str,
        customer: Customer,
        order: _Order,
        asked: Any,
        received_on: date,
        notation: _Notations,
        refused: Counter[str],
    ) -> HandoffLine | None:
        reference = locate(text, asked.line_or_item_span, bounded=True)
        if reference is None:
            return None
        found = await self._order_line(scope, customer, order, reference.text)
        if found is None:
            return None
        # Counted only for a line that is kept: a refused line counts once.
        flags: Counter[str] = Counter()
        quantity = self._quantity(text, asked.new_quantity_span, notation, flags)
        located_date = locate(text, asked.new_date_span, bounded=True)
        day = None
        from_record: list[FromRecord] = ["quantity"] if quantity and quantity.by_record else []
        if located_date is not None:
            words = located_date.text
            settled = settle(
                lambda n: parse_date(words, received_on, n), notation.mail, notation.record
            )
            day = settled.value
            if settled.by_record:
                from_record.append("date")
            if settled.contradicts_record:
                flags["date_contradicts_record"] += 1
        if located_date is not None and day is None:
            flags["date_unread"] += 1
        if quantity is None and located_date is None:
            # A line the customer changes nothing on is no line of the hand-off.
            return None
        refused.update(flags)
        return HandoffLine(
            reference=reference,
            line_no=found.line_no,
            item=found.prv_code,
            new_quantity=quantity.value if quantity else None,
            quantity=quantity.words if quantity else None,
            new_date=day,
            date_span=located_date,
            from_record=tuple(from_record),
        )

    async def _order_line(
        self, scope: SalesScope, customer: Customer, order: _Order, named: str
    ) -> _OrderLine | None:
        """The one line of ``order`` a reference names: its number, its PRV
        code or the customer's code for it, else None."""
        number = line_number_of(named)
        if number is not None:
            return next((line for line in order.lines if line.line_no == number), None)
        code = named.strip().upper()
        matches = [line for line in order.lines if code in {c.upper() for c in line.codes}]
        if not matches:
            entry = (await self.catalog.convert_entry(scope, customer.code, named.strip())).data
            if entry is not None:
                matches = [line for line in order.lines if line.prv_code == entry.prv_code]
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _quantity(
        text: str, span: str | None, notation: _Notations, refused: Counter[str]
    ) -> QuantityRead | None:
        """The quantity in metres and the customer's words for it; the words
        alone, flagged (``quantity_unread``), when code does not read them as
        metres (`quantity_at`); None when the span is not there."""
        located = locate(text, span, bounded=True)
        read = quantity_at(text, located, notation.mail, notation.record) if located else None
        if span is not None and read is None:
            refused["quantity"] += 1
        elif read is not None and read.value is None:
            refused["quantity_unread"] += 1
            if read.contradicts_record:
                refused["quantity_contradicts_record"] += 1
        return read


@dataclass(frozen=True, slots=True)
class _Notations:
    """The mail's own notation and its sender's customer's record."""

    mail: Notation
    record: Notation


def _quotes(
    text: str, spans: Sequence[str], most: int, refused: Counter[str], name: str
) -> tuple[Located, ...]:
    """The customer's sentences code locates once, naming no destination,
    each once, at most ``most``."""
    kept: list[Located] = []
    for span in spans:
        located = locate(text, span)
        if located is None or carries_contact(located.text):
            refused[name] += 1
            continue
        if any((q.start, q.end) == (located.start, located.end) for q in kept):
            continue
        kept.append(located)
    return tuple(kept[:most])


# ------------------------------------------------------------- the text --


# What each template may name. A tenant writes its own version of this copy
# (ticket 36) and it is filled with `str.format`, so a placeholder is a bare
# name from these and nothing else: a format spec such as ``{customer:>999999999}``
# would build a gigabyte on every read of the inbox, and ``{customer.__class__}``
# reaches past the value.
_TEMPLATE_NAMES: Final = frozenset(
    {"customer", "po", "message_id", "lines", "lot", "quotes", "quantity"}
)
_LINE_NAMES: Final = frozenset({"line_no", "item", "quantity", "date"})
_QUOTE_NAMES: Final = frozenset({"text"})
# The request to PC for an order's delivery dates (ticket 07).
_PC_NAMES: Final = frozenset({"customer", "po", "lines"})
_PC_LINE_NAMES: Final = frozenset(
    {"line_no", "item", "customer_item", "quantity", "uom", "requested_date"}
)


def _named(names: frozenset[str]) -> dict[str, Any]:
    """The placeholders a field may name, in its JSON Schema, so the rules
    editor lists them from the set the validator holds, not from a copy
    (ticket 40)."""
    return {"x-placeholders": [f"{{{name}}}" for name in sorted(names)]}


def _plain_placeholders(text: str, names: frozenset[str]) -> str:
    """``text`` when every placeholder in it is ``{name}`` for one of ``names``."""
    for _, name, spec, conversion in Formatter().parse(text):
        if name is None:
            continue
        if name not in names or spec or conversion is not None:
            raise ValueError(f"a placeholder is one of {sorted(names)}, written {{name}}")
    return text


class HandoffTemplate(BaseModel):
    """One kind's words. Placeholders are filled by code from the hand-off:
    ``{customer}``, ``{po}``, ``{message_id}``, ``{lines}``, ``{lot}``,
    ``{quotes}``, ``{quantity}``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    to: HandoffTeam
    subject: str = Field(min_length=1, max_length=300, json_schema_extra=_named(_TEMPLATE_NAMES))
    body: str = Field(min_length=1, max_length=4000, json_schema_extra=_named(_TEMPLATE_NAMES))

    @field_validator("subject", "body")
    @classmethod
    def _placeholders(cls, value: str) -> str:
        return _plain_placeholders(value, _TEMPLATE_NAMES)


class PcRequestTemplate(BaseModel):
    """The words of the request Sales sends PC for an order's delivery dates
    (ticket 07), from the order case: ``{customer}``, ``{po}``, ``{lines}``
    in the subject and body, one ``line`` per line asked with ``{line_no}``,
    ``{item}`` (the PRV code), ``{customer_item}``, ``{quantity}``,
    ``{uom}`` and ``{requested_date}``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject: str = Field(min_length=1, max_length=300, json_schema_extra=_named(_PC_NAMES))
    line: str = Field(min_length=1, max_length=300, json_schema_extra=_named(_PC_LINE_NAMES))
    body: str = Field(min_length=1, max_length=4000, json_schema_extra=_named(_PC_NAMES))

    @field_validator("subject", "body")
    @classmethod
    def _placeholders(cls, value: str) -> str:
        return _plain_placeholders(value, _PC_NAMES)

    @field_validator("line")
    @classmethod
    def _line_placeholders(cls, value: str) -> str:
        return _plain_placeholders(value, _PC_LINE_NAMES)


class HandoffCopy(BaseModel):
    """`configs/copy/sales_handoffs@<version>.yaml`: the hand-off's words."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field(pattern=r"^1\.0$")
    copy_id: str = Field(pattern=r"^sales_handoffs$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    # How a missing value, a line, a quote and a quantity are written.
    unknown: str = Field(min_length=1, max_length=60)
    line: str = Field(min_length=1, max_length=300, json_schema_extra=_named(_LINE_NAMES))
    quote: str = Field(min_length=1, max_length=60, json_schema_extra=_named(_QUOTE_NAMES))
    templates: Mapping[HandoffKind, HandoffTemplate]
    # The request to PC for an order's delivery dates (ticket 07, 1.1.0).
    pc_request: PcRequestTemplate

    @field_validator("line")
    @classmethod
    def _line_placeholders(cls, value: str) -> str:
        return _plain_placeholders(value, _LINE_NAMES)

    @field_validator("quote")
    @classmethod
    def _quote_placeholders(cls, value: str) -> str:
        return _plain_placeholders(value, _QUOTE_NAMES)

    @property
    def ref(self) -> str:
        return f"{self.copy_id}@{self.version}"


class HandoffCopyPort(Protocol):
    """The hand-off copy a scope's tenant writes with (ticket 36)."""

    async def handoff_copy(self, scope: SalesScope) -> HandoffCopy: ...


@dataclass(frozen=True, slots=True)
class RenderedHandoff:
    to: HandoffTeam
    subject: str
    body: str
    template_ref: str


def render(
    handoff: Handoff, copy: HandoffCopy, *, customer_code: str, message_id: str
) -> RenderedHandoff:
    """The hand-off's subject and body: the template's words around what code
    kept. A value code did not keep is written as the copy's ``unknown``, for
    Sales to fill; nothing is written that the mail did not say. A skill's
    kind (ticket 42 family 5) is written with the words of the fields it
    asks for and goes to the team the skill names."""
    template = copy.templates[handoff.kind]
    unknown = copy.unknown

    def unread(words: Located | None) -> str:
        """A value code did not read: ``unknown``, and the customer's own
        words for it beside, quoted, for Sales to fill from."""
        if words is None:
            return unknown
        return f"{unknown} {copy.quote.format(text=words.text).strip()}"

    lines = "\n".join(
        copy.line.format(
            line_no=line.line_no,
            item=line.item or unknown,
            quantity=_number(line.new_quantity) if line.new_quantity else unread(line.quantity),
            date=line.new_date.strftime("%d/%m/%Y") if line.new_date else unread(line.date_span),
        )
        for line in handoff.lines
    )
    sample = handoff.sample_quantity
    quotes = "\n".join(copy.quote.format(text=quote.text) for quote in handoff.quotes)
    values = {
        "customer": customer_code,
        "po": handoff.po_no or unknown,
        "message_id": message_id,
        "lines": lines or unknown,
        "lot": handoff.lot.text if handoff.lot else unknown,
        "quotes": quotes or unknown,
        "quantity": _number(sample) if sample else unread(handoff.quantity),
    }
    return RenderedHandoff(
        to=template.to if handoff.to is None else handoff.to,
        subject=template.subject.format(**values),
        body=template.body.format(**values),
        template_ref=f"{copy.ref}#{handoff.kind}",
    )


@dataclass(frozen=True, slots=True)
class PcAskedLine:
    """One line of the request to PC, as the order case enters it."""

    line_no: int
    prv_code: str | None
    customer_item_code: str
    quantity: Decimal
    uom: str
    # None: the PO prints it blank (date to follow).
    requested_date: date | None


@dataclass(frozen=True, slots=True)
class RenderedPcRequest:
    subject: str
    body: str
    template_ref: str


def render_pc_request(
    copy: HandoffCopy, *, customer_code: str, po_no: str, lines: Sequence[PcAskedLine]
) -> RenderedPcRequest:
    """The request to PC: the template's words around the case's own values,
    one line per line asked. A value the case does not have (no PRV code yet,
    a date to follow) is written as the copy's ``unknown``."""
    template, unknown = copy.pc_request, copy.unknown
    listed = "\n".join(
        template.line.format(
            line_no=line.line_no,
            item=line.prv_code or unknown,
            customer_item=line.customer_item_code,
            quantity=_number(line.quantity),
            uom=line.uom,
            requested_date=(
                line.requested_date.strftime("%d/%m/%Y") if line.requested_date else unknown
            ),
        )
        for line in lines
    )
    values = {"customer": customer_code, "po": po_no, "lines": listed}
    return RenderedPcRequest(
        subject=template.subject.format(**values),
        body=template.body.format(**values),
        template_ref=f"{copy.ref}#pc_request",
    )


def _number(value: Decimal) -> str:
    """A quantity with Vietnamese grouping: 2.000, 12.5 as 12,5."""
    whole, _, fraction = f"{value.normalize():f}".partition(".")
    grouped = f"{int(whole):,}".replace(",", ".")
    return f"{grouped},{fraction}" if fraction else grouped
