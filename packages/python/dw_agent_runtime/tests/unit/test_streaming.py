"""Words reach a person as they are written, and only once they are checked."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Sequence

import httpx
import pytest
from pydantic import BaseModel, Field

from dw_agent_runtime.adapters.model_interpretation import GatewayInterpretation
from dw_agent_runtime.adapters.openai_compatible import OpenAICompatibleAdapter
from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.gateway import InMemoryUsageRecorder, ModelUsage, RoutingModelGateway
from dw_agent_runtime.model.interpretation import ModelUnavailableError, PromptRef
from dw_agent_runtime.model.profiles import ModelProfile, ModelProfileRegistry, Provider
from dw_agent_runtime.model.prompts import PromptArtifact, PromptRegistry
from dw_agent_runtime.model.streaming import (
    ChatDelta,
    ChatDone,
    ChatEvent,
    ChatStep,
    JsonStringField,
    StreamedAnswer,
    WordingRefusedError,
    opened_stream,
    released,
)
from dw_agent_runtime.ports import ModelOutputInvalidError, ModelRequest
from dw_kernel.errors import InfrastructureError

pytestmark = pytest.mark.unit


class Answer(BaseModel):
    answer: str = Field(min_length=1, max_length=40)


async def _pieces(*pieces: str) -> AsyncGenerator[str, None]:
    for piece in pieces:
        yield piece


async def _all(stream: AsyncGenerator[str, None]) -> list[str]:
    return [piece async for piece in stream]


# ---------------------------------------------------------- the JSON field --


@pytest.mark.parametrize(
    "raw",
    [
        '{"answer": "PO 12 đã nhận"}',
        '{\n  "answer" : "dòng 1\\ndòng 2 \\"trích\\" \\\\ \\u00e9 \\ud83d\\ude00"\n}',
        '```json\n{"answer":"trong rào"}\n```',
    ],
)
def test_a_field_reads_the_same_whatever_the_chunks(raw: str) -> None:
    """A provider cuts its stream anywhere, inside an escape included."""
    whole = json.loads(raw[raw.index("{") : raw.rindex("}") + 1])["answer"]
    for size in range(1, len(raw) + 1):
        field = JsonStringField("answer")
        read = "".join(field.feed(raw[i : i + size]) for i in range(0, len(raw), size))
        assert read == whole, size


def test_another_field_of_the_same_name_inside_a_value_is_not_the_field() -> None:
    field = JsonStringField("answer")
    raw = '{"note": "\\"answer\\": \\"giả\\"", "answer": "thật"}'
    assert field.feed(raw) == "thật"


def test_a_key_written_twice_is_read_once() -> None:
    field = JsonStringField("answer")
    assert field.feed('{"answer": "một", "answer": "hai"}') == "một"


def test_text_after_the_field_closes_is_not_read() -> None:
    field = JsonStringField("answer")
    assert field.feed('{"answer": "xong", "other": "không"}') == "xong"


# ------------------------------------------------------------ the release --


async def test_each_word_is_released_once_the_whole_so_far_passes() -> None:
    asked: list[str] = []

    def allowed(text: str) -> bool:
        asked.append(text)
        return True

    out = await _all(released(_pieces("PO đ", "ang ", "chờ ", "duyệt"), allowed))
    assert "".join(out) == "PO đang chờ duyệt"
    # Words, not the provider's chunks: "đ" never reached anyone alone.
    assert out[0] == "PO "
    assert asked[-1] == "PO đang chờ duyệt"


async def test_a_word_that_fails_never_leaves() -> None:
    """The figure check is on whole words, so a number is never shown cut."""
    seen: list[str] = []

    def allowed(text: str) -> bool:
        return "99" not in text

    with pytest.raises(WordingRefusedError):
        async for piece in released(_pieces("PO đã ", "nhận 9", "9 cái rồi"), allowed):
            seen.append(piece)
    assert "".join(seen) == "PO đã nhận "


async def test_the_last_word_is_checked_too() -> None:
    """Nothing follows it, so no whitespace ever releases it."""
    seen: list[str] = []
    with pytest.raises(WordingRefusedError):
        async for piece in released(_pieces("Còn 7"), lambda text: "7" not in text):
            seen.append(piece)
    assert seen == ["Còn "]


async def test_a_refused_word_closes_what_it_was_reading() -> None:
    """Else the model writes on to the end, holding its one slot, for no one."""
    closed: list[bool] = []

    async def source() -> AsyncGenerator[str, None]:
        try:
            yield "sai "
            yield "còn nữa "
        finally:
            closed.append(True)

    with pytest.raises(WordingRefusedError):
        await _all(released(source(), lambda text: False))
    assert closed == [True]


# ---------------------------------------------------------------- the wire --


def _sse(*chunks: dict[str, object]) -> bytes:
    lines = [f"data: {json.dumps(c, ensure_ascii=False)}\n\n" for c in chunks]
    return ("".join(lines) + "data: [DONE]\n\n").encode()


def _delta(text: str) -> dict[str, object]:
    return {"choices": [{"delta": {"content": text}}]}


class _Upstream(httpx.AsyncByteStream):
    """A provider's body, noting whether it was closed."""

    def __init__(self, body: bytes) -> None:
        self.body = body
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for i in range(0, len(self.body), 7):
            yield self.body[i : i + 7]

    async def aclose(self) -> None:
        self.closed = True


