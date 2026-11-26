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
import unicodedata
import uuid
from collections.abc import AsyncGenerator, Callable, Sequence
from contextlib import AbstractAsyncContextManager, aclosing
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
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
from dw_kernel.errors import ConflictError, NotFoundError, QuotaExceededError
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.assignment import AssigneeView
from dw_sales.application.assistant_copy import AssistantCopyPort, AssistantWords
from dw_sales.application.bravo_line_writes import (
    CANCEL_REASON_CHARS,
    AnyChange,
    BravoLineWriteView,
    CancelChange,
    ConfirmedDateChange,
    QuantityChange,
    cancel_reason,
)
from dw_sales.application.chat_prompts import QUESTION_INTENT
from dw_sales.application.local_time import local_day
from dw_sales.application.order_ports import OrderRulesPort
from dw_sales.application.orders_service import OrderQueries
from dw_sales.application.overview_service import OverviewService, WorkItem
from dw_sales.application.quotes_service import QuoteQueries
from dw_sales.application.views import CaseChangeView, OrderSummaryView, QuoteSummaryView
from dw_sales.domain.assistant import (
    ACTION,
    HISTORY_TURNS,
    OFFERS,
    ORDER_STATE,
    QUOTE_STATE,
    CaseKey,
    CaseOffer,
    CaseRef,
    ChatDecision,
    Proposal,
    ProposedAssignment,
    ProposedBravoWrite,
    ProposedDecision,
    QuestionIntent,
    QuestionKind,
    Session,
    Turn,
    WriteField,
    day,
    label,
    same_reference,
)
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.order_checks import ModelStep
from dw_sales.domain.process import DW_NAMES

# The prompts: `QUESTION_INTENT` (`chat_prompts`, the case chat's model step)
# and `assistant_answer@1.0.0.yaml`; a test holds each to its file and its
# rendered size under `*_TOKENS`.
ASSISTANT_ANSWER: Final = PromptRef("sales.assistant_answer", "1.0.0")
# 1600 since question_intent@1.5.0 (ticket 79): 1.4.0 rendered at 1486 of
# 1500, and a kind more cannot be said in 14 tokens. 1700 since 1.6.0
# (ticket 71), which renders at 1648 with a line's cancel and its reason.
# Still far under the step's input room (onprem.yaml, 6000 of an 8192 context).
INTENT_TOKENS: Final = 1700
ANSWER_TOKENS: Final = 900
_INTENT_OUTPUT: Final = 300
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


@dataclass(frozen=True)
class CaseChatStatements:
    """`orders_service.ChatStatementsPort`: what the case chat stated to the
    caller in their own conversation on a case, oldest first (ticket 57).
    The store's RLS keeps another person's conversation out, and `_held`
    says so again."""

    store: AssistantStoreFactory

    async def stated(self, context: AccessContext, case_id: uuid.UUID) -> Sequence[Proposal]:
        async with self.store(context) as store:
            session = await store.conversation(case_id)
            if session is None or session.user_id != context.principal_id:
                return ()
            turns = await store.turns(session.session_id)
        return [t.proposal for t in turns if t.proposal is not None]


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
    # A flag's decision stated for the PIC to confirm (ticket 56): exactly
    # what `POST .../turns/{seq}/confirm` records, bound by ``content_hash``.
    proposal: ProposalView | None = None


class ProposalView(BaseModel):
    """What a turn stated for the PIC to confirm: a flag's decision
    (``action`` decide_finding) or a Bravo write (bravo_write)."""

    model_config = ConfigDict(frozen=True)

    action: Literal["decide_finding", "bravo_write", "assign"] = "decide_finding"
    finding_key: str | None = None
    decision: ChatDecision | None = None
    reason: str | None = None
    line_no: int | None = None
    field: WriteField | None = None
    value: str | None = None
    # `assign` only: the person the case would be given to, by name.
    assignee_name: str | None = None
    case_version: int
    content_hash: str


