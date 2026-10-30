"""The status assistant's sessions in memory, for the eval world (ADR 0007).

Kept per (tenant, workspace, user), as the tables' policy keeps them: another
person, workspace or tenant asking for a session's id finds nothing, which is
what the SQL store's RLS does and what the graders and tests lean on.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from dw_platform.application.access_context import AccessContext
from dw_sales.application.assistant import AssistantStorePort
from dw_sales.domain.assistant import Session, Turn

_Key = tuple[uuid.UUID, uuid.UUID, uuid.UUID]


@dataclass
class _Held:
    sessions: dict[uuid.UUID, Session] = field(default_factory=dict)
    turns: dict[uuid.UUID, list[Turn]] = field(default_factory=dict)


@dataclass
class MemoryAssistantStore:
    """Implements `AssistantStorePort` over one person's sessions."""

    held: _Held

    async def session(self, session_id: uuid.UUID) -> Session | None:
        return self.held.sessions.get(session_id)

    async def sessions(self, limit: int) -> Sequence[Session]:
        newest = sorted(
            self.held.sessions.values(), key=lambda s: (s.last_turn_at, s.session_id), reverse=True
        )
        return newest[:limit]

    async def turns(self, session_id: uuid.UUID) -> Sequence[Turn]:
        return list(self.held.turns.get(session_id, []))

    async def open(self, session: Session) -> None:
        if session.session_id in self.held.sessions:
            raise ValueError("a session is opened once")
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
        self.held.sessions[turn.session_id] = Session(
            session_id=session.session_id,
            user_id=session.user_id,
            title=session.title,
            created_at=session.created_at,
            last_turn_at=turn.asked_at,
        )


@dataclass
class MemoryAssistantStores:
    """`AssistantStoreFactory` over every person's sessions."""

    people: dict[_Key, _Held] = field(default_factory=dict)

    @asynccontextmanager
    async def __call__(self, context: AccessContext) -> AsyncIterator[AssistantStorePort]:
        key = (context.tenant_id, context.workspace_id, context.principal_id)
        yield MemoryAssistantStore(self.people.setdefault(key, _Held()))
