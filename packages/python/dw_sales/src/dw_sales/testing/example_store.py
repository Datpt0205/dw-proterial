"""`ExampleUnitOfWorkFactory` in memory, for unit tests and evals (ticket 38).

Holds the SQL store's contract, not only the happy path: each scope's
examples are its own (what RLS gives the SQL store), `settle` writes only an
example still queued and drops its files, `submit` only a replayed one,
`prune` drops an example never sent with its files, a worked pair is its
scope's (ticket 41), and a transaction that does not commit writes nothing.
The platform's audit and outbox are written at once, as the eval store's
are.
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
from dw_sales.application.salesorder_learning import SalesOrderExample, WorkedPair


@dataclass
class _ScopeState:
    examples: dict[uuid.UUID, SalesOrderExample] = field(default_factory=dict)
    files: dict[uuid.UUID, tuple[bytes, bytes]] = field(default_factory=dict)
    pairs: list[WorkedPair] = field(default_factory=list)

    def copy(self) -> _ScopeState:
        return _ScopeState(dict(self.examples), dict(self.files), list(self.pairs))


class _Examples:
    def __init__(self, state: _ScopeState) -> None:
        self._state = state

    async def add(self, example: SalesOrderExample, po: bytes, salesorder: bytes) -> None:
        if example.example_id in self._state.examples:
            raise ConflictError(
                "the sales store refused the change",
                details={"constraint": "pk_salesorder_examples"},
            )
        self._state.examples[example.example_id] = example
        self._state.files[example.example_id] = (po, salesorder)

    async def get(self, example_id: uuid.UUID) -> SalesOrderExample | None:
        return self._state.examples.get(example_id)

    async def files(self, example_id: uuid.UUID) -> tuple[bytes, bytes] | None:
        return self._state.files.get(example_id)

    async def settle(self, example: SalesOrderExample) -> bool:
        stored = self._state.examples.get(example.example_id)
        if stored is None or stored.status != "queued":
            return False
        self._state.examples[example.example_id] = example
        self._state.files.pop(example.example_id, None)
        return True

    async def submit(self, example_id: uuid.UUID, version_id: uuid.UUID) -> bool:
        stored = self._state.examples.get(example_id)
        if stored is None or stored.status != "replayed":
            return False
        self._state.examples[example_id] = stored.model_copy(
            update={"status": "submitted", "version_id": version_id}
        )
        return True

    async def for_customer(self, customer_code: str, limit: int) -> Sequence[SalesOrderExample]:
        found = [e for e in self._state.examples.values() if e.customer_code == customer_code]
        return sorted(found, key=lambda e: e.requested_at, reverse=True)[:limit]

    async def for_version(self, version_id: uuid.UUID) -> SalesOrderExample | None:
        return next((e for e in self._state.examples.values() if e.version_id == version_id), None)

    async def prune(self, before: datetime) -> int:
        old = [
            e.example_id
            for e in self._state.examples.values()
            if e.requested_at < before and e.status != "submitted"
        ]
        for example_id in old:
            del self._state.examples[example_id]
            self._state.files.pop(example_id, None)
        return len(old)


class _Pairs:
    def __init__(self, state: _ScopeState) -> None:
        self._state = state

    async def add(self, pair: WorkedPair) -> None:
        if any(p.pair_id == pair.pair_id for p in self._state.pairs):
            raise ConflictError(
                "the sales store refused the change",
                details={"constraint": "pk_salesorder_pairs"},
            )
        self._state.pairs.append(pair)

    async def for_customer(self, customer_code: str, limit: int) -> Sequence[WorkedPair]:
        found = [p for p in self._state.pairs if p.customer_code == customer_code]
        return sorted(found, key=lambda p: p.added_at, reverse=True)[:limit]


class _Work:
    def __init__(self, store: MemoryExampleStore, scope: SalesScope) -> None:
        self._store, self._scope = store, scope
        self._state = store.state(scope).copy()
        self.examples = _Examples(self._state)
        self.pairs = _Pairs(self._state)
        self.audit = store.audit
        self.outbox = store.outbox

    async def commit(self) -> None:
        self._store.states[self._scope] = self._state
        self._state = self._state.copy()
        self.examples = _Examples(self._state)
        self.pairs = _Pairs(self._state)

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
class MemoryExampleStore:
    """Implements `ExampleUnitOfWorkFactory` (module docstring)."""

    audit: MemoryAudit = field(default_factory=MemoryAudit)
    outbox: MemoryOutbox = field(default_factory=MemoryOutbox)
    states: dict[SalesScope, _ScopeState] = field(default_factory=dict)

    def state(self, scope: SalesScope) -> _ScopeState:
        return self.states.setdefault(scope, _ScopeState())

    def __call__(self, scope: SalesScope) -> _Work:
        return _Work(self, scope)
