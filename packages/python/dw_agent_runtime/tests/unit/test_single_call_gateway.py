"""Unit: a one-call run leaves nothing behind in the process's spend ledger.

Against the real `RoutingModelGateway` sharing one `RunBudgetLedger` — the
production shape — not a fake that records into the ledger on the test's
behalf, which would prove only that the fake cooperates.
"""

import uuid
from pathlib import Path

import pytest
from pydantic import BaseModel

from dw_agent_runtime.adapters.mock_model import MockModelAdapter
from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.budget import RunBudgetLedger
from dw_agent_runtime.model.gateway import InMemoryUsageRecorder, RoutingModelGateway
from dw_agent_runtime.model.profiles import ModelProfileRegistry
from dw_agent_runtime.model.prompts import PromptArtifact, PromptRegistry
from dw_agent_runtime.model.single_call import SingleCallModelGateway
from dw_agent_runtime.ports import ModelOutputInvalidError, ModelRequest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[5]


class Answer(BaseModel):
    answer: str


def _run_context() -> RunContext:
    return RunContext(
        run_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        actor_id=uuid.uuid4(),
        worker_id="demo.one_call",
        worker_version="1.0.0",
        channel="web",
        plan_id="professional",
        roles=frozenset({"member"}),
        scopes=frozenset(),
        trace_id="trace-1",
    )


def _gateways(adapter: MockModelAdapter) -> tuple[RoutingModelGateway, RunBudgetLedger]:
    profiles = ModelProfileRegistry()
    profiles.load_directory(REPO_ROOT / "configs" / "models")
    prompts = PromptRegistry()
    prompts.register(
        PromptArtifact.model_validate(
            {
                "schema_version": "1.0",
                "prompt_id": "demo.answer",
                "version": "1.0.0",
                "system": "Trả lời ngắn.",
                "template": "Câu hỏi: {question}",
                "variables": frozenset({"question"}),
            }
        )
    )
    ledger = RunBudgetLedger()
    gateway = RoutingModelGateway(
        profiles=profiles,
        prompts=prompts,
        adapters={"mock": adapter},
        usage_recorder=InMemoryUsageRecorder(),
        default_profile="balanced",
        budget=ledger,
    )
    return gateway, ledger


_REQUEST = ModelRequest(
    task="structured_extraction",
    prompt_id="demo.answer",
    prompt_version="1.0.0",
    variables={"question": "x"},
)


async def test_the_bare_gateway_keeps_one_entry_per_call() -> None:
    """The leak this wrapper exists for — if this stops holding, the wrapper
    may have become unnecessary and should be reconsidered, not kept by
    habit."""
    adapter = MockModelAdapter()
    adapter.register_builder("demo.answer", "1.0.0", lambda prompt: {"answer": "ok"})
    gateway, ledger = _gateways(adapter)

    for _ in range(3):
        await gateway.generate_structured(_REQUEST, Answer, run_context=_run_context())

    assert len(ledger.spend) == 3


async def test_a_one_call_run_is_forgotten_once_it_succeeds() -> None:
    adapter = MockModelAdapter()
    adapter.register_builder("demo.answer", "1.0.0", lambda prompt: {"answer": "ok"})
    gateway, ledger = _gateways(adapter)
    single = SingleCallModelGateway(inner=gateway, ledger=ledger)

    for _ in range(3):
        result = await single.generate_structured(_REQUEST, Answer, run_context=_run_context())
        assert result.answer == "ok"

    assert ledger.spend == {}


async def test_a_one_call_run_is_forgotten_when_the_call_fails() -> None:
    """Every attempt spent (and recorded) before the schema refused it — the
    entry must still go, or a failing prompt leaks faster than a working one."""
    adapter = MockModelAdapter()
    adapter.register_builder("demo.answer", "1.0.0", lambda prompt: {"wrong": True})
    gateway, ledger = _gateways(adapter)
    single = SingleCallModelGateway(inner=gateway, ledger=ledger)

    with pytest.raises(ModelOutputInvalidError):
        await single.generate_structured(_REQUEST, Answer, run_context=_run_context())

    assert ledger.spend == {}
