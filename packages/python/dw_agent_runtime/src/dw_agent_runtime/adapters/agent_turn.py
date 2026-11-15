"""`AgentTurnPort` over a platform agent (`agent_factory.build_agent`).

One turn is one invocation of an agent compiled once per process: the worker's
prompt (`WorkerSystemPrompt`, rendered with this turn's inputs, each contained
by the registry), the tools the worker's toolset pins (each call through
`ToolExecutor`), every platform middleware, and the turn's ceiling
(`TurnCeilingMiddleware` for calls and tokens; `asyncio.wait_for` here for
time). The answer is the turn's last assistant message, a JSON object validated
into the caller's schema; anything else is no usable answer.

The inputs reach the prompt through a context variable set for the turn: the
agent is compiled once, so they cannot be closed over, and `RunContext` is the
platform's, not a step's. A turn with none set renders nothing (the prompt's
variables do not match) and fails as no usable answer.

`AgentTurnKit` is what a process holds to build such turns: the tools a context
registers, the executor they run through, the specs and toolsets that say which
are offered, the chat model of the worker's profile, and the run's one spend
ledger. A composition root builds it; a context registers its tools on it and
asks it for a turn.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from langchain.agents.middleware import ModelRequest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.errors import GraphRecursionError
from pydantic import BaseModel, ValidationError

from dw_agent_runtime.adapters.agent_factory import AgentSpec, build_agent
from dw_agent_runtime.adapters.chat_model import ChatModelFactory
from dw_agent_runtime.adapters.openai_compatible import _extract_json_object
from dw_agent_runtime.adapters.skills import TurnSkills, skill_reader
from dw_agent_runtime.contracts import RunContext, ToolDefinition, WorkerDefinition
from dw_agent_runtime.executor import ToolExecutor
from dw_agent_runtime.model.agent_turn import (
    TurnCeiling,
    TurnCeilingReachedError,
)
from dw_agent_runtime.model.budget import BudgetExceededError, RunBudgetLedger
from dw_agent_runtime.model.copy import RuntimeCopy
from dw_agent_runtime.model.interpretation import ModelUnavailableError, PromptRef
from dw_agent_runtime.model.profiles import ModelProfileRegistry
from dw_agent_runtime.model.prompts import PromptRegistry
from dw_agent_runtime.registry import ConfigError
from dw_agent_runtime.tool_specs import ToolSpecRegistry
from dw_agent_runtime.tools import RegisteredTool, ToolRegistry
from dw_agent_runtime.toolsets import ToolsetRegistry
from dw_kernel.errors import TenantContextMissingError

__all__ = ["CHAT_ROUTE", "AgentTurnKit", "BoundedAgentTurn"]

_LOG = logging.getLogger("dw_agent_runtime.model")

# The profile route an agent turn talks through.
CHAT_ROUTE = "chat"
# The turn's one human message: code's words. What is read is in the prompt.
_ASK = "Read what you were given above and answer with the JSON object only."

_INPUTS: ContextVar[Mapping[str, str] | None] = ContextVar("dw_agent_turn_inputs", default=None)


def _turn_variables(request: ModelRequest[Any]) -> dict[str, str]:
    """The prompt variables of the turn in progress; none outside a turn."""
    return dict(_INPUTS.get() or {})


@dataclass(frozen=True)
class BoundedAgentTurn:
    """Implements `AgentTurnPort` with a compiled platform agent."""

    agent: Any
    prompt: PromptRef
    model_profile: str
    ceiling: TurnCeiling

    @property
    def route(self) -> str:
        return CHAT_ROUTE

    async def read[OutputT: BaseModel](
        self, inputs: Mapping[str, str], schema: type[OutputT], *, run: RunContext
    ) -> OutputT:
        token = _INPUTS.set(dict(inputs))
        try:
            state = await asyncio.wait_for(
                self.agent.ainvoke(
                    {"messages": [HumanMessage(_ASK)]},
                    context=run,
                    # A backstop only: the ceiling counts the calls, and a
                    # model call and a tool round are a few steps each.
                    config={"recursion_limit": 4 * self.ceiling.max_model_calls + 8},
                ),
                timeout=self.ceiling.max_seconds,
            )
        except TimeoutError:
            raise TurnCeilingReachedError("time") from None
        except GraphRecursionError:
            raise TurnCeilingReachedError("calls") from None
        except (TurnCeilingReachedError, BudgetExceededError, TenantContextMissingError):
            # The turn's ceiling is the step's to fall back on; the run's
            # budget stops the run; a run with no tenant is never degraded.
            raise
        except Exception as exc:
            raise self._unavailable(run, exc) from exc
        finally:
            _INPUTS.reset(token)
        return self._answer(state, schema, run)

    def _answer[OutputT: BaseModel](
        self, state: Mapping[str, Any], schema: type[OutputT], run: RunContext
    ) -> OutputT:
        messages = state.get("messages") or []
        last = messages[-1] if messages else None
        if not isinstance(last, AIMessage) or last.tool_calls:
            raise self._unavailable(run, ValueError("the turn ended without an answer"))
        try:
            return schema.model_validate(_extract_json_object(last.text))
        except (ValueError, ValidationError) as exc:
            raise self._unavailable(run, exc) from exc

    def _unavailable(self, run: RunContext, exc: Exception) -> ModelUnavailableError:
        # Ids and the error's kind only: never an input or an answer, which
        # are a customer's words.
        _LOG.warning(
            "agent turn unavailable for run %s (%s, %s): %s",
            run.run_id,
            self.prompt,
            self.model_profile,
            type(exc).__name__,
        )
        return ModelUnavailableError(type(exc).__name__)


@dataclass(frozen=True)
class AgentTurnKit:
    """What a process holds to build agent turns (module docstring)."""

    chat_models: ChatModelFactory
    tools: ToolRegistry
    executor: ToolExecutor
    tool_specs: ToolSpecRegistry
    toolsets: ToolsetRegistry
    prompts: PromptRegistry
    copy: RuntimeCopy
    # The process's one per-run ledger: a turn spends against its run's ceiling.
    budget: RunBudgetLedger
    profiles: ModelProfileRegistry
    # The tools registered as skill loaders (`register_skill_reader`): offered
    # only to a turn served skills, never to one that loads none.
    skill_readers: set[str] = field(default_factory=set)

    def definition(self, name: str, version: str) -> ToolDefinition:
        """A tool's definition from its spec in ``configs/tools``: its policy is
        the spec's, never the registering code's."""
        return self.tool_specs.definition(name, version)

    def register(self, tool: RegisteredTool) -> None:
        self.tools.register(tool)

    def register_skill_reader(self, definition: ToolDefinition) -> None:
        """The skill-loading tool under ``definition`` (`skills.skill_reader`),
        answered from the set served around each turn."""
        self.tools.register(skill_reader(definition))
        self.skill_readers.add(definition.name)

    def turn(
        self,
        worker: WorkerDefinition,
        prompt: PromptRef,
        ceiling: TurnCeiling,
        *,
        skills: TurnSkills | None = None,
    ) -> BoundedAgentTurn:
        """A turn of ``worker``'s agent under ``prompt``: the tools its toolset
        pins (`configs/toolsets/<worker_id>@<toolset_version>.yaml`), on the
        chat route of its default profile. Built once, at startup: a pin no
        tool was registered for fails here, not on the first message.

        Given ``skills``, the turn carries the skills catalogue and offers the
        skill-loading tool it names, which the toolset must pin; without, a
        skill loader the toolset pins is not offered (a turn that is served no
        skill has nothing to load)."""
        if worker.toolset_version is None:
            raise ConfigError(
                "a worker with no toolset has no agent turn",
                details={"worker_id": worker.worker_id},
            )
        toolset = self.toolsets.resolve(worker.worker_id, worker.toolset_version)
        offered = [
            d
            for d in self.tools.definitions_for(toolset.pins)
            if skills is not None or d.name not in self.skill_readers
        ]
        if skills is not None and not any(
            d.name == skills.read_tool and d.name in self.skill_readers for d in offered
        ):
            raise ConfigError(
                "a turn served skills needs its skill loader registered and pinned",
                details={"worker_id": worker.worker_id, "tool": skills.read_tool},
            )
        spec = AgentSpec(
            model=self.chat_models.resolve(worker.default_model_profile),
            offered=offered,
            registry=self.tools,
            executor=self.executor,
            copy=self.copy,
            approval_type_prefix=f"{worker.domain}.",
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.version,
            prompts=self.prompts,
            prompt_variables=_turn_variables,
            budget=self.budget,
            profiles=self.profiles,
            profile_id=worker.default_model_profile,
            ceiling=ceiling,
            skills=skills,
        )
        # No checkpointer, not even the host run's: a turn is one invocation,
        # and run inside a DW node it would otherwise checkpoint the customer's
        # words into that run's thread as a subgraph.
        agent = build_agent(spec, checkpointer=False)
        return BoundedAgentTurn(agent, prompt, worker.default_model_profile, ceiling)