class ConfirmedView(BaseModel):
    """A confirmed decision: DW1's sentence, and the case's new version."""

    model_config = ConfigDict(frozen=True)

    answer: str
    case_version: int


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
        proposal=_proposal_view(turn.proposal) if on_case and turn.proposal else None,
    )


def _proposal_view(proposal: Proposal) -> ProposalView:
    if isinstance(proposal, ProposedAssignment):
        return ProposalView(
            action="assign",
            assignee_name=proposal.name,
            case_version=proposal.case_version,
            content_hash=proposal.content_hash,
        )
    if isinstance(proposal, ProposedBravoWrite):
        return ProposalView(
            action="bravo_write",
            line_no=proposal.line_no,
            field=proposal.field,
            value=proposal.value,
            case_version=proposal.case_version,
            content_hash=proposal.content_hash,
        )
    return ProposalView(
        finding_key=proposal.finding_key,
        decision=proposal.decision,
        reason=proposal.reason,
        case_version=proposal.case_version,
        content_hash=proposal.content_hash,
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
    proposal: Proposal | None = None


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


class FindingDecisionPort(Protocol):
    """Records one flag's decision as the page's button does (ticket 56): the
    command checks the caller's scope, the case's version and the decision."""

    async def dispose(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        finding_key: str,
        *,
        case_version: int,
        disposition: Literal["open", "accepted", "corrected_by_sales", "ask_customer"],
        reason: str | None = None,
        value: str | None = None,
        source: str | None = None,
    ) -> CaseChangeView: ...


class AssignmentPort(Protocol):
    """`AssignmentService`: who a case may be given to, and giving it."""

    async def candidates(
        self, context: AccessContext, kind: CaseKind, case_id: uuid.UUID
    ) -> Sequence[AssigneeView]: ...

    async def reassign(
        self,
        context: AccessContext,
        kind: CaseKind,
        case_id: uuid.UUID,
        *,
        assignee: uuid.UUID | None,
        case_version: int,
    ) -> CaseChangeView: ...


class BravoWriteProposalPort(Protocol):
    """Proposes an SO line's write into Bravo as ticket 53's own service
    does: it checks the caller's right and record visibility, the case's
    version, and the row Bravo holds, and opens the write's approval."""

    async def propose(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        line_no: int,
        change: AnyChange,
        *,
        case_version: int,
    ) -> BravoLineWriteView: ...


@dataclass(frozen=True, slots=True)
class _Flag:
    """An open flag of the bound case, as the model is shown it."""

    key: str
    code: str
    line_no: int | None
    allowed: frozenset[str]


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
    # Where a confirmed flag decision is recorded (ticket 56); None: the
    # chat states no decision.
    decisions: FindingDecisionPort | None = None
    # Where a confirmed Bravo write is proposed (ticket 56 over 53); None:
    # the chat states no write.
    bravo_writes: BravoWriteProposalPort | None = None
    # The tenant's order rules, whose `model_assist.case_chat` says whether
    # the chat states anything for the PIC to confirm (ticket 57); None:
    # the rules are not read and the chat states nothing.
    rules: OrderRulesPort | None = None
    # Who a case may be given to, and the giving (ticket 79); None: the chat
    # gives no case.
    assignment: AssignmentPort | None = None

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

    async def confirm(
        self, context: AccessContext, case: CaseKey, seq: int, content_hash: str
    ) -> ConfirmedView:
        """Records the decision turn ``seq`` of the caller's own conversation
        on ``case`` stated, when ``content_hash`` is that statement's (ticket
        56). Another person's turn, another case's, or a turn that stated no
        decision is not found; a hash that is not the statement's, or a case
        that moved since, is a conflict. The command itself checks the
        caller's scope and the case's version, as the page's button does."""
        await self.gate.require(context, SalesScopes.CASE_READ, resource_type=_RESOURCE)
        words = (await self.copy.assistant_copy(sales_scope(context))).words
        bound = await self._bound(context, case)
        async with self.store(context) as store:
            session = _held(await store.conversation(bound.ref.case_id), context, bound.ref)
            turns: Sequence[Turn] = await store.turns(session.session_id) if session else ()
        turn = next((t for t in turns if t.seq == seq), None)
        proposal = turn.proposal if turn is not None else None
        if (
            proposal is None
            or proposal.case_id != bound.ref.case_id
            or proposal.case_kind is not bound.ref.kind
        ):
            raise NotFoundError("no such decision", details={"seq": seq})
        if proposal.content_hash != content_hash:
            raise ConflictError("the decision confirmed is not the one stated")
        if proposal.case_version != bound.version:
            raise ConflictError("the case changed since the decision was stated")
        if isinstance(proposal, ProposedBravoWrite):
            return await self._propose_write(context, proposal, words)
        if isinstance(proposal, ProposedAssignment):
            if self.assignment is None:
                raise NotFoundError("no such decision", details={"seq": seq})
            # The service checks the right and the version again, as the
            # page's "Giao lại" does.
            change = await self.assignment.reassign(
                context,
                proposal.case_kind,
                proposal.case_id,
                assignee=proposal.assignee,
                case_version=proposal.case_version,
            )
            answer = words.say("assign_done", case=bound.ref.label, person=proposal.name)
            return ConfirmedView(answer=answer, case_version=change.case_version)
        if self.decisions is None:
            raise NotFoundError("no such decision", details={"seq": seq})
        flag = next((f for f in bound.flags if f.key == proposal.finding_key), None)
        if flag is None:
            raise ConflictError("the flag is no longer open")
        change = await self.decisions.dispose(
            context,
            proposal.case_id,
            proposal.finding_key,
            case_version=proposal.case_version,
            disposition=proposal.decision,
            reason=proposal.reason,
        )
        answer = words.say(
            "decide_done",
            flag=_flag_words(flag),
            decision=_decision_word(proposal.decision, words),
        )
        return ConfirmedView(answer=answer, case_version=change.case_version)

    async def _stating(self, context: AccessContext) -> bool:
        """Whether the tenant's rules let the chat state a decision or a
        write for the PIC to confirm (`model_assist.case_chat`)."""
        if self.rules is None:
            return False
        rules = await self.rules.rules(sales_scope(context))
        return rules.model_assist.on(ModelStep.CASE_CHAT)

    async def _propose_write(
        self, context: AccessContext, proposal: ProposedBravoWrite, words: AssistantWords
    ) -> ConfirmedView:
        """A confirmed write, proposed through ticket 53's own service as the
        confirming person: it checks their right, the case and Bravo's row
        again, and opens the approval; nothing is written into Bravo here."""
        if self.bravo_writes is None:
            raise NotFoundError("no such decision")
        line = str(proposal.line_no)
        change: AnyChange
        if proposal.field == "cancel":
            change = CancelChange(field="cancel", reason=proposal.value)
            answer = words.say("write_cancel_done", line=line)
        else:
            change = (
                ConfirmedDateChange(
                    field="confirmed_date", value=date.fromisoformat(proposal.value)
                )
                if proposal.field == "confirmed_date"
                else QuantityChange(field="quantity", value=Decimal(proposal.value))
            )
            answer = words.say("write_done", field=_field_word(proposal.field, words), line=line)
        await self.bravo_writes.propose(
            context,
            proposal.case_id,
            proposal.line_no,
            change,
            case_version=proposal.case_version,
        )
        # A proposal moves Bravo's write, not the case: its version stands.
        return ConfirmedView(answer=answer, case_version=proposal.case_version)

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
        intent = await self._intent(
            context, question, earlier, focus, bound.flags if bound is not None else ()
        )
        yield ChatStep(key="look", title=words.step_look)
        if bound is not None:
            # Nothing is stated where the tenant turned the step off (ticket 57).
            stating = await self._stating(context)
            # A decision is stated only to someone the command would let
            # record it; anyone else hears it is not theirs to decide here.
            deciding = (
                stating
                and self.decisions is not None
                and self.gate.allows(context, SalesScopes.ORDER_PREPARE)
            )
            # A write is stated only to someone its service would let propose it.
            writing = (
                stating
                and self.bravo_writes is not None
                and self.gate.allows(context, SalesScopes.BRAVO_WRITE)
            )
            # A case is given only by someone the assignment service lets
            # give it, among the people it would list (ticket 79).
            candidates: Sequence[Candidate] = ()
            assigning = (
                stating
                and self.assignment is not None
                and self.gate.allows(context, SalesScopes.CASE_ASSIGN)
            )
            if (
                assigning
                and self.assignment is not None
                and intent is not None
                and intent.kind is QuestionKind.ASSIGN_CASE
            ):
                candidates = [
                    Candidate(c.user_id, c.display_name)
                    for c in await self.assignment.candidates(
                        context, bound.ref.kind, bound.ref.case_id
                    )
                ]
            found = _in_case(
                intent,
                bound,
                words,
                deciding=deciding,
                writing=writing,
                assigning=assigning,
                candidates=candidates,
            )
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
            proposal=found.proposal,
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
                    whole = await self.orders.get(context, case.case_id)
                    flags = tuple(
                        _Flag(f.key, f.code.value, f.line_no, frozenset(f.allowed))
                        for f in whole.findings
                        if f.disposition.kind == "open"
                    )
                    return _Bound(
                        _order_ref(order),
                        order.po_no,
                        order_facts(order, zone),
                        version=whole.case_version,
                        flags=flags,
                        lines=tuple(line.line_no for line in whole.lines),
                        so_no=whole.bravo_so_no,
                    )
        else:
            for quote in await self.quotes.summaries(context):
                if quote.case_id == case.case_id:
                    return _Bound(
                        _quote_ref(quote),
                        quote.rfq_no,
                        quote_facts(quote, zone),
                        version=quote.case_version,
                    )
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
        flags: Sequence[_Flag] = (),
    ) -> QuestionIntent | None:
        """The question as the model reads it; None when there is no reading.
        ``flags``: the bound case's open flags, codes and lines only."""
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
        shown = json.dumps([{"code": f.code, "line": f.line_no} for f in flags], ensure_ascii=False)
        try:
            return await self.model.interpret(
                QUESTION_INTENT,
                {"question": question, "history": history, "flags": shown},
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
                | QuestionKind.DECIDE_FINDING
                | QuestionKind.PROPOSE_BRAVO_WRITE
                | QuestionKind.ASSIGN_CASE
            ):
                # A flag is decided, and a Bravo write proposed, in its case's
                # own conversation (ticket 56): here, the link to it, nothing
                # recorded.
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
    # An order's version and open flags (ticket 56); a quote's are not read.
    version: int = 0
    flags: tuple[_Flag, ...] = ()
    # An order's PO line numbers and its SO number in Bravo (ticket 56 over 53).
    lines: tuple[int, ...] = ()
    so_no: str | None = None

    def sentence(self, words: AssistantWords) -> str:
        said = order_sentence if self.ref.kind is CaseKind.ORDER else quote_sentence
        return said(self.facts, words)


