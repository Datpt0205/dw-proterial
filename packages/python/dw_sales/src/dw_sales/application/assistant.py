"""Status questions answered from live data (dw_sales ADR 0007), in one
conversation per case and one general conversation per person (ticket 46).

A **case conversation** (`/sales/assistant/cases/{kind}/{case_id}/...`) is
bound by code to the case the route names, checked on every use against what
the caller may read (the case list's own gate and record visibility): a case
they may not read is not found, and so is another person's conversation on
it. Its answers rest on that case alone; a question about another case or
about the person's work is pointed to the general conversation, never
answered from what it asks for. The **general conversation**
(`/sales/assistant/ask`) answers the person's work and offers a case it names
as a link to that case's conversation, resolved among the cases the caller
may read, never with the case's own data. No conversation is found by an id a
client sends.

Per turn:

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
   sentence. Facts never hold an amount. As it streams, each word is held
   to that same check before it leaves (`dw_agent_runtime.model.streaming`).
4. **The turn is kept** in the caller's own conversation (RLS by tenant,
   workspace and user; `sales.prune_assistant_sessions()` after 30 days),
   which is opened with its first turn. Once the answer has reached the
   person, the conversation is marked seen; one kept and never delivered is
   the unread mark the case lists show.

The general conversation's focus, the case it last linked, is structured
state: the kind and id code resolved, re-checked against what the caller may
see on every turn. A case conversation's focus is its case.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator, Callable, Sequence
from contextlib import AbstractAsyncContextManager, aclosing
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Final, Literal, Protocol
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from dw_agent_runtime.context import caller_run
from dw_agent_runtime.model.figure_check import names_amount, unsupported
from dw_agent_runtime.model.interpretation import (
    InterpretationPort,
    ModelUnavailableError,
    PromptRef,
    StreamingInterpretationPort,
)
from dw_agent_runtime.model.streaming import (
    ChatDelta,
    ChatDone,
    ChatEvent,
    ChatReplace,
    ChatStep,
    WordingRefusedError,
    released,
)
from dw_kernel.errors import NotFoundError, QuotaExceededError
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.assistant_copy import AssistantCopyPort, AssistantWords
from dw_sales.application.local_time import local_day
from dw_sales.application.orders_service import OrderQueries
from dw_sales.application.overview_service import OverviewService, WorkItem
from dw_sales.application.quotes_service import QuoteQueries
from dw_sales.application.views import OrderSummaryView, QuoteSummaryView
from dw_sales.domain.assistant import (
    ACTION,
    HISTORY_TURNS,
    OFFERS,
    ORDER_STATE,
    QUOTE_STATE,
    CaseKey,
    CaseOffer,
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
from dw_sales.domain.process import DW_NAMES

# The prompts. Their files are `configs/prompts/sales/question_intent@1.1.0.yaml`
# and `assistant_answer@1.0.0.yaml`; a test holds each to its file and its
# rendered size under `*_TOKENS`.
# 1.1.0 (ticket 46): the three steps of a case a person may ask for.
QUESTION_INTENT: Final = PromptRef("sales.question_intent", "1.1.0")
ASSISTANT_ANSWER: Final = PromptRef("sales.assistant_answer", "1.0.0")
INTENT_TOKENS: Final = 1100
ANSWER_TOKENS: Final = 900
_INTENT_OUTPUT: Final = 200
_ANSWER_OUTPUT: Final = 500
# The work an answer lists; the rest are counted.
_LISTED: Final = 10
_WORK_PAGE: Final = 50
_TITLE_CHARS: Final = 80
# The assistant page lists at most this many case conversations (ticket 46).
RECENT_CASES: Final = 10
# The unread marks one read returns; a person's conversations are pruned
# after 30 days, so this is a ceiling, not a page.
_UNREAD: Final = 200
_RESOURCE: Final = "sales_assistant"

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class ModelAnswer(BaseModel):
    """What the wording call writes: the answer, nothing else."""

    model_config = _FROZEN

    answer: str = Field(min_length=1, max_length=1500)


# --------------------------------------------------------------- store --


class AssistantStorePort(Protocol):
    """The caller's own conversations: the adapter binds tenant, workspace and
    user, so another person's conversation is not found."""

    async def conversation(self, case_id: uuid.UUID | None) -> Session | None:
        """The caller's conversation on ``case_id``; None: their general one."""
        ...

    async def recent(self, limit: int) -> Sequence[Session]:
        """The caller's case conversations, the most recently talked about first."""
        ...

    async def unread(self, limit: int) -> Sequence[Session]:
        """The caller's case conversations with an answer kept after they
        last saw it."""
        ...

    async def turns(self, session_id: uuid.UUID) -> Sequence[Turn]:
        """A conversation's turns, oldest first."""
        ...

    async def open(self, session: Session) -> None: ...

    async def add(self, turn: Turn) -> None:
        """Keep ``turn`` and move its conversation's last use to its time."""
        ...

    async def seen(self, session_id: uuid.UUID, at: datetime) -> None:
        """The person has seen the conversation as of ``at``."""
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
    # In a case's conversation, the case page's own control for the step
    # asked (ticket 46); the page draws it where it has one.
    offer: CaseOffer | None = None


