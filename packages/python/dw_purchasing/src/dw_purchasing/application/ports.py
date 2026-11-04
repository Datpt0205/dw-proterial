"""What Purchasing needs from outside, declared by the consumer.

The composition root satisfies each: the store with its SQL repository (RLS
binds every transaction to the verified context's tenant and workspace), the
mailbox with the demo's mock until a mailbox is connected, the tenant's rules
with the platform's policy overrides.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ApprovalAudience
from dw_platform.application.rule_versions import RuleVersionStorePort
from dw_platform.domain.approval import ApprovalDecision, ApprovalRequest
from dw_platform.domain.audit import AuditEvent
from dw_platform.domain.messages import InboundMessage
from dw_purchasing.domain.attachments import AttachmentReading
from dw_purchasing.domain.cases import PurchaseCase
from dw_purchasing.domain.checks import MasterData
from dw_purchasing.domain.orders import Cell


class Disposition(StrEnum):
    """What DW2 did with one mail."""

    # A request was read and a case opened for it.
    OPENED = "opened"
    # Not a request DW2 could receive: a person reads it.
    TO_PERSON = "to_person"
    # A known supplier's verified mail about one case (a quote, an order's
    # confirmation), handled there by DW2's lane: read, or its buyer told.
    SUPPLIER = "supplier"


@dataclass(frozen=True, slots=True)
class MessageOutcome:
    """One mail, settled once: a second press finds it and reads nothing."""

    message_id: str
    disposition: Disposition
    # Why a person reads it: a code, never the mail's words.
    reason: str | None
    case_id: uuid.UUID | None
    settled_by: uuid.UUID
    settled_at: datetime


class CasesPort(Protocol):
    async def add(self, case: PurchaseCase) -> None: ...

    async def get(self, case_id: uuid.UUID) -> PurchaseCase | None: ...

    async def save(self, case: PurchaseCase, *, expected_version: int) -> None:
        """Replaces the case stored at ``expected_version``; refuses (409) a
        case another writer moved on meanwhile."""
        ...

    async def waiting(self, statuses: frozenset[str], *, limit: int) -> Sequence[PurchaseCase]:
        """Oldest first, the cases in one of ``statuses``: what DW2's lane
        takes the next step of."""
        ...

    async def by_approval(self, approval_id: uuid.UUID) -> PurchaseCase | None:
        """The case sent to this approval, if any."""
        ...

    async def page(
        self,
        *,
        limit: int,
        before: tuple[datetime, uuid.UUID] | None,
        requested_by: uuid.UUID | None = None,
    ) -> Sequence[PurchaseCase]:
        """Newest first by (received_at, case_id), strictly before ``before``;
        only the cases ``requested_by`` asked for when it is given."""
        ...


class OutcomesPort(Protocol):
    async def get(self, message_id: str) -> MessageOutcome | None: ...

    async def add(self, outcome: MessageOutcome) -> None:
        """Refuses (`ConflictError`) a message already settled."""
        ...

    async def all(self) -> Sequence[MessageOutcome]: ...


class AuditPort(Protocol):
    async def append(self, event: AuditEvent) -> None: ...


class ApprovalsPort(Protocol):
    """The platform's approvals, as a run-less Purchasing decision uses them:
    opened in the case's transaction, read back when the decision is carried
    out (the narrow side of `ApprovalRepositoryPort`)."""

    async def add(self, request: ApprovalRequest) -> None: ...

    async def get(
        self, request_id: uuid.UUID, *, workspace_id: uuid.UUID, audience: ApprovalAudience
    ) -> ApprovalRequest | None: ...

    async def latest_decision(
        self, request_id: uuid.UUID, *, workspace_id: uuid.UUID, audience: ApprovalAudience
    ) -> ApprovalDecision | None: ...


class PurchasingWork(Protocol):
    """One transaction, bound to one tenant and workspace. It commits as it
    closes without an error (`commit` says so to the platform's engines)."""

    @property
    def cases(self) -> CasesPort: ...

    @property
    def outcomes(self) -> OutcomesPort: ...

    @property
    def audit(self) -> AuditPort: ...

    @property
    def approvals(self) -> ApprovalsPort: ...

    @property
    def rule_versions(self) -> RuleVersionStorePort:
        """The tenant's rule versions (tenant-wide, whichever workspace)."""
        ...

    async def commit(self) -> None: ...


PurchasingUnitOfWork = Callable[[AccessContext], AbstractAsyncContextManager[PurchasingWork]]


class InboxPort(Protocol):
    """The mailbox requests arrive in, for the caller's tenant and workspace."""

    async def list_messages(self, context: AccessContext) -> Sequence[InboundMessage]: ...

    async def get_message(
        self, context: AccessContext, message_id: str
    ) -> InboundMessage | None: ...

    async def attachment_readings(
        self, context: AccessContext, message_id: str
    ) -> Mapping[str, AttachmentReading]:
        """What was read of each attachment of the message as it was stored,
        by attachment id (`domain.attachments`); one never read is absent."""
        ...


class MasterDataPort(Protocol):
    """What the company knows (items, quotations on file, past prices,
    budgets), for the caller's tenant and workspace."""

    async def for_context(self, context: AccessContext) -> MasterData: ...


class SpreadsheetPort(Protocol):
    """Writes one sheet of rows to a workbook's bytes, every string as text."""

    def write(
        self, sheet: str, rows: Sequence[Sequence[Cell]], *, date_format: str, at: datetime
    ) -> bytes: ...


@dataclass(frozen=True, slots=True)
class Person:
    display_name: str
    # Empty when the directory does not say.
    department: str
    # The address the member signs in with; None when the directory has none.
    email: str | None = None


class PeoplePort(Protocol):
    """Who a member of the caller's workspace is (the platform's directory):
    a requester's name and department on their request are the directory's,
    never what a form says."""

    async def person(self, context: AccessContext, user_id: uuid.UUID) -> Person | None: ...


class NoticesPort(Protocol):
    """In-app notifications to the members of the caller's workspace who
    hold any of ``scopes`` (read by the function that builds every access
    context, so who is told and who may act cannot disagree), and to
    ``people`` besides, never to ``excluding`` (who may not act on it: a
    maker is not asked to approve). Once per ``source_key``: telling again
    is a no-op."""

    async def tell(
        self,
        context: AccessContext,
        *,
        scopes: frozenset[str],
        people: Sequence[uuid.UUID] = (),
        excluding: Sequence[uuid.UUID] = (),
        source_key: str,
        title: str,
        body: str,
        link: str | None,
    ) -> None: ...


class NoNotices:
    """Implements `NoticesPort` where nobody is to be told (a lane's test
    of something else); the composition root wires the platform's."""

    async def tell(
        self,
        context: AccessContext,
        *,
        scopes: frozenset[str],
        people: Sequence[uuid.UUID] = (),
        excluding: Sequence[uuid.UUID] = (),
        source_key: str,
        title: str,
        body: str,
        link: str | None,
    ) -> None:
        return None
