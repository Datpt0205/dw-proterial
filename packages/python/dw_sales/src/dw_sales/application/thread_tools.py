"""DW1's read-only tools for reading a thread message (dw_sales ADR 0012
decision 1, tickets 30 and 31).

Six tools, each a versioned spec in ``configs/tools`` (side effect ``none``,
approval ``never``, idempotent), offered together by DW1's toolset
(``configs/toolsets/sales-dw1@<version>.yaml``, which ``configs/workers/sales.yaml``
pins): the thread's earlier messages, a snapshot of the thread's cases, a case
by its number, the conversion list, an item's lead time, and PC's answer on an
order. No tool writes, sends or approves; each runs through the platform's
`ToolExecutor`, which authorizes it (``sales.inbox.process``), validates its
input and output, and audits the call.

**Bound from the run, never an argument.** What a tool reads is the turn's
binding (`ThreadBinding`): the tenant and workspace, the one customer and the
cases code linked the message to (its thread headers, `threads.ThreadLinks`),
and the thread's earlier messages on those cases. Code sets it around one turn
(`bound_to`, `thread_agent.ThreadAgent`); a tool's input names only what the
model read in the message (a number, the customer's item code, a PRV code). No
input schema has a customer, tenant or workspace in it (a test walks the specs).
A number of another customer's resolves to nothing: the lookup is made by the
bound customer here, in the tool, whatever the message or the model asks.

**Fail closed.** A call with no binding (outside a turn), or from a run of
another tenant or workspace than the binding's, is refused
(`PermissionDeniedError`): the turn is code's, and a tool that cannot tell whose
data it may read reads none.

**What a tool returns** is code's view of the record: numbers, statuses,
quantities and dates; never a price, an amount or a person. The thread's
messages are the customer's words, newest part only, and they are data to the
model as the message itself is: what a message's reading stands on is located
by code in that message alone (`reply_intent.verified_intents`), so a sentence
a tool returned can never be a quote the reading stands on.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Annotated, Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from dw_agent_runtime.contracts import RunContext, ToolDefinition
from dw_agent_runtime.tools import RegisteredTool
from dw_kernel.errors import PermissionDeniedError
from dw_platform.domain.mail_parts import newest_part
from dw_platform.domain.messages import InboundMessage
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.order_ports import OrderCaseLookupPort, OrderRulesPort
from dw_sales.application.ports import SalesCatalogPort, SalesScope
from dw_sales.application.threads import ThreadedCase, ThreadMembersPort
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.orders import OrderCase
from dw_sales.domain.quotes import QuoteCase

_IN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
_OUT = ConfigDict(frozen=True, extra="forbid")

# Every tool's spec version; the toolset pins these (a test holds the two).
TOOL_VERSION: Final = "1.0.0"
THREAD_MESSAGES: Final = "sales.thread_messages"
CASE_SNAPSHOT: Final = "sales.case_snapshot"
CASE_BY_NUMBER: Final = "sales.case_by_number"
CONVERSION_LOOKUP: Final = "sales.conversion_lookup"
LEAD_TIME: Final = "sales.lead_time"
PC_STATUS: Final = "sales.pc_status"

# The earlier messages a turn is shown: the latest few, each cut. A thread is
# read for what the message answers, not end to end.
EARLIER_MESSAGES: Final = 5
MESSAGE_CHARS: Final = 1200
# The lines a case view shows, the first ones: a turn's calls share the route's
# 6,000 tokens, and a message naming line 80 of a long PO is a person's.
CASE_LINES: Final = 30

_Number = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[^\x00-\x1f\x7f]+$")]
_Code = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[^\x00-\x1f\x7f]+$")]


# ------------------------------------------------------------ the views --


class ThreadMessageView(BaseModel):
    """An earlier message of the thread: the newest part the customer wrote."""

    model_config = _OUT

    author: Literal["customer", "sales"]
    received_on: date
    subject: str
    text: str


class PcDeliveryView(BaseModel):
    model_config = _OUT

    quantity: Decimal
    first_date: date
    date: date


class CaseLineView(BaseModel):
    """One line as it is entered: the customer's code, the PRV code it maps
    to, the quantity and unit, the date asked, the dates confirmed and PC's."""

    model_config = _OUT

    line_no: int
    customer_item_code: str | None
    prv_code: str | None
    quantity: Decimal | None
    unit: str | None
    requested_date: date | None
    confirmed_dates: tuple[date, ...] = ()
    pc_deliveries: tuple[PcDeliveryView, ...] = ()


