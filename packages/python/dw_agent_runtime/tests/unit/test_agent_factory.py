"""`build_agent` carries every property the six platform middlewares protect.

The contract is presence, not order — measured: all 720 orderings of the six were
run against these properties and none broke. So each test below is written to
fail when the middleware that owns its property is missing, and
`test_every_middleware_is_load_bearing` proves that for all six at once: drop any
single one and exactly its property goes red. A test here that could not fail
would be the same mistake as a middleware nobody installed.

Seven properties, six owners. "An approval pauses the run" belongs to no single
middleware — the pause comes from the tool itself — and is measured to catch the
one hazard presence does not cover: a seventh middleware that swallows it.
"""

from __future__ import annotations

from typing import Any

import pytest
from fakes import NOW, FakeExecutionStore, FakeUoWFactory
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel
from test_langchain_tools import COPY, LeadInput, LeadOutput, make_definition, make_run_context

from dw_agent_runtime.adapters.agent_factory import AgentSpec, build_agent, platform_middleware
from dw_agent_runtime.adapters.chat_model import MockChatModel
from dw_agent_runtime.adapters.langchain_tools import platform_tools
from dw_agent_runtime.contracts import RunContext, ToolDefinition
from dw_agent_runtime.executor import ToolExecutor
from dw_agent_runtime.tools import RegisteredTool, ToolRegistry
from dw_kernel.ports import FixedClock, SequentialIdGenerator

pytestmark = pytest.mark.unit

WORKER_PROMPT = "Bạn là trợ lý bán hàng của FDX."
THREAD = {"configurable": {"thread_id": "t-1"}}


async def _ok(payload: BaseModel, run_context: RunContext) -> LeadOutput:
    return LeadOutput(lead_id="ok")


async def _boom(payload: BaseModel, run_context: RunContext) -> LeadOutput:
    raise RuntimeError("nhà cung cấp sập")


READ = make_definition(name="crm.read_lead", side_effect_level="none")
BOOM = make_definition(name="crm.boom", side_effect_level="none")
GATED = make_definition(name="crm.send_quote", approval_policy="always")
# Registered, but not in this worker's toolset.
FOREIGN = make_definition(name="billing.refund")
ADMIN_ONLY = make_definition(name="crm.purge", required_scopes=frozenset({"crm.admin"}))


class _Builtin(BaseTool):
    """Stands in for a tool a harness would install without any worker asking."""

    name: str = "write_file"
    description: str = "Ghi một tệp."

    def _run(self, *args: Any, **kwargs: Any) -> str:
        return "ghi xong"


def _registry() -> tuple[ToolRegistry, ToolExecutor]:
    registry = ToolRegistry()
    for definition, handler in (
        (READ, _ok),
        (BOOM, _boom),
        (GATED, _ok),
        (FOREIGN, _ok),
        (ADMIN_ONLY, _ok),
    ):
        registry.register(
            RegisteredTool(
                definition=definition,
                input_model=LeadInput,
                output_model=LeadOutput,
                handler=handler,
            )
        )
    executor = ToolExecutor(
        registry=registry,
        execution_store=FakeExecutionStore(),
        uow_factory=FakeUoWFactory(),
        clock=FixedClock(NOW),
        id_generator=SequentialIdGenerator(),
    )
    return registry, executor


# The worker's toolset: FOREIGN is deliberately absent.
OFFERED: tuple[ToolDefinition, ...] = (READ, BOOM, GATED, ADMIN_ONLY)


def _spec(model: MockChatModel) -> AgentSpec:
    registry, executor = _registry()
    return AgentSpec(
        model=model,
        offered=OFFERED,
        registry=registry,
        executor=executor,
        copy=COPY,
        approval_type_prefix="sales_chat.",
        render_prompt=lambda request: WORKER_PROMPT,
    )


