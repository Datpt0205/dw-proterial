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
- each quantity and date parsed from its span; each quote that names no
  destination (`carries_contact`).

No usable answer is an ``unavailable`` hand-off, and an answer code keeps
nothing of is ``nothing_located``: either is an empty form for Sales, the
message routed as before. A budget or quota refusal propagates: the run stops.

`render` writes the hand-off's subject and body from the versioned template
(`HandoffCopy`, `configs/copy/sales_handoffs@<version>.yaml`): the template's
words, the values code kept, and the customer's sentences in quotation marks.
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from dw_agent_runtime.contracts import RunContext
from dw_sales.application.model_reading import (
    InterpretationPort,
    ModelUnavailableError,
    PromptRef,
    cut_to_tokens,
)
from dw_sales.application.order_ports import OrderCaseLookupPort
from dw_sales.application.ports import SalesCatalogPort, SalesScope
from dw_sales.domain.catalog import Customer
from dw_sales.domain.handoffs import (
    MAX_ITEMS,
    MAX_QUOTES,
    MODEL_SCHEMAS,
    Handoff,
    HandoffKind,
    HandoffLine,
    Located,
    ModelComplaint,
    ModelDeliveryChange,
    ModelSampleRequest,
    carries_contact,
    line_number_of,
    locate,
    locate_identifier,
    quantity_of,
)
from dw_sales.domain.mail_parts import MessagePart
from dw_sales.domain.rfq_reading import parse_date, parse_document_no

# The prompt the spans are copied with. Its file is
# `configs/prompts/sales/request_handoff@1.0.0.yaml`; a test holds the two
# together, and a new wording is a new version here and a new file there.
REQUEST_HANDOFF: Final = PromptRef("sales.request_handoff", "1.0.0")
# A handful of short spans, or three sentences: about 200 tokens measured.
_OUTPUT_TOKENS: Final = 800
# What the prompt itself costs, held above its rendered size by a test.
PROMPT_TOKENS: Final = 1800


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
    ) -> Handoff:
        stamp = {
            "kind": kind,
            "prompt": str(REQUEST_HANDOFF),
            "model_profile": self.model.model_profile,
            "route": self.model.route,
            "rules": rules_version,
        }
        inputs = {
            "kind": kind,
            "subject": part.subject,
            "body": cut_to_tokens(part.body, self.model.max_input_tokens - PROMPT_TOKENS),
        }
        try:
            answer = await self.model.interpret(
                REQUEST_HANDOFF,
                inputs,
                MODEL_SCHEMAS[kind],
                run=run,
                max_output_tokens=_OUTPUT_TOKENS,
            )
        except ModelUnavailableError:
            return Handoff.model_validate({**stamp, "outcome": "unavailable"})
        refused: Counter[str] = Counter()
        kept = await self._kept(scope, part.text, customer, answer, received_on, refused)
        located = any(
            kept.get(name) for name in ("po_no", "lines", "lot", "quotes", "sample_quantity")
        )
        return Handoff.model_validate(
            {
                **stamp,
                **kept,
                "outcome": "read" if located else "nothing_located",
                "refused": dict(refused),
            }
        )

    async def _kept(
        self,
        scope: SalesScope,
        text: str,
        customer: Customer,
        answer: BaseModel,
        received_on: date,
        refused: Counter[str],
    ) -> dict[str, Any]:
        if isinstance(answer, ModelSampleRequest):
            quantity = self._quantity(text, answer.quantity_span, refused)
            return {
                "quotes": _quotes(text, answer.item_spans, MAX_ITEMS, refused, "item"),
                "sample_quantity": quantity[0] if quantity else None,
                "quantity": quantity[1] if quantity else None,
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
                line = await self._line(scope, text, customer, order, asked, received_on)
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
        for it; None when it is neither, or when two cases hold it."""
        erp = (await self.catalog.orders_for_po(scope, customer.code, po_no)).data
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
    ) -> HandoffLine | None:
        reference = locate(text, asked.line_or_item_span, bounded=True)
        if reference is None:
            return None
        found = await self._order_line(scope, customer, order, reference.text)
        if found is None:
            return None
        throwaway: Counter[str] = Counter()
        quantity = self._quantity(text, asked.new_quantity_span, throwaway)
        located_date = locate(text, asked.new_date_span, bounded=True)
        day = parse_date(located_date.text, received_on) if located_date else None
        if quantity is None and day is None:
            # A line the customer changes nothing on is no line of the hand-off.
            return None
        return HandoffLine(
            reference=reference,
            line_no=found.line_no,
            item=found.prv_code,
            new_quantity=quantity[0] if quantity else None,
            quantity=quantity[1] if quantity else None,
            new_date=day,
            date_span=located_date if day else None,
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
        text: str, span: str | None, refused: Counter[str]
    ) -> tuple[Decimal, Located] | None:
        located = locate(text, span, bounded=True)
        value = quantity_of(located.text) if located else None
        if span is not None and value is None:
            refused["quantity"] += 1
        if located is None or value is None:
            return None
        return value, located


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


# Who a hand-off is for: production control or quality assurance.
HandoffTeam = Literal["pc", "qa"]


class HandoffTemplate(BaseModel):
    """One kind's words. Placeholders are filled by code from the hand-off:
    ``{customer}``, ``{po}``, ``{message_id}``, ``{lines}``, ``{lot}``,
    ``{quotes}``, ``{quantity}``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    to: HandoffTeam
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=4000)


class HandoffCopy(BaseModel):
    """`configs/copy/sales_handoffs@<version>.yaml`: the hand-off's words."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field(pattern=r"^1\.0$")
    copy_id: str = Field(pattern=r"^sales_handoffs$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    # How a missing value, a line, a quote and a quantity are written.
    unknown: str = Field(min_length=1, max_length=60)
    line: str = Field(min_length=1, max_length=300)
    quote: str = Field(min_length=1, max_length=60)
    templates: Mapping[HandoffKind, HandoffTemplate]

    @property
    def ref(self) -> str:
        return f"{self.copy_id}@{self.version}"


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
    Sales to fill; nothing is written that the mail did not say."""
    template = copy.templates[handoff.kind]
    unknown = copy.unknown
    lines = "\n".join(
        copy.line.format(
            line_no=line.line_no,
            item=line.item or unknown,
            quantity=_number(line.new_quantity) if line.new_quantity else unknown,
            date=line.new_date.strftime("%d/%m/%Y") if line.new_date else unknown,
        )
        for line in handoff.lines
    )
    quotes = "\n".join(copy.quote.format(text=quote.text) for quote in handoff.quotes)
    values = {
        "customer": customer_code,
        "po": handoff.po_no or unknown,
        "message_id": message_id,
        "lines": lines or unknown,
        "lot": handoff.lot.text if handoff.lot else unknown,
        "quotes": quotes or unknown,
        "quantity": _number(handoff.sample_quantity) if handoff.sample_quantity else unknown,
    }
    return RenderedHandoff(
        to=template.to,
        subject=template.subject.format(**values),
        body=template.body.format(**values),
        template_ref=f"{copy.ref}#{handoff.kind}",
    )


def _number(value: Decimal) -> str:
    """A quantity with Vietnamese grouping: 2.000, 12.5 as 12,5."""
    whole, _, fraction = f"{value.normalize():f}".partition(".")
    grouped = f"{int(whole):,}".replace(",", ".")
    return f"{grouped},{fraction}" if fraction else grouped
