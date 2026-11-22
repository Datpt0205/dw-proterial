"""The case chat as a model step (ticket 57): its statements become labelled
cases when the person decides, by the chat's button or the page's, and the
tenant's `model_assist.case_chat` turns the statements off."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from dw_sales.application.assistant import CaseChatStatements
from dw_sales.application.chat_prompts import QUESTION_INTENT
from dw_sales.domain.assistant import CaseKey, ProposedDecision, Session
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.labelled_cases import chat_decision_label
from dw_sales.domain.order_checks import ModelStep, OrderRules
from dw_sales.domain.orders import Accepted, Actor, FindingCode, OrderCase
from dw_sales.evals.graders import AN, CALLERS, GIANG
from dw_sales.evals.recorded import Recorded
from dw_sales.evals.world import ALPHA, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
SHORT = FindingCode.REQUESTED_DATE_SHORT_LT.value
MOQ = FindingCode.MOQ_VIOLATION.value
READ_BY = f"{QUESTION_INTENT.prompt_id}@{QUESTION_INTENT.version}"
NOW = datetime(2026, 11, 22, 3, tzinfo=UTC)


class Reader(Recorded):
    def __init__(self, reading: dict[str, Any]) -> None:
        super().__init__(raw={})
        self.reading = reading

    async def interpret(self, prompt: Any, inputs: Any, schema: Any, **kwargs: Any) -> Any:
        self.calls.append((prompt, kwargs["run"], inputs))
        if prompt == QUESTION_INTENT:
            return schema.model_validate(self.reading)
        return schema.model_validate({"answer": "x"})


ACCEPT = {
    "kind": "decide_finding",
    "finding_code": SHORT,
    "decision": "accepted",
    "reason": "khách đồng ý LT",
}


async def _m06(reading: dict[str, Any] = ACCEPT) -> tuple[World, OrderCase, CaseKey]:
    world = open_world(
        REPO, SampleSet.of(REPO, None), CALLERS, model=Reader(reading), measured=False
    )
    ((_, case),) = (await world.process_each(AN, ["M06"])).values()
    assert isinstance(case, OrderCase)
    return world, world.order(case.case_id), CaseKey(CaseKind.ORDER, case.case_id)


def _short_key(case: OrderCase) -> str:
    return next(f.key for f in case.findings if f.code.value == SHORT)


def _moq_key(case: OrderCase) -> str:
    return next(f.key for f in case.findings if f.code.value == MOQ)


# The MOQ flag takes either decision; the short lead time cannot be asked of
# the customer.
ACCEPT_MOQ = {**ACCEPT, "finding_code": MOQ, "reason": "khách mua đủ MOQ"}


def _labels(world: World) -> list[Any]:
    return [c for c in world.store.state(ALPHA).labelled_cases if c.step is ModelStep.CASE_CHAT]


async def test_a_statement_the_pic_confirms_is_a_confirmed_case_read_by_its_prompt() -> None:
    world, case, key = await _m06()
    turn = (await world.services.assistant.ask(AN.context(), "chấp nhận cờ LT", key)).turn
    assert turn.proposal is not None
    await world.services.assistant.confirm(AN.context(), key, turn.seq, turn.proposal.content_hash)
    (label,) = _labels(world)
    assert label.verdict == "confirmed"
    assert label.prompt == READ_BY
    assert label.proposed == {"finding_key": _short_key(case), "decision": "accepted"}
    assert (label.case_id, label.line_no, label.decided_by) == (case.case_id, 3, AN.user_id)


async def test_the_page_deciding_otherwise_is_a_corrected_case() -> None:
    world, case, key = await _m06(ACCEPT_MOQ)
    turn = (await world.services.assistant.ask(AN.context(), "MOQ dòng 1 cho qua", key)).turn
    assert turn.proposal is not None
    # Not confirmed in the chat: the PIC asks the customer on the page.
    await world.services.order_commands.dispose(
        AN.context(),
        case.case_id,
        _moq_key(case),
        case_version=case.case_version,
        disposition="ask_customer",
    )
    (label,) = _labels(world)
    assert label.verdict == "corrected"
    assert label.kept == {"finding_key": _moq_key(case), "decision": "ask_customer"}


async def test_a_flag_the_chat_said_nothing_about_labels_nothing() -> None:
    world, case, _ = await _m06()
    await world.services.order_commands.dispose(
        AN.context(),
        case.case_id,
        _short_key(case),
        case_version=case.case_version,
        disposition="accepted",
        reason="PIC chấp nhận trên trang",
    )
    assert _labels(world) == []


async def test_another_persons_statement_labels_nothing_for_this_person() -> None:
    world, case, key = await _m06(ACCEPT_MOQ)
    turn = (await world.services.assistant.ask(AN.context(), "MOQ dòng 1 cho qua", key)).turn
    assert turn.proposal is not None
    # Giang decides it on the page: An's conversation is not Giang's.
    await world.services.order_commands.dispose(
        GIANG.context(),
        case.case_id,
        _moq_key(case),
        case_version=case.case_version,
        disposition="ask_customer",
    )
    assert _labels(world) == []


class _Rules:
    def __init__(self, rules: OrderRules) -> None:
        self.policy = rules

    async def rules(self, scope: object) -> OrderRules:
        return self.policy

    async def rules_at(self, scope: object, ref: str) -> OrderRules | None:
        raise NotImplementedError("not exercised by the chat")


async def test_the_tenant_turning_the_step_off_stops_every_statement() -> None:
    world, _, key = await _m06()
    on = await world.services.assistant.rules.rules(ALPHA)  # type: ignore[union-attr]
    assert on.model_assist.case_chat
    off = on.model_copy(
        update={"model_assist": on.model_assist.model_copy(update={"case_chat": False})}
    )
    assistant = replace(world.services.assistant, rules=_Rules(off))
    turn = (await assistant.ask(AN.context(), "chấp nhận cờ LT", key)).turn
    assert turn.proposal is None


async def test_with_no_rules_to_read_nothing_is_stated() -> None:
    world, _, key = await _m06()
    assistant = replace(world.services.assistant, rules=None)
    turn = (await assistant.ask(AN.context(), "chấp nhận cờ LT", key)).turn
    assert turn.proposal is None


async def test_a_statement_on_another_flag_labels_nothing() -> None:
    world, case, key = await _m06(ACCEPT_MOQ)
    turn = (await world.services.assistant.ask(AN.context(), "MOQ dòng 1 cho qua", key)).turn
    assert turn.proposal is not None
    await world.services.order_commands.dispose(
        AN.context(),
        case.case_id,
        _short_key(case),
        case_version=case.case_version,
        disposition="accepted",
        reason="PIC chấp nhận LT trên trang",
    )
    assert _labels(world) == []


async def test_an_unstamped_statement_or_a_reopened_flag_labels_nothing() -> None:
    _, case, _ = await _m06()
    key = _short_key(case)
    stamped = ProposedDecision(
        case_kind=CaseKind.ORDER,
        case_id=case.case_id,
        case_version=case.case_version,
        finding_key=key,
        decision="accepted",
        reason="ok",
        prompt=READ_BY,
    )
    decided = case.dispose(
        key,
        Accepted(reason="ok", by=AN.user_id, at=NOW),
        Actor(user_id=AN.user_id),
    )

    def label(stated: ProposedDecision, after: OrderCase) -> Any:
        return chat_decision_label(
            case, after, key, [stated], new_id=uuid.uuid4, at=NOW, by=AN.user_id
        )

    assert label(stamped, decided) is not None
    assert label(replace(stamped, prompt=None), decided) is None
    assert label(stamped, case) is None  # still open: nothing decided


async def test_another_persons_conversation_is_never_read_for_a_label() -> None:
    session = Session(
        session_id=uuid.uuid4(),
        user_id=GIANG.user_id,
        title="t",
        created_at=NOW,
        last_turn_at=NOW,
    )

    class _Store:
        async def conversation(self, case_id: object) -> Session:
            return session

        async def turns(self, session_id: object) -> list[Any]:
            raise AssertionError("another person's turns were read")

    @asynccontextmanager
    async def store(context: object) -> AsyncIterator[_Store]:
        yield _Store()

    stated = await CaseChatStatements(store).stated(AN.context(), uuid.uuid4())  # type: ignore[arg-type]
    assert list(stated) == []
