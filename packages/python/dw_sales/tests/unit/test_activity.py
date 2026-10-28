"""What DW1's model steps did (slice 3, "AI activity"): the rows derived from
the stamps, the summary's arithmetic, who may read, and that a price never
reaches a caller who may not see one, not even masked.

Cases are read from the mock mailbox as intake and the quotation flow read
them, then given the stamps a model step leaves (`model_copy`, as a stored
case read back holds them); no database (the table is
`tests/integration/test_sales_step_outcomes.py`).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import TracebackType
from typing import Any, Self, cast

import pytest
from pydantic import ValidationError

from dw_agent_runtime.contracts import RunContext
from dw_kernel.errors import ConflictError, DomainError, NotFoundError, PermissionDeniedError
from dw_kernel.ids import TenantId, WorkspaceId
from dw_kernel.ports import FixedClock
from dw_platform.application.access_context import AccessContext
from dw_sales.adapters.memory_rules import platform_book
from dw_sales.adapters.mock import MockInbox, MockSalesCatalog
from dw_sales.adapters.order_rules import PlatformOrderRules, load_order_rules
from dw_sales.adapters.policy_files import load_pricing, load_quote_rules
from dw_sales.adapters.reader_client import (
    ClientDesignReplyReader,
    ClientPoReaders,
    ClientQuoteForms,
    ClientRfqReader,
)
from dw_sales.adapters.readers.operations import InProcessReaderTransport
from dw_sales.application.access import Gate, PriceView, SalesScopes
from dw_sales.application.activity import (
    PROCESS_STEPS,
    STEPS_BY_PROMPT,
    ActivityFilter,
    ActivityService,
    activity_summary,
    case_activity,
)
from dw_sales.application.activity_ports import (
    CaseListActivity,
    StepRowFilter,
    automatic_share_last_7_days,
)
from dw_sales.application.case_store import (
    CaseOrigin,
    LoggedEvent,
    SalesUnitOfWork,
    SalesUnitOfWorkFactory,
    Stored,
)
from dw_sales.application.model_calls import (
    TimedInterpretation,
    model_calls,
    recording_model_calls,
)
from dw_sales.application.model_reading import DESCRIPTION_ATTRIBUTES, ModelUnavailableError
from dw_sales.application.order_intake import OrderIntake
from dw_sales.application.ports import SalesScope
from dw_sales.application.quotation import QuotationService
from dw_sales.application.rfq_reading import RFQ_EXTRACTION
from dw_sales.domain.activity import (
    NO_ITEM_FITS,
    OTHER_REASON,
    ModelCall,
    StepOutcome,
    outcomes_of,
    percentile,
    tally,
)
from dw_sales.domain.description_reading import DescriptionReading, ModelDescriptionReading
from dw_sales.domain.dispositions import (
    SALES_PIC_POOL,
    CaseKind,
    DispositionKind,
    MessageDisposition,
    RoutingReason,
)
from dw_sales.domain.layouts import LayoutPrefill
from dw_sales.domain.message_intent import IntentReading
from dw_sales.domain.order_checks import ModelStep
from dw_sales.domain.orders import (
    FlaggedValue,
    LineMapping,
    MappingStatus,
    OrderCase,
    RegionFlag,
)
from dw_sales.domain.process import StepId
from dw_sales.domain.quotes import QuoteCase, RequestReading, Sourced
from dw_sales.evals.graders import AN as _AN
from dw_sales.evals.graders import CALLERS
from dw_sales.evals.recorded import ByPrompt, Recorded
from dw_sales.evals.world import ALPHA, BETA, Caller, MemoryStore, SampleSet, open_world
from dw_sales.evals.world import NOW as WORLD_NOW

# An given the set `sales_rules_editor` (`sales.rules.propose`): since
# 2026-10-28 a PIC proposes only when the admin gives them it.
AN = replace(_AN, scopes=_AN.scopes | {SalesScopes.RULES_PROPOSE})

pytestmark = pytest.mark.unit

SCOPE = SalesScope(TenantId(uuid.UUID(int=1)), WorkspaceId(uuid.UUID(int=2)))
OTHER_TENANT = SalesScope(TenantId(uuid.UUID(int=3)), WorkspaceId(uuid.UUID(int=4)))
REPO = Path(__file__).resolve().parents[5]
POLICIES = REPO / "configs" / "policies"
AT = datetime(2026, 10, 23, 3, 0, tzinfo=UTC)
NONE = PriceView(amounts=False, other_customers=False)
OWN = PriceView(amounts=True, other_customers=False)
PERSON = uuid.UUID(int=0xA1)
_PROFILE = "onprem"
_MODEL = "qwen3.5-9b-dw"
_DESCRIPTION = str(DESCRIPTION_ATTRIBUTES)
_RFQ = str(RFQ_EXTRACTION)


def _ids() -> Any:
    counter = iter(range(1, 10_000))
    return lambda: uuid.UUID(int=next(counter))


def _reading(outcome: str, **extra: Any) -> DescriptionReading:
    spans = (
        [
            {
                "attribute": "cores",
                "span": "4C",
                "start": 0,
                "end": 2,
                "value": "4",
                "read_by": "code",
            }
        ]
        if outcome == "read"
        else []
    )
    return DescriptionReading.model_validate(
        {
            "prompt": _DESCRIPTION,
            "model_profile": _PROFILE,
            "route": "structured_extraction",
            "outcome": outcome,
            "spans": spans,
            **extra,
        }
    )


async def _order(message_id: str = "M04") -> OrderCase:
    inbox = MockInbox.load(SCOPE)
    intake = OrderIntake(
        catalog=MockSalesCatalog.load(SCOPE),
        inbox=inbox,
        reader=ClientPoReaders(InProcessReaderTransport()),
        quote_forms=ClientQuoteForms(InProcessReaderTransport()),
        rules=PlatformOrderRules(load_order_rules(POLICIES / "sales_order_rules@1.6.0.yaml")),
        cases=_NoCases(),
        new_case_id=lambda: uuid.UUID(int=0xC0),
    )
    message = await inbox.get_message(SCOPE, message_id)
    assert message is not None
    outcome = await intake.process(SCOPE, message)
    assert outcome.case is not None
    return outcome.case


class _NoCases:
    async def cases_for_po(self, scope: SalesScope, customer_code: str, po_no: str) -> Any:
        return ()

    async def cases_for_ycbg(self, scope: SalesScope, ycbg_no: str) -> Any:
        return ()


def _read_lines(case: OrderCase) -> OrderCase:
    """The case as a model reading of its first three lines left it: read and
    mapped, refused by check 3, and no answer."""
    first, second, third, *rest = case.lines
    stamped = []
    for line, reading, status in (
        (first, _reading("read"), MappingStatus.CANDIDATE),
        (second, _reading("not_understood", reason="text_uncovered"), MappingStatus.UNMAPPED),
        (third, _reading("unavailable"), MappingStatus.UNMAPPED),
    ):
        stamped.append(
            line.model_copy(
                update={
                    "basis": line.basis.model_copy(update={"description_reading": reading}),
                    "mapping": LineMapping(status=status)
                    if status is MappingStatus.UNMAPPED
                    else line.mapping,
                }
            )
        )
    return case.model_copy(update={"lines": (*stamped, *rest)})


async def _quote() -> QuoteCase:
    """M10 as a model read it: the request's due date and each line's
    quantity flagged as read, and a target price the customer stated."""
    catalog = MockSalesCatalog.load(SCOPE)
    service = QuotationService(
        catalog=catalog,
        inbox=MockInbox.load(SCOPE),
        rfq_reader=ClientRfqReader(InProcessReaderTransport()),
        reply_reader=ClientDesignReplyReader(InProcessReaderTransport()),
        cases=_NoCases(),
        ledger=catalog,
        policies=platform_book(
            load_quote_rules(POLICIES / "sales_quote_rules@1.1.0.yaml"),
            load_pricing(POLICIES / "sales_pricing@1.0.0.yaml"),
        ),
    )
    case = await service.open_case(SCOPE, "M10", uuid.UUID(int=7))
    request = case.request
    document = request.document
    items = tuple(
        item.model_copy(
            update={
                "flags": (FlaggedValue(field="quantity", flag=RegionFlag.MODEL_READ),),
                "stated_target_price": Sourced[Decimal](
                    value=Decimal("0.9537"), source=item.description.source
                ),
                "description_reading": _reading("read"),
                "candidates": ("PRV-0001",),
            }
        )
        for item in document.items
    )
    document = document.model_copy(update={"items": items})
    reading = RequestReading(
        prompt=_RFQ,
        model_profile=_PROFILE,
        route="structured_extraction",
        rules="sales_order_rules@1.6.0",
        calls=1,
        refused={"price_unparsed": 1},
    )
    return case.model_copy(
        update={"request": request.model_copy(update={"document": document, "reading": reading})}
    )


def _intent(outcome: str = "read") -> IntentReading:
    read = outcome == "read"
    return IntentReading(
        prompt="sales.message_intent@1.0.0",
        model_profile=_PROFILE,
        route="structured_extraction",
        rules="sales_order_rules@1.6.0",
        outcome=outcome,
        kind="po" if read else None,
        language="vi" if read else None,
    )


def _created(case: OrderCase | QuoteCase, **extra: Any) -> MessageDisposition:
    kind = CaseKind.ORDER if isinstance(case, OrderCase) else CaseKind.QUOTE
    message_id = case.message_id if isinstance(case, OrderCase) else case.request.message_id
    return MessageDisposition(
        message_id=message_id,
        kind=DispositionKind.CASE_CREATED,
        case_kind=kind,
        case_id=case.case_id,
        **extra,
    )


def _call(prompt: str, ms: float, *, answered: bool = True) -> ModelCall:
    return ModelCall(
        prompt=prompt, model_profile=_PROFILE, model=_MODEL, duration_ms=ms, answered=answered
    )


def _rows(
    disposition: MessageDisposition,
    case: OrderCase | QuoteCase | None,
    calls: Sequence[ModelCall] = (),
    at: datetime = AT,
) -> tuple[StepOutcome, ...]:
    return outcomes_of(
        disposition, case, calls, steps_by_prompt=STEPS_BY_PROMPT, at=at, new_id=_ids()
    )


# --------------------------------------------------------- the derivation --


async def test_each_item_a_step_handled_is_a_row_with_what_code_made_of_it() -> None:
    case = _read_lines(await _order())
    disposition = _created(case, reading=_intent())

    rows = _rows(
        disposition,
        case,
        [
            _call(_DESCRIPTION, 400.4),
            _call(_DESCRIPTION, 300.2),
            _call("sales.message_intent@1.0.0", 90),
        ],
    )

    intent, *lines = rows
    assert (intent.step, intent.result, intent.automatic) == (
        ModelStep.MESSAGE_INTENT,
        "accepted",
        True,
    )
    assert (intent.lane, intent.case_id) == (CaseKind.ORDER, case.case_id)
    assert [(r.line_no, r.result, r.automatic, r.reason_code) for r in lines] == [
        (case.lines[0].line_no, "accepted", True, None),
        (case.lines[1].line_no, "refused", False, "text_uncovered"),
        (case.lines[2].line_no, "unavailable", False, None),
    ]
    # The step's two calls for the message, held once, on its first row.
    assert [(r.calls, r.duration_ms) for r in lines] == [(2, 701), (0, None), (0, None)]
    assert {r.model for r in rows} == {_MODEL}
    assert all(r.message_id == case.message_id for r in rows)


async def test_a_reading_code_took_whose_attributes_fit_no_item_is_a_persons() -> None:
    case = await _order()
    first, *rest = case.lines
    unmapped = first.model_copy(
        update={
            "basis": first.basis.model_copy(update={"description_reading": _reading("read")}),
            "mapping": LineMapping(status=MappingStatus.UNMAPPED),
        }
    )

    (row,) = _rows(_created(case), case.model_copy(update={"lines": (unmapped, *rest)}))

    assert (row.result, row.automatic, row.reason_code) == ("accepted", False, NO_ITEM_FITS)


async def test_a_later_message_on_the_case_did_not_read_its_lines() -> None:
    """A reply attached to the case is not the message that read its lines."""
    case = _read_lines(await _order())
    reply = MessageDisposition(
        message_id="M99",
        kind=DispositionKind.ATTACHED_TO_CASE,
        case_kind=CaseKind.ORDER,
        case_id=case.case_id,
    )

    assert _rows(reply, case) == ()


def test_a_step_that_ran_and_stamped_nothing_is_still_counted() -> None:
    """A request no model reading could extract is routed with no case: its
    calls are the only trace, and without a row the share would count only
    successes."""
    routed = MessageDisposition(
        message_id="M40",
        kind=DispositionKind.ROUTED_TO_SALES,
        reason=RoutingReason.ATTACHMENT_UNREADABLE,
        owner=SALES_PIC_POOL,
    )

    (answered,) = _rows(routed, None, [_call(_RFQ, 1200)])
    (silent,) = _rows(routed, None, [_call(_RFQ, 30_000, answered=False)])

    assert (answered.step, answered.result, answered.reason_code) == (
        ModelStep.RFQ_EXTRACTION,
        "refused",
        "attachment_unreadable",
    )
    assert (answered.lane, answered.case_id, answered.automatic) == (CaseKind.QUOTE, None, False)
    assert (silent.result, silent.reason_code, silent.duration_ms) == ("unavailable", None, 30_000)
    # A call no step owns (a rule draft's) is no step's row.
    assert _rows(routed, None, [_call("sales.rule_draft@1.0.0", 5)]) == ()


def test_a_refused_layout_names_its_first_problem_and_an_odd_code_reads_as_other() -> None:
    routed = MessageDisposition(
        message_id="M41",
        kind=DispositionKind.ROUTED_TO_SALES,
        reason=RoutingReason.ATTACHMENT_UNREADABLE,
        owner=SALES_PIC_POOL,
        layout_prefill=LayoutPrefill(
            prompt="sales.layout_proposal@1.0.0",
            model_profile=_PROFILE,
            route="structured_extraction",
            rules="sales_order_rules@1.6.0",
            outcome="refused",
            attachment_id="M41-A1",
            problems=("Not A Code",),
        ),
    )

    (row,) = _rows(routed, None)

    assert (row.step, row.result, row.reason_code, row.lane) == (
        ModelStep.LAYOUT_PROPOSAL,
        "refused",
        OTHER_REASON,
        CaseKind.ORDER,
    )


@pytest.mark.parametrize(
    "change",
    [
        {"automatic": True, "reason_code": "text_uncovered"},
        {"automatic": True, "result": "refused", "reason_code": "x"},
        {"automatic": False, "result": "refused", "reason_code": None},
        {"automatic": False, "result": "unavailable", "reason_code": "x"},
        {"calls": 1, "duration_ms": None},
        {"refusals": {"Price!": 1}},
        {"refusals": {"price_unparsed": 0}},
        {"lane": None},
    ],
)
def test_a_row_that_does_not_say_what_happened_is_refused(change: dict[str, Any]) -> None:
    good = {
        "outcome_id": uuid.UUID(int=1),
        "occurred_at": AT,
        "message_id": "M01",
        "lane": "order",
        "case_id": uuid.UUID(int=2),
        "line_no": 1,
        "step": "description_attributes",
        "result": "accepted",
        "automatic": True,
        "reason_code": None,
        "refusals": {},
        "prompt": _DESCRIPTION,
        "model_profile": _PROFILE,
        "model": _MODEL,
        "calls": 0,
        "duration_ms": None,
    }
    StepOutcome.model_validate(good)
    with pytest.raises(ValidationError):
        StepOutcome.model_validate(good | change)


# -------------------------------------------------------------- the math --


def _row(
    step: ModelStep,
    *,
    automatic: bool = True,
    result: str = "accepted",
    reason: str | None = None,
    ms: int | None = None,
    at: datetime = AT,
    refusals: dict[str, int] | None = None,
    lane: CaseKind | None = CaseKind.ORDER,
    case_id: uuid.UUID | None = None,
    message_id: str = "M01",
) -> StepOutcome:
    return StepOutcome(
        outcome_id=uuid.uuid4(),
        occurred_at=at,
        message_id=message_id,
        lane=lane,
        case_id=case_id,
        line_no=None,
        step=step,
        result=result,
        automatic=automatic,
        reason_code=reason,
        refusals=refusals or {},
        prompt="sales.message_intent@1.0.0",
        model_profile=_PROFILE,
        model=_MODEL,
        calls=0 if ms is None else 1,
        duration_ms=ms,
    )


def test_percentiles_are_nearest_rank_and_none_for_nothing() -> None:
    assert percentile([], 0.5) is None
    assert percentile([7], 0.95) == 7
    values = list(range(1, 101))
    assert (percentile(values, 0.5), percentile(values, 0.95)) == (50, 95)
    assert percentile([30, 10, 20, 40], 0.5) == 20


def test_a_steps_tally_is_its_share_its_reasons_and_its_times() -> None:
    step = ModelStep.DESCRIPTION_ATTRIBUTES
    rows = [
        _row(step, ms=100),
        _row(step),
        _row(step, automatic=False, result="refused", reason="text_uncovered", ms=300),
        _row(step, automatic=False, result="refused", reason="text_uncovered"),
        _row(step, automatic=False, result="unavailable", ms=30_000),
        _row(ModelStep.RFQ_EXTRACTION, refusals={"price_unparsed": 2}),
    ]

    tallies = tally(rows)

    t = tallies[step]
    assert (t.handled, t.automatic, t.to_person, t.unavailable) == (5, 2, 3, 1)
    assert t.automatic_share == pytest.approx(0.4)
    assert t.reasons == {"text_uncovered": 2}
    assert sorted(t.durations) == [100, 300, 30_000]
    assert tallies[ModelStep.RFQ_EXTRACTION].reasons == {"price_unparsed": 2}
    # Every step is there, one that handled nothing with no share.
    assert set(tallies) == set(ModelStep)
    assert tallies[ModelStep.LAYOUT_PROPOSAL].automatic_share is None


def test_the_summary_links_each_count_to_its_filter_and_series_by_local_day() -> None:
    step = ModelStep.MESSAGE_INTENT
    start, end = date(2026, 10, 20), date(2026, 10, 22)
    # 23:30 UTC on the 20th is the 21st in Hà Nội.
    late = datetime(2026, 10, 20, 23, 30, tzinfo=UTC)
    rows = [
        _row(step, at=late, ms=200),
        _row(step, at=late, automatic=False, result="unavailable", ms=900),
        _row(step, at=datetime(2026, 10, 22, 1, 0, tzinfo=UTC), ms=100),
    ]

    view = activity_summary(rows, start=start, end=end, lane=CaseKind.ORDER, as_of=AT)
    body = view.model_dump(mode="json", by_alias=True)

    (summary,) = [s for s in body["steps"] if s["step"] == step.value]
    assert summary["handled"]["count"] == 3
    assert summary["automatic"] == {
        "count": 2,
        "filter": {
            "step": "message_intent",
            "handled_by": "dw1",
            "result": None,
            "reason_code": None,
            "lane": "order",
            "from": "2026-10-20",
            "to": "2026-10-22",
        },
    }
    assert summary["model_unavailable"]["count"] == 1
    assert summary["model_unavailable"]["filter"]["result"] == "unavailable"
    assert summary["automatic_share"] == pytest.approx(2 / 3)
    assert summary["latency"] == {"p50_ms": 200, "p95_ms": 900, "samples": 3}
    assert summary["process_steps"] == [s.value for s in PROCESS_STEPS[step]]
    assert (body["from"], body["to"]) == ("2026-10-20", "2026-10-22")
    per_day = {
        d["day"]: next(s for s in d["steps"] if s["step"] == step.value) for d in body["days"]
    }
    assert {day: s["handled"] for day, s in per_day.items()} == {
        "2026-10-20": 0,
        "2026-10-21": 2,
        "2026-10-22": 1,
    }
    assert per_day["2026-10-21"]["to_person"] == 1


def test_the_top_reasons_are_the_most_frequent_first_each_with_its_filter() -> None:
    step = ModelStep.DESCRIPTION_ATTRIBUTES
    rows = [
        *(_row(step, automatic=False, result="refused", reason="text_uncovered") for _ in range(3)),
        *(_row(step, automatic=False, result="refused", reason="span_not_found") for _ in range(2)),
        *(_row(step, automatic=False, result="refused", reason=f"r{c}_x") for c in "abcdef"),
    ]

    view = activity_summary(rows, start=AT.date(), end=AT.date(), lane=None, as_of=AT).model_dump(
        mode="json", by_alias=True
    )

    (summary,) = [s for s in view["steps"] if s["step"] == step.value]
    reasons = summary["top_reasons"]
    assert [(r["reason_code"], r["count"]) for r in reasons][:2] == [
        ("text_uncovered", 3),
        ("span_not_found", 2),
    ]
    assert len(reasons) == 5
    assert reasons[0]["filter"]["reason_code"] == "text_uncovered"


def test_every_model_step_takes_part_in_a_surveyed_step() -> None:
    """Read from where the process page places its switches: a step with no
    place would show its share beside nothing."""
    assert all(PROCESS_STEPS[step] for step in ModelStep)
    assert StepId.Q1 in PROCESS_STEPS[ModelStep.RFQ_EXTRACTION]


# ----------------------------------------------------- the case activity --


async def test_a_price_is_absent_for_a_caller_without_the_price_scope() -> None:
    """Not masked: neither the value nor its field nor its anchor is in the
    JSON, so a screen that forgot to hide it has nothing to show."""
    case = await _quote()
    rows = _rows(_created(case), case, [_call(_RFQ, 800)])

    hidden = case_activity(case, rows, (), {}, NONE).model_dump(mode="json")
    shown = case_activity(case, rows, (), {}, OWN).model_dump(mode="json")

    text = json.dumps(hidden)
    assert "stated_target_price" not in text
    assert "target_price" not in text
    assert "0.9537" not in text
    (rfq,) = [e for e in shown["entries"] if e["step"] == "rfq_extraction"]
    prices = [p for p in rfq["produced"] if p["field"] == "stated_target_price"]
    assert prices and all(p["value"] == "0.9537" for p in prices)
    assert prices[0]["anchor"] == {"line_no": prices[0]["line_no"], "field": "stated_target_price"}
    # What is not a price is shown to both.
    (rfq_hidden,) = [e for e in hidden["entries"] if e["step"] == "rfq_extraction"]
    assert {p["field"] for p in rfq_hidden["produced"]} == {"quantity"}
    assert rfq_hidden["refusals"] == {"price_unparsed": 1}


async def test_an_entry_says_what_ran_how_long_on_which_model_and_what_it_produced() -> None:
    case = _read_lines(await _order())
    rows = _rows(_created(case, reading=_intent()), case, [_call(_DESCRIPTION, 640)])
    taken = case.lines[1].line_no
    events = [
        LoggedEvent(
            case_kind=CaseKind.ORDER,
            case_id=case.case_id,
            case_version=2,
            action="order.mapping_confirmed",
            from_status="in_review",
            to_status="in_review",
            actor_kind="user",
            occurred_at=AT + timedelta(minutes=5),
            actor_id=str(PERSON),
        )
    ]
    dispositions = {case.message_id: _created(case, reading=_intent())}

    view = case_activity(case, rows, events, dispositions, NONE).model_dump(mode="json")

    by_line = {(e["step"], e["line_no"]): e for e in view["entries"]}
    intent = by_line[("message_intent", None)]
    assert intent["kind"] == "route"
    assert {p["field"]: p["value"] for p in intent["produced"]} == {"kind": "po", "language": "vi"}
    read = by_line[("description_attributes", case.lines[0].line_no)]
    assert (read["kind"], read["check"], read["handled_by"]) == (
        "read",
        {"result": "passed", "reason_code": None},
        "dw1",
    )
    assert (read["model"], read["prompt"], read["calls"], read["duration_ms"]) == (
        _MODEL,
        _DESCRIPTION,
        1,
        640,
    )
    assert read["produced"] == [
        {
            "field": "cores",
            "value": "4",
            "line_no": case.lines[0].line_no,
            "anchor": {"line_no": case.lines[0].line_no, "field": "description"},
        }
    ]
    refused = by_line[("description_attributes", taken)]
    assert refused["kind"] == "check"
    assert refused["check"] == {"result": "refused", "reason_code": "text_uncovered"}
    assert (refused["handled_by"], refused["taken_over_by"]) == ("person", str(PERSON))
    # The step's time is the message's, shown on each of its entries.
    assert refused["duration_ms"] == 640
    unanswered = by_line[("description_attributes", case.lines[2].line_no)]
    assert unanswered["kind"] == "model_unavailable"
    assert unanswered["check"]["result"] == "not_run"


# ---------------------------------------------------------------- service --


class _Authz:
    def __init__(self, *scopes: str) -> None:
        self.scopes = set(scopes)

    async def require(
        self,
        *,
        context: AccessContext,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
    ) -> None:
        if action not in self.scopes:
            raise PermissionDeniedError("missing scope", details={"action": action})

    def is_allowed(self, context: AccessContext, action: str) -> bool:
        return action in self.scopes


class _Store:
    def __init__(self, cases: dict[uuid.UUID, Any]) -> None:
        self.cases = cases

    async def get(self, case_id: uuid.UUID) -> Stored[Any] | None:
        case = self.cases.get(case_id)
        return None if case is None else Stored(case, CaseOrigin(None, None))


class _Overview:
    async def history(self, kind: CaseKind, case_id: uuid.UUID) -> Sequence[LoggedEvent]:
        return ()


class _Messages:
    async def get(self, message_id: str) -> MessageDisposition | None:
        return None


class _Work:
    """The members `ActivityService` reads, for the scope it was opened on."""

    def __init__(self, cases: dict[uuid.UUID, Any]) -> None:
        self.orders = _Store({k: v for k, v in cases.items() if isinstance(v, OrderCase)})
        self.quotes = _Store({k: v for k, v in cases.items() if isinstance(v, QuoteCase)})
        self.overview = _Overview()
        self.messages = _Messages()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None


class _Uow:
    def __init__(self, cases_by_scope: dict[SalesScope, dict[uuid.UUID, Any]]) -> None:
        self.cases_by_scope = cases_by_scope

    def __call__(self, scope: SalesScope) -> SalesUnitOfWork:
        return cast(SalesUnitOfWork, _Work(self.cases_by_scope.get(scope, {})))


class _Reader:
    def __init__(self, rows: dict[SalesScope, list[StepOutcome]]) -> None:
        self.rows = rows
        self.asked: list[tuple[Any, ...]] = []

    async def for_case(
        self, scope: SalesScope, kind: CaseKind, case_id: uuid.UUID
    ) -> Sequence[StepOutcome]:
        self.asked.append(("for_case", scope, kind, case_id))
        return [r for r in self.rows.get(scope, []) if r.case_id == case_id and r.lane is kind]

    async def between(
        self, scope: SalesScope, start: datetime, end: datetime, lane: CaseKind | None
    ) -> Sequence[StepOutcome]:
        self.asked.append(("between", scope, start, end, lane))
        return [
            r
            for r in self.rows.get(scope, [])
            if start <= r.occurred_at < end and (lane is None or r.lane is lane)
        ]

    async def cases(self, scope: SalesScope, rows: StepRowFilter) -> frozenset[uuid.UUID]:
        raise NotImplementedError("not exercised by the activity service")


def _context(scope: SalesScope) -> AccessContext:
    return AccessContext(
        tenant_id=scope.tenant_id.value,
        workspace_id=scope.workspace_id.value,
        principal_id=PERSON,
        roles=frozenset(),
        scopes=frozenset(),
        plan_id="professional",
    )


def _service(
    reader: _Reader, cases: dict[SalesScope, dict[uuid.UUID, Any]], *scopes: str
) -> ActivityService:
    return ActivityService(
        cast(SalesUnitOfWorkFactory, _Uow(cases)), Gate(_Authz(*scopes)), reader, FixedClock(AT)
    )


async def test_another_tenants_case_is_not_found_and_none_of_its_rows_is_read() -> None:
    case = _read_lines(await _order())
    rows = list(_rows(_created(case), case))
    reader = _Reader({OTHER_TENANT: rows})
    service = _service(reader, {OTHER_TENANT: {case.case_id: case}}, "sales.case.read")

    with pytest.raises(NotFoundError):
        await service.case_activity(_context(SCOPE), CaseKind.ORDER, case.case_id)
    assert reader.asked == []

    # Its own tenant reads it; an order's id asked as a quote is not found.
    found = await service.case_activity(_context(OTHER_TENANT), CaseKind.ORDER, case.case_id)
    assert len(found.entries) == len(rows)
    with pytest.raises(NotFoundError):
        await service.case_activity(_context(OTHER_TENANT), CaseKind.QUOTE, case.case_id)


async def test_a_case_activity_needs_the_case_read_scope() -> None:
    case = await _order()
    service = _service(_Reader({}), {SCOPE: {case.case_id: case}}, "sales.overview.read")

    with pytest.raises(PermissionDeniedError):
        await service.case_activity(_context(SCOPE), CaseKind.ORDER, case.case_id)


async def test_the_price_filter_holds_through_the_service() -> None:
    case = await _quote()
    rows = list(_rows(_created(case), case, [_call(_RFQ, 800)]))
    reader = _Reader({SCOPE: rows})

    without = await _service(
        reader, {SCOPE: {case.case_id: case}}, "sales.case.read"
    ).case_activity(_context(SCOPE), CaseKind.QUOTE, case.case_id)
    with_prices = await _service(
        reader, {SCOPE: {case.case_id: case}}, "sales.case.read", "sales.price.read"
    ).case_activity(_context(SCOPE), CaseKind.QUOTE, case.case_id)

    assert "0.9537" not in without.model_dump_json()
    assert "0.9537" in with_prices.model_dump_json()


@pytest.mark.parametrize(
    ("scopes", "allowed"),
    [
        (("sales.overview.read",), True),
        # The customer's IT, who proposes the versions that turn a step on.
        (("sales.rules.propose",), True),
        (("sales.case.read",), False),
        ((), False),
    ],
)
async def test_the_summary_is_read_with_the_overview_or_the_rules_proposal_scope(
    scopes: tuple[str, ...], allowed: bool
) -> None:
    service = _service(_Reader({}), {}, *scopes)

    if allowed:
        view = await service.summary(_context(SCOPE), start=None, end=None, lane=None)
        assert (view.to, view.from_) == (date(2026, 10, 23), date(2026, 10, 17))
    else:
        with pytest.raises(PermissionDeniedError):
            await service.summary(_context(SCOPE), start=None, end=None, lane=None)


async def test_the_summary_reads_its_own_workspace_over_local_days() -> None:
    mine = _row(ModelStep.MESSAGE_INTENT, at=datetime(2026, 10, 22, 17, 30, tzinfo=UTC))
    theirs = _row(ModelStep.MESSAGE_INTENT, at=AT)
    reader = _Reader({SCOPE: [mine], OTHER_TENANT: [theirs]})
    service = _service(reader, {}, "sales.overview.read")

    view = await service.summary(
        _context(SCOPE), start=date(2026, 10, 23), end=date(2026, 10, 23), lane=CaseKind.ORDER
    )

    (_, scope, start, end, lane) = reader.asked[0]
    assert scope == SCOPE and lane is CaseKind.ORDER
    # Hà Nội's 23 October: 17:00 UTC on the 22nd to 17:00 UTC on the 23rd.
    assert (start, end) == (
        datetime(2026, 10, 22, 17, 0, tzinfo=UTC),
        datetime(2026, 10, 23, 17, 0, tzinfo=UTC),
    )
    (intent,) = [s for s in view.steps if s.step is ModelStep.MESSAGE_INTENT]
    assert intent.handled.count == 1


@pytest.mark.parametrize(
    ("start", "end"),
    [(date(2026, 10, 23), date(2026, 10, 22)), (date(2026, 9, 1), date(2026, 10, 23))],
)
async def test_a_window_backwards_or_longer_than_31_days_is_refused(start: date, end: date) -> None:
    service = _service(_Reader({}), {}, "sales.overview.read")

    with pytest.raises(DomainError):
        await service.summary(_context(SCOPE), start=start, end=end, lane=None)


async def test_the_process_pages_share_is_the_last_7_days_for_every_step() -> None:
    step = ModelStep.DESCRIPTION_ATTRIBUTES
    rows = [
        _row(step, at=AT - timedelta(days=1)),
        _row(step, at=AT - timedelta(days=2), automatic=False, result="unavailable"),
        _row(step, at=AT - timedelta(days=8)),  # outside the week
    ]
    reader = _Reader({SCOPE: rows})

    shares = await automatic_share_last_7_days(reader, SCOPE, now=AT)

    assert reader.asked == [("between", SCOPE, AT - timedelta(days=7), AT, None)]
    assert (shares[step].handled, shares[step].automatic, shares[step].share) == (2, 1, 0.5)
    assert set(shares) == set(ModelStep)
    assert shares[ModelStep.REPLY_INTENT].share is None


# ------------------------------------------------------- the model calls --


def _run() -> RunContext:
    return RunContext(
        run_id=uuid.UUID(int=0x51),
        tenant_id=SCOPE.tenant_id.value,
        workspace_id=SCOPE.workspace_id.value,
        actor_id=PERSON,
        worker_id="sales-dw1",
        worker_version="1.0.0",
        channel="web",
        plan_id="professional",
        roles=frozenset(),
        scopes=frozenset(),
        trace_id="t51",
    )


class _Model:
    def model_for(self, tenant_id: uuid.UUID) -> str:
        return _MODEL


async def test_calls_are_timed_inside_a_message_and_passed_on_outside_one() -> None:
    model = TimedInterpretation(Recorded(raw={"lines": []}), _Model())

    await model.interpret(
        DESCRIPTION_ATTRIBUTES, {}, ModelDescriptionReading, run=_run(), max_output_tokens=10
    )
    assert model_calls() == ()

    with recording_model_calls() as calls:
        await model.interpret(
            DESCRIPTION_ATTRIBUTES, {}, ModelDescriptionReading, run=_run(), max_output_tokens=10
        )
        assert model_calls() == tuple(calls)
    (call,) = calls
    assert (call.prompt, call.model, call.model_profile, call.answered) == (
        _DESCRIPTION,
        _MODEL,
        "onprem",
        True,
    )
    assert call.duration_ms >= 0
    assert model_calls() == ()


async def test_a_call_with_no_usable_answer_is_recorded_and_still_raises() -> None:
    model = TimedInterpretation(Recorded(failure=ModelUnavailableError("down")), _Model())

    with recording_model_calls() as calls:
        with pytest.raises(ModelUnavailableError):
            await model.interpret(
                DESCRIPTION_ATTRIBUTES, {}, ModelDescriptionReading, run=_run(), max_output_tokens=1
            )

    assert [c.answered for c in calls] == [False]


# ------------------------------------------------ where the rows are kept --


async def test_the_memory_unit_of_work_keeps_rows_as_the_table_does() -> None:
    """The evals' world holds the rows (`SalesUnitOfWork.step_activity`): they
    commit or roll back with the transaction, and a row is written once, as
    the table's key refuses a second."""
    store = MemoryStore()
    row = _row(ModelStep.MESSAGE_INTENT, at=WORLD_NOW)
    async with store(ALPHA) as work:
        await work.step_activity.append([row])
    assert await store.between(ALPHA, WORLD_NOW, WORLD_NOW + timedelta(1), None) == []

    async with store(ALPHA) as work:
        await work.step_activity.append([row])
        await work.commit()
    assert await store.for_case(ALPHA, CaseKind.ORDER, uuid.uuid4()) == []
    assert await store.between(ALPHA, WORLD_NOW, WORLD_NOW + timedelta(1), None) == [row]
    assert await store.between(BETA, WORLD_NOW, WORLD_NOW + timedelta(1), None) == []
    async with store(ALPHA) as work:
        with pytest.raises(ConflictError):
            await work.step_activity.append([row])