def _adapter(
    monkeypatch: pytest.MonkeyPatch, upstream: _Upstream, status: int = 200
) -> list[bytes]:
    bodies: list[bytes] = []

    def handle(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content)
        return httpx.Response(status, stream=upstream)

    real = httpx.AsyncClient

    def client(**kwargs: object) -> httpx.AsyncClient:
        return real(transport=httpx.MockTransport(handle), **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "AsyncClient", client)
    return bodies


def _gateway(adapter: object) -> tuple[RoutingModelGateway, InMemoryUsageRecorder]:
    profiles = ModelProfileRegistry()
    route = {"provider": "onprem", "model": "m", "timeout_seconds": 5, "max_input_tokens": 100}
    profiles.register(
        ModelProfile.model_validate(
            {
                "schema_version": "1.0",
                "profile_id": "p",
                "routing_policy_version": "1.0.0",
                "structured_extraction": route,
                "reasoning": route,
                "budgets": {"max_input_tokens_per_run": 100000, "max_cost_usd_per_run": 1},
            }
        )
    )
    prompts = PromptRegistry()
    prompts.register(
        PromptArtifact.model_validate(
            {
                "schema_version": "1.0",
                "prompt_id": "t",
                "version": "1.0.0",
                "system": "nói",
                "template": "{q}",
                "variables": frozenset({"q"}),
            }
        )
    )
    recorder = InMemoryUsageRecorder()
    gateway = RoutingModelGateway(
        profiles=profiles,
        prompts=prompts,
        adapters={"onprem": adapter},  # type: ignore[dict-item]
        usage_recorder=recorder,
        default_profile="p",
    )
    return gateway, recorder


_REQUEST = ModelRequest(
    task="structured_extraction",
    prompt_id="t",
    prompt_version="1.0.0",
    variables={"q": "x"},
    model_profile="p",
    max_output_tokens=50,
)


def _run() -> RunContext:
    return RunContext(
        run_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        actor_id=uuid.uuid4(),
        worker_id="w",
        worker_version="1.0.0",
        channel="web",
        plan_id="professional",
        roles=frozenset({"member"}),
        scopes=frozenset(),
        trace_id="t",
    )


