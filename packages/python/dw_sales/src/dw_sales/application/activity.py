""" "DW1 đã làm gì": what DW1's model steps did, for one case and over time
(slice 3, the server half of the AI activity page).

**What is read, and from where.** Each step's row (`domain.activity.StepOutcome`,
`sales.step_outcomes`) says when it ran, for how long, on which model and
prompt, and what code made of the answer. WHAT was read is not on the row: it
is joined from the stamp it was read into, the one owner of it (a line's
`DescriptionReading`, a quote's model-read fields, a message's disposition).
A row of an earlier message on the case (a revision's) shows no values: the
case no longer holds the lines that message read.

**Prices are absent, not masked.** A value that is a price (`PRICE_FIELDS`) is
left out of ``produced`` altogether, with its anchor, for a caller without
`sales.price.read`: an activity log is a side door to the case
(`.claude/rules/ui-quality.md` §6), and a field the JSON does not carry cannot
be shown by a screen that forgot to hide it. No row holds a prompt, a model's
words or a reasoning; the rows hold no value at all.

**Who may read.**

- One case's activity: `sales.case.read`, as its history (`pipeline.history`);
  a case of another tenant or workspace is not found (404), never forbidden.
- The summary: counts and times, no case content and no amount, which is
  what `sales.overview.read` reads (Sales and the head hold it; the
  leadership viewer holds only it). `sales.rules.propose` reads it too: the
  customer's IT proposes the versions that turn a model step on, on the
  process page that shows the same share beside each step. Neither narrows to
  a person's own cases: a count carries no case and no customer.

**The 7-day share** beside a step on the process page is
`activity_ports.automatic_share_last_7_days`, the same tally over the last 168
hours. The ports, and the case list filter each count links to, are declared
there (`activity_ports`), where the services that read them can import them.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from dw_kernel.ports import UtcClock
from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import Gate, PriceView, SalesScopes, sales_scope
from dw_sales.application.activity_ports import HandledBy, StepActivityReadPort, day_window
from dw_sales.application.case_store import LoggedEvent, SalesUnitOfWorkFactory
from dw_sales.application.model_readiness import BARS
from dw_sales.application.process_settings import model_steps
from dw_sales.application.quotes_service import local_day
from dw_sales.application.support import stored_order, stored_quote
from dw_sales.domain.activity import StepOutcome, StepResult, StepTally, percentile, tally
from dw_sales.domain.dispositions import CaseKind, MessageDisposition
from dw_sales.domain.order_checks import ModelStep
from dw_sales.domain.orders import AMOUNT_FIELDS, OrderCase
from dw_sales.domain.process import StepId
from dw_sales.domain.quotes import QuoteCase

_VIEW = ConfigDict(frozen=True)

# The step each prompt belongs to, from the bars that pin them: a call whose
# step stamped nothing is still that step's row.
STEPS_BY_PROMPT: Final[Mapping[str, ModelStep]] = {
    str(bar.prompt): step for step, bar in BARS.items()
}
# The surveyed steps each model step takes part in: where the process page
# places its switch (`process_settings.model_steps`), inverted.
PROCESS_STEPS: Final[Mapping[ModelStep, tuple[StepId, ...]]] = {
    step: tuple(s for s in StepId if step in model_steps(s)) for step in ModelStep
}
# The fields whose value is a price: an order's amounts (`AMOUNT_FIELDS`), and
# a quotation's target price, as the form prints it or as a customer stated it
# and a model read it (both shown only with `sales.price.read` by the case view).
PRICE_FIELDS: Final = AMOUNT_FIELDS | {"target_price", "stated_target_price"}
# The default window: the last week, today included.
DEFAULT_SUMMARY_DAYS: Final = 7
# The reason codes a step's summary lists, most frequent first.
TOP_REASONS: Final = 5
# Steps whose produced values are on the message's disposition, not the case.
_ON_DISPOSITION: Final = frozenset(
    {ModelStep.MESSAGE_INTENT, ModelStep.REPLY_INTENT, ModelStep.REQUEST_HANDOFF}
)
# Steps whose product is a route (code routes from the kind read).
_ROUTING: Final = frozenset({ModelStep.MESSAGE_INTENT, ModelStep.REPLY_INTENT})


# -------------------------------------------------------------------- views --


class AnchorRef(BaseModel):
    """Where the case view anchors the value: the line (None for the
    request's or the PO's own fields) and the field its ``anchors`` key it by."""

    model_config = _VIEW

    line_no: int | None
    field: str


class ProducedValue(BaseModel):
    model_config = _VIEW

    field: str
    value: str
    line_no: int | None
    anchor: AnchorRef | None


class CheckView(BaseModel):
    """Code's check of the model's answer: passed, refused with the reason
    code, or not run because no answer came."""

    model_config = _VIEW

    result: Literal["passed", "refused", "not_run"]
    reason_code: str | None


ActivityKind = Literal["read", "route", "check", "to_person", "model_unavailable"]


class ActivityEntry(BaseModel):
    model_config = _VIEW

    step: ModelStep
    process_steps: list[StepId]
    # read: DW1 read it and code took it; route: code routed from what was
    # read; check: a check refused the answer; to_person: taken, and nothing
    # in it DW1 could use (no item fits); model_unavailable: no usable answer.
    kind: ActivityKind
    occurred_at: datetime
    # The step's calls for the message this entry is of, and their time.
    calls: int
    duration_ms: int | None
    model: str | None
    model_profile: str
    prompt: str
    message_id: str
    line_no: int | None
    check: CheckView
    handled_by: HandledBy
    # The first person who acted on the case after a step left it to one.
    taken_over_by: uuid.UUID | None
    produced: list[ProducedValue]
    # Values refused inside what code took, by reason: counts only.
    refusals: dict[str, int]


class CaseActivityView(BaseModel):
    model_config = _VIEW

    case_kind: CaseKind
    case_id: uuid.UUID
    entries: list[ActivityEntry]


class ActivityFilter(BaseModel):
    """The case list filter a count stands for: the parameters, not a URL."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    step: ModelStep
    handled_by: HandledBy | None = None
    result: StepResult | None = None
    reason_code: str | None = None
    lane: CaseKind | None = None
    from_: date = Field(serialization_alias="from")
    to: date