async def test_a_message_dw1_processes_writes_its_rows_in_its_own_transaction() -> None:
    """The write path has no "keeps none" branch: the world's inbox writes the
    rows of the steps that ran, here the intent and the hand-off of M31."""
    intent = Recorded(raw={"language": "vi", "referenced_number_spans": [], "kind": "complaint"})
    handoff = Recorded(
        raw={
            "po_no_span": "VLX-PO-2608-0102",
            "lot_no_span": "LOT-2609-118",
            "problem_quote_spans": ["có 2 cuộn bị móp lõi cuộn, dây bên trong bị trầy vỏ"],
        }
    )
    model = ByPrompt({"sales.message_intent": intent, "sales.request_handoff": handoff})
    world = open_world(REPO, SampleSet.of(REPO, None), CALLERS, model=model)

    await world.process_each(AN, ["M31"])

    rows = await world.store.between(
        ALPHA, WORLD_NOW - timedelta(1), WORLD_NOW + timedelta(1), None
    )
    assert sorted((r.message_id, r.step.value) for r in rows) == [
        ("M31", ModelStep.MESSAGE_INTENT.value),
        ("M31", ModelStep.REQUEST_HANDOFF.value),
    ]


# ------------------------------------------------- the case lists' filter --


def test_a_case_list_takes_exactly_the_parameters_a_count_links_to() -> None:
    """A count's `ActivityFilter`, serialised, is what the case list routes
    read: a field added to one and not the other fails here."""
    from fastapi.dependencies.utils import get_dependant

    from dw_sales.presentation.routes import case_list_activity

    linked = ActivityFilter(
        step=ModelStep.MESSAGE_INTENT, from_=date(2026, 10, 1), to=date(2026, 10, 5)
    )
    read = get_dependant(path="/", call=case_list_activity).query_params
    assert {p.alias for p in read} == set(linked.model_dump(by_alias=True))