class ConversationView(BaseModel):
    """A conversation as its person sees it; before its first turn, empty."""

    model_config = ConfigDict(frozen=True)

    # The case it is bound to, as the case's page calls it; None: the
    # person's general conversation.
    case: CaseRefView | None
    turns: list[TurnView]


class CaseConversationView(BaseModel):
    """A case talked about, on the assistant page's short list."""

    model_config = ConfigDict(frozen=True)

    case: CaseRefView
    last_turn_at: str
    unread: bool


class AnswerView(BaseModel):
    model_config = ConfigDict(frozen=True)

    turn: TurnView


def _ref_view(ref: CaseRef) -> CaseRefView:
    return CaseRefView(kind=ref.kind.value, case_id=ref.case_id, label=ref.label)


def _turn_view(turn: Turn, *, on_case: bool) -> TurnView:
    return TurnView(
        seq=turn.seq,
        asked_at=turn.asked_at.isoformat(),
        question=turn.question,
        kind=turn.kind,
        answer=turn.answer,
        cites=[_ref_view(c) for c in turn.cites],
        answered_by=turn.answered_by,
        offer=OFFERS.get(turn.kind) if on_case else None,
    )


def _conversation_view(case: CaseRef | None, turns: Sequence[Turn]) -> ConversationView:
    return ConversationView(
        case=_ref_view(case) if case else None,
        turns=[_turn_view(t, on_case=case is not None) for t in turns],
    )


# --------------------------------------------------------------- facts --


@dataclass(frozen=True, slots=True)
class _Worded:
    """The text a turn keeps, and who wrote it."""

    text: str
    by: Literal["model", "code"]


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


def order_facts(order: OrderSummaryView, zone: ZoneInfo) -> dict[str, Any]:
    return {
        "question_kind": "order_status",
        "po_no": order.po_no,
        "revision": order.revision,
        "customer_code": order.customer_code,
        "status": label(ORDER_STATE, order.status),
        "received_on": day(local_day(order.received_at, zone)),
        "open_flags": order.open_findings,
        "blocking_flags": order.open_blocking_findings,
        "awaits_cross_check": order.awaits_cross_check,
    }


def order_sentence(facts: dict[str, Any], words: AssistantWords) -> str:
    parts = [
        words.say(
            "order_status",
            po_no=facts["po_no"],
            revision=facts["revision"],
            customer=facts["customer_code"],
            status=facts["status"],
            received_on=facts["received_on"],
        )
    ]
    if facts["open_flags"]:
        parts.append(
            words.say(
                "order_flags",
                open_flags=facts["open_flags"],
                blocking_flags=facts["blocking_flags"],
            )
        )
    if facts["awaits_cross_check"]:
        parts.append(words.order_cross_check)
    return " ".join(parts)


def quote_facts(quote: QuoteSummaryView, zone: ZoneInfo) -> dict[str, Any]:
    return {
        "question_kind": "quote_status",
        "request_no": quote.rfq_no,
        "customer_code": quote.customer_code,
        "status": label(QUOTE_STATE, quote.status),
        "received_on": day(local_day(quote.received_at, zone)),
        "quote_due": day(quote.quote_due) if quote.quote_due else None,
        "overdue": quote.overdue,
        "ycbg_no": quote.ycbg_no,
        "open_flags": quote.open_findings,
    }


