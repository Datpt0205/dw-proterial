"""DW1 on the agent runtime: what Sales asks of it, declared here.

Three things run as DW1 runs (`dw_sales.workflows.graph`), each started by a
person and each counted against the tenant's plan by the runner, which is
where every run begins (`RunAllowancePort`):

- processing the mailbox ("DW xử lý"), one message or all of them;
- a quotation submitted for approval (WIV-03-023 step 9): the run pauses on
  a `sales.quote` approval and resumes with the decision;
- an order recorded in Bravo, for its cross-check (WIV-03-012 step 9): the
  run pauses on a `sales.order.cross_check` approval.

The decision is a person's, made through the platform's approvals
(`POST /api/v1/approvals/{id}/decisions`), and applied to the case by the
run when it resumes. Who may decide is stamped on the approval from
`DECIDE_SCOPES`; who may not (every maker of the case) is named in it; and
everything the run carries, in its input, its approval and its result, is
ids, versions and a document hash, never an amount (spec decision 8).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.ports import InboxPort
from dw_sales.application.support import stored_order, stored_quote
from dw_sales.application.views import (
    CaseChangeView,
    MessageDispositionView,
    message_disposition,
    order_change,
    quote_change,
)
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.orders import OrderCase, OrderStatus
from dw_sales.domain.quotes import QuoteCase, QuoteStatus

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class DecisionType(StrEnum):
    """The approval types DW1 raises, as the platform's approvals name them."""

    QUOTE_APPROVAL = "sales.quote"
    ORDER_CROSS_CHECK = "sales.order.cross_check"


# Who decides each one: the one place this is said. The interrupt stamps it on
# the approval, the platform requires it of the decider, and the guard refuses
# an approval stamped with anything else. `approvals.decide`, which a
# permission set such as `approver_boost` hands out, decides neither.
DECIDE_SCOPES: Final[Mapping[DecisionType, SalesScopes]] = MappingProxyType(
    {
        DecisionType.QUOTE_APPROVAL: SalesScopes.QUOTE_APPROVE,
        DecisionType.ORDER_CROSS_CHECK: SalesScopes.ORDER_CROSS_CHECK,
    }
)

# Every Sales approval shares it: the composition root makes it strict (a
# second person, and a written comment) with `strict_approval_prefixes`, and
# registers this context's decision guard under it.
APPROVAL_PREFIX: Final = "sales."

# The words an approval carries as its reason: what is decided, no figure.
_REASONS: Final[Mapping[DecisionType, str]] = MappingProxyType(
    {
        DecisionType.QUOTE_APPROVAL: "Báo giá chờ duyệt (WIV-03-023 bước 9)",
        DecisionType.ORDER_CROSS_CHECK: "Đơn đã nhập Bravo chờ kiểm chéo (WIV-03-012 bước 9)",
    }
)


def subject_of(kind: CaseKind, case_id: uuid.UUID) -> str:
    """The case a run is about, as the run row names it (`subject_ref`)."""
    return f"sales_{kind.value}_case:{case_id}"


def awaiting(case: OrderCase | QuoteCase) -> DecisionType | None:
    """The decision this case waits on in its state, if any."""
    if isinstance(case, QuoteCase):
        return DecisionType.QUOTE_APPROVAL if case.status is QuoteStatus.PENDING_APPROVAL else None
    if case.status is OrderStatus.UPLOADED_TO_BRAVO and case.cross_check_required is not False:
        return DecisionType.ORDER_CROSS_CHECK
    return None


