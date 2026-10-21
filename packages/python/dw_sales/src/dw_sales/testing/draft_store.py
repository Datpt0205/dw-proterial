"""`RuleDraftUnitOfWorkFactory` in memory, for unit tests and evals
("Tạo từ tệp mẫu").

Holds the SQL store's contract, not only the happy path: each scope's drafts
are its own (what RLS gives the SQL store), `settle` writes only a draft still
queued and drops its file, `prune` drops a draft with its file, and a
transaction that does not commit writes nothing. The platform's audit and
outbox are written at once, as the eval store's are.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from types import TracebackType
from typing import Self

from dw_agent_runtime.testing.memory_runtime import MemoryAudit, MemoryOutbox
from dw_kernel.errors import ConflictError
from dw_sales.application.ports import SalesScope
from dw_sales.application.rule_drafts import RuleDraft


@dataclass
class _ScopeState:
    drafts: dict[uuid.UUID, RuleDraft] = field(default_factory=dict)
    files: dict[uuid.UUID, bytes] = field(default_factory=dict)

    def copy(self) -> _ScopeState:
        return _ScopeState(dict(self.drafts), dict(self.files))


class _Drafts:
    def __init__(self, state: _ScopeState) -> None:
        self._state = state

    async def add(self, draft: RuleDraft, content: bytes) -> None:
        if draft.draft_id in self._state.drafts:
            raise ConflictError(
                "the sales store refused the change", details={"constraint": "pk_rule_drafts"}
            )
        self._state.drafts[draft.draft_id] = draft
        self._state.files[draft.draft_id] = content

    async def get(self, draft_id: uuid.UUID) -> RuleDraft | None:
        return self._state.drafts.get(draft_id)

    async def content(self, draft_id: uuid.UUID) -> bytes | None:
        return self._state.files.get(draft_id)

    async def settle(self, draft: RuleDraft) -> bool:
        stored = self._state.drafts.get(draft.draft_id)
        if stored is None or stored.status != "queued":
            return False
        self._state.drafts[draft.draft_id] = draft
        self._state.files.pop(draft.draft_id, None)
        return True

    async def prune(self, before: datetime) -> int:
        old = [d.draft_id for d in self._state.drafts.values() if d.requested_at < before]
        for draft_id in old:
            del self._state.drafts[draft_id]
            self._state.files.pop(draft_id, None)
        return len(old)


class _Work:
    def __init__(self, store: MemoryRuleDraftStore, scope: SalesScope) -> None:
        self._store, self._scope = store, scope
        self._state = store.state(scope).copy()
        self.drafts = _Drafts(self._state)
        self.audit = store.audit
        self.outbox = store.outbox

    async def commit(self) -> None:
        self._store.states[self._scope] = self._state
        self._state = self._state.copy()
        self.drafts = _Drafts(self._state)

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
class MemoryRuleDraftStore:
    """Implements `RuleDraftUnitOfWorkFactory` (module docstring)."""

    audit: MemoryAudit = field(default_factory=MemoryAudit)
    outbox: MemoryOutbox = field(default_factory=MemoryOutbox)
    states: dict[SalesScope, _ScopeState] = field(default_factory=dict)

    def state(self, scope: SalesScope) -> _ScopeState:
        return self.states.setdefault(scope, _ScopeState())

    def __call__(self, scope: SalesScope) -> _Work:
        return _Work(self, scope)