def quote_sentence(facts: dict[str, Any], words: AssistantWords) -> str:
    parts = [
        words.say(
            "quote_status",
            request_no=facts["request_no"] or words.no_number,
            customer=facts["customer_code"],
            status=facts["status"],
            received_on=facts["received_on"],
        )
    ]
    if facts["quote_due"]:
        late = "quote_late" if facts["overdue"] else "quote_due"
        parts.append(words.say(late, due=facts["quote_due"]))
    if facts["ycbg_no"]:
        parts.append(words.say("quote_ycbg", ycbg_no=facts["ycbg_no"]))
    if facts["open_flags"]:
        parts.append(words.say("quote_flags", open_flags=facts["open_flags"]))
    return " ".join(parts)


def work_sentence(facts: dict[str, Any], words: AssistantWords) -> str:
    overdue = facts["question_kind"] == "overdue"
    if not facts["count"]:
        return words.no_overdue if overdue else words.no_work
    head = words.say("overdue_head" if overdue else "work_head", count=facts["count"])
    lines = [
        words.say(
            "work_item_due" if item["due"] else "work_item",
            what=item["what"],
            customer=item["customer_code"] or words.unknown_customer,
            next_step=item["next_step"],
            due=item["due"],
        )
        for item in facts["items"]
    ]
    if facts["more"]:
        lines.append(words.say("work_more", more=facts["more"]))
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
    # The tenant's words for code's own sentences (ticket 42 family 6).
    copy: AssistantCopyPort

    async def conversation(
        self, context: AccessContext, case: CaseKey | None = None
    ) -> ConversationView:
        """The caller's conversation on ``case`` (their general one for None);
        empty before its first turn, nothing to create. Reading a case's
        conversation is seeing it: its unread mark goes."""
        await self.gate.require(context, SalesScopes.CASE_READ, resource_type=_RESOURCE)
        bound = await self._bound(context, case) if case is not None else None
        ref = bound.ref if bound is not None else None
        async with self.store(context) as store:
            session = _held(await store.conversation(ref.case_id if ref else None), context, ref)
            if session is None:
                return _conversation_view(ref, ())
            turns = await store.turns(session.session_id)
            if ref is not None and session.unread:
                await store.seen(session.session_id, self.clock.now())
        return _conversation_view(ref, turns)

    async def recent(self, context: AccessContext) -> list[CaseConversationView]:
        """The cases the caller talked about most recently, at most
        `RECENT_CASES`, each still among the cases they may read and named
        as its page names it now."""
        await self.gate.require(context, SalesScopes.CASE_READ, resource_type=_RESOURCE)
        async with self.store(context) as store:
            sessions = await store.recent(RECENT_CASES)
        kinds = {s.case.kind for s in sessions if s.case is not None}
        readable = await self._readable(context, kinds)
        return [
            CaseConversationView(
                case=_ref_view(readable[s.case.case_id]),
                last_turn_at=s.last_turn_at.isoformat(),
                unread=s.unread,
            )
            for s in sessions
            if s.case is not None and s.case.case_id in readable
        ]

    async def unread(self, context: AccessContext) -> list[uuid.UUID]:
        """The cases whose conversation holds an answer the caller has not
        seen: one read of their own conversations, for the marks on the case
        lists, which already hold only cases the caller may read."""
        await self.gate.require(context, SalesScopes.CASE_READ, resource_type=_RESOURCE)
        async with self.store(context) as store:
            sessions = await store.unread(_UNREAD)
        return [s.case.case_id for s in sessions if s.case is not None]

    async def ask(
        self, context: AccessContext, question: str, case: CaseKey | None = None
    ) -> AnswerView:
        """`stream`'s turn, whole: one path, so neither can drift from the
        other. Read to its end: the answer returned is the answer seen."""
        view: AnswerView | None = None
        async with aclosing(self.stream(context, question, case)) as events:
            async for event in events:
                if isinstance(event, ChatDone):
                    view = event.view
        if view is None:
            raise AssertionError("a turn always ends in ChatDone")
        return view

    async def stream(
        self, context: AccessContext, question: str, case: CaseKey | None = None
    ) -> AsyncGenerator[ChatEvent[AnswerView], None]:
        """A turn as it happens. Whatever refuses the caller (the scope, a case
        they may not read) raises before the first event, while the route can
        still answer with a status."""
        await self.gate.require(context, SalesScopes.CASE_READ, resource_type=_RESOURCE)
        words = (await self.copy.assistant_copy(sales_scope(context))).words
        bound = await self._bound(context, case) if case is not None else None
        ref = bound.ref if bound is not None else None
        now = self.clock.now()
        async with self.store(context) as store:
            session = _held(await store.conversation(ref.case_id if ref else None), context, ref)
            earlier: Sequence[Turn] = await store.turns(session.session_id) if session else ()
        opened: Session | None = None
        if session is None:
            # Opened with its first turn, in one transaction.
            session = opened = Session(
                session_id=self.ids.new_uuid(),
                user_id=context.principal_id,
                title=(ref.label if ref else question.strip())[:_TITLE_CHARS],
                created_at=now,
                last_turn_at=now,
                case=ref,
            )
        focus = ref or (earlier[-1].focus if earlier else None)
        yield ChatStep(key="read", title=words.step_read)
        intent = await self._intent(context, question, earlier, focus)
        yield ChatStep(key="look", title=words.step_look)
        if bound is not None:
            found = _in_case(intent, bound, words)
        else:
            found = await self._find(context, intent, focus, words)
        answer: str = found.sentence
        by: Literal["model", "code"] = "code"
        async with aclosing(self._worded(context, question, found)) as wording:
            async for event in wording:
                if isinstance(event, _Worded):
                    answer, by = event.text, event.by
                else:
                    yield event
        turn = Turn(
            session_id=session.session_id,
            seq=len(earlier) + 1,
            asked_at=now,
            question=question,
            kind=intent.kind if intent else QuestionKind.OUT_OF_SCOPE,
            reference=intent.reference if intent else None,
            answer=answer,
            cites=found.cites,
            # A case conversation is always on its case; a general turn about
            # nothing in particular keeps the case it last linked.
            focus=ref or found.focus or focus,
            answered_by=by,
        )
        async with self.store(context) as store:
            if opened is not None:
                await store.open(opened)
            await store.add(turn)
        yield ChatDone(AnswerView(turn=_turn_view(turn, on_case=ref is not None)))
        # Reached only once the answer has been handed on: a person who left
        # before it arrived finds the case marked unread.
        async with self.store(context) as store:
            await store.seen(session.session_id, self.clock.now())

    async def _bound(self, context: AccessContext, case: CaseKey) -> _Bound:
        """The case a conversation is bound to, among the cases the caller may
        read through the case list's own gate and record visibility; not
        found otherwise, the same as a case that never existed."""
        zone = await self.overview.time_zone(sales_scope(context))
        if case.kind is CaseKind.ORDER:
            for order in await self.orders.summaries(context):
                if order.case_id == case.case_id:
                    return _Bound(_order_ref(order), order.po_no, order_facts(order, zone))
        else:
            for quote in await self.quotes.summaries(context):
                if quote.case_id == case.case_id:
                    return _Bound(_quote_ref(quote), quote.rfq_no, quote_facts(quote, zone))
        raise NotFoundError(
            "no such case", details={"kind": case.kind.value, "case_id": str(case.case_id)}
        )

    async def _readable(
        self, context: AccessContext, kinds: set[CaseKind]
    ) -> dict[uuid.UUID, CaseRef]:
        """The cases of ``kinds`` the caller may read, by id, as their pages
        name them."""
        refs: dict[uuid.UUID, CaseRef] = {}
        if CaseKind.ORDER in kinds:
            refs |= {o.case_id: _order_ref(o) for o in await self.orders.summaries(context)}
        if CaseKind.QUOTE in kinds:
            refs |= {q.case_id: _quote_ref(q) for q in await self.quotes.summaries(context)}
        return refs

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
        self,
        context: AccessContext,
        intent: QuestionIntent | None,
        focus: CaseRef | None,
        words: AssistantWords,
    ) -> _Found:
        if intent is None:
            return _Found(f"{words.not_understood} {words.catalog}")
        match intent.kind:
            case QuestionKind.OUT_OF_SCOPE:
                return _Found(f"{words.out_of_scope} {words.catalog}")
            case QuestionKind.ORDER_STATUS:
                return await self._order(context, intent, focus, words)
            case QuestionKind.QUOTE_STATUS:
                return await self._quote(context, intent, focus, words)
            case QuestionKind.MY_WORK | QuestionKind.OVERDUE:
                return await self._work(context, intent.kind, words)
            case (
                QuestionKind.DRAFT_REPLY
                | QuestionKind.REMIND_CUSTOMER
                | QuestionKind.EXPLAIN_THREAD
            ):
                return await self._step(context, intent, focus, words)

    async def _order(
        self,
        context: AccessContext,
        intent: QuestionIntent,
        focus: CaseRef | None,
        words: AssistantWords,
    ) -> _Found:
        """The order a general question names, as a link to its conversation
        (ticket 46): found among the orders the caller may read, answered
        with none of its data."""
        orders = await self.orders.summaries(context)
        if intent.reference is not None:
            matches = [o for o in orders if same_reference(intent.reference, o.po_no)]
        elif intent.about_previous and focus is not None and focus.kind is CaseKind.ORDER:
            matches = [o for o in orders if o.case_id == focus.case_id]
        else:
            return _Found(words.which_order)
        if not matches:
            return _not_found(words, words.order_word, intent.reference)
        # A PO sent twice is two cases; the latest is the one in play.
        return _linked(_order_ref(max(matches, key=lambda o: o.received_at)), words)

    async def _quote(
        self,
        context: AccessContext,
        intent: QuestionIntent,
        focus: CaseRef | None,
        words: AssistantWords,
    ) -> _Found:
        quotes = await self.quotes.summaries(context)
        if intent.reference is not None:
            matches = [q for q in quotes if same_reference(intent.reference, q.rfq_no)]
        elif intent.about_previous and focus is not None and focus.kind is CaseKind.QUOTE:
            matches = [q for q in quotes if q.case_id == focus.case_id]
        else:
            return _Found(words.which_quote)
        if not matches:
            return _not_found(words, words.quote_word, intent.reference)
        return _linked(_quote_ref(max(matches, key=lambda q: q.received_at)), words)

    async def _step(
        self,
        context: AccessContext,
        intent: QuestionIntent,
        focus: CaseRef | None,
        words: AssistantWords,
    ) -> _Found:
        """A step of a case asked in the general conversation (ticket 46): a
        link to the case's own conversation, where its page's buttons are,
        found among the cases the caller may read; nothing is done here."""
        if intent.reference is not None:
            orders = [
                o
                for o in await self.orders.summaries(context)
                if same_reference(intent.reference, o.po_no)
            ]
            if orders:
                return _linked(_order_ref(max(orders, key=lambda o: o.received_at)), words)
            quotes = [
                q
                for q in await self.quotes.summaries(context)
                if same_reference(intent.reference, q.rfq_no)
            ]
            if quotes:
                return _linked(_quote_ref(max(quotes, key=lambda q: q.received_at)), words)
            return _not_found(words, words.case_word, intent.reference)
        if intent.about_previous and focus is not None:
            readable = await self._readable(context, {focus.kind})
            if focus.case_id in readable:
                return _linked(readable[focus.case_id], words)
        return _Found(words.act_in_case)

    async def _work(
        self, context: AccessContext, kind: QuestionKind, words: AssistantWords
    ) -> _Found:
        today = local_day(self.clock.now(), await self.overview.time_zone(sales_scope(context)))
        items = list((await self.overview.my_work(context, limit=_WORK_PAGE)).items)
        if kind is QuestionKind.OVERDUE:
            items = [i for i in items if i.due is not None and i.due < today]
        names = await self._names(context, items)
        listed = items[:_LISTED]
        facts = {
            "question_kind": kind.value,
            "today": day(today),
            "count": len(items),
            "items": [_work_item(i, names, today, words) for i in listed],
            "more": max(len(items) - _LISTED, 0),
        }
        cites = tuple(names[i.id] for i in listed if i.id in names)
        return _Found(work_sentence(facts, words), facts, cites)

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
    ) -> AsyncGenerator[ChatDelta | ChatReplace | _Worded, None]:
        """The model's wording of the facts while code can check it, word by
        word; code's sentence otherwise, in place of any words already shown.
        Ends in the text to keep."""
        if found.facts is None or self.model is None:
            yield ChatDelta(text=found.sentence)
            yield _Worded(found.sentence, "code")
            return
        facts = json.dumps(found.facts, ensure_ascii=False, indent=1)

        def checkable(text: str) -> bool:
            return not unsupported(text, facts, names=DW_NAMES) and not names_amount(text)

        shown = ""
        try:
            words = released(self._wording(context, question, facts), checkable)
            async with aclosing(words) as stream:
                async for word in stream:
                    shown += word
                    yield ChatDelta(text=word)
        except (ModelUnavailableError, QuotaExceededError, WordingRefusedError):
            yield ChatReplace(text=found.sentence) if shown else ChatDelta(text=found.sentence)
            yield _Worded(found.sentence, "code")
            return
        if not shown:
            yield ChatDelta(text=found.sentence)
            yield _Worded(found.sentence, "code")
            return
        yield _Worded(shown, "model")

    async def _wording(
        self, context: AccessContext, question: str, facts: str
    ) -> AsyncGenerator[str, None]:
        """The model's text on the facts, as it writes it where it can."""
        assert self.model is not None
        inputs = {"question": question, "facts": facts}
        run = self._run(context, "sales-assistant-answer")
        if isinstance(self.model, StreamingInterpretationPort):
            pieces = self.model.stream_field(
                ASSISTANT_ANSWER,
                inputs,
                ModelAnswer,
                "answer",
                run=run,
                max_output_tokens=_ANSWER_OUTPUT,
            )
            async with aclosing(pieces) as stream:
                async for piece in stream:
                    yield piece
            return
        answer = await self.model.interpret(
            ASSISTANT_ANSWER, inputs, ModelAnswer, run=run, max_output_tokens=_ANSWER_OUTPUT
        )
        yield answer.answer