class CaseView(BaseModel):
    """A case as a tool shows it: its kind, the numbers it is known by (the
    PO number; the RFQ and YCBG numbers), its status, its lines, and since
    when it waits on PC's dates (an order)."""

    model_config = _OUT

    kind: Literal["order", "quote"]
    numbers: tuple[str, ...]
    status: str
    lines: tuple[CaseLineView, ...]
    waiting_on_pc_since: date | None = None


class NoInput(BaseModel):
    """A tool that reads only what the turn is bound to."""

    model_config = _IN


class NumberInput(BaseModel):
    model_config = _IN

    # A PO, RFQ or YCBG number exactly as the message writes it.
    number: _Number


class ConversionInput(BaseModel):
    model_config = _IN

    # The customer's own code or words for an item, as the message writes it.
    customer_item_code: _Code


class LeadTimeInput(BaseModel):
    model_config = _IN

    # The seller's PRV item code.
    prv_code: _Number


class ThreadMessagesOutput(BaseModel):
    model_config = _OUT

    messages: tuple[ThreadMessageView, ...]


class CaseSnapshotOutput(BaseModel):
    model_config = _OUT

    cases: tuple[CaseView, ...]


class CaseByNumberOutput(BaseModel):
    model_config = _OUT

    found: bool
    case: CaseView | None = None


class ConversionOutput(BaseModel):
    model_config = _OUT

    found: bool
    customer_item_code: str
    prv_code: str | None = None
    item_name: str | None = None


class LeadTimeOutput(BaseModel):
    model_config = _OUT

    found: bool
    prv_code: str
    standard_lead_time_days: int | None = None
    # How the order rules count it: from the day the PO was received or the
    # date it prints, in calendar days.
    counted_from: Literal["received_date", "po_date"]
    day_basis: Literal["calendar"]


class PcStatusOutput(BaseModel):
    model_config = _OUT

    found: bool
    number: str
    waiting_on_pc_since: date | None = None
    lines: tuple[CaseLineView, ...] = ()


def order_view(case: OrderCase) -> CaseView:
    """An order as a tool shows it: no price, no amount, no person."""
    lines = []
    for line in case.lines[:CASE_LINES]:
        entered = line.effective
        answer = line.pc_answer
        lines.append(
            CaseLineView(
                line_no=line.line_no,
                customer_item_code=str(entered.customer_item_code),
                prv_code=line.mapping.prv_code,
                quantity=entered.quantity,
                unit=entered.uom,
                requested_date=entered.requested_date,
                confirmed_dates=line.confirmed_delivery_dates,
                pc_deliveries=()
                if answer is None
                else tuple(
                    PcDeliveryView(quantity=d.quantity, date=d.date, first_date=d.first_date)
                    for d in answer.deliveries
                ),
            )
        )
    request = case.pc_request
    return CaseView(
        kind="order",
        numbers=(str(case.header.po_no),),
        status=case.status.value,
        lines=tuple(lines),
        waiting_on_pc_since=None if request is None else request.at.date(),
    )


def quote_view(case: QuoteCase) -> CaseView:
    """A request for quotation as a tool shows it: no target price."""
    request = case.request
    numbers = (request.rfq_no, case.ycbg.ycbg_no if case.ycbg is not None else None)
    return CaseView(
        kind="quote",
        numbers=tuple(n for n in numbers if n),
        status=case.status.value,
        lines=tuple(
            CaseLineView(
                line_no=item.line_no,
                customer_item_code=(
                    None if item.customer_item_code is None else str(item.customer_item_code.value)
                ),
                prv_code=None,
                quantity=item.quantity.value,
                unit=str(item.uom.value),
                requested_date=item.needed_by.value,
            )
            for item in request.document.items[:CASE_LINES]
        ),
    )


# ------------------------------------------------------------ the binding --


@dataclass(frozen=True, slots=True)
class ThreadBinding:
    """What one turn's tools may read, set by code (module docstring)."""

    scope: SalesScope
    customer_code: str
    # The message being read, for the log; never read by a tool.
    message_id: str
    earlier: tuple[ThreadMessageView, ...]
    cases: tuple[CaseView, ...]


