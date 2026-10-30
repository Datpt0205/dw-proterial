"""Status questions answered from live data, in sessions (dw_sales ADR 0007).

`POST /sales/assistant/ask` takes a question and, optionally, the session it
continues. Per turn:

1. **The model reads the question** (`sales.question_intent@1.0.0`) into a
   `QuestionIntent`, shown the session's last turns and the case it is on as
   untrusted history. No model, or an answer the schema refuses: "DW1 did not
   understand", with what it can answer. Never a guessed case.
2. **Code answers it** through the query services the portal reads, so the
   assistant finds only what the caller's pages would show: a number that
   matches none of those cases is "not found", a question about "that PO"
   with no case in the conversation asks which.
3. **The model words the answer** (`sales.assistant_answer@1.0.0`) from the
   facts code built; code keeps the wording only when every figure is among
   the facts and it names no amount, and otherwise answers in its own
   sentence. Facts never hold an amount.
4. **The turn is kept** in the caller's own session (RLS by tenant,
   workspace and user; `sales.prune_assistant_sessions()` after 30 days).

The session's focus, the case the conversation is on, is structured state:
the kind and id code resolved, re-checked against what the caller may see on
every turn.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import date
from typing import Any, Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from dw_kernel.errors import NotFoundError, QuotaExceededError
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import Gate, SalesScopes
from dw_sales.application.artifact_content import local_time
from dw_sales.application.figure_check import names_amount, unsupported
from dw_sales.application.model_reading import InterpretationPort, ModelUnavailableError, PromptRef
from dw_sales.application.orders_service import OrderQueries
from dw_sales.application.overview_service import OverviewService, WorkItem
from dw_sales.application.quotes_service import QuoteQueries
from dw_sales.application.runs import caller_run
from dw_sales.application.views import OrderSummaryView, QuoteSummaryView
from dw_sales.domain.assistant import (
    ACTION,
    CATALOG,
    HISTORY_TURNS,
    ORDER_STATE,
    QUOTE_STATE,
    CaseRef,
    QuestionIntent,
    QuestionKind,
    Session,
    Turn,
    day,
    label,
    same_reference,
)
from dw_sales.domain.dispositions import CaseKind

# The prompts. Their files are `configs/prompts/sales/question_intent@1.0.0.yaml`
# and `assistant_answer@1.0.0.yaml`; a test holds each to its file and its
# rendered size under `*_TOKENS`.
QUESTION_INTENT: Final = PromptRef("sales.question_intent", "1.0.0")
ASSISTANT_ANSWER: Final = PromptRef("sales.assistant_answer", "1.0.0")
INTENT_TOKENS: Final = 1100
ANSWER_TOKENS: Final = 900
_INTENT_OUTPUT: Final = 200
_ANSWER_OUTPUT: Final = 500
# The work an answer lists; the rest are counted.
_LISTED: Final = 10
_WORK_PAGE: Final = 50
_TITLE_CHARS: Final = 80
_RESOURCE: Final = "sales_assistant"

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class ModelAnswer(BaseModel):
    """What the wording call writes: the answer, nothing else."""

    model_config = _FROZEN

    answer: str = Field(min_length=1, max_length=1500)


# --------------------------------------------------------------- store --


class AssistantStorePort(Protocol):
    """The caller's own sessions: the adapter binds tenant, workspace and
    user, so another person's session is not found."""

    async def session(self, session_id: uuid.UUID) -> Session | None: ...

    async def sessions(self, limit: int) -> Sequence[Session]:
        """The caller's sessions, the most recently used first."""
        ...

    async def turns(self, session_id: uuid.UUID) -> Sequence[Turn]:
        """A session's turns, oldest first."""
        ...

    async def open(self, session: Session) -> None: ...

    async def add(self, turn: Turn) -> None:
        """Keep ``turn`` and move its session's last use to its time."""
        ...


AssistantStoreFactory = Callable[[AccessContext], AbstractAsyncContextManager[AssistantStorePort]]


# --------------------------------------------------------------- views --


