"""`AssistantStorePort` on PostgreSQL (`sales.assistant_sessions`,
`sales.assistant_turns`; dw_sales ADR 0007, ticket 46), and the worker's
retention (`sales.prune_assistant_sessions()`).

Each store is one transaction bound to the caller's tenant, workspace **and
user** (`tenant_session`): the tables' policy reads all three, so another
person's conversation is not found, whatever case is asked for. The
statements name the same three again, so a policy dropped by mistake still
finds nothing. A conversation is found by its case (or as the general one),
which the table's unique indexes keep to one per person.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.application.access_context import AccessContext
from dw_sales.adapters.persistence import tables
from dw_sales.application.assistant import AssistantStorePort
from dw_sales.domain.assistant import CaseRef, QuestionKind, Session, Turn, proposal_from_stored
from dw_sales.domain.dispositions import CaseKind

_S = tables.assistant_sessions
_T = tables.assistant_turns


def _ref(kind: str | None, case_id: uuid.UUID | None, label: str | None) -> CaseRef | None:
    if kind is None or case_id is None or label is None:
        return None
    return CaseRef(CaseKind(kind), case_id, label)


def _session(row: RowMapping) -> Session:
    return Session(
        session_id=row["id"],
        user_id=row["user_id"],
        title=row["title"],
        created_at=row["created_at"],
        last_turn_at=row["last_turn_at"],
        # A case conversation's title is its case's label when it was opened.
        case=_ref(row["case_kind"], row["case_id"], row["title"]),
        last_read_at=row["last_read_at"],
    )


def _turn(row: RowMapping) -> Turn:
    cites: list[dict[str, Any]] = row["cites"]
    return Turn(
        session_id=row["session_id"],
        seq=row["seq"],
        asked_at=row["asked_at"],
        question=row["question"],
        kind=QuestionKind(row["kind"]),
        reference=row["reference"],
        answer=row["answer"],
        cites=tuple(
            CaseRef(CaseKind(c["kind"]), uuid.UUID(c["case_id"]), c["label"]) for c in cites
        ),
        focus=_ref(row["focus_kind"], row["focus_case_id"], row["focus_label"]),
        answered_by=row["answered_by"],
        proposal=proposal_from_stored(row["proposal"]) if row["proposal"] else None,
    )


@dataclass(frozen=True)
class SqlAssistantStore:
    """Implements `AssistantStorePort` inside one bound transaction."""

    db: AsyncSession
    tenant_id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID

    def _mine(self, table: sa.Table) -> tuple[sa.ColumnElement[bool], ...]:
        return (
            table.c.tenant_id == self.tenant_id,
            table.c.workspace_id == self.workspace_id,
            table.c.user_id == self.user_id,
        )

    async def conversation(self, case_id: uuid.UUID | None) -> Session | None:
        on = _S.c.case_id.is_(None) if case_id is None else _S.c.case_id == case_id
        row = (await self.db.execute(sa.select(_S).where(on, *self._mine(_S)))).mappings().first()
        return None if row is None else _session(row)

    async def _on_cases(self, limit: int, *where: sa.ColumnElement[bool]) -> Sequence[Session]:
        """The person's case conversations, the most recently talked about
        first: `ix_assistant_sessions_tenant_id_user_id_last_turn_at_id`."""
        rows = (
            await self.db.execute(
                sa.select(_S)
                .where(_S.c.case_id.is_not(None), *where, *self._mine(_S))
                .order_by(_S.c.last_turn_at.desc(), _S.c.id.desc())
                .limit(limit)
            )
        ).mappings()
        return [_session(r) for r in rows]

    async def recent(self, limit: int) -> Sequence[Session]:
        return await self._on_cases(limit)

    async def unread(self, limit: int) -> Sequence[Session]:
        return await self._on_cases(
            limit,
            sa.or_(_S.c.last_read_at.is_(None), _S.c.last_turn_at > _S.c.last_read_at),
        )

    async def turns(self, session_id: uuid.UUID) -> Sequence[Turn]:
        rows = (
            await self.db.execute(
                sa.select(_T)
                .where(_T.c.session_id == session_id, *self._mine(_T))
                .order_by(_T.c.seq)
            )
        ).mappings()
        return [_turn(r) for r in rows]

    async def open(self, session: Session) -> None:
        await self.db.execute(
            sa.insert(_S).values(
                id=session.session_id,
                tenant_id=self.tenant_id,
                workspace_id=self.workspace_id,
                user_id=self.user_id,
                title=session.title,
                created_at=session.created_at,
                last_turn_at=session.last_turn_at,
                case_kind=session.case.kind.value if session.case else None,
                case_id=session.case.case_id if session.case else None,
            )
        )

    async def add(self, turn: Turn) -> None:
        focus = turn.focus
        await self.db.execute(
            sa.insert(_T).values(
                session_id=turn.session_id,
                seq=turn.seq,
                tenant_id=self.tenant_id,
                workspace_id=self.workspace_id,
                user_id=self.user_id,
                asked_at=turn.asked_at,
                question=turn.question,
                kind=turn.kind.value,
                reference=turn.reference,
                answer=turn.answer,
                cites=[
                    {"kind": c.kind.value, "case_id": str(c.case_id), "label": c.label}
                    for c in turn.cites
                ],
                focus_kind=focus.kind.value if focus else None,
                focus_case_id=focus.case_id if focus else None,
                focus_label=focus.label if focus else None,
                answered_by=turn.answered_by,
                proposal=turn.proposal.stored() if turn.proposal else None,
            )
        )
        await self.db.execute(
            sa.update(_S)
            .where(_S.c.id == turn.session_id, *self._mine(_S))
            .values(last_turn_at=turn.asked_at)
        )

    async def seen(self, session_id: uuid.UUID, at: datetime) -> None:
        await self.db.execute(
            sa.update(_S).where(_S.c.id == session_id, *self._mine(_S)).values(last_read_at=at)
        )


@dataclass(frozen=True)
class SqlAssistantStoreFactory:
    """`AssistantStoreFactory`: one transaction per use, bound to the caller."""

    session_factory: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def __call__(self, context: AccessContext) -> AsyncIterator[AssistantStorePort]:
        async with tenant_session(
            self.session_factory, TenantScope.from_access_context(context)
        ) as session:
            yield SqlAssistantStore(
                session, context.tenant_id, context.workspace_id, context.principal_id
            )


@dataclass(frozen=True)
class SqlAssistantRetention:
    """Implements `dw_worker.consumers.retention.RetentionPrunePort`.

    The window is the database's (`sales.prune_assistant_sessions()`, 30 days
    after a session's last turn): a technical bound on a working conversation,
    like the in-app inbox's, not a legal term, so it is not in
    `retention@*.yaml`."""

    session_factory: async_sessionmaker[AsyncSession]

    async def prune(self) -> None:
        async with self.session_factory() as session, session.begin():
            await session.execute(sa.text("SELECT sales.prune_assistant_sessions()"))