class DecisionAsked(BaseModel):
    """What DW1 pauses on: the approval's payload. Ids, a version and a hash.

    ``case_version`` is the version the case was raised for decision at;
    ``makers`` everyone who made it (the strict check refuses each of them);
    ``document_sha256`` the quotation document an approver approves.
    """

    model_config = _FROZEN

    approval_type: DecisionType
    decide_scope: str
    reason: str
    case_kind: CaseKind
    case_id: uuid.UUID
    case_version: int = Field(ge=1)
    document_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    makers: tuple[uuid.UUID, ...]

    @classmethod
    def of_quote(cls, case: QuoteCase) -> DecisionAsked:
        submission = case.submission
        assert submission is not None  # pending approval holds its submission
        return cls._of(
            DecisionType.QUOTE_APPROVAL,
            CaseKind.QUOTE,
            case.case_id,
            case.case_version,
            # The pricer, and whoever submitted: the requester is excluded too.
            makers=frozenset({submission.priced_by, submission.submitted_by}),
            document_sha256=submission.document_sha256,
        )

    @classmethod
    def of_order(cls, case: OrderCase) -> DecisionAsked:
        return cls._of(
            DecisionType.ORDER_CROSS_CHECK,
            CaseKind.ORDER,
            case.case_id,
            case.case_version,
            # The preparer, the Bravo recorder in this round and earlier ones,
            # and whoever typed a value still on the case (`OrderCase.makers`).
            makers=case.makers,
        )

    @classmethod
    def _of(
        cls,
        kind: DecisionType,
        case_kind: CaseKind,
        case_id: uuid.UUID,
        case_version: int,
        *,
        makers: frozenset[uuid.UUID],
        document_sha256: str | None = None,
    ) -> DecisionAsked:
        return cls(
            approval_type=kind,
            decide_scope=DECIDE_SCOPES[kind].value,
            reason=_REASONS[kind],
            case_kind=case_kind,
            case_id=case_id,
            case_version=case_version,
            document_sha256=document_sha256,
            makers=tuple(sorted(makers, key=str)),
        )

    def payload(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class DecisionGiven(BaseModel):
    """The decision a run resumes with, as `ApproveAndResumeService` sends it."""

    model_config = ConfigDict(frozen=True, extra="ignore", hide_input_in_errors=True)

    approved: bool
    comment: str
    decided_by: uuid.UUID
    reasons: dict[str, str] = Field(default_factory=dict)
    subject_version: int | None = None


TaskKind = Literal["process", "quote_approval", "order_cross_check"]


class Dw1Task(BaseModel):
    """What a DW1 run is asked to do: its input row. Ids and numbers only."""

    model_config = _FROZEN

    kind: TaskKind
    # "process": one message, or all still without a disposition when None.
    message_id: str | None = Field(default=None, pattern=r"^[!-~]{1,512}$")
    case_id: uuid.UUID | None = None
    case_version: int | None = Field(default=None, ge=1)
    quote_no: str | None = None
    so_no: str | None = None
    entry_compared: bool = False


class Dw1RunsPort(Protocol):
    """Starting a DW1 run, as Sales needs it; the runtime satisfies it.

    Returns when the run has finished or paused on its decision. The run's
    refusals reach the caller as the run raised them (403, 409, 422, and 429
    when the plan's runs for the day are spent).
    """

    async def run(
        self, context: AccessContext, task: Dw1Task, *, subject_ref: str | None
    ) -> None: ...


class PendingDecisionsPort(Protocol):
    """The decision a case waits on, as Sales reads it and withdraws it."""

    async def pending(self, context: AccessContext, subject_ref: str) -> uuid.UUID | None:
        """The approval the case's run waits on, or None."""
        ...

    async def withdraw(self, context: AccessContext, subject_ref: str) -> None:
        """Cancel it: the case moved on without the decision."""
        ...


async def withdraw_if_left(
    decisions: PendingDecisionsPort,
    context: AccessContext,
    before: OrderCase | QuoteCase,
    after: OrderCase | QuoteCase,
) -> None:
    """Withdraw what ``before`` waited on, when ``after`` no longer waits on it.

    A quotation priced again or declined while its approval was pending, an
    order revised while its cross-check was: the approval would otherwise sit
    in an approver's inbox for a document nobody will send.
    """
    if awaiting(before) is not None and awaiting(after) is None:
        kind = CaseKind.QUOTE if isinstance(before, QuoteCase) else CaseKind.ORDER
        await decisions.withdraw(context, subject_of(kind, before.case_id))


_QUOTE = "sales_quote_case"
_ORDER = "sales_order_case"


@dataclass(frozen=True)
class Dw1Runs:
    """The routes' way to start DW1: the scope first, then the run.

    The scope is asked for here, before a run is spent, and again by the step
    the run takes. A refusal before the run costs no run.
    """

    uow: SalesUnitOfWorkFactory
    gate: Gate
    inbox: InboxPort
    runs: Dw1RunsPort
    decisions: PendingDecisionsPort

    async def process(self, context: AccessContext, message_id: str) -> MessageDispositionView:
        await self.gate.require(
            context,
            SalesScopes.INBOX_PROCESS,
            resource_type="sales_message",
            resource_id=message_id,
        )
        await self.runs.run(
            context, Dw1Task(kind="process", message_id=message_id), subject_ref=None
        )
        logged = await self._logged(context)
        return logged[message_id]

    async def process_all(self, context: AccessContext) -> list[MessageDispositionView]:
        """Every message still without a disposition, oldest first, in one run."""
        await self.gate.require(context, SalesScopes.INBOX_PROCESS, resource_type="sales_message")
        before = set(await self._logged(context))
        await self.runs.run(context, Dw1Task(kind="process"), subject_ref=None)
        after = await self._logged(context)
        order = [m.message_id for m in await self.inbox.list_messages(sales_scope(context))]
        return [after[m] for m in order if m in after and m not in before]

    async def submit_quote(
        self, context: AccessContext, case_id: uuid.UUID, *, case_version: int, quote_no: str
    ) -> CaseChangeView:
        """Step 8, then the wait for step 9: the run pauses on the approval."""
        await self.gate.require(
            context, SalesScopes.QUOTE_PREPARE, resource_type=_QUOTE, resource_id=str(case_id)
        )
        subject = subject_of(CaseKind.QUOTE, case_id)
        # Anything an earlier round left waiting: a withdrawal that failed.
        await self.decisions.withdraw(context, subject)
        task = Dw1Task(
            kind="quote_approval", case_id=case_id, case_version=case_version, quote_no=quote_no
        )
        await self.runs.run(context, task, subject_ref=subject)
        async with self.uow(sales_scope(context)) as work:
            return quote_change((await stored_quote(work, case_id)).case)

    async def record_bravo_entry(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        *,
        case_version: int,
        so_no: str | None,
        entry_compared: bool,
    ) -> CaseChangeView:
        """The Bravo entry (or a revision's change applied there), then the wait
        for the cross-check when the case's rules require one."""
        await self.gate.require(
            context, SalesScopes.ORDER_PREPARE, resource_type=_ORDER, resource_id=str(case_id)
        )
        subject = subject_of(CaseKind.ORDER, case_id)
        await self.decisions.withdraw(context, subject)
        task = Dw1Task(
            kind="order_cross_check",
            case_id=case_id,
            case_version=case_version,
            so_no=so_no,
            entry_compared=entry_compared,
        )
        await self.runs.run(context, task, subject_ref=subject)
        async with self.uow(sales_scope(context)) as work:
            return order_change((await stored_order(work, case_id)).case)

    async def _logged(self, context: AccessContext) -> dict[str, MessageDispositionView]:
        async with self.uow(sales_scope(context)) as work:
            logged = await work.messages.list_all()
        return {
            m.disposition.message_id: message_disposition(m.disposition, m.processed_at)
            for m in logged
        }
