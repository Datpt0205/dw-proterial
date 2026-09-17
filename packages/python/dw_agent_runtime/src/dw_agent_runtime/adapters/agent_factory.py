"""The one place a platform agent is assembled.

Every bounded context used to build its own: `create_agent(...)` with whichever
middleware its author remembered. The six middlewares in this package each close
a hole that was found in production — a builtin tool that bypassed the executor,
a tool nobody declared passing a scope check by not being declared, a worker
prompt that silently deleted the skills catalogue, a sibling approval nobody was
shown, a tool failure that killed the turn and lost the transcript, a binary
file that made the provider reject the whole request. A context that assembles
its own agent and forgets one reopens that hole, and nothing tells it so.

So assembly is a platform artifact, not a per-context habit.

What is and is not a contract here, measured rather than assumed. All 720
orderings of the six were run against the six properties they protect, and not
one ordering broke any of them: none of these middlewares reads what another one
writes, so their order is free. What is NOT free is their PRESENCE — removing any
single one breaks exactly the property it owns. That is what this factory
guarantees and what `test_agent_factory.py` pins. An order will become a contract
the day a middleware reads another's output (a summariser that must see files
already stripped is the first coming), and it should be asserted then, by a test
that fails, rather than declared now by one that cannot.

Built on `create_agent`, not `create_deep_agent`. Measured on the pinned
deepagents: the deep variant installs eight builtin tools on its own —
`delete`, `edit_file`, `glob`, `grep`, `ls`, `read_file`, `task`, `write_file` —
every one of which reaches outside the run without passing `ToolExecutor`, and
therefore without authorization, idempotency or audit. The set is not even
stable: comments written against an earlier release named `execute` and not
`delete`. Installing a library's tools and then stripping them is a denylist
against a list the library is free to change. `create_agent` installs nothing,
so the platform adds exactly what it controls.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, ModelRequest
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore

from dw_agent_runtime.adapters.langchain_tools import (
    OfferedToolsOnlyMiddleware,
    OneApprovalPerStepMiddleware,
    PlatformToolErrorsMiddleware,
    ScopedToolsMiddleware,
    UnreadableFilesMiddleware,
    platform_tools,
)
from dw_agent_runtime.adapters.system_prompt import WorkerSystemPrompt
from dw_agent_runtime.contracts import RunContext, ToolDefinition
from dw_agent_runtime.executor import ToolExecutor
from dw_agent_runtime.model.copy import RuntimeCopy
from dw_agent_runtime.tools import ToolRegistry

__all__ = ["AgentSpec", "build_agent", "platform_middleware"]


@dataclass(frozen=True)
class AgentSpec:
    """Everything one worker's agent is built from.

    `offered` is the resolved toolset — the definitions this worker pins, not
    every tool the registry holds. It is handed to the tool builder and to every
    middleware as one list, which is the point: a scope filter reading the whole
    registry while the tool list reads the toolset is how a tool registered for
    another worker becomes callable here.
    """

    model: BaseChatModel
    offered: Sequence[ToolDefinition]
    registry: ToolRegistry
    executor: ToolExecutor
    copy: RuntimeCopy
    # Prefixes the approval type a gated tool raises, so the approvals screen
    # can route a decision back to the context that owns it.
    approval_type_prefix: str
    # Rendered per model call, not once at build: the prompt names today's date
    # and the screen in view, and the agent is compiled once per process.
    render_prompt: Callable[[ModelRequest[Any]], str]


def platform_middleware(spec: AgentSpec) -> list[AgentMiddleware[Any, Any]]:
    """The six middlewares every platform agent carries.

    Exposed on its own so a context that must add middleware of its own extends
    this list rather than rebuilding it — rebuilding is exactly how one gets
    dropped.

    Any middleware added to this list must let `GraphBubbleUp` through. Measured:
    a single `awrap_tool_call` that catches `BaseException` and returns a message
    swallows the `interrupt()` an approval raises, and the run carries on as if
    a person had said yes. `PlatformToolErrorsMiddleware` is safe because it
    subclasses `ToolErrorMiddleware`, which re-raises it; a hand-written
    `try/except` is not.
    """
    offered = list(spec.offered)
    return [
        WorkerSystemPrompt(spec.render_prompt),
        UnreadableFilesMiddleware(),
        OfferedToolsOnlyMiddleware(offered),
        ScopedToolsMiddleware(offered),
        # NOTE for Mốc 2: this computes which tools are gated ONCE, here, from
        # `ToolDefinition.requires_approval()` — which takes no arguments and so
        # cannot know the worker, tenant or autonomy level of the run. That is
        # correct today and wrong the moment approval depends on the run: the
        # agent is compiled once per process, so a set frozen at build time
        # cannot serve two tenants at two autonomy levels. The gate must move to
        # a per-call decision read from the run context.
        OneApprovalPerStepMiddleware(offered, copy=spec.copy),
        PlatformToolErrorsMiddleware(offered, copy=spec.copy),
    ]


def build_agent(
    spec: AgentSpec,
    *,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    store: BaseStore | None = None,
) -> Any:
    """Assemble a platform agent from one worker's spec.

    Returns the compiled graph `create_agent` produces. The checkpointer is
    optional because a graph a runner hosts is compiled by the runner, which
    passes its own; one built for a test or a one-shot call has none.
    """
    offered = list(spec.offered)
    return create_agent(
        model=spec.model,
        tools=platform_tools(
            offered,
            spec.registry,
            spec.executor,
            approval_type_prefix=spec.approval_type_prefix,
            copy=spec.copy,
        ),
        middleware=platform_middleware(spec),
        context_schema=RunContext,
        checkpointer=checkpointer,
        store=store,
    )
