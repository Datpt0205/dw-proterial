"""An in-memory Purchasing store for tests and the eval smoke.

It honours what the SQL store promises: every transaction sees only its own
tenant and workspace (as RLS narrows them), a transaction that raises leaves
nothing behind, a message is settled once (`ConflictError` the second time),
an outcome names only a case already written, and a case id is never
written twice.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime

from dw_kernel.errors import ConflictError
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import AuditEvent
from dw_purchasing.application.ports import MessageOutcome
from dw_purchasing.domain.requests import PurchaseCase

_Scope = tuple[uuid.UUID, uuid.UUID]


@dataclass
class _Rows:
    cases: dict[uuid.UUID, PurchaseCase] = field(default_factory=dict)
    outcomes: dict[str, MessageOutcome] = field(default_factory=dict)
    audit: list[AuditEvent] = field(default_factory=list)

    def copy(self) -> _Rows:
        return _Rows(dict(self.cases), dict(self.outcomes), list(self.audit))


@dataclass
class _Cases:
    rows: _Rows

    async def add(self, case: PurchaseCase) -> None:
        if case.case_id in self.rows.cases:
            raise ConflictError("case exists", details={"case_id": str(case.case_id)})
        self.rows.cases[case.case_id] = case

    async def get(self, case_id: uuid.UUID) -> PurchaseCase | None:
        return self.rows.cases.get(case_id)

    async def page(
        self, *, limit: int, before: tuple[datetime, uuid.UUID] | None
    ) -> Sequence[PurchaseCase]:
        ordered = sorted(
            self.rows.cases.values(), key=lambda c: (c.received_at, c.case_id), reverse=True
        )
        if before is not None:
            ordered = [c for c in ordered if (c.received_at, c.case_id) < before]
        return ordered[:limit]


@dataclass
class _Outcomes:
    rows: _Rows

    async def get(self, message_id: str) -> MessageOutcome | None:
        return self.rows.outcomes.get(message_id)

    async def add(self, outcome: MessageOutcome) -> None:
        if outcome.message_id in self.rows.outcomes:
            raise ConflictError("thư đã được xử lý", details={"message_id": outcome.message_id})
        if outcome.case_id is not None and outcome.case_id not in self.rows.cases:
            # `fk_mail_outcomes_case_id_cases`: the case is written first.
            raise ValueError("an outcome names a case that does not exist")
        self.rows.outcomes[outcome.message_id] = outcome

    async def all(self) -> Sequence[MessageOutcome]:
        return list(self.rows.outcomes.values())


@dataclass
class _Audit:
    rows: _Rows

    async def append(self, event: AuditEvent) -> None:
        self.rows.audit.append(event)


@dataclass
class _Work:
    rows: _Rows

    @property
    def cases(self) -> _Cases:
        return _Cases(self.rows)

    @property
    def outcomes(self) -> _Outcomes:
        return _Outcomes(self.rows)

    @property
    def audit(self) -> _Audit:
        return _Audit(self.rows)


@dataclass
class MemoryStore:
    """Implements `PurchasingUnitOfWork` (call it with a context)."""

    scopes: dict[_Scope, _Rows] = field(default_factory=dict)

    @asynccontextmanager
    async def __call__(self, context: AccessContext) -> AsyncIterator[_Work]:
        key = (context.tenant_id, context.workspace_id)
        working = self.scopes.get(key, _Rows()).copy()
        yield _Work(working)
        self.scopes[key] = working

    def rows(self, tenant_id: uuid.UUID, workspace_id: uuid.UUID) -> _Rows:
        return self.scopes.get((tenant_id, workspace_id), _Rows())