_BOUND: ContextVar[ThreadBinding | None] = ContextVar("dw_sales_thread_binding", default=None)


@contextmanager
def bound_to(binding: ThreadBinding) -> Iterator[ThreadBinding]:
    """The tools read ``binding`` inside the block, and nothing outside it."""
    token = _BOUND.set(binding)
    try:
        yield binding
    finally:
        _BOUND.reset(token)


def _binding(run: RunContext) -> ThreadBinding:
    binding = _BOUND.get()
    if binding is None:
        raise PermissionDeniedError(
            "a thread tool reads only inside a turn bound to a thread",
            details={"rule": "thread_tool_unbound"},
        )
    scope = binding.scope
    if (scope.tenant_id.value, scope.workspace_id.value) != (run.tenant_id, run.workspace_id):
        raise PermissionDeniedError(
            "a thread tool reads only the run's own tenant and workspace",
            details={"rule": "thread_tool_scope"},
        )
    return binding


def _same(a: str, b: str) -> bool:
    fold = unicodedata.normalize("NFKC", a).strip().casefold()
    return fold == unicodedata.normalize("NFKC", b).strip().casefold()


# ------------------------------------------------------------ the tools --


@dataclass(frozen=True)
class ThreadTools:
    """The six tools' handlers, over DW1's own read ports."""

    orders: OrderCaseLookupPort
    catalog: SalesCatalogPort
    rules: OrderRulesPort

    async def thread_messages(self, payload: BaseModel, run: RunContext) -> ThreadMessagesOutput:
        return ThreadMessagesOutput(messages=_binding(run).earlier)

    async def case_snapshot(self, payload: BaseModel, run: RunContext) -> CaseSnapshotOutput:
        return CaseSnapshotOutput(cases=_binding(run).cases)

    async def case_by_number(self, payload: BaseModel, run: RunContext) -> CaseByNumberOutput:
        assert isinstance(payload, NumberInput)
        case = await self._case(_binding(run), payload.number)
        return CaseByNumberOutput(found=case is not None, case=case)

    async def pc_status(self, payload: BaseModel, run: RunContext) -> PcStatusOutput:
        assert isinstance(payload, NumberInput)
        case = await self._case(_binding(run), payload.number)
        if case is None or case.kind != "order":
            return PcStatusOutput(found=False, number=payload.number)
        return PcStatusOutput(
            found=True,
            number=payload.number,
            waiting_on_pc_since=case.waiting_on_pc_since,
            lines=case.lines,
        )

    async def conversion_lookup(self, payload: BaseModel, run: RunContext) -> ConversionOutput:
        assert isinstance(payload, ConversionInput)
        binding = _binding(run)
        code = payload.customer_item_code
        entry = (await self.catalog.convert_entry(binding.scope, binding.customer_code, code)).data
        if entry is None or entry.customer_code != binding.customer_code:
            return ConversionOutput(found=False, customer_item_code=code)
        item = (await self.catalog.item_by_prv_code(binding.scope, entry.prv_code)).data
        return ConversionOutput(
            found=True,
            customer_item_code=code,
            prv_code=entry.prv_code,
            item_name=None if item is None or item.name is None else str(item.name),
        )

    async def lead_time(self, payload: BaseModel, run: RunContext) -> LeadTimeOutput:
        assert isinstance(payload, LeadTimeInput)
        binding = _binding(run)
        rule = (await self.rules.rules(binding.scope)).short_lead_time
        item = (await self.catalog.item_by_prv_code(binding.scope, payload.prv_code)).data
        return LeadTimeOutput(
            found=item is not None,
            prv_code=payload.prv_code,
            standard_lead_time_days=None if item is None else item.standard_lead_time_days,
            counted_from=rule.start,
            day_basis=rule.day_basis,
        )

    async def _case(self, binding: ThreadBinding, number: str) -> CaseView | None:
        """The bound customer's case known by ``number``: one of the thread's,
        else the live order case of that customer's PO number. Another
        customer's number is nothing: the lookup is by the bound customer,
        and what comes back is held to it again."""
        for case in binding.cases:
            if any(_same(number, known) for known in case.numbers):
                return case
        found = await self.orders.cases_for_po(binding.scope, binding.customer_code, number)
        live = [
            c
            for c in found
            if c.customer_code == binding.customer_code and c.superseded_by_case is None
        ]
        return order_view(live[0]) if len(live) == 1 else None


