"""DW2's Hỏi đáp (DW02 function 6): status questions answered from live data.

DW1's design (dw_sales ADR 0007), in DW2's own code (the contexts never
import each other):

- **The model reads, code answers.** `purchasing.question_intent@1.0.0`
  turns the question (and the session's last turns, both untrusted data)
  into a `QuestionIntent`; code finds what it names among the cases the
  asker may see, through `PurchaseRequests.cases`, the query the pages read
  (a requester's own only, narrowed in the query), and words the answer
  itself. No amount is ever in it.
- **What it did** is returned with the answer (`steps`): how the question
  was read, what was looked up and how many found. Nothing else.
- **Sessions are a person's own** (`purchasing.assistant_*`, RLS by user),
  kept 30 days after their last turn.
- **No model, or one that fails:** "DW2 chưa hiểu câu này" and the catalog,
  never a guess.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator, Sequence
from contextlib import aclosing
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict

from dw_agent_runtime.context import caller_run
from dw_agent_runtime.model.interpretation import (
    InterpretationPort,
    ModelUnavailableError,
    PromptRef,
)
from dw_agent_runtime.model.streaming import ChatDelta, ChatDone, ChatEvent, ChatStep
from dw_kernel.errors import NotFoundError, QuotaExceededError
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_purchasing.application.access import Gate, PurchasingScopes
from dw_purchasing.application.follow_up import OrderFollowUp
from dw_purchasing.application.intake import PurchaseRequests, Worker
from dw_purchasing.domain.assistant import (
    CASE_STATE,
    CATALOG,
    HISTORY_TURNS,
    AssistantQuestionKind,
    CaseRef,
    QuestionIntent,
    Session,
    Turn,
    same_reference,
    title_of,
    written_in,
)
from dw_purchasing.domain.cases import CaseStatus, PurchaseCase

QUESTION_INTENT: Final = PromptRef("purchasing.question_intent", "1.0.0")
_RESOURCE: Final = "purchasing_assistant"
_OUTPUT_TOKENS: Final = 200
# The cases a question is looked up among, newest first: what the list page
# would show on its first pages.
LOOKED_AT: Final = 200


class AssistantStorePort(Protocol):
    """A person's sessions and turns (RLS narrows every read to the asker)."""

    async def sessions(self, context: AccessContext, *, limit: int) -> Sequence[Session]: ...

    async def session(self, context: AccessContext, session_id: uuid.UUID) -> Session | None: ...

    async def turns(self, context: AccessContext, session_id: uuid.UUID) -> Sequence[Turn]: ...

    async def append(self, context: AccessContext, session: Session, turn: Turn) -> None:
        """Adds ``turn``, creating ``session`` when it is new, in one transaction."""
        ...


