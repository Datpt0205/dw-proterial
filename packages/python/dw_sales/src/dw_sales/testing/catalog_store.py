"""`CatalogUnitOfWorkFactory` in memory, for unit tests and evals (ticket 41).

Holds the SQL store's contract, not only the happy path: each scope's
snapshots are its own (what RLS gives the SQL store), a second open import
of a list is refused as `uq_catalog_snapshots_one_open` refuses it, a decided
snapshot's decider may be neither maker
(`ck_catalog_snapshots_checker_not_maker`), `update` writes only from the
expected status and drops the file once it leaves `queued`, and a
transaction that does not commit writes no snapshot. The platform's
approvals, audit and outbox are written at once, as the eval store's are.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, Self

from dw_agent_runtime.testing.memory_runtime import MemoryApprovals, MemoryAudit, MemoryOutbox
from dw_kernel.errors import ConflictError
from dw_sales.application.catalog_imports import OPEN, CatalogSnapshot, ImportStatus
from dw_sales.application.ports import SalesScope
from dw_sales.application.snapshot_catalog import ApprovedList
from dw_sales.domain.master_data import CatalogList, records_of


@dataclass
class _ScopeState:
    snapshots: dict[uuid.UUID, CatalogSnapshot] = field(default_factory=dict)
    files: dict[uuid.UUID, bytes] = field(default_factory=dict)
    records: dict[uuid.UUID, list[tuple[str, dict[str, Any]]]] = field(default_factory=dict)

    def copy(self) -> _ScopeState:
        return _ScopeState(dict(self.snapshots), dict(self.files), dict(self.records))


class _Snapshots:
    def __init__(self, state: _ScopeState) -> None:
        self._state = state

    async def add(self, snapshot: CatalogSnapshot, content: bytes | None) -> None:
        if snapshot.status in OPEN and await self.open_for(snapshot.catalog_list) is not None:
            raise ConflictError(
                "the sales store refused the change",
                details={"constraint": "uq_catalog_snapshots_one_open"},
            )
        self._state.snapshots[snapshot.snapshot_id] = snapshot
        if content is not None:
            self._state.files[snapshot.snapshot_id] = content

    async def get(self, snapshot_id: uuid.UUID) -> CatalogSnapshot | None:
        return self._state.snapshots.get(snapshot_id)

    async def open_for(self, catalog_list: CatalogList) -> CatalogSnapshot | None:
        return next(
            (
                s
                for s in self._state.snapshots.values()
                if s.catalog_list is catalog_list and s.status in OPEN
            ),
            None,
        )

    async def approved(self, catalog_list: CatalogList) -> CatalogSnapshot | None:
        return next(
            (
                s
                for s in self._state.snapshots.values()
                if s.catalog_list is catalog_list and s.status == "approved"
            ),
            None,
        )

    async def recent(self, catalog_list: CatalogList, limit: int) -> Sequence[CatalogSnapshot]:
        mine = [s for s in self._state.snapshots.values() if s.catalog_list is catalog_list]
        return sorted(mine, key=lambda s: (s.imported_at, s.snapshot_id), reverse=True)[:limit]

    async def content(self, snapshot_id: uuid.UUID) -> bytes | None:
        return self._state.files.get(snapshot_id)

    async def update(self, snapshot: CatalogSnapshot, *, expected: ImportStatus) -> bool:
        stored = self._state.snapshots.get(snapshot.snapshot_id)
        if stored is None or stored.status != expected:
            return False
        if snapshot.decided_by is not None and snapshot.decided_by in snapshot.makers:
            raise ConflictError(
                "the sales store refused the change",
                details={"constraint": "ck_catalog_snapshots_checker_not_maker"},
            )
        self._state.snapshots[snapshot.snapshot_id] = snapshot
        if snapshot.status != "queued":
            self._state.files.pop(snapshot.snapshot_id, None)
        return True

    async def write_records(
        self, snapshot_id: uuid.UUID, records: Sequence[tuple[str, Mapping[str, Any]]]
    ) -> None:
        keys = [key for key, _ in records]
        if len(set(keys)) != len(keys):
            raise ConflictError(
                "the sales store refused the change", details={"constraint": "uq_catalog_rows_key"}
            )
        self._state.records[snapshot_id] = [(key, dict(record)) for key, record in records]

    async def records(self, snapshot_id: uuid.UUID) -> Sequence[Mapping[str, Any]]:
        return [record for _, record in self._state.records.get(snapshot_id, [])]


class _Work:
    def __init__(self, store: MemoryCatalogStore, scope: SalesScope) -> None:
        self._store, self._scope = store, scope
        self._state = store.state(scope).copy()
        self.snapshots = _Snapshots(self._state)
        self.approvals = store.approvals.scoped(scope.tenant_id.value)
        self.audit = store.audit
        self.outbox = store.outbox

    async def commit(self) -> None:
        self._store.states[self._scope] = self._state
        self._state = self._state.copy()
        self.snapshots = _Snapshots(self._state)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None


@dataclass
class MemoryCatalogStore:
    """Implements `CatalogUnitOfWorkFactory` (module docstring)."""

    approvals: MemoryApprovals
    audit: MemoryAudit = field(default_factory=MemoryAudit)
    outbox: MemoryOutbox = field(default_factory=MemoryOutbox)
    states: dict[SalesScope, _ScopeState] = field(default_factory=dict)

    def state(self, scope: SalesScope) -> _ScopeState:
        return self.states.setdefault(scope, _ScopeState())

    def __call__(self, scope: SalesScope) -> _Work:
        return _Work(self, scope)


@dataclass(frozen=True)
class MemoryApprovedLists:
    """`ApprovedListsPort` over a `MemoryCatalogStore`: what each scope committed."""

    store: MemoryCatalogStore

    async def approved(self, scope: SalesScope, catalog_list: CatalogList) -> ApprovedList | None:
        state = self.store.state(scope)
        found = next(
            (
                s
                for s in state.snapshots.values()
                if s.catalog_list is catalog_list and s.status == "approved"
            ),
            None,
        )
        if found is None:
            return None
        documents = [record for _, record in state.records.get(found.snapshot_id, [])]
        return ApprovedList.of(
            catalog_list, found.snapshot_id, found.as_of, records_of(catalog_list, documents)
        )
