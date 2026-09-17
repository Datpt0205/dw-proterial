"""Context compaction: recorded, failure-tolerant, and never user-authored.

Each test pins one of the three things `PlatformSummarizationMiddleware` changes
about the library's `SummarizationMiddleware`, and each is written so that
undoing that change turns it red. The two properties the library already got
right — a pending approval survives, a history too long for one pass is still
compacted — are pinned too, so a future upgrade that breaks them is caught here
rather than in a customer's run.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, cast

import pytest
from fakes import NOW, FakeAuditRepo, FakeUoWFactory
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from test_agent_factory import PROFILE_ID, THREAD, _profiles, _spec
from test_langchain_tools import make_run_context

from dw_agent_runtime.adapters.agent_factory import platform_middleware
from dw_agent_runtime.adapters.chat_model import MockChatModel
from dw_agent_runtime.adapters.context_compaction import (
    COMPACTED_ACTION,
    PlatformSummarizationMiddleware,
)
from dw_agent_runtime.adapters.langchain_tools import platform_tools
from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.budget import BudgetExceededError, RunBudgetLedger
from dw_agent_runtime.model.copy import load_runtime_copy
from dw_agent_runtime.registry import ConfigError
from dw_kernel.ports import FixedClock, SequentialIdGenerator
from dw_platform.domain.audit import AuditEvent

pytestmark = pytest.mark.unit

_COPY_DIR = Path(__file__).resolve().parents[5] / "configs" / "copy"
COPY = load_runtime_copy(_COPY_DIR / "runtime@1.4.0.yaml")
SUMMARY = "Khách cần báo giá cho 3 máy chủ."

# Small, so a short scripted history crosses them.
TRIGGER_MESSAGES = 10
KEEP_MESSAGES = 4


def _history(turns: int) -> list[BaseMessage]:
    out: list[BaseMessage] = []
    for i in range(turns):
        out.append(HumanMessage(content=f"câu hỏi số {i}", id=f"h{i}"))
        out.append(AIMessage(content=f"trả lời số {i}", id=f"a{i}"))
    return out


def _summariser(reply: str = SUMMARY) -> MockChatModel:
    return MockChatModel(responses=[AIMessage(content=reply)], mock_reply=reply)


class _BrokenSummariser(MockChatModel):
    def _generate(self, *args: Any, **kwargs: Any) -> ChatResult:
        raise RuntimeError("nhà cung cấp tóm tắt đang sập")


class _FailingAudit(FakeAuditRepo):
    async def append(self, event: AuditEvent) -> None:
        raise RuntimeError("cơ sở dữ liệu audit không ghi được")


def _compactor(
    summariser: MockChatModel,
    audit: FakeAuditRepo | None = None,
    budget: RunBudgetLedger | None = None,
) -> tuple[PlatformSummarizationMiddleware, FakeAuditRepo]:
    repo = audit if audit is not None else FakeAuditRepo()
    middleware = PlatformSummarizationMiddleware(
        summariser,
        copy=COPY,
        uow_factory=FakeUoWFactory(audit_repo=repo),
        clock=FixedClock(NOW),
        ids=SequentialIdGenerator(),
        budget=budget if budget is not None else RunBudgetLedger(),
        profiles=_profiles(),
        profile_id=PROFILE_ID,
        summary_profile_id=PROFILE_ID,
        trigger=("messages", TRIGGER_MESSAGES),
        keep=("messages", KEEP_MESSAGES),
    )
    return middleware, repo


async def _run(middleware: PlatformSummarizationMiddleware, turns: int) -> list[BaseMessage]:
    agent: Any = create_agent(
        model=MockChatModel(responses=[AIMessage(content="xong")], mock_reply="xong"),
        tools=[],
        middleware=[middleware],
        context_schema=RunContext,
        checkpointer=InMemorySaver(),
    )
    await agent.ainvoke({"messages": _history(turns)}, THREAD, context=make_run_context())
    state = await agent.aget_state(THREAD)
    return cast(list[BaseMessage], state.values["messages"])


# ------------------------------------------------------------ still compacts --


async def test_a_long_history_is_compacted() -> None:
    """The fixes must not quietly switch compaction off — that would pass every
    test below by never doing the thing they guard."""
    middleware, _ = _compactor(_summariser())

    messages = await _run(middleware, turns=8)

    assert len(messages) < 16
    assert "h0" not in [m.id for m in messages]


async def test_a_short_history_is_left_alone() -> None:
    middleware, audit = _compactor(_summariser())

    messages = await _run(middleware, turns=2)

    assert [m.id for m in messages[:4]] == ["h0", "a0", "h1", "a1"]
    assert audit.events == []


# --------------------------------------------------------------- 1. recorded --


async def test_every_compaction_is_recorded_before_it_removes_anything() -> None:
    middleware, audit = _compactor(_summariser())

    await _run(middleware, turns=8)

    [event] = [e for e in audit.events if e.action == COMPACTED_ACTION]
    assert cast(int, event.details["removed_messages"]) > 0
    assert len(cast(str, event.details["removed_digest"])) == 64
    assert event.details["copy_version"] == "1.4.0"


async def test_the_same_history_digests_the_same() -> None:
    """A digest that changed between two identical compactions could never prove
    a kept copy was the thing removed."""
    first, audit_one = _compactor(_summariser())
    second, audit_two = _compactor(_summariser())

    await _run(first, turns=8)
    await _run(second, turns=8)

    assert (
        audit_one.events[0].details["removed_digest"]
        == audit_two.events[0].details["removed_digest"]
    )


async def test_history_is_never_removed_when_the_record_cannot_be_written() -> None:
    """The invariant: no record, no removal."""
    middleware, _ = _compactor(_summariser(), audit=_FailingAudit())

    messages = await _run(middleware, turns=8)

    assert "h0" in [m.id for m in messages]
    assert not any(SUMMARY in str(m.content) for m in messages)


# ----------------------------------------------------------- 2. fails open --


async def test_a_failing_summariser_leaves_history_intact_and_the_turn_alive() -> None:
    middleware, audit = _compactor(_BrokenSummariser(responses=[], mock_reply=""))

    messages = await _run(middleware, turns=8)

    assert "h0" in [m.id for m in messages]
    assert messages[-1].content == "xong"
    assert audit.events == []


# ------------------------------------------------- 4. no placeholder trades --


async def test_history_too_large_to_summarise_is_not_traded_for_a_placeholder() -> None:
    """The library removes the history and inserts "too long to summarize" in its
    place. Nothing summarisable means nothing is compacted."""
    middleware, audit = _compactor(_summariser())
    # Below any single message's size, so trimming leaves nothing to summarise.
    middleware.trim_tokens_to_summarize = 1

    messages = await _run(middleware, turns=8)

    assert "h0" in [m.id for m in messages]
    assert not any("too long" in str(m.content).lower() for m in messages)
    assert audit.events == []


# --------------------------------------------------- 5. counted and bounded --


async def test_a_summarys_tokens_count_against_the_runs_ceiling() -> None:
    """Measured before this existed: the summariser ran and the ledger held one
    entry — the agent's. A run that kept compacting spent on summaries unbounded."""
    ledger = RunBudgetLedger()
    middleware, _ = _compactor(_summariser(), budget=ledger)
    context = make_run_context().model_copy(update={"run_id": uuid.uuid4()})
    agent: Any = create_agent(
        model=MockChatModel(responses=[AIMessage(content="xong")], mock_reply="xong"),
        tools=[],
        middleware=[middleware],
        context_schema=RunContext,
        checkpointer=InMemorySaver(),
    )

    await agent.ainvoke({"messages": _history(8)}, THREAD, context=context)

    spend = ledger.spend[context.run_id]
    assert spend.calls == 1
    assert spend.input_tokens > 0