def _world_cases() -> Any:
    return open_world(REPO, SampleSet.of(REPO, None), CALLERS)


async def test_a_case_list_keeps_the_cases_a_matching_row_names() -> None:
    world = _world_cases()
    seen = await world.process_each(AN, ["M01", "M04", "M10"])
    first, second, quote = (seen[m][1].case_id for m in ("M01", "M04", "M10"))
    step = ModelStep.DESCRIPTION_ATTRIBUTES
    today = WORLD_NOW.date()
    world.store.state(ALPHA).step_outcomes.extend(
        [
            _row(
                step,
                automatic=False,
                result="refused",
                reason="text_uncovered",
                at=WORLD_NOW,
                case_id=first,
            ),
            _row(step, at=WORLD_NOW, case_id=second, refusals={"span_not_found": 1}),
            # Before the window: not this list's.
            _row(
                step,
                automatic=False,
                result="unavailable",
                at=WORLD_NOW - timedelta(days=2),
                case_id=second,
            ),
            _row(ModelStep.RFQ_EXTRACTION, at=WORLD_NOW, lane=CaseKind.QUOTE, case_id=quote),
        ]
    )

    async def orders(**asked: Any) -> set[uuid.UUID]:
        activity = CaseListActivity(step=step, start=today, end=today, **asked)
        return {o.case_id for o in await world.services.orders.summaries(AN.context(), activity)}

    assert await orders() == {first, second}
    assert await orders(handled_by="person") == {first}
    assert await orders(handled_by="dw1") == {second}
    assert await orders(result="unavailable") == set()
    # A reason counts as the summary counts it: an item's own, or a value
    # refused inside one code took.
    assert await orders(reason_code="text_uncovered") == {first}
    assert await orders(reason_code="span_not_found") == {second}
    assert await orders(lane=CaseKind.ORDER) == {first, second}
    quotes = await world.services.quotes.summaries(
        AN.context(),
        CaseListActivity(step=ModelStep.RFQ_EXTRACTION, start=today, end=today),
    )
    assert [q.case_id for q in quotes] == [quote]
    # No filter: the whole list.
    assert len(await world.services.orders.summaries(AN.context())) == 2