class AssistantStepView(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    title: str


class AssistantCaseRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: uuid.UUID
    label: str


class AssistantTurnView(BaseModel):
    model_config = ConfigDict(frozen=True)

    seq: int
    asked_at: datetime
    question: str
    kind: AssistantQuestionKind
    answer: str
    cites: list[AssistantCaseRef]
    answered_by: Literal["model", "code"]
    steps: list[AssistantStepView]


class AssistantSessionView(BaseModel):
    model_config = ConfigDict(frozen=True)

    session_id: uuid.UUID
    title: str
    created_at: datetime
    last_turn_at: datetime


class AssistantSessionDetailView(AssistantSessionView):
    turns: list[AssistantTurnView]


class AssistantAnswerView(BaseModel):
    model_config = ConfigDict(frozen=True)

    session_id: uuid.UUID
    turn: AssistantTurnView


@dataclass(frozen=True, slots=True)
class _Answer:
    text: str
    cites: tuple[CaseRef, ...]
    focus: CaseRef | None


def _ref(case: PurchaseCase) -> CaseRef:
    return CaseRef(case.case_id, case.request.pr_no)


def steps_of(turn: Turn) -> list[AssistantStepView]:
    """What DW2 did for ``turn``, as the stored turn says it."""
    read = {
        AssistantQuestionKind.REQUEST_STATUS: "Hiểu là hỏi một yêu cầu mua hàng đang ở bước nào",
        AssistantQuestionKind.MY_WORK: "Hiểu là hỏi việc đang chờ bạn",
        AssistantQuestionKind.LATE_ORDERS: "Hiểu là hỏi các dòng đơn đặt hàng trễ hạn",
        AssistantQuestionKind.OUT_OF_SCOPE: "Câu này ngoài những gì DW2 trả lời",
    }[turn.kind]
    steps = [AssistantStepView(key="read", title=read)]
    if turn.kind is not AssistantQuestionKind.OUT_OF_SCOPE:
        steps.append(
            AssistantStepView(
                key="look",
                title=(
                    f"Tra {len(turn.cites)} hồ sơ trong phạm vi bạn được xem"
                    if turn.cites
                    else "Tra trong phạm vi bạn được xem"
                ),
            )
        )
    return steps


def _view(turn: Turn) -> AssistantTurnView:
    return AssistantTurnView(
        seq=turn.seq,
        asked_at=turn.asked_at,
        question=turn.question,
        kind=turn.kind,
        answer=turn.answer,
        cites=[AssistantCaseRef(case_id=c.case_id, label=c.label) for c in turn.cites],
        answered_by=turn.answered_by,
        steps=steps_of(turn),
    )


@dataclass(frozen=True)
class AssistantService:
    store: AssistantStorePort
    gate: Gate
    requests: PurchaseRequests
    follow_up: OrderFollowUp
    model: InterpretationPort | None
    worker: Worker
    clock: UtcClock
    ids: IdGenerator

    async def sessions(
        self, context: AccessContext, *, limit: int = 30
    ) -> list[AssistantSessionView]:
        await self._may_ask(context)
        return [_session_view(s) for s in await self.store.sessions(context, limit=limit)]

    async def session(
        self, context: AccessContext, session_id: uuid.UUID
    ) -> AssistantSessionDetailView:
        await self._may_ask(context)
        found = await self._own(context, session_id)
        turns = await self.store.turns(context, session_id)
        return AssistantSessionDetailView(
            **_session_view(found).model_dump(), turns=[_view(t) for t in turns]
        )

    async def ask(
        self, context: AccessContext, question: str, session_id: uuid.UUID | None = None
    ) -> AssistantAnswerView:
        """`stream`'s turn, whole: one path, so neither can drift from the other."""
        async with aclosing(self.stream(context, question, session_id)) as events:
            async for event in events:
                if isinstance(event, ChatDone):
                    return event.view
        raise AssertionError("a turn always ends in ChatDone")

    async def stream(
        self, context: AccessContext, question: str, session_id: uuid.UUID | None = None
    ) -> AsyncGenerator[ChatEvent[AssistantAnswerView], None]:
        """A turn as it happens: DW2 words its answers itself, so what arrives
        as it goes is what it is doing. Whatever refuses the caller raises
        before the first event, while the route can still answer with a
        status."""
        await self._may_ask(context)
        now = self.clock.now()
        if session_id is None:
            session = Session(
                self.ids.new_uuid(), context.principal_id, title_of(question), now, now
            )
            history: Sequence[Turn] = ()
        else:
            found = await self._own(context, session_id)
            session = Session(found.session_id, found.user_id, found.title, found.created_at, now)
            history = await self.store.turns(context, session_id)
        yield ChatStep(key="read", title="Đang đọc câu hỏi")
        intent = await self._intent(context, question, history)
        focus = history[-1].focus if history else None
        yield ChatStep(key="look", title="Đang tra trong phạm vi bạn được xem")
        answer = (
            _Answer(_NOT_UNDERSTOOD, (), focus)
            if intent is None
            else await self._answer(context, _copied(intent, question), focus)
        )
        turn = Turn(
            session_id=session.session_id,
            seq=(history[-1].seq + 1) if history else 1,
            asked_at=now,
            question=question,
            kind=intent.kind if intent is not None else AssistantQuestionKind.OUT_OF_SCOPE,
            reference=intent.reference if intent is not None else None,
            answer=answer.text,
            cites=answer.cites,
            focus=answer.focus,
            answered_by="code",
        )
        await self.store.append(context, session, turn)
        yield ChatDelta(text=answer.text)
        yield ChatDone(AssistantAnswerView(session_id=session.session_id, turn=_view(turn)))

    # ------------------------------------------------------------ steps --

    async def _may_ask(self, context: AccessContext) -> None:
        await self.gate.require_any(
            context, PurchasingScopes.REQUEST_READ, PurchasingScopes.REQUEST_READ_OWN
        )

    async def _own(self, context: AccessContext, session_id: uuid.UUID) -> Session:
        found = await self.store.session(context, session_id)
        if found is None or found.user_id != context.principal_id:
            raise NotFoundError(
                "không có phiên hỏi đáp này", details={"session_id": str(session_id)}
            )
        return found

    async def _intent(
        self, context: AccessContext, question: str, history: Sequence[Turn]
    ) -> QuestionIntent | None:
        if self.model is None:
            return None
        shown = [
            {"question": t.question, "kind": t.kind.value, "reference": t.reference}
            for t in history[-HISTORY_TURNS:]
        ]
        try:
            return await self.model.interpret(
                QUESTION_INTENT,
                {"question": question, "history": json.dumps(shown, ensure_ascii=False)},
                QuestionIntent,
                run=caller_run(
                    context,
                    run_id=self.ids.new_uuid(),
                    worker_id=self.worker.worker_id,
                    worker_version=self.worker.worker_version,
                    trace="dw2-question-intent",
                    subject_ref=_RESOURCE,
                ),
                max_output_tokens=_OUTPUT_TOKENS,
            )
        except (ModelUnavailableError, QuotaExceededError):
            return None

    async def _answer(
        self, context: AccessContext, intent: QuestionIntent, focus: CaseRef | None
    ) -> _Answer:
        if intent.kind is AssistantQuestionKind.OUT_OF_SCOPE:
            return _Answer(CATALOG, (), focus)
        if intent.kind is AssistantQuestionKind.LATE_ORDERS:
            return await self._late(context, focus)
        cases = await self.requests.cases(context, limit=LOOKED_AT, before=None)
        if intent.kind is AssistantQuestionKind.MY_WORK:
            return self._work(context, cases, focus)
        if intent.reference is not None:
            named = [c for c in cases if same_reference(intent.reference, c.request.pr_no)]
        elif intent.about_previous and focus is not None:
            named = [c for c in cases if c.case_id == focus.case_id]
        else:
            return _Answer("Bạn hỏi yêu cầu mua hàng số nào?", (), focus)
        if len(named) != 1:
            return _Answer(
                f"DW2 không thấy yêu cầu {intent.reference or 'đó'} trong các hồ sơ bạn được xem.",
                (),
                focus,
            )
        (case,) = named
        return _Answer(_status(case), (_ref(case),), _ref(case))

    def _work(
        self, context: AccessContext, cases: Sequence[PurchaseCase], focus: CaseRef | None
    ) -> _Answer:
        def holds(scope: PurchasingScopes) -> bool:
            return self.gate.allows(context, scope)

        waiting: list[tuple[str, PurchaseCase]] = []
        for case in cases:
            if (
                case.status is CaseStatus.RECEIVED
                and case.review is not None
                and case.review.pending
                and holds(PurchasingScopes.REQUEST_INTAKE)
            ):
                waiting.append(("xem lại bản DW2 đọc", case))
            elif case.status is CaseStatus.RECEIVED and holds(PurchasingScopes.REQUEST_SUBMIT):
                waiting.append(("gửi người duyệt", case))
            elif case.status is CaseStatus.APPROVED and holds(PurchasingScopes.RFQ_PREPARE):
                waiting.append(("hỏi giá", case))
            elif case.status is CaseStatus.RFQ_DRAFTED and holds(PurchasingScopes.RFQ_PREPARE):
                waiting.append(("chọn nhà cung cấp", case))
            elif case.status is CaseStatus.SUPPLIER_SELECTED and holds(PurchasingScopes.PO_PREPARE):
                waiting.append(("soạn PO", case))
            elif (
                case.status is CaseStatus.AWAITING_APPROVAL
                and case.approval is not None
                and holds(PurchasingScopes(case.approval.required_scope))
            ):
                waiting.append(("duyệt", case))
        if not waiting:
            return _Answer("Không có việc nào đang chờ bạn.", (), focus)
        shown = waiting[:8]
        lines = [f"- {c.request.pr_no}: {what}" for what, c in shown]
        more = f"\n… và {len(waiting) - len(shown)} việc nữa." if len(waiting) > len(shown) else ""
        return _Answer(
            f"{len(waiting)} việc đang chờ bạn:\n" + "\n".join(lines) + more,
            tuple(_ref(c) for _, c in shown),
            focus,
        )

    async def _late(self, context: AccessContext, focus: CaseRef | None) -> _Answer:
        if not self.gate.allows(context, PurchasingScopes.PO_PREPARE):
            return _Answer("Theo dõi đơn đặt hàng không thuộc vai của bạn.", (), focus)
        late = await self.follow_up.late(context)
        if not late:
            return _Answer("Không có dòng đơn đặt hàng nào trễ hạn.", (), focus)
        shown = late[:8]
        lines = [
            f"- {x.pr_no}, đơn {x.po_ref} dòng {x.line_no}: hẹn {x.due_on:%d/%m/%Y},"
            f" còn thiếu {format(x.owed.normalize(), 'f')}"
            for x in shown
        ]
        cites: dict[uuid.UUID, CaseRef] = {}
        for x in shown:
            cites.setdefault(x.case_id, CaseRef(x.case_id, x.pr_no))
        more = f"\n… và {len(late) - len(shown)} dòng nữa." if len(late) > len(shown) else ""
        return _Answer(
            f"{len(late)} dòng trễ hạn:\n" + "\n".join(lines) + more,
            tuple(cites.values()),
            focus,
        )


_NOT_UNDERSTOOD: Final = "DW2 chưa hiểu câu này. " + CATALOG


def _copied(intent: QuestionIntent, question: str) -> QuestionIntent:
    """``intent`` with its number dropped where the question does not write it."""
    if intent.reference is None or written_in(intent.reference, question):
        return intent
    return intent.model_copy(update={"reference": None})


def _status(case: PurchaseCase) -> str:
    """Where ``case`` stands, in the pages' words; never an amount."""
    said = f"{case.request.pr_no} ({case.request.department}): {CASE_STATE[case.status.value]}."
    if case.review is not None and case.review.pending:
        said += " Đang chờ người xem lại bản DW2 đọc."
    if case.po is not None:
        numbered = sum(1 for t in case.tracking if t.bravo_no)
        confirmed = sum(1 for t in case.tracking if t.confirmation and t.confirmation.accepted_by)
        said += (
            f" {len(case.po.orders)} đơn đặt hàng: {numbered} đã có số PO Bravo,"
            f" {confirmed} đã có xác nhận của nhà cung cấp."
        )
    return said


def _session_view(session: Session) -> AssistantSessionView:
    return AssistantSessionView(
        session_id=session.session_id,
        title=session.title,
        created_at=session.created_at,
        last_turn_at=session.last_turn_at,
    )