class CaseRefView(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["order", "quote"]
    case_id: uuid.UUID
    label: str


class TurnView(BaseModel):
    model_config = ConfigDict(frozen=True)

    seq: int
    asked_at: str
    question: str
    kind: QuestionKind
    answer: str
    cites: list[CaseRefView]
    # "model": the model's wording, checked against the facts; "code": DW1's
    # own sentence. Either way the facts are code's.
    answered_by: Literal["model", "code"]


class SessionView(BaseModel):
    model_config = ConfigDict(frozen=True)

    session_id: uuid.UUID
    title: str
    created_at: str
    last_turn_at: str


class SessionDetailView(SessionView):
    turns: list[TurnView]


class AnswerView(BaseModel):
    model_config = ConfigDict(frozen=True)

    session_id: uuid.UUID
    turn: TurnView


def _ref_view(ref: CaseRef) -> CaseRefView:
    return CaseRefView(kind=ref.kind.value, case_id=ref.case_id, label=ref.label)


def _turn_view(turn: Turn) -> TurnView:
    return TurnView(
        seq=turn.seq,
        asked_at=turn.asked_at.isoformat(),
        question=turn.question,
        kind=turn.kind,
        answer=turn.answer,
        cites=[_ref_view(c) for c in turn.cites],
        answered_by=turn.answered_by,
    )


def _session_view(session: Session) -> SessionView:
    return SessionView(
        session_id=session.session_id,
        title=session.title,
        created_at=session.created_at.isoformat(),
        last_turn_at=session.last_turn_at.isoformat(),
    )


# --------------------------------------------------------------- facts --


@dataclass(frozen=True)
class _Found:
    """What code found for a question: facts for the wording call (or None
    when code's sentence is the answer), the sentence, and the cases."""

    sentence: str
    facts: dict[str, Any] | None = None
    cites: tuple[CaseRef, ...] = ()
    focus: CaseRef | None = None


def _order_ref(order: OrderSummaryView) -> CaseRef:
    return CaseRef(CaseKind.ORDER, order.case_id, f"PO {order.po_no}")


def _quote_ref(quote: QuoteSummaryView) -> CaseRef:
    return CaseRef(CaseKind.QUOTE, quote.case_id, f"Yêu cầu báo giá {quote.rfq_no or '(chưa số)'}")


def order_facts(order: OrderSummaryView) -> dict[str, Any]:
    return {
        "question_kind": "order_status",
        "po_no": order.po_no,
        "revision": order.revision,
        "customer_code": order.customer_code,
        "status": label(ORDER_STATE, order.status),
        "received_on": day(local_time(order.received_at).date()),
        "open_flags": order.open_findings,
        "blocking_flags": order.open_blocking_findings,
        "awaits_cross_check": order.awaits_cross_check,
    }


def order_sentence(facts: dict[str, Any]) -> str:
    text = (
        f"PO {facts['po_no']} (rev {facts['revision']}) của khách {facts['customer_code']}: "
        f"{facts['status']}. Nhận ngày {facts['received_on']}."
    )
    if facts["open_flags"]:
        text += f" Còn {facts['open_flags']} cờ đang mở, {facts['blocking_flags']} cờ chặn."
    if facts["awaits_cross_check"]:
        text += " Đang chờ kiểm chéo."
    return text


def quote_facts(quote: QuoteSummaryView) -> dict[str, Any]:
    return {
        "question_kind": "quote_status",
        "request_no": quote.rfq_no,
        "customer_code": quote.customer_code,
        "status": label(QUOTE_STATE, quote.status),
        "received_on": day(local_time(quote.received_at).date()),
        "quote_due": day(quote.quote_due) if quote.quote_due else None,
        "overdue": quote.overdue,
        "ycbg_no": quote.ycbg_no,
        "open_flags": quote.open_findings,
    }


def quote_sentence(facts: dict[str, Any]) -> str:
    text = (
        f"Yêu cầu báo giá {facts['request_no'] or '(chưa số)'} của khách "
        f"{facts['customer_code']}: {facts['status']}. Nhận ngày {facts['received_on']}."
    )
    if facts["quote_due"]:
        late = " (đã quá hạn)" if facts["overdue"] else ""
        text += f" Hạn báo giá {facts['quote_due']}{late}."
    if facts["ycbg_no"]:
        text += f" Số YCBG {facts['ycbg_no']}."
    if facts["open_flags"]:
        text += f" Còn {facts['open_flags']} cờ đang mở."
    return text


def work_sentence(facts: dict[str, Any]) -> str:
    overdue = facts["question_kind"] == "overdue"
    if not facts["count"]:
        return "Bạn không có việc nào quá hạn." if overdue else "Bạn không có việc nào đang chờ."
    head = f"Bạn có {facts['count']} việc {'quá hạn' if overdue else 'đang chờ'}:"
    lines = [
        f"- {item['what']} (khách {item['customer_code'] or 'chưa rõ'}): {item['next_step']}"
        + (f", hạn {item['due']}" if item["due"] else "")
        for item in facts["items"]
    ]
    if facts["more"]:
        lines.append(f"- và {facts['more']} việc khác trong Việc cần làm.")
    return "\n".join([head, *lines])


# ------------------------------------------------------------- service --


@dataclass(frozen=True)
class AssistantService:
    """`/sales/assistant/*` (module docstring)."""

    store: AssistantStoreFactory
    gate: Gate
    orders: OrderQueries
    quotes: QuoteQueries
    overview: OverviewService
    model: InterpretationPort | None
    clock: UtcClock
    ids: IdGenerator
    worker_id: str
    worker_version: str

    async def sessions(self, context: AccessContext, limit: int = 30) -> list[SessionView]:
        await self.gate.require(context, SalesScopes.CASE_READ, resource_type=_RESOURCE)
        async with self.store(context) as store:
            return [_session_view(s) for s in await store.sessions(limit)]

    async def session(self, context: AccessContext, session_id: uuid.UUID) -> SessionDetailView:
        await self.gate.require(
            context, SalesScopes.CASE_READ, resource_type=_RESOURCE, resource_id=str(session_id)
        )
        async with self.store(context) as store:
            session = await self._own(store, context, session_id)
            turns = await store.turns(session_id)
        return SessionDetailView(
            **_session_view(session).model_dump(), turns=[_turn_view(t) for t in turns]
        )

    async def ask(
        self, context: AccessContext, question: str, session_id: uuid.UUID | None = None
    ) -> AnswerView:
        await self.gate.require(context, SalesScopes.CASE_READ, resource_type=_RESOURCE)
        now = self.clock.now()
        opened: Session | None = None
        earlier: Sequence[Turn] = ()
        if session_id is None:
            # Opened with its first turn, in one transaction.
            session = opened = Session(
                session_id=self.ids.new_uuid(),
                user_id=context.principal_id,
                title=question.strip()[:_TITLE_CHARS],
                created_at=now,
                last_turn_at=now,
            )
        else:
            async with self.store(context) as store:
                session = await self._own(store, context, session_id)
                earlier = await store.turns(session_id)
        focus = earlier[-1].focus if earlier else None
        intent = await self._intent(context, question, earlier, focus)
        found = await self._find(context, intent, focus)
        answer, by = await self._worded(context, question, found)
        turn = Turn(
            session_id=session.session_id,
            seq=len(earlier) + 1,
            asked_at=now,
            question=question,
            kind=intent.kind if intent else QuestionKind.OUT_OF_SCOPE,
            reference=intent.reference if intent else None,
            answer=answer,
            cites=found.cites,
            # A turn about nothing in particular keeps the conversation's case.
            focus=found.focus or focus,
            answered_by=by,
        )
        async with self.store(context) as store:
            if opened is not None:
                await store.open(opened)
            await store.add(turn)
        return AnswerView(session_id=session.session_id, turn=_turn_view(turn))

    async def _own(
        self, store: AssistantStorePort, context: AccessContext, session_id: uuid.UUID
    ) -> Session:
        session = await store.session(session_id)
        # The adapter's RLS keeps another person's session out; this says so
        # again where the service decides.
        if session is None or session.user_id != context.principal_id:
            raise NotFoundError("no such session", details={"session_id": str(session_id)})
        return session

    def _run(self, context: AccessContext, trace: str) -> Any:
        return caller_run(
            context,
            run_id=self.ids.new_uuid(),
            worker_id=self.worker_id,
            worker_version=self.worker_version,
            trace=trace,
            subject_ref=_RESOURCE,
        )

    async def _intent(
        self,
        context: AccessContext,
        question: str,
        earlier: Sequence[Turn],
        focus: CaseRef | None,
    ) -> QuestionIntent | None:
        """The question as the model reads it; None when there is no reading."""
        if self.model is None:
            return None
        history = json.dumps(
            {
                "earlier_turns": [
                    {"question": t.question, "kind": t.kind.value, "reference": t.reference}
                    for t in earlier[-HISTORY_TURNS:]
                ],
                "case_in_conversation": focus.label if focus else None,
            },
            ensure_ascii=False,
            indent=1,
        )
        try:
            return await self.model.interpret(
                QUESTION_INTENT,
                {"question": question, "history": history},
                QuestionIntent,
                run=self._run(context, "sales-assistant-intent"),
                max_output_tokens=_INTENT_OUTPUT,
            )
        except (ModelUnavailableError, QuotaExceededError):
            return None

    async def _find(
        self, context: AccessContext, intent: QuestionIntent | None, focus: CaseRef | None
    ) -> _Found:
        if intent is None:
            return _Found(f"DW1 chưa hiểu câu hỏi lúc này. {CATALOG}")
        match intent.kind:
            case QuestionKind.OUT_OF_SCOPE:
                return _Found(f"Câu này ngoài những gì DW1 trả lời. {CATALOG}")
            case QuestionKind.ORDER_STATUS:
                return await self._order(context, intent, focus)
            case QuestionKind.QUOTE_STATUS:
                return await self._quote(context, intent, focus)
            case QuestionKind.MY_WORK | QuestionKind.OVERDUE:
                return await self._work(context, intent.kind)

    async def _order(
        self, context: AccessContext, intent: QuestionIntent, focus: CaseRef | None
    ) -> _Found:
        orders = await self.orders.summaries(context)
        if intent.reference is not None:
            matches = [o for o in orders if same_reference(intent.reference, o.po_no)]
        elif intent.about_previous and focus is not None and focus.kind is CaseKind.ORDER:
            matches = [o for o in orders if o.case_id == focus.case_id]
        else:
            return _Found("Bạn hỏi PO nào? Hãy ghi số PO.")
        if not matches:
            return _not_found("PO", intent.reference)
        # A PO sent twice is two cases; the latest is the one in play.
        order = max(matches, key=lambda o: o.received_at)
        facts = order_facts(order)
        ref = _order_ref(order)
        return _Found(order_sentence(facts), facts, (ref,), ref)

    async def _quote(
        self, context: AccessContext, intent: QuestionIntent, focus: CaseRef | None
    ) -> _Found:
        quotes = await self.quotes.summaries(context)
        if intent.reference is not None:
            matches = [q for q in quotes if same_reference(intent.reference, q.rfq_no)]
        elif intent.about_previous and focus is not None and focus.kind is CaseKind.QUOTE:
            matches = [q for q in quotes if q.case_id == focus.case_id]
        else:
            return _Found("Bạn hỏi yêu cầu báo giá nào? Hãy ghi số yêu cầu.")
        if not matches:
            return _not_found("yêu cầu báo giá", intent.reference)
        quote = max(matches, key=lambda q: q.received_at)
        facts = quote_facts(quote)
        ref = _quote_ref(quote)
        return _Found(quote_sentence(facts), facts, (ref,), ref)

    async def _work(self, context: AccessContext, kind: QuestionKind) -> _Found:
        today = local_time(self.clock.now()).date()
        items = list((await self.overview.my_work(context, limit=_WORK_PAGE)).items)
        if kind is QuestionKind.OVERDUE:
            items = [i for i in items if i.due is not None and i.due < today]
        names = await self._names(context, items)
        listed = items[:_LISTED]
        facts = {
            "question_kind": kind.value,
            "today": day(today),
            "count": len(items),
            "items": [_work_item(i, names, today) for i in listed],
            "more": max(len(items) - _LISTED, 0),
        }
        cites = tuple(names[i.id] for i in listed if i.id in names)
        return _Found(work_sentence(facts), facts, cites)

    async def _names(self, context: AccessContext, items: list[WorkItem]) -> dict[str, CaseRef]:
        """The cases the work names, by id, as their pages call them."""
        wanted = {i.kind for i in items}
        refs: dict[str, CaseRef] = {}
        if "order" in wanted:
            refs |= {str(o.case_id): _order_ref(o) for o in await self.orders.summaries(context)}
        if "quote" in wanted:
            refs |= {str(q.case_id): _quote_ref(q) for q in await self.quotes.summaries(context)}
        return refs

    async def _worded(
        self, context: AccessContext, question: str, found: _Found
    ) -> tuple[str, Literal["model", "code"]]:
        """The model's wording of the facts when code can check it; code's
        sentence otherwise."""
        if found.facts is None or self.model is None:
            return found.sentence, "code"
        facts = json.dumps(found.facts, ensure_ascii=False, indent=1)
        try:
            answer = await self.model.interpret(
                ASSISTANT_ANSWER,
                {"question": question, "facts": facts},
                ModelAnswer,
                run=self._run(context, "sales-assistant-answer"),
                max_output_tokens=_ANSWER_OUTPUT,
            )
        except (ModelUnavailableError, QuotaExceededError):
            return found.sentence, "code"
        if unsupported(answer.answer, facts) or names_amount(answer.answer):
            return found.sentence, "code"
        return answer.answer, "model"


def _not_found(what: str, reference: str | None) -> _Found:
    return _Found(
        f"Không tìm thấy {what} {reference} trong các hồ sơ bạn được xem. "
        "Kiểm tra lại số, hoặc hồ sơ thuộc người khác."
    )


def _work_item(item: WorkItem, names: dict[str, CaseRef], today: date) -> dict[str, Any]:
    named = names.get(item.id)
    what = named.label if named else ("Thư cần xử lý" if item.kind == "message" else item.id)
    return {
        "what": what,
        "customer_code": item.customer_code,
        # A routed mail's action names its routing reason (`handle_<reason>`):
        # the work list draws the mail, the answer says what it is.
        "next_step": "Xử lý thư" if item.kind == "message" else label(ACTION, item.action),
        "due": day(item.due) if item.due else None,
        "overdue": item.due is not None and item.due < today,
    }
