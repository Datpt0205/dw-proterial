"""Status questions answered from live data, in sessions (dw_sales ADR 0007):
what the model is asked, what code answers, whose cases and sessions."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncGenerator, Callable
from pathlib import Path
from typing import Any

import pytest

from dw_agent_runtime.model.interpretation import (
    ModelUnavailableError,
    estimated_tokens,
)
from dw_agent_runtime.model.streaming import ChatDelta, ChatDone, ChatReplace, ChatStep
from dw_kernel.errors import NotFoundError, PermissionDeniedError
from dw_sales.application.assistant import (
    ANSWER_TOKENS,
    ASSISTANT_ANSWER,
    INTENT_TOKENS,
    QUESTION_INTENT,
)
from dw_sales.domain.assistant import (
    ACTION,
    CATALOG,
    ORDER_STATE,
    QUOTE_STATE,
    QuestionKind,
    same_reference,
)
from dw_sales.evals.graders import AN, CALLERS, OUTSIDER, READER
from dw_sales.evals.recorded import Recorded
from dw_sales.evals.world import ALPHA, BETA, SampleSet, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]

Reading = Callable[[str, dict[str, Any]], dict[str, Any]]


class Scripted(Recorded):
    """Reads each question with ``read`` and words each answer with ``word``."""

    def __init__(self, read: Reading, word: Callable[[dict[str, Any]], str] | None = None) -> None:
        super().__init__(raw={})
        self.read = read
        self.word = word or (lambda facts: json.dumps(facts, ensure_ascii=False))

    async def interpret(self, prompt: Any, inputs: Any, schema: Any, **kwargs: Any) -> Any:
        self.calls.append((prompt, kwargs["run"], inputs))
        if prompt == QUESTION_INTENT:
            return schema.model_validate(
                self.read(inputs["question"], json.loads(inputs["history"]))
            )
        return schema.model_validate({"answer": self.word(json.loads(inputs["facts"]))})


def _reads(question: str, history: dict[str, Any]) -> dict[str, Any]:
    """A faithful reader: a PO or RFQ number, "đó" for the case discussed."""
    found = re.search(r"([A-Za-z]{2,4}[\s-]+(?:PO|RFQ)[\w\s-]*\d)", question, re.IGNORECASE)
    if "quá hạn" in question:
        return {"kind": "overdue"}
    if "việc" in question:
        return {"kind": "my_work"}
    if "giá bao nhiêu" in question:
        return {"kind": "out_of_scope"}
    kind = "quote_status" if "RFQ" in question.upper() or "báo giá" in question else "order_status"
    if found:
        return {"kind": kind, "reference": found.group(1)}
    return {"kind": kind, "about_previous": "đó" in question}


def _world(model: Any) -> World:
    return open_world(REPO, SampleSet.of(REPO, None), CALLERS, model=model, measured=False)


async def _orders(world: World) -> World:
    await world.process_each(AN, ["M01", "M04", "M09"])
    return world


async def test_a_po_written_loosely_is_found_answered_from_its_facts_and_kept() -> None:
    model = Scripted(_reads)
    world = await _orders(_world(model))
    view = await world.services.assistant.ask(AN.context(), "PO nrv po 26 0457 tới đâu rồi?")
    turn = view.turn
    assert (turn.kind, turn.answered_by) == (QuestionKind.ORDER_STATUS, "model")
    assert [c.label for c in turn.cites] == ["PO NRV-PO-26-0457"]
    facts = json.loads(turn.answer)
    assert facts["po_no"] == "NRV-PO-26-0457" and facts["status"] == "Chờ PIC tự kiểm"
    # No amount reaches the facts, whoever asks.
    assert not {"amount", "price", "unit_price", "total"} & set(facts)
    _, run, _ = model.calls[0]
    assert (run.tenant_id, run.actor_id) == (ALPHA.tenant_id.value, AN.user_id)
    kept = await world.services.assistant.session(AN.context(), view.session_id)
    assert [t.question for t in kept.turns] == ["PO nrv po 26 0457 tới đâu rồi?"]


async def test_that_po_resolves_to_the_case_the_conversation_is_on() -> None:
    model = Scripted(_reads)
    world = await _orders(_world(model))
    first = await world.services.assistant.ask(AN.context(), "PO VLX-PO-2609-0118 sao rồi?")
    second = await world.services.assistant.ask(
        AN.context(), "PO đó đã xác nhận chưa?", first.session_id
    )
    assert [c.label for c in second.turn.cites] == ["PO VLX-PO-2609-0118"]
    # The model saw the earlier turn as history, and the case by its label.
    history = json.loads(model.calls[-2][2]["history"])
    assert history["case_in_conversation"] == "PO VLX-PO-2609-0118"
    assert history["earlier_turns"][0]["reference"] == "VLX-PO-2609-0118"
    assert second.turn.seq == 2


async def test_that_po_with_nothing_discussed_asks_which_rather_than_guessing() -> None:
    world = await _orders(_world(Scripted(_reads)))
    view = await world.services.assistant.ask(AN.context(), "PO đó sao rồi?")
    assert view.turn.cites == [] and "PO nào" in view.turn.answer


async def test_a_number_no_case_holds_is_not_found_and_names_nothing_else() -> None:
    world = await _orders(_world(Scripted(_reads)))
    view = await world.services.assistant.ask(AN.context(), "PO NRV-PO-26-9999 tới đâu?")
    assert view.turn.cites == [] and "Không tìm thấy" in view.turn.answer
    # A part of a number is no number.
    assert not same_reference("0457", "NRV-PO-26-0457")
    assert same_reference("nrv po 26/0457", "NRV-PO-26-0457")


async def test_another_tenant_asking_for_the_po_finds_nothing() -> None:
    world = await _orders(_world(Scripted(_reads)))
    view = await world.services.assistant.ask(OUTSIDER.context(BETA), "PO NRV-PO-26-0457?")
    assert view.turn.cites == [] and "NRV-PO-26-0457" not in view.turn.answer.replace(
        "Không tìm thấy PO NRV-PO-26-0457", ""
    )


async def test_a_quote_request_is_answered_by_its_number() -> None:
    world = await _orders(_world(Scripted(_reads)))
    view = await world.services.assistant.ask(AN.context(), "Báo giá QRL-RFQ-2609-03 thế nào?")
    facts = json.loads(view.turn.answer)
    assert facts["request_no"] == "QRL-RFQ-2609-03" and facts["status"] == "Đã soạn YCBG"


async def test_my_work_lists_the_callers_items_with_their_next_step() -> None:
    world = await _orders(_world(Scripted(_reads)))
    view = await world.services.assistant.ask(AN.context(), "Tôi còn việc gì?")
    facts = json.loads(view.turn.answer)
    assert facts["question_kind"] == "my_work" and facts["count"] == 2
    assert {i["next_step"] for i in facts["items"]} == {ACTION["self_check"]}
    assert len(view.turn.cites) == 2


async def test_nothing_overdue_is_said_plainly() -> None:
    world = await _orders(_world(Scripted(_reads, word=lambda facts: "x" * 0 + "Không có.")))
    view = await world.services.assistant.ask(AN.context(), "Việc nào quá hạn?")
    assert view.turn.kind is QuestionKind.OVERDUE and view.turn.cites == []


async def test_out_of_scope_says_what_dw1_answers_and_words_nothing() -> None:
    model = Scripted(_reads)
    world = await _orders(_world(model))
    view = await world.services.assistant.ask(AN.context(), "Cáp CB-2006 giá bao nhiêu?")
    assert CATALOG in view.turn.answer and view.turn.answered_by == "code"
    assert [c[0] for c in model.calls] == [QUESTION_INTENT]


async def test_without_a_model_dw1_says_it_did_not_understand_and_guesses_nothing() -> None:
    world = await _orders(_world(Recorded(failure=ModelUnavailableError("down"))))
    view = await world.services.assistant.ask(AN.context(), "PO NRV-PO-26-0457?")
    assert view.turn.cites == [] and "chưa hiểu" in view.turn.answer
    assert view.turn.kind is QuestionKind.OUT_OF_SCOPE


@pytest.mark.parametrize(
    "wording",
    [
        lambda facts: f"PO {facts['po_no']}: đơn giá 12,5 USD.",
        lambda facts: f"PO {facts['po_no']} giao ngày 31/12/2026.",
    ],
)
async def test_a_wording_with_an_amount_or_a_figure_not_in_the_facts_gives_codes_sentence(
    wording: Callable[[dict[str, Any]], str],
) -> None:
    world = await _orders(_world(Scripted(_reads, word=wording)))
    view = await world.services.assistant.ask(AN.context(), "PO NRV-PO-26-0457?")
    assert view.turn.answered_by == "code"
    assert view.turn.answer.startswith("PO NRV-PO-26-0457 (rev 0) của khách NRV: Chờ PIC tự kiểm.")


async def test_a_session_is_its_persons_own() -> None:
    world = await _orders(_world(Scripted(_reads)))
    view = await world.services.assistant.ask(AN.context(), "PO NRV-PO-26-0457?")
    with pytest.raises(NotFoundError):
        await world.services.assistant.session(READER.context(), view.session_id)
    with pytest.raises(NotFoundError):
        await world.services.assistant.ask(READER.context(), "PO đó?", view.session_id)
    assert await world.services.assistant.sessions(READER.context()) == []
    assert [s.session_id for s in await world.services.assistant.sessions(AN.context())] == [
        view.session_id
    ]


# ---------------------------------------------------- held to their owners --


def _glossary(heading: str) -> dict[str, str]:
    text = (REPO / "packages/python/dw_sales/CONTEXT.md").read_text(encoding="utf-8")
    section = text.split(f"## {heading}\n", 1)[1].split("\n## ", 1)[0]
    rows = [line.strip("|").split("|") for line in section.splitlines() if line.startswith("|")]
    return {r[0].strip().strip("`"): r[1].strip() for r in rows[2:]}


def _screen(name: str) -> dict[str, str]:
    text = (REPO / "apps/web/app/sales/_lib/labels.ts").read_text(encoding="utf-8")
    body = text.split(f"export const {name} = {{", 1)[1].split("} as const", 1)[0]
    return dict(re.findall(r"^\s+([a-z_]+): \"([^\"]+)\",", body, re.MULTILINE))


def test_the_words_are_the_glossarys_and_the_work_lists() -> None:
    assert _glossary("Order case states") == ORDER_STATE
    assert _glossary("Quote case states") == QUOTE_STATE
    assert _screen("ACTION") == ACTION


def test_the_kinds_are_the_ones_the_table_admits() -> None:
    migration = next((REPO / "db/migrations/versions").glob("e0940c90ce04_*.py"))
    admitted = re.search(r'_KINDS = "\(([^)]*)\)"', migration.read_text(encoding="utf-8"))
    assert admitted is not None
    assert set(re.findall(r"'([a-z_]+)'", admitted.group(1))) == {k.value for k in QuestionKind}


@pytest.mark.parametrize(
    "ref, budget, variables",
    [
        (QUESTION_INTENT, INTENT_TOKENS, {"question": "", "history": ""}),
        (ASSISTANT_ANSWER, ANSWER_TOKENS, {"question": "", "facts": ""}),
    ],
)
def test_each_prompt_is_the_one_the_step_names_and_fits_its_room(
    ref: Any, budget: int, variables: dict[str, str]
) -> None:
    from dw_agent_runtime.model.prompts import PromptRegistry

    prompts = PromptRegistry()
    prompts.load_directory(REPO / "configs" / "prompts")
    rendered = prompts.render(
        ref.prompt_id, ref.version, variables, tenant_id=ALPHA.tenant_id.value
    )
    assert estimated_tokens(rendered.system + rendered.user) < budget


async def test_the_service_refuses_another_persons_session_even_from_a_leaky_store() -> None:
    """The store's RLS keeps another person's session out; the service says so
    again, so a policy dropped by mistake still leaks nothing."""
    from contextlib import asynccontextmanager

    from dw_sales.application.assistant import AssistantService
    from dw_sales.evals.assistant_memory import MemoryAssistantStore, _Held

    world = await _orders(_world(Scripted(_reads)))
    held = _Held()

    @asynccontextmanager
    async def everyone(context: Any) -> Any:
        yield MemoryAssistantStore(held)

    service = world.services.assistant
    leaky = AssistantService(
        everyone,
        service.gate,
        service.orders,
        service.quotes,
        service.overview,
        service.model,
        service.clock,
        service.ids,
        service.worker_id,
        service.worker_version,
    )
    view = await leaky.ask(AN.context(), "PO NRV-PO-26-0457?")
    with pytest.raises(NotFoundError):
        await leaky.session(READER.context(), view.session_id)
    with pytest.raises(NotFoundError):
        await leaky.ask(READER.context(), "PO đó?", view.session_id)


async def test_who_reads_no_case_asks_nothing_and_sees_no_session() -> None:
    """Leadership's overview alone (`sales_viewer`) reads aggregates, never a
    case: the assistant refuses it where the service decides."""
    import uuid as _uuid

    from dw_kernel.errors import PermissionDeniedError
    from dw_sales.application.access import SalesScopes
    from dw_sales.evals.graders import Caller

    viewer = Caller(
        _uuid.UUID(int=0x5E),
        "Trần Quản Lý",
        "viewer@alpha.local",
        frozenset({SalesScopes.OVERVIEW_READ}),
    )
    world = await _orders(_world(Scripted(_reads)))
    with pytest.raises(PermissionDeniedError):
        # A question outside the list reaches no case query, whose own check
        # would refuse it: only the assistant's does.
        await world.services.assistant.ask(viewer.context(), "Cáp CB-2006 giá bao nhiêu?")
    with pytest.raises(PermissionDeniedError):
        await world.services.assistant.sessions(viewer.context())


# ------------------------------------------------------------- as it comes --


class Writing(Scripted):
    """`Scripted`, its wording arriving a few characters at a time. ``fails``
    stops it after that many characters, as a model that dies mid-sentence."""

    def __init__(
        self,
        read: Reading,
        word: Callable[[dict[str, Any]], str],
        fails: int | None = None,
    ) -> None:
        super().__init__(read, word)
        self.fails = fails
        self.closed = False

    async def stream_field(
        self, prompt: Any, inputs: Any, schema: Any, field: str, **kwargs: Any
    ) -> AsyncGenerator[str, None]:
        self.calls.append((prompt, kwargs["run"], inputs))
        text = self.word(json.loads(inputs["facts"]))
        try:
            for start in range(0, len(text), 3):
                if self.fails is not None and start >= self.fails:
                    raise ModelUnavailableError("died")
                yield text[start : start + 3]
        finally:
            self.closed = True


async def _turn(world: World, question: str) -> list[Any]:
    return [event async for event in world.services.assistant.stream(AN.context(), question)]


def _said(events: list[Any]) -> str:
    return "".join(e.text for e in events if isinstance(e, ChatDelta))


QUESTION = "PO NRV-PO-26-0457 tới đâu rồi?"


async def test_a_wording_arrives_word_by_word_and_is_what_the_turn_keeps() -> None:
    model = Writing(_reads, lambda facts: f"PO {facts['po_no']} đang {facts['status']} rồi")
    world = await _orders(_world(model))
    events = await _turn(world, QUESTION)
    assert [e.key for e in events if isinstance(e, ChatStep)] == ["read", "look"]
    assert len([e for e in events if isinstance(e, ChatDelta)]) > 3
    assert model.closed
    done = events[-1]
    assert isinstance(done, ChatDone)
    assert done.view.turn.answer == _said(events)
    assert done.view.turn.answered_by == "model"
    kept = await world.services.assistant.session(AN.context(), done.view.session_id)
    assert kept.turns[0].answer == _said(events)


async def test_the_step_is_said_before_the_model_is_asked() -> None:
    model = Writing(_reads, lambda facts: "xong")
    world = await _orders(_world(model))
    stream = world.services.assistant.stream(AN.context(), QUESTION)
    first = await anext(stream)
    assert isinstance(first, ChatStep) and model.calls == []
    await stream.aclose()


@pytest.mark.parametrize(
    "tail", ["vào ngày 2099-01-01 nhé", "giá USD ổn", "giảm 7% nhé"], ids=["figure", "code", "pct"]
)
async def test_a_wording_that_stops_being_checkable_is_replaced_and_never_shown(
    tail: str,
) -> None:
    """The stream's own guard: the unchecked word reaches no one, and the turn
    keeps code's sentence, not the words that had been shown."""
    model = Writing(_reads, lambda facts: f"Hồ sơ đang được xử lý {tail} thêm chữ")
    world = await _orders(_world(model))
    events = await _turn(world, QUESTION)
    assert _said(events).startswith("Hồ sơ đang")
    for bad in tail.split():
        if any(c.isdigit() for c in bad) or bad in {"USD", "7%"}:
            assert bad not in _said(events)
    replaced = [e for e in events if isinstance(e, ChatReplace)]
    assert len(replaced) == 1
    done = events[-1]
    assert isinstance(done, ChatDone)
    assert done.view.turn.answered_by == "code"
    assert done.view.turn.answer == replaced[0].text
    assert "NRV-PO-26-0457" in replaced[0].text
    # A wording nobody will read is not written to its end.
    assert model.closed