_Handler = Callable[[ThreadTools], Callable[[BaseModel, RunContext], Awaitable[BaseModel]]]

# Each tool: its input and output model and its handler. The policy (scopes,
# side effect, approval, timeout) is its spec's, read by the executor.
THREAD_TOOLS: Final[Mapping[str, tuple[type[BaseModel], type[BaseModel], _Handler]]] = {
    THREAD_MESSAGES: (NoInput, ThreadMessagesOutput, lambda t: t.thread_messages),
    CASE_SNAPSHOT: (NoInput, CaseSnapshotOutput, lambda t: t.case_snapshot),
    CASE_BY_NUMBER: (NumberInput, CaseByNumberOutput, lambda t: t.case_by_number),
    CONVERSION_LOOKUP: (ConversionInput, ConversionOutput, lambda t: t.conversion_lookup),
    LEAD_TIME: (LeadTimeInput, LeadTimeOutput, lambda t: t.lead_time),
    PC_STATUS: (NumberInput, PcStatusOutput, lambda t: t.pc_status),
}


def registered_tools(
    tools: ThreadTools, definition: Callable[[str, str], ToolDefinition]
) -> list[RegisteredTool]:
    """The six tools, each with its definition from its spec (``definition``,
    the spec registry's), for the composition root to register."""
    return [
        RegisteredTool(
            definition=definition(name, TOOL_VERSION),
            input_model=input_model,
            output_model=output_model,
            handler=handler(tools),
        )
        for name, (input_model, output_model, handler) in THREAD_TOOLS.items()
    ]


# ------------------------------------------------------ binding a thread --


class ThreadContextPort(Protocol):
    """What a turn is bound to, for a message and the cases code linked it to."""

    async def binding(
        self, scope: SalesScope, message: InboundMessage, cases: Sequence[ThreadedCase]
    ) -> ThreadBinding | None: ...


@dataclass(frozen=True)
class ThreadContext:
    """Implements `ThreadContextPort` with the workspace's log and mailbox."""

    uow: SalesUnitOfWorkFactory
    mailbox: ThreadMembersPort

    async def binding(
        self, scope: SalesScope, message: InboundMessage, cases: Sequence[ThreadedCase]
    ) -> ThreadBinding | None:
        """The cases (all of one customer, else None: a turn reads for one
        customer only) as views, and the thread's earlier messages that the
        log puts on one of them: the latest `EARLIER_MESSAGES`, newest part
        only, each cut to `MESSAGE_CHARS`."""
        customers = {case.customer_code for case in cases}
        if len(customers) != 1:
            return None
        (customer,) = customers
        thread = [
            m
            for m in await self.mailbox.thread_messages(scope, message)
            if m.message_id != message.message_id and m.received_at <= message.received_at
        ]
        ids = {case.case_id for case in cases}
        views: list[CaseView] = []
        async with self.uow(scope) as work:
            on_cases = {
                entry.message_id
                for entry in await work.messages.cases_of([m.message_id for m in thread])
                if entry.case_id in ids
            }
            for case in cases:
                if case.case_kind is CaseKind.ORDER:
                    order = await work.orders.get(case.case_id)
                    if order is not None and order.case.customer_code == customer:
                        views.append(order_view(order.case))
                else:
                    quote = await work.quotes.get(case.case_id)
                    if quote is not None and quote.case.customer_code == customer:
                        views.append(quote_view(quote.case))
        earlier = [m for m in thread if m.message_id in on_cases][-EARLIER_MESSAGES:]
        return ThreadBinding(
            scope=scope,
            customer_code=customer,
            message_id=message.message_id,
            earlier=tuple(_message_view(m) for m in earlier),
            cases=tuple(views),
        )


def _message_view(message: InboundMessage) -> ThreadMessageView:
    part = newest_part(message)
    return ThreadMessageView(
        author="customer",
        received_on=message.received_at.date(),
        subject=part.subject,
        text=part.body[:MESSAGE_CHARS],
    )
