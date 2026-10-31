"""A case's mail thread summarised by the model, each point citing its mail
(the AI list, item 8).

A case gathers mail: the PO and its revisions, the customer's replies, Design's
answers. Catching up meant opening each one. On request, the model reads the
thread (each mail's sender, date, subject and newest part, oldest first) and
writes what stands now in a few points, each naming the mails it rests on.

- **Code checks** each point: it cites at least one mail of this thread and
  no other, and every number, date and code in it is in a mail it cites
  (`figure_check`). A point that fails is dropped and counted; nothing passes
  as the thread's that the thread does not say.
- **Who sees it** is who reads the case: the thread is the mail the inbox
  already shows a case reader, and a case the caller may not see is not
  found. Nothing is stored.
- One call through the one-call door, as the caller; no model, or no point
  left, says DW1 could not summarise it.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from dw_agent_runtime.model.figure_check import unsupported
from dw_kernel.errors import QuotaExceededError
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.model_reading import InterpretationPort, ModelUnavailableError, PromptRef
from dw_sales.application.ports import InboxPort
from dw_sales.application.runs import caller_run
from dw_sales.application.support import stored_order, stored_quote
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.mail_parts import newest_part
from dw_sales.domain.process import DW_NAMES

# The prompt a thread is summarised with. Its file is
# `configs/prompts/sales/thread_summary@1.0.0.yaml`; a test holds the two
# together, and the rendered prompt under `PROMPT_TOKENS`.
THREAD_SUMMARY: Final = PromptRef("sales.thread_summary", "1.0.0")
PROMPT_TOKENS: Final = 900
_OUTPUT_TOKENS: Final = 900
# The newest this-many mails of the thread, each cut to this many characters.
MAX_MAILS: Final = 12
_MAIL_CHARS: Final = 1500

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class ModelPoint(BaseModel):
    model_config = _FROZEN

    text: str = Field(min_length=1, max_length=400)
    cites: list[str] = Field(default_factory=list, max_length=6)


class ModelThreadSummary(BaseModel):
    """What the model answers: a few points, each citing its mails."""

    model_config = _FROZEN

    points: list[ModelPoint] = Field(default_factory=list, max_length=8)


class SummaryPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    cites: list[str]


class ThreadSummaryView(BaseModel):
    """A summary, or why there is none; always marked as the model's."""

    model_config = ConfigDict(frozen=True)

    case_id: uuid.UUID
    status: Literal["summarized", "empty", "unavailable", "refused"]
    points: list[SummaryPoint] = []
    # The mails read, and the points dropped for citing or quoting what the
    # thread does not hold.
    mails: int = 0
    dropped: int = 0
    prompt_ref: str | None = None
    model_profile: str | None = None


def checked(answer: ModelThreadSummary, mails: dict[str, str]) -> tuple[list[SummaryPoint], int]:
    """The points whose every cite is a mail of the thread and every figure
    is in a mail they cite (or is the id of one); and how many were dropped."""
    kept: list[SummaryPoint] = []
    for point in answer.points:
        cites = list(dict.fromkeys(point.cites))
        if not cites or any(c not in mails for c in cites):
            continue
        sources = "\n".join([*cites, *(mails[c] for c in cites)])
        if unsupported(point.text, sources, names=DW_NAMES):
            continue
        kept.append(SummaryPoint(text=point.text, cites=cites))
    return kept, len(answer.points) - len(kept)


@dataclass(frozen=True)
class ThreadSummaries:
    """`GET /{orders,quotes}/{case_id}/thread-summary` (module docstring)."""

    uow: SalesUnitOfWorkFactory
    gate: Gate
    inbox: InboxPort
    model: InterpretationPort | None
    clock: UtcClock
    ids: IdGenerator
    worker_id: str
    worker_version: str

    async def summarize(
        self, context: AccessContext, kind: CaseKind, case_id: uuid.UUID
    ) -> ThreadSummaryView:
        resource = f"sales_{kind.value}_case"
        await self.gate.require(
            context, SalesScopes.CASE_READ, resource_type=resource, resource_id=str(case_id)
        )
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            if kind is CaseKind.ORDER:
                await stored_order(work, case_id, viewer=context)
            else:
                await stored_quote(work, case_id, viewer=context)
            logged = [
                m
                for m in await work.messages.list_all()
                if m.disposition.case_id == case_id and m.disposition.case_kind is kind
            ]
        logged.sort(key=lambda m: (m.processed_at, m.disposition.message_id))
        mails: dict[str, str] = {}
        for entry in logged[-MAX_MAILS:]:
            message = await self.inbox.get_message(scope, entry.disposition.message_id)
            if message is None:
                continue
            sender = message.sender
            mails[message.message_id] = (
                f"From: {sender.display_name} <{sender.address}>\n"
                f"Date: {message.received_at.isoformat()}\n"
                f"{newest_part(message).text}"
            )[:_MAIL_CHARS]
        if not mails:
            return ThreadSummaryView(case_id=case_id, status="empty")
        if self.model is None:
            return ThreadSummaryView(case_id=case_id, status="unavailable", mails=len(mails))
        stamp = {
            "case_id": case_id,
            "mails": len(mails),
            "prompt_ref": str(THREAD_SUMMARY),
            "model_profile": self.model.model_profile,
        }
        thread = json.dumps(
            [{"mail_id": mail_id, "mail": text} for mail_id, text in mails.items()],
            ensure_ascii=False,
            indent=1,
        )
        try:
            answer = await self.model.interpret(
                THREAD_SUMMARY,
                {"thread": thread},
                ModelThreadSummary,
                run=caller_run(
                    context,
                    run_id=self.ids.new_uuid(),
                    worker_id=self.worker_id,
                    worker_version=self.worker_version,
                    trace="sales-thread",
                    subject_ref=f"{resource}:{case_id}",
                ),
                max_output_tokens=_OUTPUT_TOKENS,
            )
        except (ModelUnavailableError, QuotaExceededError):
            return ThreadSummaryView(**stamp, status="unavailable")
        points, dropped = checked(answer, mails)
        if not points:
            return ThreadSummaryView(**stamp, status="refused", dropped=dropped)
        return ThreadSummaryView(**stamp, status="summarized", points=points, dropped=dropped)
