"""`YcbgExportUnitOfWorkFactory` in memory, for unit tests and evals (ticket 16).

Holds the SQL store's contract, not only the happy path: each scope's exports
are its own (what RLS gives the SQL store), `settle` writes only an export
still queued and drops its file, `prune` drops an export with its file, and a
transaction that does not commit writes nothing. The platform's audit and
outbox are written at once, as the eval store's are.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from types import TracebackType
from typing import Self

from dw_agent_runtime.testing.memory_runtime import MemoryAudit, MemoryOutbox
from dw_kernel.errors import ConflictError
from dw_sales.application.ports import SalesScope
from dw_sales.application.ycbg_exports import YcbgExport


@dataclass
class _ScopeState:
    exports: dict[uuid.UUID, YcbgExport] = field(default_factory=dict)
    files: dict[uuid.UUID, bytes] = field(default_factory=dict)

    def copy(self) -> _ScopeState:
        return _ScopeState(dict(self.exports), dict(self.files))


class _Exports:
    def __init__(self, state: _ScopeState) -> None:
        self._state = state

    async def add(self, export: YcbgExport, content: bytes) -> None:
        if export.export_id in self._state.exports:
            raise ConflictError(
                "the sales store refused the change", details={"constraint": "pk_ycbg_exports"}
            )
        self._state.exports[export.export_id] = export
        self._state.files[export.export_id] = content

    async def get(self, export_id: uuid.UUID) -> YcbgExport | None:
        return self._state.exports.get(export_id)

    async def latest(self, limit: int) -> Sequence[YcbgExport]:
        ordered = sorted(
            self._state.exports.values(),
            key=lambda e: (e.uploaded_at, e.export_id),
            reverse=True,
        )
        return ordered[:limit]

    async def content(self, export_id: uuid.UUID) -> bytes | None:
        return self._state.files.get(export_id)

    async def settle(self, export: YcbgExport) -> bool:
        stored = self._state.exports.get(export.export_id)
        if stored is None or stored.status != "queued":
            return False
        self._state.exports[export.export_id] = export
        self._state.files.pop(export.export_id, None)
        return True

    async def prune(self, before: datetime) -> int:
        old = [e.export_id for e in self._state.exports.values() if e.uploaded_at < before]
        for export_id in old:
            del self._state.exports[export_id]
            self._state.files.pop(export_id, None)
        return len(old)

    async def queued_before(self, before: datetime) -> Sequence[YcbgExport]:
        return sorted(
            (
                e
                for e in self._state.exports.values()
                if e.status == "queued" and e.uploaded_at < before
            ),
            key=lambda e: e.uploaded_at,
        )


class _Work:
    def __init__(self, store: MemoryYcbgExportStore, scope: SalesScope) -> None:
        self._store, self._scope = store, scope
        self._state = store.state(scope).copy()
        self.ycbg_exports = _Exports(self._state)
        self.audit = store.audit
        self.outbox = store.outbox

    async def commit(self) -> None:
        self._store.states[self._scope] = self._state
        self._state = self._state.copy()
        self.ycbg_exports = _Exports(self._state)

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
class MemoryYcbgExportStore:
    """Implements `YcbgExportUnitOfWorkFactory` (module docstring)."""

    audit: MemoryAudit = field(default_factory=MemoryAudit)
    outbox: MemoryOutbox = field(default_factory=MemoryOutbox)
    states: dict[SalesScope, _ScopeState] = field(default_factory=dict)

    def state(self, scope: SalesScope) -> _ScopeState:
        return self.states.setdefault(scope, _ScopeState())

    def __call__(self, scope: SalesScope) -> _Work:
        return _Work(self, scope)