@dataclass(frozen=True)
class _Bound:
    """The case a conversation is bound to: what it is called, its number as
    a person would write it, and code's facts about it."""

    ref: CaseRef
    number: str | None
    facts: dict[str, Any]

    def sentence(self, words: AssistantWords) -> str:
        said = order_sentence if self.ref.kind is CaseKind.ORDER else quote_sentence
        return said(self.facts, words)


def _in_case(intent: QuestionIntent | None, bound: _Bound, words: AssistantWords) -> _Found:
    """A case conversation's answer: the bound case's facts, or a pointer
    elsewhere. Nothing here looks another case up, whatever the question
    names, so nothing of another case or customer can reach the answer."""
    if intent is None:
        return _Found(f"{words.not_understood} {words.case_catalog}")
    match intent.kind:
        case QuestionKind.OUT_OF_SCOPE:
            return _Found(f"{words.out_of_scope_case} {words.case_catalog}")
        case QuestionKind.MY_WORK | QuestionKind.OVERDUE:
            return _Found(words.elsewhere)
        case QuestionKind.DRAFT_REPLY | QuestionKind.REMIND_CUSTOMER | QuestionKind.EXPLAIN_THREAD:
            # The page's own control, drawn under this sentence; the
            # chat starts nothing, and no fact is worded.
            said = getattr(words, _OFFER_WORDS[OFFERS[intent.kind]])
            return _Found(said, None, (bound.ref,), bound.ref)
        case QuestionKind.ORDER_STATUS | QuestionKind.QUOTE_STATUS:
            if intent.reference is not None and not same_reference(intent.reference, bound.number):
                only = words.say("only_this_case", case=bound.ref.label)
                return _Found(f"{only} {words.elsewhere}")
            return _Found(bound.sentence(words), bound.facts, (bound.ref,), bound.ref)


