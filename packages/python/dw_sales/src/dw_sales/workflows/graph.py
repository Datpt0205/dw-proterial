"""DW1's graph: one run per thing DW1 is asked to do, pausing where a person decides.

Registered on the runtime seam as (`DW1_WORKER_ID`, `GRAPH_VERSION`) and run
by the worker `configs/workers/sales.yaml` pins, so a run records the graph
version it started on and a resume replays that exact one.

    START -> start -+-> END                      (processing; no cross-check needed)
                    +-> decide (interrupt) -> END

- **start** does the step the task names (`Dw1Task.kind`): processing the
  mailbox, submitting a quotation, recording a Bravo entry. A step that
  raises a decision returns what to ask (`DecisionAsked`).
- **decide** pauses on it. The runner turns the pause into a platform
  approval; the platform's decision resumes the node, which applies it to the
  case (`CaseDecisions.apply`). The pause is the node's first line, so the
  replay on resume does nothing twice.

No model is called here, and no tool is offered: DW1 reads documents with
deterministic parsers (spec decision 13), and its worker declares no
toolset, which is how ADR 0007's rule (a turn that reads a document gets no
outbound tool) holds today; `test_dw1_worker.py` turns red the day either
changes. Nodes take what they need by injection (`Dw1Steps`): no SQL, no
adapter.

The state keeps ids, versions, a hash and outcome codes. It is the run's
result row, so a comment or a reason a person typed is applied to the case
and never kept here (spec decision 8).
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Protocol, TypedDict

from dw_agent_runtime.approval_flow import ApproveAndResumeService
from dw_agent_runtime.context import access_context_from_run
from dw_agent_runtime.contracts import RunContext, WorkerDefinition
from dw_agent_runtime.registry import ConfigError, GraphRegistry, WorkerRegistry
from dw_platform.application.access_context import AccessContext
from dw_sales.application.decisions import CaseDecisions
from dw_sales.application.runs import APPROVAL_PREFIX, DecisionAsked, DecisionGiven, Dw1Task
from dw_sales.application.support import DW1_WORKER_ID

GRAPH_VERSION = "1.0.0"
STATE_SCHEMA_VERSION = "1.0"


class Dw1Steps(Protocol):
    """What the graph calls; `CaseDecisions` satisfies it."""

    async def process(
        self, context: AccessContext, message_id: str | None
    ) -> list[dict[str, str | None]]: ...

    async def submit_quote(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        *,
        case_version: int,
        quote_no: str,
        run_id: uuid.UUID,
    ) -> DecisionAsked: ...

    async def record_bravo_entry(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        *,
        case_version: int,
        so_no: str | None,
        entry_compared: bool,
        run_id: uuid.UUID,
    ) -> DecisionAsked | None: ...

    async def apply(
        self,
        context: AccessContext,
        asked: DecisionAsked,
        given: DecisionGiven,
        *,
        run_id: uuid.UUID,
    ) -> str: ...


class Dw1State(TypedDict, total=False):
    schema_version: str
    task: dict[str, Any]
    # "process": each message's disposition and its case, by id.
    processed: list[dict[str, str | None]]
    # What the run waits on: `DecisionAsked`, the approval's payload.
    asked: dict[str, Any]
    # How the run ended: "processed", "no_decision_needed", or the event the
    # decision wrote ("quote.approved", "order.returned", ...).
    outcome: str


def build_graph(steps: Dw1Steps) -> Any:
    """The uncompiled graph; the runner compiles it with its checkpointer.

    LangGraph is imported here, not at module level, so the module (and the
    `Dw1Steps` it declares) imports without the engine.
    """
    from langgraph.graph import END, START, StateGraph
    from langgraph.runtime import Runtime
    from langgraph.types import interrupt

    async def start(state: Dw1State, runtime: Runtime[RunContext]) -> Dw1State:
        task = Dw1Task.model_validate(state["task"])
        context = access_context_from_run(runtime.context)
        asked: DecisionAsked | None
        if task.kind == "process":
            processed = await steps.process(context, task.message_id)
            return {"processed": processed, "outcome": "processed"}
        if task.case_id is None or task.case_version is None:
            raise ValueError("a decision task names its case and the version it was made on")
        if task.kind == "quote_approval":
            if task.quote_no is None:
                raise ValueError("a quotation is submitted under its number")
            asked = await steps.submit_quote(
                context,
                task.case_id,
                case_version=task.case_version,
                quote_no=task.quote_no,
                run_id=runtime.context.run_id,
            )
        else:
            asked = await steps.record_bravo_entry(
                context,
                task.case_id,
                case_version=task.case_version,
                so_no=task.so_no,
                entry_compared=task.entry_compared,
                run_id=runtime.context.run_id,
            )
        if asked is None:
            return {"outcome": "no_decision_needed"}
        return {"asked": asked.payload()}

    async def decide(state: Dw1State, runtime: Runtime[RunContext]) -> Dw1State:
        answer = interrupt(state["asked"])
        given = DecisionGiven.model_validate(answer)
        outcome = await steps.apply(
            access_context_from_run(runtime.context),
            DecisionAsked.model_validate(state["asked"]),
            given,
            run_id=runtime.context.run_id,
        )
        return {"outcome": outcome}

    def after_start(state: Dw1State) -> str:
        return "decide" if state.get("asked") else END

    graph: Any = StateGraph(Dw1State, context_schema=RunContext)
    graph.add_node("start", start)
    graph.add_node("decide", decide)
    graph.add_edge(START, "start")
    graph.add_conditional_edges("start", after_start, ["decide", END])
    graph.add_edge("decide", END)
    return graph


def register(
    *,
    graphs: GraphRegistry,
    workers: WorkerRegistry,
    approvals: ApproveAndResumeService,
    steps: CaseDecisions,
    worker_file: Path,
) -> WorkerDefinition:
    """DW1 on a runtime: its graph, its worker, and its approvals' rules.

    The one place a composition root (the API, the eval runner) plugs DW1 in,
    so the three things that must agree are set together:

    - the graph, under the worker id the events name and the version here;
    - the worker config, which must pin exactly that graph (fails at startup,
      not on the first run);
    - every `sales.` approval strict (a second person who made none of the
      case, and a written comment), and checked by this context before it is
      recorded (`CaseDecisions.check`).
    """
    graphs.register(DW1_WORKER_ID, GRAPH_VERSION, lambda: build_graph(steps))
    loaded = workers.load_file(worker_file).definition
    if loaded.worker_id != DW1_WORKER_ID or loaded.graph_version != GRAPH_VERSION:
        raise ConfigError(
            f"{worker_file.name} must run {DW1_WORKER_ID}@{GRAPH_VERSION},"
            f" not {loaded.worker_id}@{loaded.graph_version}"
        )
    approvals.strict_approval_prefixes |= {APPROVAL_PREFIX}
    approvals.decision_guards[APPROVAL_PREFIX] = steps
    return loaded
