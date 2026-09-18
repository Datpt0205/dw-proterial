"""What this worker already knows, put in front of the model as data.

The read half of memory. Writing has worked since the provenance change and
nothing read it back, so a stored fact was a row nobody consulted — a control
that is configured and unenforced, which is the shape this repository keeps
producing.

Three decisions worth stating, because each is a boundary rather than a
preference:

**The run decides what is recalled, never the model.** Tenant, workspace,
clearance and subject all come off the `RunContext` the runner built from a
verified `AccessContext`. Nothing the model emits reaches the query. A tool that
let the agent ask for "memories about X" would be the same mistake as letting it
supply its own retrieval filter.

**Recalled text is untrusted.** It was written from documents a customer
supplied, so a sentence inside it may well read as an instruction. It arrives
framed as data through `RuntimeCopy.recalled_memory`, in the same position the
compaction summary uses, and the frame says so in the words the model reads.

**Failing to recall is not failing the run.** A database that is slow or down
degrades the agent to one that has forgotten, which is the behaviour of every
run before this middleware existed. It does not degrade it to one that stops. The
exception is logged, not swallowed silently.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from typing import Any, Protocol, cast

from langchain.agents.middleware import AgentMiddleware, ModelRequest
from langchain_core.messages import SystemMessage

from dw_agent_runtime.context import access_context_from_run
from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.copy import RuntimeCopy
from dw_platform.application.access_context import AccessContext

logger = logging.getLogger("dw_agent_runtime.recalled_memory")

__all__ = ["MemoryRecallPort", "RecalledFact", "RecalledMemoryMiddleware"]


class RecalledFact(Protocol):
    """The part of a stored memory this middleware renders.

    Declared here rather than importing `dw_memory.MemoryItem`: the consumer
    states what it needs, and the runtime does not take a dependency on the
    memory package to put a sentence in a prompt.
    """

    @property
    def content(self) -> str: ...

    @property
    def confidence(self) -> float: ...


class MemoryRecallPort(Protocol):
    """What the composition root must satisfy — `MemoryService.recall` does."""

    async def recall(
        self,
        context: AccessContext,
        *,
        worker_id: str,
        subject_refs: Sequence[str],
        now: datetime,
        limit: int = ...,
    ) -> tuple[RecalledFact, ...]: ...


class RecalledMemoryMiddleware(AgentMiddleware[Any, Any]):
    """Puts what is already known about this run's subject into the system message."""

    def __init__(
        self,
        recall: MemoryRecallPort,
        *,
        copy: RuntimeCopy,
        clock: Callable[[], datetime],
    ) -> None:
        super().__init__()
        if copy.recalled_memory_frame is None:
            # Refused at construction, not at the first model call. Without the
            # frame the only thing left to do would be to paste remembered
            # sentences in unframed, which is the injection this exists to avoid
            # — and a host would discover that in production rather than at boot.
            raise ValueError(
                f"runtime copy {copy.version} has no recalled_memory_frame; "
                "load runtime@1.5.0 or later before wiring recall"
            )
        self._recall = recall
        self._copy = copy
        self._clock = clock

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[Any]],
    ) -> Any:
        facts = await self._facts_for(request)
        if not facts:
            return await handler(request)
        block = cast(Any, {"type": "text", "text": self._copy.recalled_memory(facts)})
        existing = list(request.system_message.content_blocks) if request.system_message else []
        # After the worker prompt, before the conversation: the prompt is what the
        # worker IS, and remembered facts are what it happens to know today.
        return await handler(
            request.override(system_message=SystemMessage(content_blocks=[*existing, block]))
        )

    async def _facts_for(self, request: ModelRequest[Any]) -> str:
        run_context = getattr(request.runtime, "context", None)
        if not isinstance(run_context, RunContext):
            # A runner that did not set the context has not been through the
            # boundary that resolves tenancy; recalling anything here would mean
            # guessing whose memory to read.
            return ""
        if run_context.subject_ref is None:
            return ""
        try:
            items = await self._recall.recall(
                access_context_from_run(run_context),
                worker_id=run_context.worker_id,
                subject_refs=(run_context.subject_ref,),
                now=self._clock(),
            )
        except Exception:
            logger.warning(
                "recall failed; the run continues without memory",
                extra={"run_id": str(run_context.run_id), "worker_id": run_context.worker_id},
                exc_info=True,
            )
            return ""
        return "\n".join(f"- {item.content}" for item in items)
