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
from typing import Literal, Protocol, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from dw_platform.application.ports import AuditRepositoryPort
from dw_sales.application.ports import SalesScope
from dw_sales.domain.dispositions import CaseKind, MessageDisposition
from dw_sales.domain.orders import OrderCase
from dw_sales.domain.quotes import QuoteCase

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
    None when no user matched; ``release_manifest_ref`` the release the case
    was opened under.
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
    a page of a PDF or a sheet of a workbook, for one case version."""

    model_config = _FROZEN

    principal_id: uuid.UUID
    case_kind: CaseKind
    case_id: uuid.UUID
    case_version: int = Field(ge=1)
    attachment_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,128}$")
    attachment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page: int | None = Field(default=None, ge=1)
    sheet: str | None = Field(default=None, min_length=1, max_length=31)
    served_at: AwareDatetime

    @model_validator(mode="after")
    def _one_region(self) -> Self:
        if (self.page is None) == (self.sheet is None):
            raise ValueError("a served region is a page or a sheet")
        return self


@dataclass(frozen=True, slots=True)
class SourceRegion:
    attachment_id: str
    page: int | None
    sheet: str | None


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


class QuoteCaseStorePort(Protocol):
    async def get(self, case_id: uuid.UUID) -> Stored[QuoteCase] | None: ...

    async def list_all(self) -> Sequence[Stored[QuoteCase]]:
        """Every case of the workspace, newest first."""
        ...

    async def add(self, case: QuoteCase, origin: CaseOrigin, event: CaseEvent) -> None: ...

    async def save(self, case: QuoteCase, *, expected_version: int, event: CaseEvent) -> None: ...


class MessageLogPort(Protocol):
    """What became of each inbound message (spec decision 10)."""

    async def record(self, disposition: MessageDisposition, processed_at: datetime) -> None:
        """The message's disposition, replacing any earlier one for it."""
        ...

    async def get(self, message_id: str) -> MessageDisposition | None: ...

    async def list_all(self) -> Sequence[LoggedMessage]:
        """Every message with a disposition, newest processed first."""
        ...


class CaseEventLogPort(Protocol):
    async def list_all(self) -> Sequence[LoggedEvent]:
        """Every event of the workspace's cases, oldest first."""
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
    async def add(self, artifact: ArtifactRecord) -> None: ...

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
    def events(self) -> CaseEventLogPort: ...

    @property
    def served(self) -> SourceServedPort: ...

    @property
    def artifacts(self) -> ArtifactLogPort: ...

    @property
    def worker(self) -> WorkerSwitchPort: ...

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