def _in_case(
    intent: QuestionIntent | None,
    bound: _Bound,
    words: AssistantWords,
    *,
    deciding: bool = False,
    writing: bool = False,
    assigning: bool = False,
    candidates: Sequence[Candidate] = (),
) -> _Found:
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
        case QuestionKind.DECIDE_FINDING:
            if not deciding:
                return _Found(f"{words.out_of_scope_case} {words.case_catalog}")
            return _decision(intent, bound, words)
        case QuestionKind.PROPOSE_BRAVO_WRITE:
            if not writing:
                return _Found(f"{words.out_of_scope_case} {words.case_catalog}")
            return _bravo_write(intent, bound, words)
        case QuestionKind.ASSIGN_CASE:
            if not assigning:
                return _Found(words.assign_not_yours)
            return _assignment(intent, bound, candidates, words)
        case QuestionKind.ORDER_STATUS | QuestionKind.QUOTE_STATUS:
            if intent.reference is not None and not same_reference(intent.reference, bound.number):
                only = words.say("only_this_case", case=bound.ref.label)
                return _Found(f"{only} {words.elsewhere}")
            return _Found(bound.sentence(words), bound.facts, (bound.ref,), bound.ref)


def _flag_words(flag: _Flag) -> str:
    return flag.code if flag.line_no is None else f"{flag.code} (dòng {flag.line_no})"


