"""Export-control results in memory (WIV-03-032): what the evals and the unit
tests run on. Each workspace held apart, as RLS holds them in PostgreSQL; a
transaction's writes kept only once it commits."""

from __future__ import annotations

from collections.abc import Sequence
from types import TracebackType
from typing import Self
from uuid import UUID

from dw_kernel.pagination import Page, PageRequest
from dw_platform.domain.audit import AuditEntry, AuditEvent
from dw_sales.application.ports import SalesScope
from dw_sales.domain.export_control import ScreeningRecord, ScreeningStep

_Key = tuple[str, ScreeningStep]


class _Screenings:
    """Implements `ScreeningStorePort` over one workspace's pending state."""

    def __init__(self, held: dict[_Key, ScreeningRecord]) -> None:
        self.held = held

    async def records(self) -> Sequence[ScreeningRecord]:
        return [self.held[key] for key in sorted(self.held)]

    async def put(self, record: ScreeningRecord) -> None:
        self.held[(record.customer_code, record.step)] = record


class _Audit:
    """The audit port as an export-control transaction writes it: appended,
    kept on commit. Nothing here reads the trail back."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def append(self, event: AuditEvent) -> None:
        self.events.append(event)

    async def list_page(
        self,
        request: PageRequest,
        *,
        workspace_id: UUID,
        support_grant_id: UUID | None = None,
    ) -> Page[AuditEntry]:
        raise NotImplementedError("not exercised by export control")

    async def list_for_run(
        self, run_id: UUID, *, workspace_id: UUID, limit: int = 100
    ) -> list[AuditEvent]:
        raise NotImplementedError("not exercised by export control")


class MemoryExportControlUnitOfWork:
    """Implements `ExportControlUnitOfWork`."""

    def __init__(self, store: MemoryExportControl, scope: SalesScope) -> None:
        self._store, self._scope = store, scope
        self.screenings = _Screenings(dict(store.held.get(scope, {})))
        self.audit = _Audit()

    async def commit(self) -> None:
        self._store.held[self._scope] = dict(self.screenings.held)
        self._store.audit.extend(self.audit.events)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None


class MemoryExportControl:
    """Implements `ExportControlUnitOfWorkFactory`: every workspace's results,
    and the audit rows their transactions committed."""

    def __init__(self) -> None:
        self.held: dict[SalesScope, dict[_Key, ScreeningRecord]] = {}
        self.audit: list[AuditEvent] = []

    def __call__(self, scope: SalesScope) -> MemoryExportControlUnitOfWork:
        return MemoryExportControlUnitOfWork(self, scope)