# The sentence above each offered control (`AssistantWords`).
_OFFER_WORDS: Final[dict[CaseOffer, str]] = {
    "reply_draft": "offer_reply",
    "customer_reminder": "offer_reminder",
    "thread_summary": "offer_thread",
}


def _held(session: Session | None, context: AccessContext, ref: CaseRef | None) -> Session | None:
    """The store's RLS keeps another person's conversation out; this says so
    again where the service decides, so a policy dropped by mistake still
    shows nobody another person's turns."""
    if session is None:
        return None
    on = session.case.case_id if session.case is not None else None
    if session.user_id != context.principal_id or on != (ref.case_id if ref else None):
        raise NotFoundError("no such conversation")
    return session


def _linked(ref: CaseRef, words: AssistantWords) -> _Found:
    """A case the general conversation names: a link, none of its data."""
    return _Found(words.say("linked", case=ref.label), None, (ref,), ref)


def _not_found(words: AssistantWords, what: str, reference: str | None) -> _Found:
    return _Found(words.say("not_found", what=what, reference=reference))


def _work_item(
    item: WorkItem, names: dict[str, CaseRef], today: date, words: AssistantWords
) -> dict[str, Any]:
    named = names.get(item.id)
    what = named.label if named else (words.mail_work if item.kind == "message" else item.id)
    return {
        "what": what,
        "customer_code": item.customer_code,
        # A routed mail's action names its routing reason (`handle_<reason>`):
        # the work list draws the mail, the answer says what it is.
        "next_step": words.mail_step if item.kind == "message" else label(ACTION, item.action),
        "due": day(item.due) if item.due else None,
        "overdue": item.due is not None and item.due < today,
    }
