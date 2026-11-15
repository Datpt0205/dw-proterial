"""The status assistant's conversations in memory, for the eval world (ADR
0007, ticket 46).

Kept per (tenant, workspace, user), as the tables' policy keeps them: another
person, workspace or tenant finds none of them, which is what the SQL store's
RLS does and what the graders and tests lean on. One general conversation per
person and one per case, as the table's unique indexes hold them.
"""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime

from dw_platform.application.access_context import AccessContext
from dw_sales.application.assistant import AssistantStorePort
from dw_sales.domain.assistant import Session, Turn

_Key = tuple[uuid.UUID, uuid.UUID, uuid.UUID]


@dataclass
class _Held:
    sessions: dict[uuid.UUID, Session] = field(default_factory=dict)
    turns: dict[uuid.UUID, list[Turn]] = field(default_factory=dict)


def _on(session: Session) -> uuid.UUID | None:
    return session.case.case_id if session.case is not None else None


@dataclass
class MemoryAssistantStore:
    """Implements `AssistantStorePort` over one person's conversations."""

    held: _Held

    def _newest(self) -> list[Session]:
        on_cases = [s for s in self.held.sessions.values() if s.case is not None]
        return sorted(on_cases, key=lambda s: (s.last_turn_at, s.session_id), reverse=True)

    async def conversation(self, case_id: uuid.UUID | None) -> Session | None:
        return next((s for s in self.held.sessions.values() if _on(s) == case_id), None)

    async def recent(self, limit: int) -> Sequence[Session]:
        return self._newest()[:limit]

    async def unread(self, limit: int) -> Sequence[Session]:
        return [s for s in self._newest() if s.unread][:limit]

    async def turns(self, session_id: uuid.UUID) -> Sequence[Turn]:
        return list(self.held.turns.get(session_id, []))

    async def open(self, session: Session) -> None:
        if session.session_id in self.held.sessions:
            raise ValueError("a conversation is opened once")
        if await self.conversation(_on(session)) is not None:
            # The SQL store's unique index: one per case, one general.
            raise ValueError("this person already has that conversation")
        self.held.sessions[session.session_id] = session
        self.held.turns[session.session_id] = []

    async def add(self, turn: Turn) -> None:
        session = self.held.sessions.get(turn.session_id)
        if session is None:
            # The SQL store's foreign key refuses a turn in no session of theirs.
            raise ValueError("no such session of this person")
        turns = self.held.turns[turn.session_id]
        if any(t.seq == turn.seq for t in turns):
            raise ValueError("a turn's place is taken")
        turns.append(turn)
        self.held.sessions[turn.session_id] = dataclasses.replace(
            session, last_turn_at=turn.asked_at
        )

    async def seen(self, session_id: uuid.UUID, at: datetime) -> None:
        session = self.held.sessions.get(session_id)
        if session is not None:
            self.held.sessions[session_id] = dataclasses.replace(session, last_read_at=at)


@dataclass
class MemoryAssistantStores:
    """`AssistantStoreFactory` over every person's conversations."""

    people: dict[_Key, _Held] = field(default_factory=dict)

    @asynccontextmanager
    async def __call__(self, context: AccessContext) -> AsyncIterator[AssistantStorePort]:
        key = (context.tenant_id, context.workspace_id, context.principal_id)
        yield MemoryAssistantStore(self.people.setdefault(key, _Held()))
