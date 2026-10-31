"""PC's answer on delivery dates, read by the model from the mail Sales pastes
(the AI list, item 7; WIV-03-012 step O4).

DW1 proposes each line's date from the lead time; when the date has to come
from production control (PC), Sales asks PC by mail and types PC's answer
into the confirmation, line by line. PC's mail is internal, and internal
mail does not reach DW1's mailbox, so Sales pastes it into the confirmation
and the model reads, per line (and per delivery of a split line), the date
PC gives, copied as the mail writes it.

- **Code checks** each date: the words are in the pasted text as written,
  whole (not inside a longer date),
  they read as that very day (day before month, as a Vietnamese mail writes
  it, or an ISO date; a day and month alone take the year the model gave),
  and the line and delivery are the case's. A date that fails is dropped
  and counted.
- **Nothing is recorded**: the dates fill the confirmation's fields, and
  Sales still confirms each line and presses "Ghi đã gửi xác nhận", the one
  door that records them. Nothing is stored of the pasted text.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from dw_agent_runtime.context import caller_run
from dw_agent_runtime.model.interpretation import (
    InterpretationPort,
    ModelUnavailableError,
    PromptRef,
    estimated_tokens,
)
from dw_kernel.errors import QuotaExceededError
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.support import same_version, stored_order
from dw_sales.domain.orders import OrderCase

# The prompt the dates are read with. Its file is
# `configs/prompts/sales/pc_dates@1.0.0.yaml`; a test holds the two together,
# and the rendered prompt under `PROMPT_TOKENS`.
PC_DATES: Final = PromptRef("sales.pc_dates", "1.0.0")
PROMPT_TOKENS: Final = 900
_OUTPUT_TOKENS: Final = 800
# The longest text pasted that is read at all.
MAX_TEXT: Final = 8000
_ORDER: Final = "sales_order_case"

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class ModelPcDate(BaseModel):
    model_config = _FROZEN

    line_no: int = Field(ge=1, le=999)
    # The delivery of a split line, from 1; 1 for a line delivered at once.
    delivery: int = Field(default=1, ge=1, le=99)
    # The date as the mail writes it, and as the model reads it.
    date_text: str = Field(min_length=1, max_length=40)
    date: date


class ModelPcDates(BaseModel):
    model_config = _FROZEN

    dates: list[ModelPcDate] = Field(default_factory=list, max_length=200)


class PcDateView(BaseModel):
    model_config = ConfigDict(frozen=True)

    line_no: int
    delivery: int
    date: date
    # The words in PC's mail the date rests on.
    quote: str


class PcDatesView(BaseModel):
    """The dates read, or why there are none; always marked as the model's."""

    model_config = ConfigDict(frozen=True)

    status: Literal["read", "nothing", "unavailable"]
    dates: list[PcDateView] = []
    # Dates the model gave that the text or the case did not bear out.
    dropped: int = 0
    prompt_ref: str | None = None
    model_profile: str | None = None


_NUMERIC: Final = re.compile(r"^\s*(\d{1,4})[./-](\d{1,2})(?:[./-](\d{2,4}))?\s*$")


def reads_as(text: str, day: date) -> bool:
    """Whether ``text`` writes ``day``: ISO (year first), or day before month
    with or without the year (a two-digit year is this century's)."""
    found = _NUMERIC.match(text)
    if found is None:
        return False
    first, second, third = found.groups()
    if len(first) == 4:
        if third is None:
            return False
        year, month, dom = int(first), int(second), int(third)
    else:
        dom, month = int(first), int(second)
        year = day.year if third is None else int(third) + (2000 if len(third) == 2 else 0)
    return (year, month, dom) == (day.year, day.month, day.day)


def written_in(words: str, text: str) -> bool:
    """Whether ``text`` writes ``words`` whole: "1/11/2026" is not written
    by "01/11/2026", nor "05/11" by "05/11/2026"; a full stop ending the
    sentence is no part of the date."""
    before = r"(?<![\w/-])(?<!\d\.)"
    after = r"(?![\w/-])(?!\.\d)"
    return re.search(before + re.escape(words) + after, text) is not None


def deliveries(case: OrderCase) -> dict[int, int]:
    """Per line, how many deliveries it is confirmed in."""
    return {
        line.line_no: len(line.effective.schedules) if line.effective.prints_schedules else 1
        for line in case.lines
    }


def checked(answer: ModelPcDates, text: str, case: OrderCase) -> tuple[list[PcDateView], int]:
    """The dates whose words are in ``text`` as written, read as that day, on
    a line and delivery of the case; and how many were dropped. A line and
    delivery named twice keeps neither: the mail did not settle it."""
    counts = deliveries(case)
    seen: dict[tuple[int, int], int] = {}
    for item in answer.dates:
        seen[(item.line_no, item.delivery)] = seen.get((item.line_no, item.delivery), 0) + 1
    kept = [
        PcDateView(
            line_no=item.line_no,
            delivery=item.delivery,
            date=item.date,
            quote=item.date_text,
        )
        for item in answer.dates
        if item.delivery <= counts.get(item.line_no, 0)
        and seen[(item.line_no, item.delivery)] == 1
        and written_in(item.date_text, text)
        and reads_as(item.date_text, item.date)
    ]
    return kept, len(answer.dates) - len(kept)


def _facts(case: OrderCase) -> list[dict[str, object]]:
    return [
        {
            "line_no": line.line_no,
            "customer_item_code": line.effective.customer_item_code,
            "prv_code": line.mapping.prv_code,
            "deliveries": count,
        }
        for line, count in zip(case.lines, deliveries(case).values(), strict=True)
    ]


@dataclass(frozen=True)
class PcDateReplies:
    """`POST /orders/{case_id}/pc-dates` (module docstring)."""

    uow: SalesUnitOfWorkFactory
    gate: Gate
    model: InterpretationPort | None
    clock: UtcClock
    ids: IdGenerator
    worker_id: str
    worker_version: str

    async def read(
        self, context: AccessContext, case_id: uuid.UUID, *, case_version: int, text: str
    ) -> PcDatesView:
        await self.gate.require(
            context, SalesScopes.ORDER_PREPARE, resource_type=_ORDER, resource_id=str(case_id)
        )
        async with self.uow(sales_scope(context)) as work:
            case = (await stored_order(work, case_id, viewer=context)).case
        same_version(case_id, case.case_version, case_version)
        if self.model is None:
            return PcDatesView(status="unavailable")
        pasted = text[:MAX_TEXT]
        stamp = {"prompt_ref": str(PC_DATES), "model_profile": self.model.model_profile}
        if estimated_tokens(pasted) > self.model.max_input_tokens - PROMPT_TOKENS:
            return PcDatesView(**stamp, status="unavailable")
        try:
            answer = await self.model.interpret(
                PC_DATES,
                {
                    "lines": json.dumps(_facts(case), ensure_ascii=False, indent=1),
                    "mail": pasted,
                },
                ModelPcDates,
                run=caller_run(
                    context,
                    run_id=self.ids.new_uuid(),
                    worker_id=self.worker_id,
                    worker_version=self.worker_version,
                    trace="sales-pc-dates",
                    subject_ref=f"{_ORDER}:{case_id}",
                ),
                max_output_tokens=_OUTPUT_TOKENS,
            )
        except (ModelUnavailableError, QuotaExceededError):
            return PcDatesView(**stamp, status="unavailable")
        dates, dropped = checked(answer, pasted, case)
        return PcDatesView(
            **stamp, status="read" if dates else "nothing", dates=dates, dropped=dropped
        )
