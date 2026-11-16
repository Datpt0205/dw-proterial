"""A customer's notation record: kept from Sales' confirmations, read by every
reader of the customer's words, shown and changed on the master data (ticket 37).

The rules are `domain.customer_notation`'s and the reading the platform's
(`dw_platform.domain.notation.settle`). Here:

- **Readers** ask `NotationRecordPort` for the sender's customer's entries,
  in the reader's own scope: another customer's, or another tenant's, is
  never asked for (`record_for`).
- **Commands learn** after the case decision commits (`learn`), as a
  confirmed item code is kept for the customer's next PO: one entry per
  customer and kind, written with its audit row in one transaction by the
  ledger, and only where the value changes.
- **A person** sees the entries and the evidence each rests on, sets one or
  forgets one (`CustomerNotations`): reading needs `sales.case.read`,
  changing `sales.order.prepare`, the scope of those who confirm values.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict, ValidationError

from dw_kernel.errors import DomainError, NotFoundError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import AuditEvent
from dw_platform.domain.notation import KIND_VALUES, Notation, NotationKind
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.ports import SalesCatalogPort, SalesScope
from dw_sales.domain.customer_notation import (
    Lesson,
    NotationCaseKind,
    NotationEntry,
    NotationSource,
    customer_record,
)

_RESOURCE = "sales_customer"


class NotationRecordPort(Protocol):
    """What a reader asks: one customer's entries, in the reader's scope."""

    async def entries(self, scope: SalesScope, customer_code: str) -> Sequence[NotationEntry]: ...


class NotationLedgerPort(NotationRecordPort, Protocol):
    """Where the entries are kept (`SqlCustomerNotations`). ``keep`` writes
    the entry and ``event`` in one transaction where the kind is new or its
    value changes, and says whether it did; ``forget`` removes one, with its
    event, and says whether there was one."""

    async def keep(self, scope: SalesScope, entry: NotationEntry, event: AuditEvent) -> bool: ...

    async def forget(
        self, scope: SalesScope, customer_code: str, kind: NotationKind, event: AuditEvent
    ) -> bool: ...


async def record_for(
    records: NotationRecordPort, scope: SalesScope, customer_code: str
) -> Notation:
    """The customer's record as `notation.settle` reads it."""
    return customer_record(await records.entries(scope, customer_code))


def _event(
    scope: SalesScope,
    ids: IdGenerator,
    actor: uuid.UUID,
    action: str,
    customer_code: str,
    at: datetime,
    details: dict[str, object],
) -> AuditEvent:
    return AuditEvent(
        id=ids.new_uuid(),
        tenant_id=TenantId(scope.tenant_id.value),
        workspace_id=WorkspaceId(scope.workspace_id.value),
        actor_id=UserId(actor),
        action=action,
        resource_type=_RESOURCE,
        resource_id=customer_code,
        occurred_at=at,
        details=details,
    )


async def learn(
    ledger: NotationLedgerPort,
    ids: IdGenerator,
    scope: SalesScope,
    lessons: Sequence[Lesson],
    *,
    customer_code: str,
    case_kind: NotationCaseKind,
    case_id: uuid.UUID,
    by: uuid.UUID,
    at: datetime,
) -> None:
    """Keeps what a decision taught (`customer_notation.order_lesson`,
    `quote_lessons`). The audit names the kind, the value, the case and the
    field, never the customer's words."""
    for taught in lessons:
        entry = NotationEntry(
            customer_code=customer_code,
            kind=taught.learned.kind,
            value=taught.learned.value,
            source="confirmed",
            case_kind=case_kind,
            case_id=case_id,
            field=taught.field,
            written=taught.written,
            confirmed=taught.confirmed,
            by=by,
            at=at,
        )
        details: dict[str, object] = {
            "kind": entry.kind,
            "value": entry.value,
            "case_kind": case_kind,
            "case_id": str(case_id),
            "field": taught.field,
        }
        event = _event(
            scope, ids, by, "sales.customer_notation.learned", customer_code, at, details
        )
        await ledger.keep(scope, entry, event)


