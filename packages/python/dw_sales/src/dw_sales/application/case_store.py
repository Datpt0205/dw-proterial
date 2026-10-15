"""What the sales flows keep, declared by them; the composition root satisfies it.

Case state lives in PostgreSQL (spec decision 3). A unit of work is one
transaction bound to one tenant's workspace, taken from the verified access
context or the run, never from a request. Everything written in it commits or
rolls back together: the case, its event, and the platform audit row
(`AuditRepositoryPort`, ticket 04 G28).

Three rules shape these ports:

- **No change without its event.** `add` and `save` take the `CaseEvent` that
  explains them and record it in the same transaction, with the case version
  and the status move read from the case itself. A store that could save a
  case silently would let a transition go unlogged.
- **An event holds no value.** Its fields are ids, codes and names: the
  action, a finding key, a field name, a reason code, the actor. There is no
  free-text field for an amount to travel in (spec decision 8).
- **A decision names the version it was made on.** `save` takes the version
  the caller read and refuses with a conflict when the case moved since.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import TYPE_CHECKING, Final, Literal, Protocol, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from dw_platform.application.authorization import ApprovalAudience
from dw_platform.application.ports import AuditRepositoryPort
from dw_platform.domain.approval import ApprovalRequest
from dw_sales.application.ports import SalesScope
from dw_sales.domain.dispositions import CaseKind, MessageDisposition
from dw_sales.domain.layouts import LayoutStatus, PoLayout
from dw_sales.domain.orders import OrderCase
from dw_sales.domain.quotes import QuoteCase

if TYPE_CHECKING:
    from dw_sales.application.overview_ports import OverviewReadPort
    from dw_sales.application.rules import RuleVersionStorePort

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

_PRINCIPAL = r"^[!-~]{1,254}$"


class EventActor(BaseModel):
    """Who acted: DW1 (a worker, with its id and version) or a person.

    A person's ``actor_id`` is their principal id (a uuid, as text in the
    event row); a worker's is its own service id. ``initiated_by`` is the
    person whose request started a worker's action ("DW xử lý"), when one did.
    """

    model_config = _FROZEN

    kind: Literal["worker", "user"]
    actor_id: str = Field(pattern=_PRINCIPAL)
    worker_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_.-]{0,63}$")
    worker_version: str | None = Field(default=None, pattern=r"^\d+\.\d+\.\d+$")
    initiated_by: uuid.UUID | None = None

    @model_validator(mode="after")
    def _a_worker_names_itself(self) -> Self:
        named = self.worker_id is not None and self.worker_version is not None
        anonymous = self.worker_id is None and self.worker_version is None
        if (self.kind == "worker" and not named) or (self.kind == "user" and not anonymous):
            raise ValueError("a worker names its id and version, and a person neither")
        if self.kind == "user":
            try:
                uuid.UUID(self.actor_id)
            except ValueError:
                raise ValueError("a person is named by their principal id") from None
        return self

    @classmethod
    def person(cls, principal_id: uuid.UUID) -> EventActor:
        return cls(kind="user", actor_id=str(principal_id))

    @classmethod
    def worker(
        cls, worker_id: str, worker_version: str, *, initiated_by: uuid.UUID | None
    ) -> EventActor:
        return cls(
            kind="worker",
            actor_id=f"svc|{worker_id}",
            worker_id=worker_id,
            worker_version=worker_version,
            initiated_by=initiated_by,
        )


class CaseEvent(BaseModel):
    """One transition or human action on a case.

    ``action`` is ``<order|quote>.<what>`` (``order.prepared``,
    ``order.value_corrected``). ``finding_key`` is a finding's ``code:line``,
    ``field`` the name of a corrected value, ``reason_code`` a close, decline
    or routing reason. The case version and the status move are the case's.
    """

    model_config = _FROZEN

    action: str = Field(pattern=r"^(order|quote)\.[a-z][a-z_]{1,47}$")
    actor: EventActor
    occurred_at: AwareDatetime
    finding_key: str | None = Field(default=None, pattern=r"^[a-z_]{1,40}:([1-9][0-9]{0,4}|-)$")
    field: str | None = Field(default=None, pattern=r"^[a-z_]{1,32}$")
    reason_code: str | None = Field(default=None, pattern=r"^[a-z_]{1,40}$")


@dataclass(frozen=True, slots=True)
class CaseOrigin:
    """Stamped when a case is opened and never looked up again (G22).

    ``assigned_to`` is the user the customer's Sales PIC resolved to then, or
    None when no user matched, until the head reassigns the case (ticket 17,
    `assign`); ``release_manifest_ref`` the release the case was opened under.
    """

    assigned_to: uuid.UUID | None
    release_manifest_ref: str | None


@dataclass(frozen=True, slots=True)
class Stored[CaseT]:
    """A case as stored, with what was stamped on it when it was opened.

    An order case is read back with every earlier maker the database
    accumulated (`OrderCase.earlier_makers`), so the case refuses a checker
    among them itself; `ck_order_cases_checker_not_maker` refuses the same
    whatever writes the row.
    """

    case: CaseT
    origin: CaseOrigin


class ServedSource(BaseModel):
    """One region of a case's source a principal was shown (spec decision 12):
    a page of a PDF or a sheet of a workbook, for one case version; or, for a
    quotation a model read from the mail (ticket 29), the message's text the
    case holds (``attachment_id`` None, its text's sha256)."""

    model_config = _FROZEN

    principal_id: uuid.UUID
    case_kind: CaseKind
    case_id: uuid.UUID
    case_version: int = Field(ge=1)
    attachment_id: str | None = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    attachment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page: int | None = Field(default=None, ge=1)
    sheet: str | None = Field(default=None, min_length=1, max_length=31)
    served_at: AwareDatetime

    @model_validator(mode="after")
    def _one_region(self) -> Self:
        if self.attachment_id is None:
            if self.page is not None or self.sheet is not None:
                raise ValueError("the message's text has no page or sheet")
            if self.case_kind is not CaseKind.QUOTE:
                raise ValueError("only a quotation is read from the message's text")
        elif (self.page is None) == (self.sheet is None):
            raise ValueError("a served region is a page or a sheet")
        return self


@dataclass(frozen=True, slots=True)
class SourceRegion:
    """A page or a sheet of one attachment; `MESSAGE_TEXT` for the message's
    own text."""

    attachment_id: str | None
    page: int | None
    sheet: str | None


MESSAGE_TEXT: Final = SourceRegion(None, None, None)


class ArtifactRecord(BaseModel):
    """A file generated for a case at one version (ticket 06).

    The object key is derived, never chosen: it always carries the tenant and
    workspace, so offboarding finds it and no caller can aim it elsewhere.
    """

    model_config = _FROZEN

    artifact_id: uuid.UUID
    case_kind: CaseKind
    case_id: uuid.UUID
    case_version: int = Field(ge=1)
    kind: str = Field(pattern=r"^[a-z][a-z0-9_]{2,47}$")
    template_ref: str = Field(pattern=r"^[a-z][a-z0-9_.-]*@\d+\.\d+\.\d+$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_type: str = Field(pattern=r"^[a-z]+/[A-Za-z0-9.+-]{1,100}$")
    size_bytes: int = Field(gt=0)
    created_by: uuid.UUID
    created_at: AwareDatetime

    def object_key(self, scope: SalesScope) -> str:
        return f"{scope.tenant_id}/{scope.workspace_id}/sales/{self.case_id}/{self.artifact_id}"


@dataclass(frozen=True, slots=True)
class WorkerState:
    """Whether DW1 is paused in a workspace, and the last change to that.

    A workspace nobody has paused is running, with no change on record.
    """

    paused: bool
    changed_by: uuid.UUID | None = None
    changed_at: datetime | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class LoggedMessage:
    """A message's disposition and when DW1 processed it (its ingest)."""

    disposition: MessageDisposition
    processed_at: datetime


# Where a message's processing stands (ticket 25): `sales.processing_jobs`.
JobStatus = Literal["queued", "running", "done", "failed"]
# Why a job failed, from a fixed set the table's CHECK holds too:
# - ``quota``: the plan's runs for the day are spent;
# - ``not_permitted``: whoever asked may no longer process the mailbox there;
# - ``paused``: DW1 was paused in the workspace before the job ran;
# - ``conflict``: the message was processed meanwhile, or is on a case;
# - ``not_found``: the mailbox no longer holds the message;
# - ``unavailable``: the scanner or the reader did not answer, every attempt;
# - ``model_retry``: a model gave no usable answer and the message is young
#   enough to be read again later (ticket 31);
# - ``abandoned``: the worker processing it died, every attempt;
# - ``error``: anything else, logged by the worker.
JobError = Literal[
    "quota",
    "not_permitted",
    "paused",
    "conflict",
    "not_found",
    "unavailable",
    "model_retry",
    "abandoned",
    "error",
]


@dataclass(frozen=True, slots=True)
class ProcessingJob:
    """A message's processing: queued by a person, or by DW1's mailbox lane,
    and run by the worker (`dw_sales.application.processing`).

    ``attempts`` counts the claims of this round and is the claim's token: a
    settlement names it, and a worker whose claim was reaped settles nothing.
    ``failures`` counts the rounds that ended failed in a row, which is how
    long DW1's mailbox lane waits before queueing it again."""

    job_id: uuid.UUID
    message_id: str
    status: JobStatus
    requested_by: uuid.UUID
    requested_at: datetime
    attempts: int
    failures: int
    available_at: datetime
    error: JobError | None
    updated_at: datetime

    @property
    def active(self) -> bool:
        """Queued or running: enqueueing it again changes nothing."""
        return self.status in ("queued", "running")


@dataclass(frozen=True, slots=True)
class Settlement:
    """How a claimed job ends its run: done, back in the queue (after an
    outage, not before ``available_at``), or failed with its reason."""

    status: Literal["done", "queued", "failed"]
    error: JobError | None = None
    available_at: datetime | None = None

    @classmethod
    def done(cls) -> Settlement:
        return cls("done")

    @classmethod
    def retry(cls, at: datetime) -> Settlement:
        return cls("queued", available_at=at)

    @classmethod
    def failed(cls, error: JobError) -> Settlement:
        return cls("failed", error=error)


@dataclass(frozen=True, slots=True)
class LoggedEvent:
    """One case event as the overview reads it: a status move, when, by whom."""

    case_kind: CaseKind
    case_id: uuid.UUID
    case_version: int
    action: str
    from_status: str | None
    to_status: str
    actor_kind: Literal["worker", "user"]
    occurred_at: datetime


class OrderCaseStorePort(Protocol):
    async def get(self, case_id: uuid.UUID) -> Stored[OrderCase] | None: ...

    async def list_all(self) -> Sequence[Stored[OrderCase]]:
        """Every case of the workspace, newest first."""
        ...

    async def add(self, case: OrderCase, origin: CaseOrigin, event: CaseEvent) -> None:
        """A case just opened. Refused with a conflict when the case, its
        message, or (for an original) its PO number is already stored."""
        ...

    async def save(self, case: OrderCase, *, expected_version: int, event: CaseEvent) -> None:
        """The case's next state, decided on ``expected_version``.

        A revision that joined the case supersedes the stored current one.
        Refused with a conflict when the stored case is at another version.
        """
        ...

    async def assign(self, case_id: uuid.UUID, assigned_to: uuid.UUID | None) -> None:
        """The case's assignee (ticket 17). The caller saves the case's next
        version with its event in the same transaction."""
        ...


class QuoteCaseStorePort(Protocol):
    async def get(self, case_id: uuid.UUID) -> Stored[QuoteCase] | None: ...

    async def list_all(self) -> Sequence[Stored[QuoteCase]]:
        """Every case of the workspace, newest first."""
        ...

    async def add(self, case: QuoteCase, origin: CaseOrigin, event: CaseEvent) -> None: ...

    async def save(self, case: QuoteCase, *, expected_version: int, event: CaseEvent) -> None: ...

    async def assign(self, case_id: uuid.UUID, assigned_to: uuid.UUID | None) -> None: ...


class LayoutStorePort(Protocol):
    """The PO layouts people mapped and decided in the workspace (ticket 30)."""

    async def get(self, layout_id: uuid.UUID) -> PoLayout | None: ...

    async def list_all(self) -> Sequence[PoLayout]:
        """Every layout of the workspace, newest proposed first."""
        ...

    async def add(self, layout: PoLayout) -> None: ...

    async def save(self, layout: PoLayout, *, expected: LayoutStatus) -> None:
        """The layout's next state, decided on the status it had: a decision
        made on a layout someone else decided meanwhile is refused (409)."""
        ...


class RunLessApprovalsPort(Protocol):
    """The platform's approvals, as a run-less Sales decision uses them (a PO
    layout's, ticket 30; a rule version's, ticket 38): opened in the
    proposal's transaction, and read back when the decision is carried out.
    The narrow side of `ApprovalRepositoryPort`."""

    async def add(self, request: ApprovalRequest) -> None: ...

    async def get(
        self, request_id: uuid.UUID, *, workspace_id: uuid.UUID, audience: ApprovalAudience
    ) -> ApprovalRequest | None: ...


class MessageLogPort(Protocol):
    """What became of each inbound message (spec decision 10)."""

    async def record(self, disposition: MessageDisposition, processed_at: datetime) -> None:
        """The message's disposition: its first, or one replacing a routing to
        Sales (a routed message may be processed again).

        Raises `ConflictError` (`message_already_processed`) when the message
        already has any other disposition: the (workspace, message_id) pair is
        the message's idempotency key, so whichever of a person and DW1's
        mailbox lane gets there second has its whole transaction refused.
        """
        ...

    async def get(self, message_id: str) -> MessageDisposition | None: ...

    async def list_all(self) -> Sequence[LoggedMessage]:
        """Every message with a disposition, newest processed first."""
        ...


class ProcessingJobsPort(Protocol):
    """Each message's processing job in one workspace (ticket 25)."""

    async def enqueue(
        self, message_id: str, requested_by: uuid.UUID, at: datetime, job_id: uuid.UUID
    ) -> tuple[ProcessingJob, bool]:
        """The message's job, queued, and whether this call queued it.

        A message with no job gets one (``job_id``); a done or failed job is
        queued again, its attempts reset and ``requested_by`` the new asker.
        A job already queued or running is returned as it is, unchanged: the
        (workspace, message_id) pair is its idempotency key, so a second
        press, or the lane and a person at once, queue it once.
        """
        ...

    async def get(self, message_id: str) -> ProcessingJob | None: ...

    async def list_all(self) -> Sequence[ProcessingJob]: ...

    async def settle(self, job: ProcessingJob, outcome: Settlement, at: datetime) -> bool:
        """End the run of ``job``, claimed with ``job.attempts``: False, and
        nothing written, when the claim is no longer this caller's (the
        reaper put the job back in the queue and another worker took it)."""
        ...


class SourceServedPort(Protocol):
    async def record(self, served: ServedSource) -> None:
        """Idempotent: the same region served again keeps its first record."""
        ...

    async def served(
        self, principal_id: uuid.UUID, case_kind: CaseKind, case_id: uuid.UUID, case_version: int
    ) -> frozenset[SourceRegion]:
        """The regions ``principal_id`` was served of this case version."""
        ...


class ArtifactLogPort(Protocol):
    async def add(self, artifact: ArtifactRecord) -> bool:
        """Record the artifact, unless its case already holds a file of its
        kind and content type at its version: then record nothing and return
        False. A render that raced another one at the same version loses here,
        once the other has committed."""
        ...

    async def get(self, artifact_id: uuid.UUID) -> ArtifactRecord | None: ...

    async def for_case(self, case_kind: CaseKind, case_id: uuid.UUID) -> Sequence[ArtifactRecord]:
        """Every artifact rendered for the case, oldest first, at any version."""
        ...


class WorkerSwitchPort(Protocol):
    async def state(self) -> WorkerState: ...

    async def set(self, state: WorkerState) -> None: ...


class SalesUnitOfWork(Protocol):
    """One transaction in one tenant's workspace. Leaving it without `commit`
    rolls everything back."""

    # Read-only members, so an implementation may hold its concrete stores.
    @property
    def orders(self) -> OrderCaseStorePort: ...

    @property
    def quotes(self) -> QuoteCaseStorePort: ...

    @property
    def messages(self) -> MessageLogPort: ...

    @property
    def overview(self) -> OverviewReadPort: ...

    @property
    def rule_versions(self) -> RuleVersionStorePort: ...

    @property
    def served(self) -> SourceServedPort: ...

    @property
    def artifacts(self) -> ArtifactLogPort: ...

    @property
    def worker(self) -> WorkerSwitchPort: ...

    @property
    def layouts(self) -> LayoutStorePort: ...

    @property
    def jobs(self) -> ProcessingJobsPort: ...

    @property
    def approvals(self) -> RunLessApprovalsPort: ...

    @property
    def audit(self) -> AuditRepositoryPort: ...

    async def commit(self) -> None: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...


class SalesUnitOfWorkFactory(Protocol):
    def __call__(self, scope: SalesScope) -> SalesUnitOfWork: ...
