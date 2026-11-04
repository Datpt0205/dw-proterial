"""DW2's Hỏi đáp (DW02 function 6) over the in-memory world: the model reads
a question, code answers from the cases the asker may see; sessions are the
asker's own; no amount is ever said."""

from __future__ import annotations

import re
import uuid
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from dw_agent_runtime.model.interpretation import ModelUnavailableError
from dw_kernel.errors import NotFoundError, PermissionDeniedError
from dw_purchasing.application.access import PurchasingScopes
from dw_purchasing.application.assistant import QUESTION_INTENT
from dw_purchasing.domain.assistant import CASE_STATE, CATALOG, AssistantQuestionKind
from dw_purchasing.testing.flows import orders_drafted, sourcing_world
from dw_purchasing.testing.world import ALPHA, BETA, EVERY_SCOPE, World, caller

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
# What a model that reads questions well answers, by a phrase the question
# holds; the follow-up first, since a session's history holds the PR too.
INTENTS: dict[str, dict[str, Any]] = {
    "nó đã": {"kind": "request_status", "reference": None, "about_previous": True},
    "PR-2611-004": {"kind": "request_status", "reference": "PR-2611-004"},
    "pr 2611 009": {"kind": "request_status", "reference": "pr 2611 009"},
    "việc của tôi": {"kind": "my_work"},
    "trễ": {"kind": "late_orders"},
    "giá rẻ nhất": {"kind": "out_of_scope"},
}
REQUESTER = uuid.UUID(int=0x2E9)
MONEY = re.compile(r"\d[\d.,]*\s*(₫|đ\b|VND|đồng)|\d{1,3}(\.\d{3}){2,}")


def _world() -> World:
    world = sourcing_world(REPO)
    world.model.by_schema["QuestionIntent"] = INTENTS
    return world


async def _ask(world: World, question: str, session: uuid.UUID | None = None, who: Any = None):  # type: ignore[no-untyped-def]
    return await world.assistant.ask(who or caller(), question, session)


async def test_a_request_s_state_is_answered_from_its_case_with_what_was_done() -> None:
    world = _world()
    item = await world.service.read_mail(caller(), "P01")
    answer = await _ask(world, "PR-2611-004 tới đâu rồi?")
    turn = answer.turn
    assert turn.kind is AssistantQuestionKind.REQUEST_STATUS and turn.answered_by == "code"
    assert turn.answer.startswith("PR-2611-004 (Xưởng cắt): Đã nhận.")
    assert [c.case_id for c in turn.cites] == [item.case_id]
    assert [s.key for s in turn.steps] == ["read", "look"]
    (call,) = [c for c in world.model.calls if c[0] == QUESTION_INTENT]
    assert call[1]["question"] == "PR-2611-004 tới đâu rồi?"


async def test_a_number_is_matched_whole_separators_aside_and_a_follow_up_reads_the_focus() -> None:
    world = _world()
    await world.service.read_mail(caller(), "P02")
    first = await _ask(world, "pr 2611 009 sao rồi")
    assert first.turn.answer.startswith("PR-2611-009")
    again = await _ask(world, "nó đã duyệt chưa?", first.session_id)
    assert again.turn.seq == 2 and again.turn.cites == first.turn.cites


async def test_a_requester_is_answered_from_their_own_requests_only() -> None:
    world = _world()
    await world.service.read_mail(caller(), "P01")
    requester = caller(
        scopes=frozenset({PurchasingScopes.REQUEST_READ_OWN.value}), principal=REQUESTER
    )
    answer = await _ask(world, "PR-2611-004 tới đâu rồi?", who=requester)
    assert answer.turn.cites == [] and "không thấy" in answer.turn.answer


async def test_my_work_lists_what_the_asker_s_scopes_let_them_do_next() -> None:
    world = _world()
    for message_id in ("P01", "P02"):
        await world.service.read_mail(caller(), message_id)
    answer = await _ask(world, "việc của tôi là gì")
    assert answer.turn.answer.startswith("2 việc đang chờ bạn:")
    assert "PR-2611-004: gửi người duyệt" in answer.turn.answer
    reader = caller(scopes=frozenset({PurchasingScopes.REQUEST_READ.value}))
    nothing = await _ask(world, "việc của tôi là gì", who=reader)
    assert nothing.turn.answer == "Không có việc nào đang chờ bạn."


async def test_late_order_lines_are_said_without_a_price_and_only_to_a_buyer() -> None:
    world = _world()
    await orders_drafted(world)
    world.clock.advance_to(world.clock.now().replace(month=11, day=25))  # type: ignore[attr-defined]
    answer = await _ask(world, "đơn nào trễ?")
    # Line 3 has no need-by date, so it is never late.
    assert answer.turn.answer.startswith("2 dòng trễ hạn:")
    assert "hẹn 20/11/2026" in answer.turn.answer and not MONEY.search(answer.turn.answer)
    reader = caller(scopes=frozenset({PurchasingScopes.REQUEST_READ.value}))
    refused = await _ask(world, "đơn nào trễ?", who=reader)
    assert refused.turn.answer == "Theo dõi đơn đặt hàng không thuộc vai của bạn."


