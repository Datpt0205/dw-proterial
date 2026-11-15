"""A value's confidence from the tokens the model wrote (dw_sales ADR 0015).

The response below is in the shape Strata returned on 2026-11-16 for
``logprobs: true`` with a strict JSON schema (`docs/research/2026-11-16-less-
human-review.md`, "Measured after writing"): ``choices[0].logprobs.content``,
one ``{token, logprob, top_logprobs}`` per token. Its values are synthetic.
"""

from __future__ import annotations

import json
import math
import uuid
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from dw_agent_runtime.adapters.model_interpretation import GatewayInterpretation
from dw_agent_runtime.adapters.openai_compatible import OpenAICompatibleAdapter
from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.gateway import InMemoryUsageRecorder, RoutingModelGateway
from dw_agent_runtime.model.interpretation import PromptRef, ScoredInterpretationPort
from dw_agent_runtime.model.profiles import ModelProfile, ModelProfileRegistry, ModelRoute
from dw_agent_runtime.model.prompts import PromptArtifact, PromptRegistry, RenderedPrompt
from dw_agent_runtime.model.scoring import TokenLogprob, value_confidences, value_spans

_ANSWER = '{"lines": [{"line_no": 1, "family": "PVC", "colour": null, "span": ""}]}'
# How a tokenizer might cut the answer: the label "PVC" in two tokens, one of
# them carrying its opening quote.
_TOKENS = (
    ('{"lines": [{"line_no": ', -0.0),
    ("1", -0.01),
    (', "family": ', -0.0),
    ('"P', -0.2),
    ("VC", -0.1),
    ('", "colour": ', -0.0),
    ("null", -0.5),
    (', "span": ', -0.0),
    ('""', -0.3),
    ("}]}", -0.0),
)


def _tokens() -> list[TokenLogprob]:
    return [TokenLogprob(text, lp) for text, lp in _TOKENS]


def test_each_scalar_is_located_by_its_path() -> None:
    spans = value_spans(_ANSWER)
    assert _ANSWER[slice(*spans["lines.0.family"])] == "PVC"
    assert _ANSWER[slice(*spans["lines.0.line_no"])] == "1"
    assert _ANSWER[slice(*spans["lines.0.colour"])] == "null"
    start, end = spans["lines.0.span"]
    assert start == end


def test_a_value_is_scored_by_the_tokens_its_text_lies_in() -> None:
    scores = value_confidences(_tokens())
    # "P" and "VC": exp(-0.2 - 0.1).
    assert scores["lines.0.family"] == pytest.approx(math.exp(-0.3))
    assert scores["lines.0.colour"] == pytest.approx(math.exp(-0.5))
    assert scores["lines.0.line_no"] == pytest.approx(math.exp(-0.01))
    # An empty string by its quotes.
    assert scores["lines.0.span"] == pytest.approx(math.exp(-0.3))


def test_tokens_that_spell_no_object_score_nothing() -> None:
    assert value_confidences([TokenLogprob("not json", -0.1)]) == {}
    assert value_confidences([TokenLogprob('{"a": "unclosed', -0.1)]) == {}


def test_escapes_inside_a_string_do_not_end_it() -> None:
    text = '{"a": "say \\"hi\\"", "b": 2}'
    spans = value_spans(text)
    assert text[slice(*spans["a"])] == 'say \\"hi\\"'
    assert text[slice(*spans["b"])] == "2"


# ------------------------------------------------- the adapter and the door --


class _Line(BaseModel):
    line_no: int
    family: str | None
    colour: str | None
    span: str


class _Answer(BaseModel):
    lines: list[_Line]


def _response(*, logprobs: bool) -> dict[str, Any]:
    choice: dict[str, Any] = {"message": {"role": "assistant", "content": _ANSWER}}
    if logprobs:
        choice["logprobs"] = {
            "content": [{"token": text, "logprob": lp, "top_logprobs": []} for text, lp in _TOKENS]
        }
    return {"choices": [choice], "usage": {"prompt_tokens": 10, "completion_tokens": 10}}