async def test_a_model_that_dies_mid_sentence_gives_codes_sentence_in_its_place() -> None:
    model = Writing(_reads, lambda facts: "Hồ sơ đang được xử lý bình thường nhé", fails=12)
    world = await _orders(_world(model))
    events = await _turn(world, QUESTION)
    assert _said(events) and any(isinstance(e, ChatReplace) for e in events)
    done = events[-1]
    assert isinstance(done, ChatDone) and done.view.turn.answered_by == "code"


async def test_a_model_that_dies_before_a_word_gives_codes_sentence_as_the_answer() -> None:
    model = Writing(_reads, lambda facts: "Hồ sơ", fails=0)
    world = await _orders(_world(model))
    events = await _turn(world, QUESTION)
    assert not any(isinstance(e, ChatReplace) for e in events)
    done = events[-1]
    assert isinstance(done, ChatDone)
    assert _said(events) == done.view.turn.answer and done.view.turn.answered_by == "code"


async def test_out_of_scope_streams_the_catalog_and_asks_for_no_wording() -> None:
    model = Writing(_reads, lambda facts: "không được gọi")
    world = await _orders(_world(model))
    events = await _turn(world, "Cáp giá bao nhiêu một mét?")
    assert CATALOG in _said(events)
    assert all(prompt != ASSISTANT_ANSWER for prompt, _, _ in model.calls)


