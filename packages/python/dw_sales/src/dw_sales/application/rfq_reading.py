"""A model reads a request for quotation the fixed-label reader cannot.

Ticket 29, dw_sales ADR 0005 (the rules: `domain.rfq_reading`). Asked by the
quotation flow only when no attachment reads as the seller's request form,
the tenant's rules turn it on, the sender's domain is a customer's, and a DW1
run is opening the case. `RfqModelReader.read`:

1. builds the parts the model is shown: the message's newest part (subject
   first, history cut by structure) and the text of each attachment a reader
   opens (`AttachmentTextPort`), hidden content left out;
2. splits them into calls that fit the route (`max_input_tokens`, less the
   prompt): a request that needs more than `MAX_CALLS` is not read at all,
   rather than read in part, and no call is ever refused as too long;
3. asks under prompt `sales.rfq_extraction` and verifies every answer
   (`verify_rfq`);
4. reads each item's description as ticket 28 does, for candidates Sales and
   Design weigh, unless the convert list already names the item;
5. returns the request with every value it read flagged `model_read`, or why
   it was not read. A budget or quota refusal is not a reason: it stops the
   run.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Final, Literal, Protocol

from dw_agent_runtime.contracts import RunContext
from dw_sales.application.model_reading import (
    DescriptionReader,
    InterpretationPort,
    ModelUnavailableError,
    PromptRef,
    estimated_tokens,
)
from dw_sales.application.order_ports import OrderRulesPort
from dw_sales.application.ports import SalesCatalogPort, SalesScope
from dw_sales.domain.catalog import Customer, Item
from dw_sales.domain.descriptions import candidates, read_description
from dw_sales.domain.mail_parts import newest_part
from dw_sales.domain.messages import Attachment, AttachmentContent, InboundMessage
from dw_sales.domain.order_checks import IntakeCaps, OrderRules, received_date
from dw_sales.domain.orders import FlaggedValue, RegionFlag
from dw_sales.domain.quotes import (
    MessageText,
    RequestedItem,
    RequestReading,
    RfqDocument,
    Sourced,
)
from dw_sales.domain.rfq_reading import (
    MAX_LINES_PER_CALL,
    ModelRfqReading,
    Read,
    TextPart,
    VerifiedItem,
    VerifiedRfq,
    normalised,
    text_digest,
    verify_rfq,
)

# The prompt requests are read with. Its file is
# `configs/prompts/sales/rfq_extraction@1.0.0.yaml`; a test holds the two
# together, and holds the prompt's rendered size under `PROMPT_TOKENS`.
RFQ_EXTRACTION: Final = PromptRef("sales.rfq_extraction", "1.0.0")
PROMPT_TOKENS: Final = 1800
# The most calls one request is read in. Beyond it a person reads the
# request: reading part of one would miss lines nobody knows are missing.
MAX_CALLS: Final = 3
# Room for up to 15 items (about 120 tokens each) and the request's own.
_OUTPUT_TOKENS: Final = 2000

NotRead = Literal["too_long", "unavailable", "not_understood", "currency_missing", "several_files"]


class AttachmentTextPort(Protocol):
    """The text a model may read of one attachment: a PDF's pages, a
    workbook's visible sheets; nothing for a file no reader opens."""

    async def text_parts(
        self, content: AttachmentContent, caps: IntakeCaps
    ) -> Sequence[TextPart]: ...


@dataclass(frozen=True, slots=True)
class RequestRead:
    """A request a model read and code accepted."""

    document: RfqDocument
    attachment: Attachment | None
    body: MessageText | None
    reading: RequestReading


@dataclass(frozen=True, slots=True)
class _Described:
    line_no: int
    description: str