def _calling(tool: str) -> MockChatModel:
    return MockChatModel(
        responses=[
            AIMessage(
                content="", tool_calls=[{"name": tool, "args": {"company": "a"}, "id": "c1"}]
            ),
            AIMessage(content="xong"),
        ],
        mock_reply="[mock]",
    )


def _unreadable_file_message() -> HumanMessage:
    return HumanMessage(
        content=[
            {"type": "text", "text": "xem giúp tệp này"},
            {
                "type": "file",
                "mime_type": "application/octet-stream",
                "base64": "AAAA",
                "filename": "bao_gia.bin",
            },
        ]
    )


# --------------------------------------------------------------- properties --


async def test_only_the_workers_own_tools_are_offered() -> None:
    model = MockChatModel(responses=[AIMessage(content="xong")], mock_reply="[mock]")

    await build_agent(_spec(model)).ainvoke(
        {"messages": [HumanMessage("chào")]}, context=make_run_context()
    )

    assert "billing__refund" not in model.bound_tool_names
    assert "crm__read_lead" in model.bound_tool_names


async def test_a_tool_outside_the_runs_scopes_is_not_offered() -> None:
    model = MockChatModel(responses=[AIMessage(content="xong")], mock_reply="[mock]")

    await build_agent(_spec(model)).ainvoke(
        {"messages": [HumanMessage("chào")]}, context=make_run_context()
    )

    assert "crm__purge" not in model.bound_tool_names


async def test_the_worker_prompt_reaches_the_model_first() -> None:
    model = MockChatModel(responses=[AIMessage(content="xong")], mock_reply="[mock]")

    await build_agent(_spec(model)).ainvoke(
        {"messages": [HumanMessage("chào")]}, context=make_run_context()
    )

    assert model.system_prompts[0].startswith(WORKER_PROMPT)


async def test_a_file_the_model_cannot_read_never_reaches_it() -> None:
    model = MockChatModel(responses=[AIMessage(content="xong")], mock_reply="[mock]")

    await build_agent(_spec(model)).ainvoke(
        {"messages": [_unreadable_file_message()]}, context=make_run_context()
    )

    blocks = [
        block
        for message in model.calls[0]
        if isinstance(message.content, list)
        for block in message.content
    ]
    assert not any(isinstance(b, dict) and b.get("type") == "file" for b in blocks)


async def test_a_failing_tool_does_not_end_the_turn() -> None:
    model = _calling("crm__boom")

    state = await build_agent(_spec(model)).ainvoke(
        {"messages": [HumanMessage("tra lead")]}, context=make_run_context()
    )

    assert state["messages"][-1].content == "xong"


async def test_a_gated_tool_pauses_the_run_for_a_person() -> None:
    model = _calling("crm__send_quote")

    state = await build_agent(_spec(model), checkpointer=InMemorySaver()).ainvoke(
        {"messages": [HumanMessage("gửi báo giá")]}, THREAD, context=make_run_context()
    )

    assert "__interrupt__" in state


# ---------------------------------------------------------- the contract itself --