async def test_the_gateway_streams_text_then_the_validated_answer_and_records_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    usage = {"prompt_tokens": 11, "completion_tokens": 7}
    upstream = _Upstream(
        _sse(
            _delta('{"answer": "'),
            _delta("Đã "),
            _delta('nhận"}'),
            {"choices": [], "usage": usage},
        )
    )
    bodies = _adapter(monkeypatch, upstream)
    adapter = OpenAICompatibleAdapter("http://model/v1", "k", provider=Provider.ONPREM)
    gateway, recorder = _gateway(adapter)

    out = [piece async for piece in gateway.stream_structured(_REQUEST, Answer, run_context=_run())]

    assert "".join(p for p in out if isinstance(p, str)) == '{"answer": "Đã nhận"}'
    assert out[-1] == Answer(answer="Đã nhận")
    sent = json.loads(bodies[0])
    assert sent["stream"] is True
    assert sent["stream_options"] == {"include_usage": True}
    assert upstream.closed
    [(_, spent)] = recorder.records
    assert (spent.input_tokens, spent.output_tokens) == (11, 7)


async def test_what_a_thinking_model_thinks_is_not_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thought: dict[str, object] = {"choices": [{"delta": {"reasoning_content": "giá là 9 USD"}}]}
    _adapter(monkeypatch, _Upstream(_sse(thought, _delta('{"answer": "Đã nhận"}'))))
    adapter = OpenAICompatibleAdapter("http://model/v1", "k", provider=Provider.ONPREM)
    gateway, _ = _gateway(adapter)
    out = [p async for p in gateway.stream_structured(_REQUEST, Answer, run_context=_run())]
    assert "USD" not in "".join(p for p in out if isinstance(p, str))
    assert out[-1] == Answer(answer="Đã nhận")


async def test_a_stream_is_charged_when_the_provider_reports_no_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spend the provider does not report is still spend: the ceiling reads it."""
    _adapter(monkeypatch, _Upstream(_sse(_delta('{"answer": "Đã nhận đủ hàng"}'))))
    adapter = OpenAICompatibleAdapter("http://model/v1", "k", provider=Provider.ONPREM)
    gateway, recorder = _gateway(adapter)
    async for _ in gateway.stream_structured(_REQUEST, Answer, run_context=_run()):
        pass
    [(_, spent)] = recorder.records
    assert spent.input_tokens > 0
    assert spent.output_tokens > 0


async def test_an_answer_outside_the_schema_fails_at_the_end_of_the_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _adapter(monkeypatch, _Upstream(_sse(_delta('{"answer": ""}'))))
    adapter = OpenAICompatibleAdapter("http://model/v1", "k", provider=Provider.ONPREM)
    gateway, _ = _gateway(adapter)
    with pytest.raises(ModelOutputInvalidError):
        async for _ in gateway.stream_structured(_REQUEST, Answer, run_context=_run()):
            pass


async def test_a_provider_refusal_is_an_infrastructure_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _adapter(monkeypatch, _Upstream(b"no"), status=503)
    adapter = OpenAICompatibleAdapter("http://model/v1", "k", provider=Provider.ONPREM)
    gateway, _ = _gateway(adapter)
    with pytest.raises(InfrastructureError):
        async for _ in gateway.stream_structured(_REQUEST, Answer, run_context=_run()):
            pass


async def test_leaving_a_stream_early_closes_the_call_and_still_charges_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A person who closes the tab frees the GPU; the tokens were spent."""
    upstream = _Upstream(_sse(_delta('{"answer": "Đã '), _delta("nhận "), _delta('rồi"}')))
    _adapter(monkeypatch, upstream)
    adapter = OpenAICompatibleAdapter("http://model/v1", "k", provider=Provider.ONPREM)
    gateway, recorder = _gateway(adapter)
    stream = gateway.stream_structured(_REQUEST, Answer, run_context=_run())
    await anext(stream)
    await stream.aclose()
    assert upstream.closed
    assert len(recorder.records) == 1


