"""`dw_node_failure_total` is emitted, once per failed run, under the node it failed in.

Declared in `dw_observability.metrics` for months and emitted by nothing. The
node comes from the note LangGraph adds to an exception for each task it passes
through, so the first tests below run the real library: a release that rewords
the note turns them red instead of silently emptying the metric.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict

import pytest
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from dw_agent_runtime.adapters.langgraph_runner import failed_node
from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.testing.demo_graph import DEMO_WORKER_YAML
from dw_agent_runtime.testing.memory_runtime import MemoryRuntime
from dw_kernel.ports import FixedClock, SequentialIdGenerator
from dw_observability.metrics import DW_NODE_FAILURE_TOTAL, DW_RUN_TOTAL
from dw_observability.telemetry import RecordingTelemetry

pytestmark = pytest.mark.unit

WORKER = "demo_approval"
NOW = datetime(2026, 10, 15, 9, 0, tzinfo=UTC)


class State(TypedDict, total=False):
    steps: int


def _ok(state: State) -> State:
    return {"steps": 1}


def _boom(state: State) -> State:
    raise ValueError("the supplier API answered 500")


def _failing_graph() -> StateGraph:  # type: ignore[type-arg]
    """`prepare` succeeds, then `enrich` runs a subgraph whose own node fails."""
    inner: StateGraph = StateGraph(State)  # type: ignore[type-arg]
    inner.add_node("call_supplier", _boom)
    inner.add_edge(START, "call_supplier")
    inner.add_edge("call_supplier", END)
    graph: StateGraph = StateGraph(State)  # type: ignore[type-arg]
    graph.add_node("prepare", _ok)
    graph.add_node("enrich", inner.compile())
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "enrich")
    graph.add_edge("enrich", END)
    return graph


def _passing_graph() -> StateGraph:  # type: ignore[type-arg]
    graph: StateGraph = StateGraph(State)  # type: ignore[type-arg]
    graph.add_node("prepare", _ok)
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", END)
    return graph


async def test_the_library_names_the_worker_graphs_node_a_failure_came_out_of() -> None:
    with pytest.raises(ValueError) as caught:
        await _failing_graph().compile().ainvoke({"steps": 0})

    assert failed_node(caught.value) == "enrich"


def test_a_failure_outside_any_node_names_none() -> None:
    assert failed_node(ValueError("settling failed")) is None
    plain = ValueError("x")
    plain.add_note("some other library's note")
    assert failed_node(plain) is None


def _runtime(tmp_path: Path, graph: Any) -> tuple[MemoryRuntime, RecordingTelemetry]:
    telemetry = RecordingTelemetry()
    runtime = MemoryRuntime.build(
        clock=FixedClock(NOW), ids=SequentialIdGenerator(), telemetry=telemetry
    )
    runtime.graphs.register(WORKER, "1.0.0", graph)
    config = tmp_path / f"{WORKER}.yaml"
    config.write_text(DEMO_WORKER_YAML, encoding="utf-8")
    runtime.workers.load_file(config)
    return runtime, telemetry


def _run_context() -> RunContext:
    return RunContext(
        run_id=uuid.uuid4(),
        tenant_id=uuid.UUID(int=2),
        workspace_id=uuid.UUID(int=3),
        actor_id=uuid.UUID(int=4),
        worker_id=WORKER,
        worker_version="1.0.0",
        channel="web",
        plan_id="professional",
        roles=frozenset({"member"}),
        scopes=frozenset(),
        trace_id="trace-1",
    )


def _node_failures(telemetry: RecordingTelemetry) -> list[dict[str, Any]]:
    return [attrs for name, _, attrs in telemetry.metrics if name == DW_NODE_FAILURE_TOTAL]


async def test_a_run_that_fails_in_a_node_counts_that_node(tmp_path: Path) -> None:
    runtime, telemetry = _runtime(tmp_path, _failing_graph)

    with pytest.raises(ValueError):
        await runtime.runner.start(run_context=_run_context(), input_payload={"steps": 0})

    assert _node_failures(telemetry) == [
        {"worker": WORKER, "node": "enrich", "error_type": "ValueError"}
    ]


async def test_a_streamed_run_that_fails_in_a_node_counts_it_too(tmp_path: Path) -> None:
    """The streamed path settles on its own task (`_drive`), not in `start`."""
    runtime, telemetry = _runtime(tmp_path, _failing_graph)

    chunks = await runtime.runner.stream(run_context=_run_context(), input_payload={"steps": 0})
    with pytest.raises(ValueError):
        async for _ in chunks:
            pass
    await runtime.runner.drain()

    assert [a["node"] for a in _node_failures(telemetry)] == ["enrich"]


async def test_a_run_that_succeeds_counts_no_node_failure(tmp_path: Path) -> None:
    runtime, telemetry = _runtime(tmp_path, _passing_graph)

    await runtime.runner.start(run_context=_run_context(), input_payload={"steps": 0})

    assert _node_failures(telemetry) == []
    assert any(name == DW_RUN_TOTAL for name, _, _ in telemetry.metrics)


def _review(state: State) -> State:
    interrupt({"approval_type": "demo.dispatch", "reason": "check before dispatch"})
    return {}


def _failing_after_approval() -> StateGraph:  # type: ignore[type-arg]
    graph: StateGraph = StateGraph(State)  # type: ignore[type-arg]
    graph.add_node("review", _review)
    graph.add_node("dispatch", _boom)
    graph.add_edge(START, "review")
    graph.add_edge("review", "dispatch")
    graph.add_edge("dispatch", END)
    return graph


async def test_a_resumed_run_that_fails_in_a_node_counts_it_too(tmp_path: Path) -> None:
    runtime, telemetry = _runtime(tmp_path, _failing_after_approval)
    context = _run_context()
    await runtime.runner.start(run_context=context, input_payload={"steps": 0})
    assert _node_failures(telemetry) == []

    with pytest.raises(ValueError):
        await runtime.runner.resume(
            run_context=context, run_id=context.run_id, resume_payload={"approved": True}
        )

    assert [a["node"] for a in _node_failures(telemetry)] == ["dispatch"]
