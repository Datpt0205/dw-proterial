"""Context compaction the platform can stand behind.

A run long enough to outgrow the model's context window used to end at the
provider's limit with no way down. Compaction replaces older turns with a
summary. LangChain ships `SummarizationMiddleware` for it, and it was measured
before being used rather than trusted. What follows is what the measurement
found wrong for a multi-tenant platform; this class fixes exactly those things.

1. **It destroys history without a trace.** The update it returns starts with
   `RemoveMessage(REMOVE_ALL_MESSAGES)` — the checkpointed state loses the older
   turns for good, not merely the model's view of them. Measured: 30 messages in,
   6 out, the originals gone. Here every compaction writes an audit event first
   — what was removed, a digest of it, what replaced it — and if that record
   cannot be written, nothing is removed. History is never destroyed without a
   record that it was.

2. **A failing summariser kills the turn.** The summary call raises once its
   retries are spent, and the turn dies — the long run compaction exists to
   save. Here a failed summary leaves the history as it was and lets the turn
   continue: if it still fits, it succeeds; if it does not, it fails at the
   provider's limit exactly as it would have with no compaction at all. Never
   worse than not compacting.

3. **The summary is re-inserted as if the user wrote it** — a `HumanMessage`.
   Tool results carry untrusted text (a web page, a document a customer sent),
   and laundering it through a summariser hands it a user's authority. Here the
   summary is framed as system-made reference data. That lowers the odds and
   guarantees nothing: the guarantee is that every tool still passes scope
   checks and the approval gate in code, whatever the model was persuaded of.

4. **It destroys history for a placeholder.** When the older turns cannot be
   trimmed small enough to summarise, the library returns the English sentence
   "Previous conversation was too long to summarize." — and still removes the
   history and inserts that sentence in its place. Real content traded for a
   line that says nothing. Here that case compacts nothing.

5. **Its spend is invisible to the run's ceiling.** The summariser is called
   directly, not through the agent's model node, so `RunBudgetMiddleware` never
   sees it. Measured: summariser called, one ledger entry — the agent's. A run
   that kept tripping compaction would spend on summaries with no limit. Here the
   ceiling is checked before summarising and the summary's tokens are added to
   the same ledger after.

Two things measured and left alone because they were already right: a file the
model cannot read never reaches the summariser (history is serialised to text
first), and a pending approval survives compaction (tool call and result are
kept together).
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC
from typing import Any

from langchain.agents.middleware import SummarizationMiddleware
from langchain.agents.middleware.internal_call_transformer import internal_call_metadata
from langchain.agents.middleware.summarization import ContextSize
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AnyMessage, HumanMessage, RemoveMessage
from langchain_core.messages.utils import get_buffer_string
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.runtime import Runtime

from dw_agent_runtime.adapters.chat_model import chat_route
from dw_agent_runtime.context import access_context_from_run
from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.budget import RunBudgetLedger, route_cost
from dw_agent_runtime.model.copy import RuntimeCopy
from dw_agent_runtime.model.profiles import ModelProfileRegistry
from dw_agent_runtime.registry import ConfigError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.ports import PlatformUnitOfWorkFactory
from dw_platform.domain.audit import AuditEvent

__all__ = ["COMPACTED_ACTION", "COMPACTION_TASK", "PlatformSummarizationMiddleware"]

logger = logging.getLogger("dw_agent_runtime.context_compaction")

COMPACTED_ACTION = "run.context_compacted"
# What a refused summary is reported under, next to the agent loop's own task.
COMPACTION_TASK = "context_compaction"


class PlatformSummarizationMiddleware(SummarizationMiddleware):
    """Compacts long history — recorded, bounded, failure-tolerant, not user-authored."""

    def __init__(
        self,
        model: BaseChatModel,
        *,
        copy: RuntimeCopy,
        uow_factory: PlatformUnitOfWorkFactory,
        clock: UtcClock,
        ids: IdGenerator,
        budget: RunBudgetLedger,
        profiles: ModelProfileRegistry,
        # The run's profile: its ceiling is the one a summary counts against.
        profile_id: str,
        # The summariser's own profile: its price is what a summary costs. A
        # separate argument because compaction is usually given a cheaper model
        # than the one doing the work.
        summary_profile_id: str,
        trigger: ContextSize,
        keep: ContextSize,
    ) -> None:
        if copy.context_summary_prompt is None or copy.context_summary_frame is None:
            # Refuse rather than fall back to the library's own prompt: that one is
            # English, knows nothing of pending approvals, and is exactly what this
            # class exists not to use.
            raise ConfigError(
                f"runtime copy {copy.version} has no context summary text; "
                "load runtime@1.4.0 or later"
            )
        super().__init__(
            model, trigger=trigger, keep=keep, summary_prompt=copy.context_summary_prompt
        )
        self._copy = copy
        self._uow_factory = uow_factory
        self._clock = clock
        self._ids = ids
        self._budget = budget
        self._profiles = profiles
        self._profile_id = profile_id
        self._summary_profile_id = summary_profile_id

    def _build_new_messages(self, summary: str) -> list[HumanMessage]:  # type: ignore[override]
        return [
            HumanMessage(
                content=self._copy.context_summary(summary),
                # `lc_source` is the library's own marker; the second says, for
                # anything that reads the transcript later, that no person wrote it.
                additional_kwargs={"lc_source": "summarization", "dw_system_generated": True},
            )
        ]

    async def abefore_model(  # type: ignore[override]
        self, state: Any, runtime: Runtime[RunContext]
    ) -> dict[str, Any] | None:
        messages: list[AnyMessage] = state["messages"]
        self._ensure_message_ids(messages)
        if not self._should_summarize(messages, self.token_counter(messages)):
            return None
        cutoff = self._determine_cutoff_index(messages)
        if cutoff <= 0:
            return None
        removed, preserved = self._partition_messages(messages, cutoff)
        run_context = runtime.context

        # Outside the fail-open block below, on purpose. A run over its ceiling
        # must stop; caught there, the refusal would read as "the summariser
        # failed, carry on" and the ceiling would stop nothing.
        profile = self._profiles.resolve(self._profile_id, tenant_id=run_context.tenant_id)
        self._budget.check(run_context.run_id, profile.budgets, task=COMPACTION_TASK)

        try:
            summarised = await self._summarise(removed)
        except Exception:
            # Deliberately broad: the summariser is a model call and can fail in
            # every way a provider can. Whatever it was, the answer is the same —
            # leave the history intact and let the turn carry on. `CancelledError`
            # is a BaseException and passes straight through, so a closed tab
            # still stops the run.
            logger.warning(
                "context compaction skipped: summariser failed; history left intact",
                exc_info=True,
            )
            return None
        if summarised is None:
            # Nothing fit in a summary. Removing the history anyway would trade
            # real turns for a placeholder, which is the library's behaviour and
            # not this one's.
            return None
        summary, input_tokens, output_tokens = summarised
        # Recorded the moment it is known, before the audit: the tokens were spent
        # whether or not the compaction goes ahead.
        summary_route = chat_route(
            self._profiles, self._summary_profile_id, tenant_id=run_context.tenant_id
        )
        self._budget.record(
            run_context.run_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=route_cost(summary_route, input_tokens, output_tokens),
        )

        try:
            await self._record(run_context, removed, preserved, summary)
        except Exception:
            # The invariant this class exists for: no record, no removal. The
            # summary is thrown away and the history stays, so the next step can
            # try again and nothing was lost without a trace.
            logger.error(
                "context compaction abandoned: could not record it, history left intact",
                exc_info=True,
            )
            return None

        return {
            "messages": [
                RemoveMessage(id=REMOVE_ALL_MESSAGES),
                *self._build_new_messages(summary),
                *preserved,
            ]
        }

    def before_model(self, state: Any, runtime: Runtime[RunContext]) -> dict[str, Any] | None:  # type: ignore[override]
        """Refuse the synchronous path rather than silently take the library's.

        The platform runs agents asynchronously. Inheriting the sync hook would
        compact with none of the fixes above — destroying history unrecorded and
        unbounded — and nothing would say so. A clear refusal is the safe failure.
        """
        raise NotImplementedError(
            "platform context compaction is async-only; invoke the agent with ainvoke/astream"
        )

    async def _summarise(self, removed: list[AnyMessage]) -> tuple[str, int, int] | None:
        """The summary and what it cost, or None when nothing could be summarised.

        The library's own summary call discards the response once it has the text,
        and with it the token counts the ceiling needs; and where trimming leaves
        nothing it returns a placeholder sentence that would then replace real
        history. Same prompt, same trimming, same serialisation — only those two
        outcomes differ.
        """
        trimmed = self._trim_messages_for_summary(removed)
        if not trimmed:
            return None
        response = await self._summary_model.ainvoke(
            self.summary_prompt.format(messages=get_buffer_string(trimmed, format="xml")).rstrip(),
            config={"metadata": {"lc_source": "summarization", **internal_call_metadata()}},
        )
        usage = getattr(response, "usage_metadata", None) or {}
        return (
            response.text.strip(),
            int(usage.get("input_tokens", 0)),
            int(usage.get("output_tokens", 0)),
        )

    async def _record(
        self,
        run_context: RunContext,
        removed: list[AnyMessage],
        preserved: list[AnyMessage],
        summary: str,
    ) -> None:
        """One audit event per compaction, written before anything is removed.

        The digest of what was removed is what makes the event worth keeping: the
        text itself is gone from the checkpoint after this, and a digest lets any
        copy kept elsewhere be proven to be the thing that was compacted. The
        summary is stored as a digest too, not verbatim — it is already in the
        run's state, and an audit row is not the place for a transcript.
        """
        event = AuditEvent(
            id=self._ids.new_uuid(),
            tenant_id=TenantId(run_context.tenant_id),
            workspace_id=WorkspaceId(run_context.workspace_id),
            actor_id=UserId(run_context.actor_id),
            action=COMPACTED_ACTION,
            resource_type="worker_run",
            resource_id=str(run_context.run_id),
            run_id=run_context.run_id,
            trace_id=run_context.trace_id,
            details={
                "removed_messages": len(removed),
                "kept_messages": len(preserved),
                "removed_digest": _digest(removed),
                "summary_digest": hashlib.sha256(summary.encode("utf-8")).hexdigest(),
                "summary_chars": len(summary),
                "copy_version": self._copy.version,
            },
            occurred_at=self._clock.now().astimezone(UTC),
        )
        async with self._uow_factory(access_context_from_run(run_context)) as uow:
            await uow.audit.append(event)
            await uow.commit()


def _digest(messages: list[AnyMessage]) -> str:
    """A stable fingerprint of exactly the messages that were removed.

    Over type, id and content, canonically serialised: the same history always
    digests the same, and any change to what was removed changes it.
    """
    canonical = json.dumps(
        [[type(m).__name__, m.id, m.content] for m in messages],
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
