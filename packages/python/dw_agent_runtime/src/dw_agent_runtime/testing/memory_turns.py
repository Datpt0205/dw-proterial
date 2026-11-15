"""Agent turns in one process: the real `AgentTurnKit` over a given chat model.

For a context's evals and unit tests, which run without a database or a model
server. What runs is what a deployment runs: the shipped tool specs, toolsets
and prompts (`configs/`), `ToolExecutor` (authorize, validate, execute,
validate, audit), every platform middleware and the turn's ceiling. Only the
model (a scripted `MockChatModel`, a recorded replay, or the live model in an
eval's live lane) and the stores (`MemoryToolExecutions`, the runtime's
in-memory audit) are replaced.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from langchain_core.language_models import BaseChatModel

from dw_agent_runtime.adapters.agent_turn import AgentTurnKit
from dw_agent_runtime.autonomy import AutonomyApprovalPolicy
from dw_agent_runtime.executor import ToolExecutor
from dw_agent_runtime.model.budget import RunBudgetLedger
from dw_agent_runtime.model.copy import load_runtime_copy
from dw_agent_runtime.model.profiles import ModelProfileRegistry
from dw_agent_runtime.model.prompts import PromptRegistry
from dw_agent_runtime.testing.memory_runtime import MemoryToolExecutions
from dw_agent_runtime.tool_specs import ToolSpecRegistry
from dw_agent_runtime.tools import ToolRegistry
from dw_agent_runtime.toolsets import ToolsetRegistry
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.ports import PlatformUnitOfWorkFactory

# The copy the API and the worker frame tools in (`RUNTIME_COPY_CONFIG`).
RUNTIME_COPY = "runtime@1.7.0.yaml"


@dataclass(frozen=True)
class GivenChatModel:
    """A `ChatModelFactory` answering every profile with one model."""

    model: BaseChatModel

    def resolve(self, profile_id: str) -> BaseChatModel:
        return self.model


def memory_turn_kit(
    configs: Path,
    model: BaseChatModel,
    *,
    uow_factory: PlatformUnitOfWorkFactory,
    clock: UtcClock,
    ids: IdGenerator,
    executions: MemoryToolExecutions | None = None,
) -> AgentTurnKit:
    """An `AgentTurnKit` over ``model``, with what ``configs`` ships."""
    copy = load_runtime_copy(configs / "copy" / RUNTIME_COPY)
    profiles = ModelProfileRegistry()
    profiles.load_directory(configs / "models")
    prompts = PromptRegistry()
    prompts.load_directory(configs / "prompts")
    tool_specs = ToolSpecRegistry(copy=copy)
    tool_specs.load_directory(configs / "tools")
    toolsets = ToolsetRegistry()
    toolsets.load_directory(configs / "toolsets")
    tools = ToolRegistry()
    return AgentTurnKit(
        chat_models=GivenChatModel(model),
        tools=tools,
        executor=ToolExecutor(
            registry=tools,
            execution_store=executions or MemoryToolExecutions(),
            uow_factory=uow_factory,
            clock=clock,
            id_generator=ids,
            approval_policy=AutonomyApprovalPolicy(),
        ),
        tool_specs=tool_specs,
        toolsets=toolsets,
        prompts=prompts,
        copy=copy,
        budget=RunBudgetLedger(),
        profiles=profiles,
    )