async def test_a_turn_left_early_is_not_kept() -> None:
    model = Writing(_reads, lambda facts: "Hồ sơ đang được xử lý bình thường nhé")
    world = await _orders(_world(model))
    stream = world.services.assistant.stream(AN.context(), QUESTION)
    async for event in stream:
        if isinstance(event, ChatDelta):
            break
    await stream.aclose()
    assert model.closed
    assert await world.services.assistant.sessions(AN.context()) == []


async def test_who_reads_no_case_is_refused_before_the_first_event() -> None:
    """The route takes the first event before it answers 200."""
    import uuid as _uuid

    from dw_sales.application.access import SalesScopes
    from dw_sales.evals.graders import Caller

    viewer = Caller(
        _uuid.UUID(int=0x5E),
        "Trần Quản Lý",
        "viewer@alpha.local",
        frozenset({SalesScopes.OVERVIEW_READ}),
    )
    world = await _orders(_world(Writing(_reads, lambda facts: "x")))
    stream = world.services.assistant.stream(viewer.context(), QUESTION)
    with pytest.raises(PermissionDeniedError):
        await anext(stream)


async def test_another_persons_session_is_refused_before_the_first_event() -> None:
    world = await _orders(_world(Writing(_reads, lambda facts: "x")))
    view = await world.services.assistant.ask(AN.context(), QUESTION)
    stream = world.services.assistant.stream(READER.context(), QUESTION, view.session_id)
    with pytest.raises(NotFoundError):
        await anext(stream)