class LinkedCount(BaseModel):
    model_config = _VIEW

    count: int
    filter: ActivityFilter


class ReasonCount(BaseModel):
    model_config = _VIEW

    reason_code: str
    count: int
    filter: ActivityFilter


class LatencyView(BaseModel):
    """The step's time per message, nearest-rank percentiles."""

    model_config = _VIEW

    p50_ms: int | None
    p95_ms: int | None
    samples: int


class StepSummaryView(BaseModel):
    model_config = _VIEW

    step: ModelStep
    process_steps: list[StepId]
    handled: LinkedCount
    automatic: LinkedCount
    to_person: LinkedCount
    # Automatic over handled; None when the step handled nothing.
    automatic_share: float | None
    model_unavailable: LinkedCount
    top_reasons: list[ReasonCount]
    latency: LatencyView


class DayStepView(BaseModel):
    model_config = _VIEW

    step: ModelStep
    handled: int
    automatic: int
    to_person: int


class DayView(BaseModel):
    model_config = _VIEW

    day: date
    steps: list[DayStepView]


class ActivitySummaryView(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    from_: date = Field(serialization_alias="from")
    to: date
    lane: CaseKind | None
    as_of: datetime
    steps: list[StepSummaryView]
    days: list[DayView]


# ------------------------------------------------------- the case activity --


def _value(value: object) -> str:
    return value.isoformat() if isinstance(value, date) else str(value)


def _order_produced(case: OrderCase, row: StepOutcome) -> list[ProducedValue]:
    if row.step is not ModelStep.DESCRIPTION_ATTRIBUTES or row.message_id != case.message_id:
        return []
    line = next((line for line in case.lines if line.line_no == row.line_no), None)
    reading = line.basis.description_reading if line is not None else None
    if reading is None:
        return []
    anchor = AnchorRef(line_no=row.line_no, field="description")
    return [
        ProducedValue(field=s.attribute, value=s.value, line_no=row.line_no, anchor=anchor)
        for s in reading.spans
    ]


def _quote_produced(case: QuoteCase, row: StepOutcome) -> list[ProducedValue]:
    request = case.request
    if row.message_id != request.message_id:
        return []
    document = request.document
    produced: list[ProducedValue] = []
    if row.step is ModelStep.RFQ_EXTRACTION:
        for name in sorted(document.model_read):
            held = getattr(document, name)
            if held is not None:
                produced.append(
                    ProducedValue(
                        field=name,
                        value=_value(held.value),
                        line_no=None,
                        anchor=AnchorRef(line_no=None, field=name),
                    )
                )
        for item in document.items:
            names = sorted(item.model_read)
            if item.stated_target_price is not None:
                names.append("stated_target_price")
            for name in names:
                held = getattr(item, name)
                if held is not None and held.value is not None:
                    produced.append(
                        ProducedValue(
                            field=name,
                            value=_value(held.value),
                            line_no=item.line_no,
                            anchor=AnchorRef(line_no=item.line_no, field=name),
                        )
                    )
    elif row.step is ModelStep.DESCRIPTION_ATTRIBUTES:
        read = next((i for i in document.items if i.line_no == row.line_no), None)
        reading = read.description_reading if read is not None else None
        if reading is not None:
            anchor = AnchorRef(line_no=row.line_no, field="description")
            produced = [
                ProducedValue(field=s.attribute, value=s.value, line_no=row.line_no, anchor=anchor)
                for s in reading.spans
            ]
    return produced


def _disposition_produced(
    disposition: MessageDisposition | None, row: StepOutcome
) -> list[ProducedValue]:
    if disposition is None:
        return []

    def plain(name: str, value: object, line_no: int | None = None) -> ProducedValue:
        return ProducedValue(field=name, value=_value(value), line_no=line_no, anchor=None)

    if row.step is ModelStep.MESSAGE_INTENT and disposition.reading is not None:
        reading = disposition.reading
        return [
            plain(n, v) for n, v in (("kind", reading.kind), ("language", reading.language)) if v
        ]
    if row.step is ModelStep.REPLY_INTENT and disposition.reply is not None:
        reply = disposition.reply.reading
        return [] if reply is None or reply.kind is None else [plain("kind", reply.kind)]
    if row.step is ModelStep.REQUEST_HANDOFF and disposition.handoff is not None:
        handoff = disposition.handoff
        produced = [
            plain(n, v) for n, v in (("po_no", handoff.po_no), ("so_no", handoff.so_no)) if v
        ]
        for line in handoff.lines:
            if line.new_quantity is not None:
                produced.append(plain("new_quantity", line.new_quantity, line.line_no))
            if line.new_date is not None:
                produced.append(plain("new_date", line.new_date, line.line_no))
        return produced
    return []


def _kind(row: StepOutcome) -> ActivityKind:
    if row.result == "unavailable":
        return "model_unavailable"
    if row.result == "refused":
        return "check"
    if not row.automatic:
        return "to_person"
    return "route" if row.step in _ROUTING else "read"


def _check(row: StepOutcome) -> CheckView:
    if row.result == "unavailable":
        return CheckView(result="not_run", reason_code=None)
    if row.result == "refused":
        return CheckView(result="refused", reason_code=row.reason_code)
    return CheckView(result="passed", reason_code=None)


def _taken_over_by(row: StepOutcome, events: Sequence[LoggedEvent]) -> uuid.UUID | None:
    if row.automatic:
        return None
    for event in events:
        if event.actor_kind == "user" and event.occurred_at >= row.occurred_at and event.actor_id:
            try:
                return uuid.UUID(event.actor_id)
            except ValueError:
                continue
    return None


def case_activity(
    case: OrderCase | QuoteCase,
    rows: Sequence[StepOutcome],
    events: Sequence[LoggedEvent],
    dispositions: Mapping[str, MessageDisposition],
    prices: PriceView,
) -> CaseActivityView:
    """One case's entries, oldest first, each with what it produced as the
    case and the messages hold it now; a price only for ``prices.amounts``."""
    # The step's calls and time per message, held on its first row.
    timed = {(r.message_id, r.step): r for r in rows if r.calls > 0}
    ordered = sorted(rows, key=lambda r: (r.occurred_at, r.step.value, r.line_no or 0))
    entries: list[ActivityEntry] = []
    for row in ordered:
        if row.step in _ON_DISPOSITION:
            produced = _disposition_produced(dispositions.get(row.message_id), row)
        elif isinstance(case, OrderCase):
            produced = _order_produced(case, row)
        else:
            produced = _quote_produced(case, row)
        if not prices.amounts:
            produced = [p for p in produced if p.field not in PRICE_FIELDS]
        holder = timed.get((row.message_id, row.step))
        entries.append(
            ActivityEntry(
                step=row.step,
                process_steps=list(PROCESS_STEPS[row.step]),
                kind=_kind(row),
                occurred_at=row.occurred_at,
                calls=holder.calls if holder is not None else 0,
                duration_ms=holder.duration_ms if holder is not None else None,
                model=row.model,
                model_profile=row.model_profile,
                prompt=row.prompt,
                message_id=row.message_id,
                line_no=row.line_no,
                check=_check(row),
                handled_by="dw1" if row.automatic else "person",
                taken_over_by=_taken_over_by(row, events),
                produced=produced,
                refusals=dict(row.refusals),
            )
        )
    kind = CaseKind.ORDER if isinstance(case, OrderCase) else CaseKind.QUOTE
    return CaseActivityView(case_kind=kind, case_id=case.case_id, entries=entries)


# --------------------------------------------------------------- the summary --


def activity_summary(
    rows: Sequence[StepOutcome],
    *,
    start: date,
    end: date,
    lane: CaseKind | None,
    as_of: datetime,
) -> ActivitySummaryView:
    """Per step over ``start``..``end`` (local days, both included): counts
    each with the case list filter it stands for, the top reason codes, the
    latency, and a series per day."""

    def link(
        step: ModelStep,
        count: int,
        *,
        handled_by: HandledBy | None = None,
        result: StepResult | None = None,
    ) -> LinkedCount:
        narrowed = ActivityFilter(
            step=step, handled_by=handled_by, result=result, lane=lane, from_=start, to=end
        )
        return LinkedCount(count=count, filter=narrowed)

    def summary(step: ModelStep, t: StepTally) -> StepSummaryView:
        return StepSummaryView(
            step=step,
            process_steps=list(PROCESS_STEPS[step]),
            handled=link(step, t.handled),
            automatic=link(step, t.automatic, handled_by="dw1"),
            to_person=link(step, t.to_person, handled_by="person"),
            automatic_share=t.automatic_share,
            model_unavailable=link(step, t.unavailable, result="unavailable"),
            top_reasons=[
                ReasonCount(
                    reason_code=code,
                    count=count,
                    filter=ActivityFilter(
                        step=step, reason_code=code, lane=lane, from_=start, to=end
                    ),
                )
                for code, count in sorted(t.reasons.items(), key=lambda kv: (-kv[1], kv[0]))[
                    :TOP_REASONS
                ]
            ],
            latency=LatencyView(
                p50_ms=percentile(t.durations, 0.5),
                p95_ms=percentile(t.durations, 0.95),
                samples=len(t.durations),
            ),
        )

    by_day: dict[date, list[StepOutcome]] = {}
    for row in rows:
        by_day.setdefault(local_day(row.occurred_at), []).append(row)
    days: list[DayView] = []
    day = start
    while day <= end:
        tallies = tally(by_day.get(day, ()))
        days.append(
            DayView(
                day=day,
                steps=[
                    DayStepView(
                        step=step, handled=t.handled, automatic=t.automatic, to_person=t.to_person
                    )
                    for step, t in tallies.items()
                ],
            )
        )
        day += timedelta(days=1)
    return ActivitySummaryView(
        from_=start,
        to=end,
        lane=lane,
        as_of=as_of,
        steps=[summary(step, t) for step, t in tally(rows).items()],
        days=days,
    )


# ------------------------------------------------------------------ service --


@dataclass(frozen=True)
class ActivityService:
    uow: SalesUnitOfWorkFactory
    gate: Gate
    reader: StepActivityReadPort
    clock: UtcClock

    async def case_activity(
        self, context: AccessContext, kind: CaseKind, case_id: uuid.UUID
    ) -> CaseActivityView:
        await self.gate.require(
            context,
            SalesScopes.CASE_READ,
            resource_type=f"sales_{kind.value}",
            resource_id=str(case_id),
        )
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            # Another workspace's or tenant's case is not found, before any row
            # is read.
            case: OrderCase | QuoteCase
            if kind is CaseKind.ORDER:
                case = (await stored_order(work, case_id)).case
            else:
                case = (await stored_quote(work, case_id)).case
            events = await work.overview.history(kind, case_id)
            rows = await self.reader.for_case(scope, kind, case_id)
            dispositions: dict[str, MessageDisposition] = {}
            for message_id in sorted({r.message_id for r in rows if r.step in _ON_DISPOSITION}):
                found = await work.messages.get(message_id)
                if found is not None:
                    dispositions[message_id] = found
        return case_activity(case, rows, events, dispositions, self.gate.prices(context))

    async def summary(
        self,
        context: AccessContext,
        *,
        start: date | None,
        end: date | None,
        lane: CaseKind | None,
    ) -> ActivitySummaryView:
        if not (
            self.gate.allows(context, SalesScopes.OVERVIEW_READ)
            or self.gate.allows(context, SalesScopes.RULES_PROPOSE)
        ):
            # Refused as the platform refuses, naming the scope that reads it.
            await self.gate.require(
                context, SalesScopes.OVERVIEW_READ, resource_type="sales_activity"
            )
        now = self.clock.now()
        last = end or local_day(now)
        first = start or last - timedelta(days=DEFAULT_SUMMARY_DAYS - 1)
        since, until = day_window(first, last)
        rows = await self.reader.between(sales_scope(context), since, until, lane)
        return activity_summary(rows, start=first, end=last, lane=lane, as_of=now)