async def test_a_drafted_case_s_state_names_no_amount() -> None:
    world = _world()
    await orders_drafted(world)
    answer = await _ask(world, "PR-2611-004 tới đâu rồi?")
    assert "3 đơn đặt hàng" in answer.turn.answer and not MONEY.search(answer.turn.answer)


async def test_out_of_scope_and_no_model_say_what_dw2_answers() -> None:
    world = _world()
    asked = await _ask(world, "nhà cung cấp nào giá rẻ nhất?")
    assert asked.turn.kind is AssistantQuestionKind.OUT_OF_SCOPE and asked.turn.answer == CATALOG
    world.model.failure = ModelUnavailableError("down")
    down = await _ask(world, "PR-2611-004 tới đâu rồi?")
    assert down.turn.kind is AssistantQuestionKind.OUT_OF_SCOPE and down.turn.answer.startswith(
        "DW2 chưa hiểu câu này."
    )


async def test_a_session_is_its_asker_s_own() -> None:
    world = _world()
    mine = await _ask(world, "việc của tôi là gì")
    other = caller(principal=uuid.UUID(int=0xFACE))
    with pytest.raises(NotFoundError):
        await world.assistant.session(other, mine.session_id)
    with pytest.raises(NotFoundError):
        await _ask(world, "nó đã duyệt chưa?", mine.session_id, who=other)
    assert await world.assistant.sessions(other) == []
    with pytest.raises(NotFoundError):
        await world.assistant.session(caller(BETA), mine.session_id)
    detail = await world.assistant.session(caller(), mine.session_id)
    assert [t.seq for t in detail.turns] == [1]


async def test_only_a_reader_of_requests_may_ask() -> None:
    world = _world()
    nobody = caller(
        scopes=EVERY_SCOPE
        - {PurchasingScopes.REQUEST_READ.value, PurchasingScopes.REQUEST_READ_OWN.value}
    )
    calls = len(world.model.calls)
    with pytest.raises(PermissionDeniedError):
        await _ask(world, "việc của tôi là gì", who=nobody)
    with pytest.raises(PermissionDeniedError):
        await world.assistant.sessions(nobody)
    assert len(world.model.calls) == calls


def test_the_states_are_the_pages_words() -> None:
    labels = (REPO / "apps/web/app/purchasing/_lib/labels.ts").read_text(encoding="utf-8")
    block = labels[labels.index("export const CASE_STATUS") :].split("};", 1)[0]
    pages = dict(re.findall(r"^\s+(\w+): \"([^\"]+)\",", block, flags=re.M))
    assert pages == CASE_STATE
    assert ALPHA and date.today()


def test_the_catalog_s_check_holds_the_domain_s_kinds() -> None:
    (migration,) = (REPO / "db/migrations/versions").glob("63b96e56db85_*.py")
    found = re.search(r'_KINDS = "\((.*)\)"', migration.read_text(encoding="utf-8"))
    assert found is not None
    assert set(re.findall(r"'(\w+)'", found.group(1))) == {k.value for k in AssistantQuestionKind}


async def test_a_number_the_question_does_not_write_is_not_looked_up() -> None:
    """The model may only copy a number; one it invents names nothing."""
    world = _world()
    await world.service.read_mail(caller(), "P01")
    world.model.by_schema["QuestionIntent"] = {
        "yêu cầu của tôi": {"kind": "request_status", "reference": "PR-2611-004"}
    }
    answer = await _ask(world, "yêu cầu của tôi sao rồi?")
    assert answer.turn.cites == [] and answer.turn.answer == "Bạn hỏi yêu cầu mua hàng số nào?"


async def test_part_of_a_number_names_nothing() -> None:
    world = _world()
    await world.service.read_mail(caller(), "P01")
    world.model.by_schema["QuestionIntent"] = {
        "004": {"kind": "request_status", "reference": "004"}
    }
    answer = await _ask(world, "004 sao rồi?")
    assert answer.turn.cites == []


async def test_a_session_another_person_holds_is_refused_even_if_the_store_hands_it_over() -> None:
    """Defence beside RLS: a store that leaks (a policy dropped) still does
    not give one person another's session."""
    import dataclasses

    world = _world()
    mine = await _ask(world, "việc của tôi là gì")
    store = world.assistant.store

    class Leaky:
        async def session(self, context: Any, session_id: uuid.UUID) -> Any:
            return await store.session(caller(), session_id)

        async def turns(self, context: Any, session_id: uuid.UUID) -> Any:
            return await store.turns(caller(), session_id)

    world.assistant = dataclasses.replace(world.assistant, store=Leaky())  # type: ignore[arg-type]
    with pytest.raises(NotFoundError):
        await world.assistant.session(caller(principal=uuid.UUID(int=0xFACE)), mine.session_id)


async def test_two_requests_of_one_number_are_not_guessed_between() -> None:
    import dataclasses

    world = _world()
    item = await world.service.read_mail(caller(), "P01")
    assert item.case_id is not None
    case = await world.service.case(caller(), item.case_id)
    twin = case.model_copy(update={"case_id": uuid.uuid4()})

    class Twins:
        async def cases(self, context: Any, *, limit: int, before: Any) -> Any:
            return [case, twin]

    world.assistant = dataclasses.replace(world.assistant, requests=Twins())  # type: ignore[arg-type]
    answer = await _ask(world, "PR-2611-004 tới đâu rồi?")
    assert answer.turn.cites == []
