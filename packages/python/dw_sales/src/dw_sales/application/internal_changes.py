"""Proterial's own change of a confirmed order: "Thay đổi nội bộ" (ticket 10,
the BA's step 6.1B; "Internal change" in CONTEXT.md).

After the confirmation, PC may move the dates of many lines at once, split
lines over several dates, or cut them, for overcapacity, NG or short stock.
PC's mail is internal and does not reach DW1's mailbox, so Sales pastes it.
Two doors, as item 7 has for PC's dates (`pc_dates`):

- **Read** (`read`): the model copies the paste's lines and deliveries and
  code keeps what it finds, resolves and parses
  (`domain.internal_changes.read_internal`). **Nothing is recorded**: what
  is read fills the form, nothing of the paste is stored, the case does not
  move. Gated as every model step (`ModelStep.INTERNAL_CHANGE`, the switch
  `model_assist.internal_change`, off in every platform version, and its
  live eval at the bar); off, unmeasured or with no model, the view says so
  and Sales types the lines.
- **Apply** (`apply`, "Áp dụng"): the reason and the lines a person checked,
  each with its deliveries, applied in one transaction with the case's next
  version, its event and its audit row: the one point the case changes
  (`OrderCase.take_internal_change`). The order enters the update loop at
  its Bravo update: the change list to apply in Bravo is the loop's Bravo
  update file (`bravo_update`: the changed lines' rows, a row per delivery,
  PC's first and current dates), approved by its id and hash, entered,
  cross-checked by someone who made none of it, and the confirmation sent
  again, which ends the loop (`update_loop.py`, ticket 29). The notice to
  the customer is the draft `internal_change_notice`, which a person sends.
  A line PC cancels whole (W07 "cancel all") is applied as PC's answer of
  no delivery (`OrderLine.cancelled`): its row in the change list holds
  nothing, the notice says it is cancelled, and the confirmation sent again
  names no date for it.

Both need `sales.order.prepare`, the PIC's, on an order of the caller's
workspace (another tenant's is not found). The audit row names ids, the
reason code and the status move, never a quantity or a date.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dw_agent_runtime.context import caller_run
from dw_agent_runtime.model.interpretation import (
    InterpretationPort,
    ModelUnavailableError,
    PromptRef,
    estimated_tokens,
)
from dw_kernel.errors import DomainError, QuotaExceededError
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import Gate, SalesScopes, order_actor, sales_scope
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.local_time import LocalZonePort, local_day
from dw_sales.application.order_intake import OrderIntake
from dw_sales.application.order_ports import ModelStepGatePort, OrderRulesPort
from dw_sales.application.pc_dates import MAX_TEXT
from dw_sales.application.ports import SalesScope
from dw_sales.application.support import person_event, same_version, save_order, stored_order
from dw_sales.application.views import CaseChangeView, UpdateDeliveryView, order_change
from dw_sales.domain.internal_changes import (
    ModelInternalChange,
    ReadLine,
    ReadProblem,
    read_internal,
)
from dw_sales.domain.order_checks import ModelStep
from dw_sales.domain.orders import (
    INTERNAL_LINES_MAX,
    PC_DELIVERIES_MAX,
    InternalReason,
    OrderCase,
)
from dw_sales.domain.rfq_reading import normalised

# The prompt PC's mail is read with. Its file is
# `configs/prompts/sales/internal_change@1.0.0.yaml`; a test holds the two
# together, and the rendered prompt under `PROMPT_TOKENS`.
INTERNAL_CHANGE: Final = PromptRef("sales.internal_change", "1.0.0")
PROMPT_TOKENS: Final = 1100
# Up to sixty lines of a few deliveries, about 40 tokens a line.
_OUTPUT_TOKENS: Final = 3000
_ORDER: Final = "sales_order_case"

ReadStatus = Literal["read", "nothing", "unavailable", "off"]


class InternalDeliveryView(BaseModel):
    """A delivery as read: a value None where the paste leaves it to a person."""

    model_config = ConfigDict(frozen=True)

    quantity: Decimal | None
    date: date | None
    # The words of PC's mail each value rests on.
    quantity_words: str | None
    date_words: str


class InternalLineView(BaseModel):
    """A line as read. ``line_no`` None: the words name no line of the order,
    refused. ``held_*``: the line as the order holds it, beside what PC gives."""

    model_config = ConfigDict(frozen=True)

    line_no: int | None
    words: str
    held_quantity: Decimal | None = None
    uom: str | None = None
    # The deliveries the order was confirmed with.
    held_deliveries: list[UpdateDeliveryView] = []
    deliveries: list[InternalDeliveryView]
    problem: ReadProblem | None


class InternalReadView(BaseModel):
    """What DW1 read of the paste, or why nothing: always marked as the
    model's on the page, and nothing of it is kept."""

    model_config = ConfigDict(frozen=True)

    status: ReadStatus
    lines: list[InternalLineView] = []
    # Changes the model gave whose words are not in the paste.
    dropped: int = 0
    # The longest paste DW1 reads (`pc_dates.MAX_TEXT`, its one owner).
    text_max: int = MAX_TEXT
    prompt_ref: str | None = None
    model_profile: str | None = None