def _decision(intent: QuestionIntent, bound: _Bound, words: AssistantWords) -> _Found:
    """A flag's decision the PIC stated, said back for them to confirm; or
    the one question that lets DW1 say it. The flag is one of the bound
    case's open flags, never a code the model made up: a code it names that
    the case does not hold open asks which, as a missing one does."""
    if bound.ref.kind is not CaseKind.ORDER:
        return _Found(words.decide_orders_only)
    if intent.reference is not None and not same_reference(intent.reference, bound.number):
        # Another PO named in this case's conversation: never decided here,
        # and never taken as this case's flag.
        only = words.say("only_this_case", case=bound.ref.label)
        return _Found(f"{only} {words.elsewhere}")
    if not bound.flags:
        return _Found(words.decide_no_flag)
    named = [f for f in bound.flags if f.code == intent.finding_code]
    if intent.finding_code is None and len(bound.flags) == 1:
        named = list(bound.flags)
    listed = ", ".join(_flag_words(f) for f in bound.flags)
    if len(named) != 1:
        return _Found(words.say("decide_which_flag", flags=listed))
    (flag,) = named
    decision = intent.decision
    if decision is None or decision not in flag.allowed:
        return _Found(words.say("decide_which_way", flag=_flag_words(flag)))
    reason = intent.reason.strip() if intent.reason else None
    if decision == "accepted" and not reason:
        return _Found(words.say("decide_need_reason", flag=_flag_words(flag)))
    proposal = ProposedDecision(
        case_kind=bound.ref.kind,
        case_id=bound.ref.case_id,
        case_version=bound.version,
        finding_key=flag.key,
        decision=decision,
        reason=reason,
        prompt=_READ_BY,
    )
    return _Found(
        _proposal_sentence(proposal, flag, words), None, (bound.ref,), bound.ref, proposal
    )