async def test_a_run_over_its_ceiling_is_stopped_not_waved_through_as_a_failed_summary() -> None:
    """The refusal must escape. Checked inside the fail-open block it would read as
    "the summariser failed, carry on", and the ceiling would stop nothing."""
    ledger = RunBudgetLedger()
    context = make_run_context().model_copy(update={"run_id": uuid.uuid4()})
    # Already past the ceiling before this step.
    ledger.record(context.run_id, input_tokens=10_000, output_tokens=0, cost_usd=0.0)
    middleware, audit = _compactor(_summariser(), budget=ledger)
    agent: Any = create_agent(
        model=MockChatModel(responses=[AIMessage(content="xong")], mock_reply="xong"),
        tools=[],
        middleware=[middleware],
        context_schema=RunContext,
        checkpointer=InMemorySaver(),
    )

    with pytest.raises(BudgetExceededError):
        await agent.ainvoke({"messages": _history(8)}, THREAD, context=context)
    assert audit.events == []


# ------------------------------------------------------- 3. not user-authored --


async def test_the_summary_is_framed_as_system_data_not_a_user_request() -> None:
    middleware, _ = _compactor(_summariser())

    messages = await _run(middleware, turns=8)

    [summary] = [m for m in messages if SUMMARY in str(m.content)]
    assert summary.additional_kwargs.get("dw_system_generated") is True
    # The frame, not just the summary: the text the model reads first says who
    # made this and that it is not an instruction.
    assert str(summary.content).index("HỆ THỐNG") < str(summary.content).index(SUMMARY)