@pytest.mark.parametrize(
    "asked",
    [
        CaseListActivity(handled_by="dw1"),
        CaseListActivity(step=ModelStep.MESSAGE_INTENT, start=date(2026, 10, 5)),
        CaseListActivity(
            step=ModelStep.MESSAGE_INTENT,
            lane=CaseKind.QUOTE,
            start=date(2026, 10, 5),
            end=date(2026, 10, 5),
        ),
        CaseListActivity(
            step=ModelStep.MESSAGE_INTENT, start=date(2026, 9, 1), end=date(2026, 10, 5)
        ),
    ],
    ids=["no_step", "no_end", "other_lane", "over_31_days"],
)
async def test_a_case_list_filter_that_names_too_little_is_refused(
    asked: CaseListActivity,
) -> None:
    """An unnamed part of a filter is not read as "any": a list narrowed by
    half a filter would read as the count it was linked from."""
    world = _world_cases()
    with pytest.raises(DomainError):
        await world.services.orders.summaries(AN.context(), asked)


async def test_a_case_list_filter_is_read_after_the_scope() -> None:
    """A caller who may not read cases is refused before the filter is
    checked or a row is read."""
    world = _world_cases()
    outsider = Caller(uuid.UUID(int=0x99), "Không Sales", "x@alpha.local", frozenset())
    with pytest.raises(PermissionDeniedError):
        await world.services.orders.summaries(
            outsider.context(), CaseListActivity(handled_by="dw1")
        )