# The prompt a statement was read with, as its labelled case names it.
_READ_BY: Final = f"{QUESTION_INTENT.prompt_id}@{QUESTION_INTENT.version}"


def _field_word(field: str, words: AssistantWords) -> str:
    return words.write_date_word if field == "confirmed_date" else words.write_quantity_word


def _canonical(field: str, written: str | None) -> str | None:
    """The value as code holds it, or None when it is not exactly one: an
    ISO date, or a positive quantity of at most four decimals, plain."""
    if written is None:
        return None
    text = written.strip()
    if field == "confirmed_date":
        try:
            return date.fromisoformat(text).isoformat() if len(text) == 10 else None
        except ValueError:
            return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    if not number.is_finite() or number <= 0 or number != number.quantize(Decimal("0.0001")):
        return None
    return format(number.normalize(), "f")


def _bravo_write(intent: QuestionIntent, bound: _Bound, words: AssistantWords) -> _Found:
    """An SO line's value the PIC asked to write into Bravo, said back for
    them to confirm; or the one question that lets DW1 say it. The line is
    one of the bound order's own, the value parsed by code: nothing the
    model wrote names the case, the SO or the row."""
    if bound.ref.kind is not CaseKind.ORDER:
        return _Found(words.write_orders_only)
    if intent.reference is not None and not same_reference(intent.reference, bound.number):
        only = words.say("only_this_case", case=bound.ref.label)
        return _Found(f"{only} {words.elsewhere}")
    if bound.so_no is None:
        return _Found(words.write_no_so)
    if intent.line_no is None or intent.line_no not in bound.lines:
        listed = ", ".join(str(n) for n in bound.lines)
        return _Found(words.say("write_which_line", lines=listed))
    line = str(intent.line_no)
    if intent.field is None:
        return _Found(words.say("write_which_field", line=line))
    if intent.field == "cancel":
        return _cancel(intent.line_no, intent.reason, bound, words)
    field = _field_word(intent.field, words)
    value = _canonical(intent.field, intent.new_value)
    if value is None:
        return _Found(words.say("write_which_value", field=field, line=line))
    proposal = ProposedBravoWrite(
        case_kind=bound.ref.kind,
        case_id=bound.ref.case_id,
        case_version=bound.version,
        line_no=intent.line_no,
        field=intent.field,
        value=value,
        prompt=_READ_BY,
    )
    shown = day(date.fromisoformat(value)) if intent.field == "confirmed_date" else value
    sentence = words.say("write_confirm", so=bound.so_no, line=line, field=field, value=shown)
    return _Found(sentence, None, (bound.ref,), bound.ref, proposal)