# ----------------------------------------------- what the library got right --


class _ByCall(MockChatModel):
    """Keyed on how many times it was called, not on the history.

    `MockChatModel` picks its reply by counting assistant messages already in the
    conversation — so compacting the conversation changes which reply it gives,
    and a test built on it measures the script shifting, not the middleware.
    Measured: the first version of this test never paused at all.
    """

    count: int = 0

    def _generate(self, messages: list[BaseMessage], *args: Any, **kwargs: Any) -> ChatResult:
        self.calls.append(list(messages))
        self.count += 1
        if self.count == 1:
            reply = AIMessage(
                content="",
                tool_calls=[{"name": "crm__send_quote", "args": {"company": "a"}, "id": "g1"}],
                id=f"m{self.count}",
            )
        else:
            reply = AIMessage(content="xong", id=f"m{self.count}")
        reply.usage_metadata = {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}
        reply.response_metadata = {"model_name": "mock"}
        return ChatResult(generations=[ChatGeneration(message=reply)])


async def test_a_pending_approval_survives_compaction() -> None:
    spec = _spec(_ByCall(responses=[], mock_reply="xong"))
    compactor, _ = _compactor(_summariser())
    agent: Any = create_agent(
        model=spec.model,
        tools=platform_tools(
            list(spec.offered),
            spec.registry,
            spec.executor,
            approval_type_prefix="s.",
            copy=spec.copy,
        ),
        middleware=[*platform_middleware(spec), compactor],
        context_schema=RunContext,
        checkpointer=InMemorySaver(),
    )
    context = make_run_context().model_copy(update={"run_id": uuid.uuid4()})

    paused = await agent.ainvoke({"messages": _history(8)}, THREAD, context=context)
    assert "__interrupt__" in paused

    done = await agent.ainvoke(
        Command(resume={"approved": True, "comment": ""}), THREAD, context=context
    )
    messages = done["messages"]
    answered = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
    asked = {c["id"] for m in messages if isinstance(m, AIMessage) for c in m.tool_calls}
    assert asked <= answered, "a tool call lost its result to compaction"
    assert messages[-1].content == "xong"


# ------------------------------------------------------------------ guards --


def test_it_refuses_a_copy_without_the_summary_text() -> None:
    with pytest.raises(ConfigError, match=r"runtime@1\.4\.0"):
        PlatformSummarizationMiddleware(
            _summariser(),
            copy=load_runtime_copy(_COPY_DIR / "runtime@1.3.0.yaml"),
            uow_factory=FakeUoWFactory(),
            clock=FixedClock(NOW),
            ids=SequentialIdGenerator(),
            budget=RunBudgetLedger(),
            profiles=_profiles(),
            profile_id=PROFILE_ID,
            summary_profile_id=PROFILE_ID,
            trigger=("messages", TRIGGER_MESSAGES),
            keep=("messages", KEEP_MESSAGES),
        )


def test_the_synchronous_path_refuses_instead_of_compacting_unrecorded() -> None:
    middleware, _ = _compactor(_summariser())
    agent: Any = create_agent(
        model=MockChatModel(responses=[AIMessage(content="xong")], mock_reply="xong"),
        tools=[],
        middleware=[middleware],
        context_schema=RunContext,
    )

    with pytest.raises(NotImplementedError, match="async-only"):
        agent.invoke({"messages": _history(8)}, context=make_run_context())