async def test_an_adapter_that_cannot_stream_answers_once() -> None:
    class Whole:
        provider_name = "onprem"

        async def complete_json(
            self, *_: object, **__: object
        ) -> tuple[dict[str, object], ModelUsage, str | None]:
            return {"answer": "cả câu"}, ModelUsage("onprem", "m", 1, 1), None

    gateway, _ = _gateway(Whole())
    out: Sequence[object] = [
        piece async for piece in gateway.stream_structured(_REQUEST, Answer, run_context=_run())
    ]
    assert out == [Answer(answer="cả câu")]


def test_a_finished_stream_carries_what_the_adapter_parsed() -> None:
    usage = ModelUsage("onprem", "m", 1, 2)
    assert StreamedAnswer({"answer": "x"}, usage).usage is usage


# ---------------------------------------------------------------- the doors --


def _door(gateway: object) -> GatewayInterpretation:
    return GatewayInterpretation(gateway, "p", 100)  # type: ignore[arg-type]


async def _field(door: GatewayInterpretation) -> list[str]:
    return await _all(
        door.stream_field(
            PromptRef("t", "1.0.0"), {"q": "x"}, Answer, "answer", run=_run(), max_output_tokens=50
        )
    )


async def test_the_door_gives_the_field_as_it_is_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _adapter(monkeypatch, _Upstream(_sse(_delta('{"answer": "Đã '), _delta('nhận"}'))))
    adapter = OpenAICompatibleAdapter("http://model/v1", "k", provider=Provider.ONPREM)
    gateway, _ = _gateway(adapter)
    assert "".join(await _field(_door(gateway))) == "Đã nhận"


async def test_text_the_schema_does_not_read_as_the_answer_is_no_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A key written twice: the reader saw the first, the schema keeps the
    last, and what a person read is not what was validated."""
    raw = '{"answer": "một", "answer": "hai"}'
    _adapter(monkeypatch, _Upstream(_sse(_delta(raw))))
    adapter = OpenAICompatibleAdapter("http://model/v1", "k", provider=Provider.ONPREM)
    gateway, _ = _gateway(adapter)
    with pytest.raises(ModelUnavailableError):
        await _field(_door(gateway))


async def test_a_provider_failure_is_model_unavailable_at_the_door(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _adapter(monkeypatch, _Upstream(b"no"), status=503)
    adapter = OpenAICompatibleAdapter("http://model/v1", "k", provider=Provider.ONPREM)
    gateway, _ = _gateway(adapter)
    with pytest.raises(ModelUnavailableError):
        await _field(_door(gateway))


async def test_a_gateway_that_cannot_stream_gives_the_field_whole() -> None:
    class Whole:
        async def generate_structured(self, *_: object, **__: object) -> Answer:
            return Answer(answer="cả câu")

    assert await _field(_door(Whole())) == ["cả câu"]


# ---------------------------------------------------------------- the frames --


async def test_a_refusal_before_the_first_event_is_raised_to_the_route() -> None:
    async def refused() -> AsyncGenerator[ChatEvent[Answer], None]:
        raise PermissionError("no")
        yield ChatStep(key="x", title="x")

    async def keep(view: Answer) -> Answer:
        return view

    with pytest.raises(PermissionError):
        await opened_stream(refused(), keep)


async def test_the_turn_is_recorded_before_it_is_said_to_be_done() -> None:
    kept: list[Answer] = []

    async def events() -> AsyncGenerator[ChatEvent[Answer], None]:
        yield ChatStep(key="read", title="Đọc")
        yield ChatDelta(text="xong")
        yield ChatDone(Answer(answer="xong"))

    async def keep(view: Answer) -> Answer:
        kept.append(view)
        return view

    frames = [frame async for frame in await opened_stream(events(), keep)]
    assert [f.split(b"\n")[0] for f in frames] == [b"event: step", b"event: delta", b"event: done"]
    assert kept == [Answer(answer="xong")]
    assert b'"answer":"xong"' in frames[-1]