class NotationEntryView(BaseModel):
    """One kind of a customer's notation on the master data screen."""

    model_config = ConfigDict(frozen=True)

    kind: NotationKind
    value: str
    source: NotationSource
    case_kind: Literal["order", "quote"] | None
    case_id: uuid.UUID | None
    field: str | None
    written: str | None
    confirmed: str | None
    by: uuid.UUID
    at: AwareDatetime


class CustomerNotationView(BaseModel):
    """A customer's notation: each kind known, what it rests on, and the
    values each kind may hold (the platform's one list, so a screen offers
    exactly what the server takes)."""

    model_config = ConfigDict(frozen=True)

    customer_code: str
    entries: list[NotationEntryView]
    choices: dict[NotationKind, list[str]]


def _view(customer_code: str, entries: Sequence[NotationEntry]) -> CustomerNotationView:
    return CustomerNotationView(
        customer_code=customer_code,
        entries=[
            NotationEntryView.model_validate(e.model_dump(exclude={"customer_code"}))
            for e in entries
        ],
        choices={kind: sorted(values) for kind, values in KIND_VALUES.items()},
    )


@dataclass(frozen=True)
class CustomerNotations:
    """The customer's notation on the master data (module docstring)."""

    gate: Gate
    ledger: NotationLedgerPort
    catalog: SalesCatalogPort
    clock: UtcClock
    ids: IdGenerator

    async def entries(self, context: AccessContext, customer_code: str) -> CustomerNotationView:
        await self.gate.require(
            context, SalesScopes.CASE_READ, resource_type=_RESOURCE, resource_id=customer_code
        )
        scope = await self._customer(context, customer_code)
        return _view(customer_code, await self.ledger.entries(scope, customer_code))

    async def set(
        self, context: AccessContext, customer_code: str, kind: NotationKind, value: str
    ) -> CustomerNotationView:
        """A person states how the customer writes ``kind``: it replaces what
        was learned, and later confirmations may change it again."""
        await self.gate.require(
            context, SalesScopes.ORDER_PREPARE, resource_type=_RESOURCE, resource_id=customer_code
        )
        scope = await self._customer(context, customer_code)
        now = self.clock.now()
        try:
            entry = NotationEntry(
                customer_code=customer_code,
                kind=kind,
                value=value,
                source="set",
                by=context.principal_id,
                at=now,
            )
        except ValidationError:
            raise DomainError("not a value of the kind", details={"field": "value"}) from None
        details: dict[str, object] = {"kind": kind, "value": value}
        event = _event(
            scope,
            self.ids,
            context.principal_id,
            "sales.customer_notation.set",
            customer_code,
            now,
            details,
        )
        await self.ledger.keep(scope, entry, event)
        return _view(customer_code, await self.ledger.entries(scope, customer_code))

    async def forget(
        self, context: AccessContext, customer_code: str, kind: NotationKind
    ) -> CustomerNotationView:
        """The kind is no longer known: the customer's values of it go to a
        person again until the next confirmation settles it."""
        await self.gate.require(
            context, SalesScopes.ORDER_PREPARE, resource_type=_RESOURCE, resource_id=customer_code
        )
        scope = await self._customer(context, customer_code)
        details: dict[str, object] = {"kind": kind}
        event = _event(
            scope,
            self.ids,
            context.principal_id,
            "sales.customer_notation.forgotten",
            customer_code,
            self.clock.now(),
            details,
        )
        if not await self.ledger.forget(scope, customer_code, kind, event):
            raise NotFoundError(
                "the customer has no such notation", details={"customer_code": customer_code}
            )
        return _view(customer_code, await self.ledger.entries(scope, customer_code))

    async def _customer(self, context: AccessContext, customer_code: str) -> SalesScope:
        """The caller's scope, once the customer is one of its own (404)."""
        scope = sales_scope(context)
        if (await self.catalog.customer_by_code(scope, customer_code)).data is None:
            raise NotFoundError("no such customer", details={"customer_code": customer_code})
        return scope