class InternalDelivery(BaseModel):
    """One delivery a person applies: how much, on PC's date."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    quantity: Decimal = Field(gt=0, max_digits=15, decimal_places=3)
    date: date


class InternalLine(BaseModel):
    """One line a person applies, with its deliveries in PC's order; or
    ``cancelled``, PC cancelling the whole line, with none. A line without
    a delivery is a cancel only where it says so: an empty list alone is
    refused, never read as one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    line_no: int = Field(ge=1, le=99_999)
    deliveries: list[InternalDelivery] = Field(default=[], max_length=PC_DELIVERIES_MAX)
    cancelled: bool = False

    @model_validator(mode="after")
    def _a_cancel_has_no_delivery(self) -> Self:
        if self.cancelled == bool(self.deliveries):
            raise ValueError("a line is cancelled with no delivery, or delivered at least once")
        return self


@dataclass(frozen=True)
class InternalChanges:
    """`/orders/{case_id}/internal-change` (module docstring)."""

    uow: SalesUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    ids: IdGenerator
    intake: OrderIntake
    zones: LocalZonePort
    rules: OrderRulesPort
    # Whether the step may run for the tenant now; None: never.
    model_steps: ModelStepGatePort | None
    model: InterpretationPort | None
    worker_id: str
    worker_version: str

    async def read(
        self, context: AccessContext, case_id: uuid.UUID, *, case_version: int, text: str
    ) -> InternalReadView:
        """PC's mail, read; nothing is recorded (module docstring)."""
        await self._require(context, case_id)
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
        same_version(case_id, case.case_version, case_version)
        if not await self._on(scope):
            return InternalReadView(status="off")
        if self.model is None:
            return InternalReadView(status="unavailable")
        stamp = {"prompt_ref": str(INTERNAL_CHANGE), "model_profile": self.model.model_profile}
        pasted = normalised(text)
        if (
            len(pasted) > MAX_TEXT
            or estimated_tokens(pasted) > self.model.max_input_tokens - PROMPT_TOKENS
        ):
            # Not cut: later lines would lose their dates with no word.
            return InternalReadView(**stamp, status="unavailable")
        try:
            answer = await self.model.interpret(
                INTERNAL_CHANGE,
                {"mail": pasted},
                ModelInternalChange,
                run=caller_run(
                    context,
                    run_id=self.ids.new_uuid(),
                    worker_id=self.worker_id,
                    worker_version=self.worker_version,
                    trace="sales-internal-change",
                    subject_ref=f"{_ORDER}:{case_id}",
                ),
                max_output_tokens=_OUTPUT_TOKENS,
            )
        except (ModelUnavailableError, QuotaExceededError):
            return InternalReadView(**stamp, status="unavailable")
        today = local_day(self.clock.now(), await self.zones.time_zone(scope))
        reading = read_internal(case, pasted, answer, today)
        return InternalReadView(
            **stamp,
            status="read" if reading.lines else "nothing",
            lines=[_line_view(case, line) for line in reading.lines],
            dropped=reading.dropped,
        )

    async def apply(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        *,
        case_version: int,
        reason: InternalReason,
        lines: Sequence[InternalLine],
    ) -> CaseChangeView:
        """ "Áp dụng": the lines a person checked applied to the order, which
        goes to its Bravo update (module docstring)."""
        await self._require(context, case_id)
        numbers = [line.line_no for line in lines]
        if len(numbers) != len(set(numbers)):
            raise DomainError(
                "một dòng được nêu hai lần: gộp các đợt giao của dòng vào một",
                details={"case_id": str(case_id), "rule": "line_named_twice"},
            )
        if len(numbers) > INTERNAL_LINES_MAX:
            raise DomainError(
                "an internal change names too many lines",
                details={"case_id": str(case_id), "max": INTERNAL_LINES_MAX},
            )
        deliveries = {
            line.line_no: [(d.quantity, d.date) for d in line.deliveries] for line in lines
        }
        actor, now, scope = order_actor(context, self.gate), self.clock.now(), sales_scope(context)
        async with self.uow(scope) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
            same_version(case_id, case.case_version, case_version)
            after = await self.intake.take_internal_change(
                scope, case, self.ids.new_uuid(), reason, deliveries, actor, now
            )
            event = person_event("order.internal_change_applied", context, now, reason_code=reason)
            await save_order(work, context, self.ids, case, after, event)
            await work.commit()
        return order_change(after)

    async def _on(self, scope: SalesScope) -> bool:
        """The step on in the tenant's rules in force and measured at its bar;
        never without the gate."""
        if self.model_steps is None:
            return False
        rules = await self.rules.rules(scope)
        return await self.model_steps.allows(scope, rules, ModelStep.INTERNAL_CHANGE)

    async def _require(self, context: AccessContext, case_id: uuid.UUID) -> None:
        await self.gate.require(
            context, SalesScopes.ORDER_PREPARE, resource_type=_ORDER, resource_id=str(case_id)
        )


def _line_view(case: OrderCase, read: ReadLine) -> InternalLineView:
    deliveries = [
        InternalDeliveryView(
            quantity=d.quantity,
            date=d.day,
            quantity_words=d.quantity_words,
            date_words=d.date_words,
        )
        for d in read.deliveries
    ]
    if read.line_no is None:
        return InternalLineView(
            line_no=None, words=read.words, deliveries=deliveries, problem=read.problem
        )
    line = case.line(read.line_no)
    return InternalLineView(
        line_no=read.line_no,
        words=read.words,
        held_quantity=line.effective.quantity,
        uom=line.effective.uom,
        held_deliveries=[
            UpdateDeliveryView(quantity=q, date=d) for q, d in line.confirmed_deliveries()
        ],
        deliveries=deliveries,
        problem=read.problem,
    )


__all__ = [
    "INTERNAL_CHANGE",
    "InternalChanges",
    "InternalDelivery",
    "InternalLine",
    "InternalReadView",
]
