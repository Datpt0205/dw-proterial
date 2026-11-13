"""`GatewayInterpretation` over a fake gateway (dw_sales ticket 28, lifted by
docs/adr/0013): which request it sends for the run, and that every way of
getting no answer is `ModelUnavailableError` while a budget refusal is not."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from pydantic import BaseModel

from dw_agent_runtime.adapters.model_interpretation import GatewayInterpretation
from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.budget import BudgetExceededError
from dw_agent_runtime.model.interpretation import (
    ModelUnavailableError,
    PromptRef,
    cut_to_tokens,
    estimated_tokens,
)
from dw_agent_runtime.ports import ModelOutputInvalidError, ModelRequest
from dw_kernel.errors import InfrastructureError, NotFoundError

pytestmark = pytest.mark.unit

PROMPT = PromptRef("ctx.question", "1.0.0")
RUN = RunContext(
    run_id=uuid.UUID(int=0x5EED),
    tenant_id=uuid.UUID(int=1),
    workspace_id=uuid.UUID(int=2),
    actor_id=uuid.UUID(int=0xA1),
    worker_id="ctx-dw",
    worker_version="1.0.0",
    channel="web",
    plan_id="professional",
    roles=frozenset(),
    scopes=frozenset(),
    trace_id="t28",
)


class _Answer(BaseModel):
    answer: str


# ------------------------------------------------ the gateway's adapter --


class _Gateway:
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.requests: list[tuple[ModelRequest, RunContext]] = []

    async def generate_structured(
        self, request: ModelRequest, output_type: type[Any], *, run_context: RunContext
    ) -> Any:
        self.requests.append((request, run_context))
        if self.failure is not None:
            raise self.failure
        return output_type.model_validate({"answer": "ok"})


async def _interpret(gateway: _Gateway) -> BaseModel:
    return await GatewayInterpretation(gateway, "onprem", 6000).interpret(
        PROMPT,
        {"question": "?"},
        _Answer,
        run=RUN,
        max_output_tokens=400,
    )


async def test_the_adapter_asks_the_gateway_on_the_workers_profile_for_the_run() -> None:
    gateway = _Gateway()
    await _interpret(gateway)

    ((request, run),) = gateway.requests
    assert run is RUN
    assert (request.prompt_id, request.prompt_version) == (
        PROMPT.prompt_id,
        PROMPT.version,
    )
    assert (request.model_profile, request.task, request.max_output_tokens) == (
        "onprem",
        "structured_extraction",
        400,
    )


@pytest.mark.parametrize(
    "failure",
    [
        InfrastructureError("model provider timed out"),
        ModelOutputInvalidError("model output failed schema validation"),
        NotFoundError("model provider not configured"),
    ],
)
async def test_every_way_of_getting_no_answer_is_model_unavailable(failure: Exception) -> None:
    with pytest.raises(ModelUnavailableError):
        await _interpret(_Gateway(failure))


async def test_a_budget_refusal_passes_through_the_adapter() -> None:
    with pytest.raises(BudgetExceededError):
        await _interpret(_Gateway(BudgetExceededError("run budget exceeded")))


# ------------------------------------------------------ the cut to fit --


def test_a_cut_keeps_whole_lines_so_1500_never_reads_as_15() -> None:
    """Hardcode audit finding 3: a cut inside a line made its end look like
    the end of a word, and a span "15" was found in "...15" cut from "1500"."""
    text = "Kính gửi phòng Mua hàng\nDây AWG24, số lượng 1500 cuộn\n" + "Ghi chú thêm\n" * 40
    for room in range(estimated_tokens(text) + 2):
        cut = cut_to_tokens(text, room)
        assert text.startswith(cut)
        assert estimated_tokens(cut) <= room
        assert cut in ("", text) or cut.endswith("\n"), (room, cut[-20:])
        assert "1500" in cut or "AWG24" not in cut


def test_a_text_that_fits_is_sent_whole_and_a_first_line_too_long_sends_nothing() -> None:
    assert cut_to_tokens("PR-2611-004 1500", 100) == "PR-2611-004 1500"
    assert cut_to_tokens("x" * 300 + "\nPR-2611-004", 50) == ""
