"""Runtime ports: workflow runner and model gateway.

LangGraph and provider SDK adapters implement these in phase 2; workflow nodes
and application handlers depend only on the protocols.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Literal, Protocol, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from dw_agent_runtime.contracts import RunContext

OutputT = TypeVar("OutputT", bound=BaseModel)

RouteKind = Literal["auto", "structured_extraction", "reasoning", "deep_reasoning"]


class ModelRequest(BaseModel):
    """Provider-neutral request for a structured model call."""

    model_config = ConfigDict(frozen=True)

    task: str
    prompt_id: str
    prompt_version: str
    variables: dict[str, str] = {}
    model_profile: str = "balanced"
    max_output_tokens: int | None = None
    # "auto" preserves legacy routing (task=="reasoning" -> reasoning route).
    route_kind: RouteKind = "auto"


class ModelGateway(Protocol):
    """Single entry point for LLM calls; output is always schema-validated."""

    async def generate_structured(
        self,
        request: ModelRequest,
        output_type: type[OutputT],
        *,
        run_context: RunContext,
    ) -> OutputT: ...


class TracedModelGateway(ModelGateway, Protocol):
    """Gateway that can also surface the model's visible reasoning text.

    ``generate_structured_traced`` returns ``(output, reasoning)`` where
    reasoning is "" when the routed model does not emit reasoning_content.
    """

    async def generate_structured_traced(
        self,
        request: ModelRequest,
        output_type: type[OutputT],
        *,
        run_context: RunContext,
    ) -> tuple[OutputT, str]: ...


class RunAllowancePort(Protocol):
    """How many runs a day a plan grants — the limit, not the count.

    The split is deliberate and it is what keeps the two packages independent.
    This package owns ``platform.worker_runs`` and can therefore count what a
    tenant has started; it has no business knowing what a subscription includes.
    The platform owns the plan catalogue and can answer the limit; it has no
    business reading another context's table. So the consumer declares this,
    the composition root satisfies it, and neither imports the other.

    ``None`` means this plan sets no limit, which is a real answer — an
    unmetered internal tenant — and not the same as a limit of zero.
    """

    def runs_per_day(self, plan_id: str) -> int | None: ...

    def spend_usd_per_day(self, plan_id: str) -> Decimal | None:
        """What this plan may spend in a day, or ``None`` for unmetered.

        Counting runs bounds how often a tenant asks; it does not bound what
        the asking costs. A plan of twenty runs a day is twenty chances to spend
        without limit, because the per-run ceiling caps one loop and nothing
        caps the day. Same split as above: the platform owns the plan and
        answers the limit, this package owns `worker_runs` and answers the spend.
        """
        ...


class StreamingWorkflowRunnerPort(Protocol):
    """Runs a workflow while emitting its progress, for chat-style channels."""

    async def stream(
        self,
        *,
        run_context: RunContext,
        input_payload: dict[str, object],
    ) -> AsyncIterator[dict[str, object]]:
        """Claim the thread and start the run; the iterator observes it.

        Awaited rather than iterated, so a thread already carrying an unfinished
        run is refused with `ConflictError` before the caller has committed to a
        response. One thread is one checkpoint: a second run on it would invoke
        the same thread with new input and overwrite whatever the first was
        waiting on.
        """
        ...


class WorkflowRunnerPort(Protocol):
    """Starts and resumes durable, checkpointed workflow runs."""

    def hosts(self, *, worker_id: str, worker_version: str, graph_version: str) -> bool:
        """Whether this process can resume that exact run.

        Keyed on the versions recorded when the run started, not on whatever the
        worker config names today: resuming replays the graph the run began on
        and the worker settings it began under. Both have to still be registered
        here, and callers must ask this before spending an approval decision --
        asking about only one of them let a deploy strand a run for ever.
        """
        ...

    async def start(
        self,
        *,
        run_context: RunContext,
        input_payload: dict[str, object],
    ) -> UUID: ...

    async def resume(
        self,
        *,
        run_context: RunContext,
        run_id: UUID,
        resume_payload: dict[str, object],
    ) -> None: ...