def _serve(monkeypatch: pytest.MonkeyPatch, *, logprobs_back: bool) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=_response(logprobs=logprobs_back))

    real = httpx.AsyncClient

    def client(**kwargs: Any) -> httpx.AsyncClient:
        return real(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    return sent


def _route(*, logprobs: bool) -> ModelRoute:
    return ModelRoute(provider="onprem", model="m", logprobs=logprobs, max_input_tokens=1000)


_PROMPT = RenderedPrompt(prompt_id="p", version="1.0.0", system="s", user="u", checksum="c")


async def test_the_adapter_asks_for_logprobs_only_where_the_route_says(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _serve(monkeypatch, logprobs_back=True)
    adapter = OpenAICompatibleAdapter(base_url="http://model.test/v1", api_key="k")
    schema = _Answer.model_json_schema()
    _, _, _, tokens = await adapter.complete_json_scored(
        _PROMPT, schema, _route(logprobs=True), max_output_tokens=100
    )
    assert sent[-1]["logprobs"] is True
    assert tokens is not None and "".join(t.text for t in tokens) == _ANSWER
    _, _, _, none = await adapter.complete_json_scored(
        _PROMPT, schema, _route(logprobs=False), max_output_tokens=100
    )
    assert "logprobs" not in sent[-1] and none is None
    await adapter.complete_json(_PROMPT, schema, _route(logprobs=True), max_output_tokens=100)
    assert "logprobs" not in sent[-1]


async def test_a_server_that_sends_no_logprobs_gives_no_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, logprobs_back=False)
    adapter = OpenAICompatibleAdapter(base_url="http://model.test/v1", api_key="k")
    _, _, _, tokens = await adapter.complete_json_scored(
        _PROMPT, _Answer.model_json_schema(), _route(logprobs=True), max_output_tokens=100
    )
    assert tokens is None


def _door(*, route_logprobs: bool) -> GatewayInterpretation:
    profiles = ModelProfileRegistry()
    profiles.register(
        ModelProfile(
            schema_version="1.0",
            profile_id="local",
            routing_policy_version="1.0.0",
            structured_extraction=_route(logprobs=route_logprobs),
            reasoning=_route(logprobs=False),
        )
    )
    prompts = PromptRegistry()
    prompts.register(
        PromptArtifact(
            schema_version="1.0", prompt_id="p", version="1.0.0", system="s", template="u"
        )
    )
    gateway = RoutingModelGateway(
        profiles=profiles,
        prompts=prompts,
        adapters={"onprem": OpenAICompatibleAdapter(base_url="http://model.test/v1", api_key="k")},
        usage_recorder=InMemoryUsageRecorder(),
        default_profile="local",
    )
    return GatewayInterpretation(gateway, "local", 1000)


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
        roles=frozenset(),
        scopes=frozenset(),
        trace_id="t44",
    )


async def test_the_door_returns_each_values_confidence_by_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, logprobs_back=True)
    door = _door(route_logprobs=True)
    assert isinstance(door, ScoredInterpretationPort)
    scored = await door.interpret_scored(
        PromptRef("p", "1.0.0"), {}, _Answer, run=_run(), max_output_tokens=100
    )
    assert scored.answer.lines[0].family == "PVC"
    assert scored.confidences is not None
    assert scored.confidences["lines.0.family"] == pytest.approx(math.exp(-0.3))


async def test_a_route_not_measured_for_logprobs_gives_no_confidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, logprobs_back=True)
    door = _door(route_logprobs=False)
    scored = await door.interpret_scored(
        PromptRef("p", "1.0.0"), {}, _Answer, run=_run(), max_output_tokens=100
    )
    assert scored.answer.lines[0].family == "PVC"
    assert scored.confidences is None