@dataclass(frozen=True)
class RfqModelReader:
    model: InterpretationPort
    texts: AttachmentTextPort
    catalog: SalesCatalogPort
    descriptions: DescriptionReader

    async def read(
        self,
        scope: SalesScope,
        message: InboundMessage,
        contents: Sequence[AttachmentContent],
        customer: Customer,
        rules: OrderRules,
        *,
        run: RunContext,
    ) -> RequestRead | NotRead:
        body_text = normalised(newest_part(message).text)
        parts = [TextPart("body", body_text, None, text_digest(body_text))]
        for content in contents:
            parts.extend(await self.texts.text_parts(content, rules.intake))
        budget = self.model.max_input_tokens - PROMPT_TOKENS
        pieces = [piece for part in parts for piece in part.pieces(budget, estimated_tokens)]
        if any(estimated_tokens(piece.text) > budget for piece in pieces):
            return "too_long"
        calls = _packed(pieces, budget)
        if len(calls) > MAX_CALLS:
            return "too_long"
        verdict = VerifiedRfq()
        received_on = received_date(message.received_at)
        for call in calls:
            inputs = {
                # Code-built JSON inside the untrusted block: a part cannot
                # close its string and pose as another part.
                "parts": json.dumps(
                    [{"part": part.part_id, "text": part.text} for part in call],
                    ensure_ascii=False,
                ),
            }
            try:
                answer = await self.model.interpret(
                    RFQ_EXTRACTION,
                    inputs,
                    ModelRfqReading,
                    run=run,
                    max_output_tokens=_OUTPUT_TOKENS,
                )
            except ModelUnavailableError:
                return "unavailable"
            verify_rfq(call, answer, received_on, into=verdict)
        return await self._request(scope, message, contents, customer, rules, verdict, run, calls)

    async def _request(
        self,
        scope: SalesScope,
        message: InboundMessage,
        contents: Sequence[AttachmentContent],
        customer: Customer,
        rules: OrderRules,
        verdict: VerifiedRfq,
        run: RunContext,
        calls: Sequence[Sequence[TextPart]],
    ) -> RequestRead | NotRead:
        if not verdict.items:
            return "not_understood"
        if verdict.currency is None:
            # No default and no correction path: pricing in a currency nobody
            # stated is a guess, so a person reads the request.
            return "currency_missing"
        reads: list[Read[Any]] = [verdict.currency]
        reads += [r for r in (verdict.rfq_no, verdict.quote_due) if r is not None]
        for item in verdict.items:
            reads += [r for r in _item_reads(item) if r is not None]
        files = {r.attachment_id for r in reads} - {None}
        if len(files) > 1:
            return "several_files"
        attachment = next(
            (c.attachment for c in contents if c.attachment.attachment_id in files), None
        )
        items = (await self.catalog.items(scope)).data
        known = await self._candidates(scope, customer, verdict.items, items, run)
        requested = tuple(
            _requested(number, item, known.get(number))
            for number, item in enumerate(verdict.items, start=1)
        )
        body_read = any(r.attachment_id is None for r in reads)
        body_text = normalised(newest_part(message).text)
        header = {"rfq_no": verdict.rfq_no, "quote_due": verdict.quote_due}
        document = RfqDocument(
            parser_version=str(RFQ_EXTRACTION),
            rfq_no=_sourced(verdict.rfq_no),
            rfq_date=None,
            quote_due=_sourced(verdict.quote_due),
            currency=Sourced(value=verdict.currency.value, source=verdict.currency.anchor),
            items=requested,
            flags=tuple(
                FlaggedValue(field=name, flag=RegionFlag.MODEL_READ)
                for name, value in (("currency", verdict.currency), *header.items())
                if value is not None
            ),
        )
        return RequestRead(
            document=document,
            attachment=attachment,
            body=MessageText(text=body_text, sha256=text_digest(body_text)) if body_read else None,
            reading=RequestReading(
                prompt=str(RFQ_EXTRACTION),
                model_profile=self.model.model_profile,
                route=self.model.route,
                rules=rules.version,
                calls=len(calls),
                refused=dict(verdict.refused),
            ),
        )

    async def _candidates(
        self,
        scope: SalesScope,
        customer: Customer,
        verified: Sequence[VerifiedItem],
        items: Sequence[Item],
        run: RunContext,
    ) -> dict[int, tuple[tuple[str, ...], Any]]:
        """Each item's candidates by its description, and the model reading
        they came from: none where the convert list names the customer's code
        (the item is known, as today), by DW1's own vocabulary where it reads
        the words, else by ticket 28's model reading."""
        found: dict[int, tuple[tuple[str, ...], Any]] = {}
        unread: list[_Described] = []
        for number, item in enumerate(verified, start=1):
            code = item.customer_item_code
            if code is not None:
                entry = (await self.catalog.convert_entry(scope, customer.code, code.value)).data
                if entry is not None:
                    continue
            stated = read_description(item.description.value)
            if stated is not None:
                found[number] = (tuple(i.prv_code for i in candidates(stated, items)), None)
            else:
                unread.append(_Described(number, item.description.value))
        if unread:
            mapped = await self.descriptions.read(unread, items, run=run)
            for number, line in mapped.items():
                found[number] = (line.mapping.candidates, line.reading)
        return found