def _cancel(line_no: int, written: str | None, bound: _Bound, words: AssistantWords) -> _Found:
    """A cancel of one line, said back with its reason as Bravo would hold
    it (`cancel_reason`, the page's own rule); or the one question that
    lets DW1 say it: no reason, or one longer than Bravo's column takes."""
    line = str(line_no)
    reason = cancel_reason(written or "")
    if not reason:
        return _Found(words.say("write_which_reason", line=line))
    if len(reason) > CANCEL_REASON_CHARS:
        return _Found(words.say("write_reason_too_long", limit=str(CANCEL_REASON_CHARS)))
    proposal = ProposedBravoWrite(
        case_kind=bound.ref.kind,
        case_id=bound.ref.case_id,
        case_version=bound.version,
        line_no=line_no,
        field="cancel",
        value=reason,
        prompt=_READ_BY,
    )
    sentence = words.say("write_cancel_confirm", so=bound.so_no, line=line, reason=reason)
    return _Found(sentence, None, (bound.ref,), bound.ref, proposal)


@dataclass(frozen=True)
class Candidate:
    """A person the case may be given to (`AssignmentService.candidates`)."""

    user_id: uuid.UUID
    name: str


def _folded(text: str) -> str:
    """Lower case, no diacritics, single spaces: "Lâm Minh Khoa" as "lam minh khoa"."""
    decomposed = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(plain.casefold().split())


def _matches(written: str, candidate: Candidate) -> bool:
    """Whether the person named is this candidate: their whole name, or the
    given name a colleague calls them by (the last word of a Vietnamese name)."""
    named, full = _folded(written), _folded(candidate.name)
    return bool(named) and (named == full or named == full.rsplit(" ", 1)[-1])


def _assignment(
    intent: QuestionIntent, bound: _Bound, candidates: Sequence[Candidate], words: AssistantWords
) -> _Found:
    """The case given to the one person the head named, said back for them to
    confirm; or the one question that lets DW1 say it. The person is one of
    the case's candidates, matched by code: nothing the model wrote is an id."""
    if intent.reference is not None and not same_reference(intent.reference, bound.number):
        only = words.say("only_this_case", case=bound.ref.label)
        return _Found(f"{only} {words.elsewhere}")
    if not candidates:
        return _Found(words.assign_nobody)
    named = [c for c in candidates if intent.assignee and _matches(intent.assignee, c)]
    if len(named) != 1:
        listed = ", ".join(c.name for c in candidates)
        return _Found(words.say("assign_which", people=listed))
    (person,) = named
    proposal = ProposedAssignment(
        case_kind=bound.ref.kind,
        case_id=bound.ref.case_id,
        case_version=bound.version,
        assignee=person.user_id,
        name=person.name,
        prompt=_READ_BY,
    )
    sentence = words.say("assign_confirm", case=bound.ref.label, person=person.name)
    return _Found(sentence, None, (bound.ref,), bound.ref, proposal)


def _decision_word(decision: ChatDecision, words: AssistantWords) -> str:
    return words.decide_accept_word if decision == "accepted" else words.decide_ask_word


def _proposal_sentence(proposal: ProposedDecision, flag: _Flag, words: AssistantWords) -> str:
    reason = words.say("decide_reason", reason=proposal.reason) if proposal.reason else ""
    return words.say(
        "decide_confirm",
        flag=_flag_words(flag),
        decision=_decision_word(proposal.decision, words),
        reason=reason,
    )


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
