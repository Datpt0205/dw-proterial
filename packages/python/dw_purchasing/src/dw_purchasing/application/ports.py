"""What Purchasing needs from outside, declared by the consumer.

The composition root satisfies each: the store with its SQL repository (RLS
binds every transaction to the verified context's tenant and workspace), the
mailbox with the demo's mock until a mailbox is connected, the tenant's rules
with the platform's policy overrides.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import AuditEvent
from dw_platform.domain.messages import InboundMessage
from dw_purchasing.domain.requests import PurchaseCase
from dw_purchasing.domain.rules import PurchasingRules


class Disposition(StrEnum):
    """What DW2 did with one mail."""

    # A request was read and a case opened for it.
    OPENED = "opened"
    # Not a request DW2 could receive: a person reads it.
    TO_PERSON = "to_person"


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

    async def page(
        self, *, limit: int, before: tuple[datetime, uuid.UUID] | None
    ) -> Sequence[PurchaseCase]:
        """Newest first by (received_at, case_id), strictly before ``before``."""
        ...


class OutcomesPort(Protocol):
    async def get(self, message_id: str) -> MessageOutcome | None: ...

    async def add(self, outcome: MessageOutcome) -> None:
        """Refuses (`ConflictError`) a message already settled."""
        ...

    async def all(self) -> Sequence[MessageOutcome]: ...


class AuditPort(Protocol):
    async def append(self, event: AuditEvent) -> None: ...


class PurchasingWork(Protocol):
    """One transaction, bound to one tenant and workspace."""

    @property
    def cases(self) -> CasesPort: ...

    @property
    def outcomes(self) -> OutcomesPort: ...

    @property
    def audit(self) -> AuditPort: ...


PurchasingUnitOfWork = Callable[[AccessContext], AbstractAsyncContextManager[PurchasingWork]]


class InboxPort(Protocol):
    """The mailbox requests arrive in, for the caller's tenant and workspace."""

    async def list_messages(self, context: AccessContext) -> Sequence[InboundMessage]: ...

    async def get_message(
        self, context: AccessContext, message_id: str
    ) -> InboundMessage | None: ...


class PlatformRulesPort(Protocol):
    """The rules that ship in ``configs/policies`` (the platform layer)."""

    def current(self) -> PurchasingRules: ...


class TenantPolicyPort(Protocol):
    """A tenant's own document for a policy id (`PolicyOverridePort.get`)."""

    async def get(self, context: AccessContext, policy_id: str) -> dict[str, object] | None: ...