def _packed(pieces: Sequence[TextPart], budget: int) -> list[list[TextPart]]:
    """The pieces in calls, in order, each call within the budget and
    `MAX_LINES_PER_CALL` lines."""
    calls: list[list[TextPart]] = []
    tokens = lines = 0
    for piece in pieces:
        cost = estimated_tokens(piece.text) + 20  # the part's id and the JSON around it
        if calls and tokens + cost <= budget and lines + piece.lines <= MAX_LINES_PER_CALL:
            calls[-1].append(piece)
            tokens, lines = tokens + cost, lines + piece.lines
        else:
            calls.append([piece])
            tokens, lines = cost, piece.lines
    return calls


def _item_reads(item: VerifiedItem) -> tuple[Read[Any] | None, ...]:
    return (
        item.description,
        item.customer_item_code,
        item.quantity,
        item.uom,
        item.needed_by,
        item.stated_target_price,
    )


def _sourced[T](read: Read[T] | None) -> Sourced[T] | None:
    return None if read is None else Sourced(value=read.value, source=read.anchor)


def _requested(
    line_no: int, item: VerifiedItem, known: tuple[tuple[str, ...], Any] | None
) -> RequestedItem:
    """One verified item as the request's line: every value the model's words
    gave flagged `model_read`; a value not read anchored at the line, so Sales
    is shown where it is missing (`rfq_incomplete`)."""
    line = item.line.anchor
    read_fields = {
        "description": item.description,
        "customer_item_code": item.customer_item_code,
        "quantity": item.quantity,
        "uom": item.uom,
        "needed_by": item.needed_by,
    }
    quantity, needed_by = item.quantity, item.needed_by
    found, reading = known if known is not None else ((), None)
    return RequestedItem(
        line_no=line_no,
        customer_item_code=_sourced(item.customer_item_code),
        description=Sourced(value=item.description.value, source=item.description.anchor),
        quantity=Sourced(
            value=quantity.value if quantity else None,
            source=quantity.anchor if quantity else line,
        ),
        # The seller quotes in metres only; with no unit read, the quantity
        # is not read either, and the line asks for it.
        uom=Sourced(value="m", source=item.uom.anchor if item.uom else line),
        needed_by=Sourced[date | None](
            value=needed_by.value if needed_by else None,
            source=needed_by.anchor if needed_by else line,
        ),
        flags=tuple(
            FlaggedValue(field=name, flag=RegionFlag.MODEL_READ)
            for name, value in read_fields.items()
            if value is not None
        ),
        stated_target_price=_sourced(item.stated_target_price),
        candidates=found,
        description_reading=reading,
    )


@dataclass(frozen=True)
class ModelRequests:
    """The quotation flow's model step: the reader, and the tenant's rules
    that say whether it is on (`model_assist.rfq_extraction`)."""

    reader: RfqModelReader
    rules: OrderRulesPort