async def _properties(middleware: list[AgentMiddleware[Any, Any]]) -> dict[str, bool]:
    """The seven properties, measured against an arbitrary middleware list.

    Rebuilds the agent directly rather than through `build_agent`, because the
    point is to remove one middleware at a time and watch what breaks.
    """
    registry, executor = _registry()

    def agent(model: MockChatModel, **kwargs: Any) -> Any:
        tools = [
            *platform_tools(
                list(OFFERED), registry, executor, approval_type_prefix="sales_chat.", copy=COPY
            ),
            _Builtin(),
        ]
        return create_agent(
            model=model,
            tools=tools,
            middleware=middleware,
            context_schema=RunContext,
            **kwargs,
        )

    view = MockChatModel(responses=[AIMessage(content="xong")], mock_reply="[mock]")
    await agent(view).ainvoke(
        {"messages": [_unreadable_file_message()]}, context=make_run_context()
    )
    blocks = [b for m in view.calls[0] if isinstance(m.content, list) for b in m.content]

    failing = _calling("crm__boom")
    try:
        turn = await agent(failing).ainvoke(
            {"messages": [HumanMessage("x")]}, context=make_run_context()
        )
        survived = turn["messages"][-1].content == "xong"
    except Exception:
        survived = False

    gated = _calling("crm__send_quote")
    try:
        paused = "__interrupt__" in await agent(gated, checkpointer=InMemorySaver()).ainvoke(
            {"messages": [HumanMessage("x")]}, THREAD, context=make_run_context()
        )
    except Exception:
        paused = False

    # Two gated calls in ONE model step. Everything downstream of a pause assumes
    # exactly one: one approval row, one card, and a resume payload that carries
    # no interrupt id — so with two, the decision a person makes about one card
    # is consumed by whichever call reaches `interrupt()` first.
    siblings = MockChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "crm__send_quote", "args": {"company": "a"}, "id": "g1"},
                    {"name": "crm__send_quote", "args": {"company": "b"}, "id": "g2"},
                ],
            ),
            AIMessage(content="xong"),
        ],
        mock_reply="[mock]",
    )
    try:
        pending = await agent(siblings, checkpointer=InMemorySaver()).ainvoke(
            {"messages": [HumanMessage("x")]}, THREAD, context=make_run_context()
        )
        cards = len(pending.get("__interrupt__", ()))
    except Exception:
        cards = 0

    return {
        "builtin hidden": "write_file" not in view.bound_tool_names,
        "out-of-scope hidden": "crm__purge" not in view.bound_tool_names,
        "prompt first": view.system_prompts[0].startswith(WORKER_PROMPT),
        "unreadable file stripped": not any(
            isinstance(b, dict) and b.get("type") == "file" for b in blocks
        ),
        "failure survived": survived,
        "approval paused": paused,
        "one approval card per step": cards == 1,
    }


# Which property each of the six owns. Order matches `platform_middleware`.
OWNS = (
    "prompt first",
    "unreadable file stripped",
    "builtin hidden",
    "out-of-scope hidden",
    "one approval card per step",
    "failure survived",
)


async def test_the_full_stack_holds_every_property() -> None:
    spec = _spec(MockChatModel(responses=[AIMessage(content="xong")], mock_reply="[mock]"))

    measured = await _properties(platform_middleware(spec))

    assert measured == dict.fromkeys(measured, True), measured


@pytest.mark.parametrize("dropped", range(6))
async def test_every_middleware_is_load_bearing(dropped: int) -> None:
    """Drop any one of the six: the property it owns must go red.

    This is the test that makes the others mean something. It would pass
    vacuously if a property check could never fail — so it asserts the failure,
    not the success.
    """
    owned = OWNS[dropped]
    spec = _spec(MockChatModel(responses=[AIMessage(content="xong")], mock_reply="[mock]"))
    stack = platform_middleware(spec)
    del stack[dropped]

    measured = await _properties(stack)

    assert measured[owned] is False, f"dropping middleware #{dropped} did not break {owned!r}"


async def test_a_middleware_that_swallows_everything_loses_the_approval() -> None:
    """Why `platform_middleware` warns that additions must let GraphBubbleUp through.

    Presence is the contract for the six; this is the hazard a SEVENTH brings. A
    hand-written catch-all around a tool call eats the `interrupt()` an approval
    raises, and the run goes on as if somebody had said yes.
    """

    class SwallowEverything(AgentMiddleware[Any, Any]):
        async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
            try:
                return await handler(request)
            except BaseException:
                return ToolMessage(content="đã xử lý", tool_call_id=request.tool_call["id"])

    spec = _spec(MockChatModel(responses=[AIMessage(content="xong")], mock_reply="[mock]"))

    measured = await _properties([*platform_middleware(spec), SwallowEverything()])

    assert measured["approval paused"] is False
