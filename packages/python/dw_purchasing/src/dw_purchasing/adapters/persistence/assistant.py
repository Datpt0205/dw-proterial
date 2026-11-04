"""`AssistantStorePort` on PostgreSQL (`purchasing.assistant_sessions`,
`purchasing.assistant_turns`, migration 63b96e56db85), and the worker's
retention (`purchasing.prune_assistant_sessions()`).

Each call is one transaction bound to the caller's tenant, workspace **and
user** (`tenant_session`): the policy reads all three, so another person's
session is not found, whatever id is asked for. The statements name the same
three again, so a policy dropped by mistake still finds nothing.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy import RowMapping
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_platform.application.access_context import AccessContext
from dw_purchasing.adapters.persistence.store import metadata
from dw_purchasing.domain.assistant import AssistantQuestionKind, CaseRef, Session, Turn

_S = sa.Table(
    "assistant_sessions",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
    sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
    sa.Column("user_id", UUID(as_uuid=True), nullable=False),
    sa.Column("title", sa.Text, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("last_turn_at", sa.DateTime(timezone=True), nullable=False),
)
_T = sa.Table(
    "assistant_turns",
    metadata,
    sa.Column("session_id", UUID(as_uuid=True), primary_key=True),
    sa.Column("seq", sa.Integer, primary_key=True),
    sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
    sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
    sa.Column("user_id", UUID(as_uuid=True), nullable=False),
    sa.Column("asked_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("question", sa.Text, nullable=False),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("reference", sa.Text),
    sa.Column("answer", sa.Text, nullable=False),
    sa.Column("cites", JSONB, nullable=False),
    sa.Column("focus_case_id", UUID(as_uuid=True)),
    sa.Column("focus_label", sa.Text),
    sa.Column("answered_by", sa.Text, nullable=False),
)


def _session(row: RowMapping) -> Session:
    return Session(
        session_id=row["id"],
        user_id=row["user_id"],
        title=row["title"],
        created_at=row["created_at"],
        last_turn_at=row["last_turn_at"],
    )


def _turn(row: RowMapping) -> Turn:
    cites: list[dict[str, Any]] = row["cites"]
    focus = (
        CaseRef(row["focus_case_id"], row["focus_label"])
        if row["focus_case_id"] is not None
        else None
    )
    return Turn(
        session_id=row["session_id"],
        seq=row["seq"],
        asked_at=row["asked_at"],
        question=row["question"],
        kind=AssistantQuestionKind(row["kind"]),
        reference=row["reference"],
        answer=row["answer"],
        cites=tuple(CaseRef(uuid.UUID(c["case_id"]), c["label"]) for c in cites),
        focus=focus,
        answered_by=row["answered_by"],
    )


def _mine(table: sa.Table, context: AccessContext) -> tuple[sa.ColumnElement[bool], ...]:
    return (
        table.c.tenant_id == context.tenant_id,
        table.c.workspace_id == context.workspace_id,
        table.c.user_id == context.principal_id,
    )


@dataclass(frozen=True)
class SqlAssistantStore:
    """Implements `AssistantStorePort`."""

    session_factory: async_sessionmaker[AsyncSession]

    def _bound(self, context: AccessContext) -> Any:
        return tenant_session(self.session_factory, TenantScope.from_access_context(context))

    async def sessions(self, context: AccessContext, *, limit: int) -> Sequence[Session]:
        async with self._bound(context) as db:
            rows = (
                await db.execute(
                    sa.select(_S)
                    .where(*_mine(_S, context))
                    .order_by(_S.c.last_turn_at.desc(), _S.c.id.desc())
                    .limit(limit)
                )
            ).mappings()
            return [_session(r) for r in rows]

    async def session(self, context: AccessContext, session_id: uuid.UUID) -> Session | None:
        async with self._bound(context) as db:
            row = (
                (await db.execute(sa.select(_S).where(_S.c.id == session_id, *_mine(_S, context))))
                .mappings()
                .first()
            )
            return None if row is None else _session(row)

    async def turns(self, context: AccessContext, session_id: uuid.UUID) -> Sequence[Turn]:
        async with self._bound(context) as db:
            rows = (
                await db.execute(
                    sa.select(_T)
                    .where(_T.c.session_id == session_id, *_mine(_T, context))
                    .order_by(_T.c.seq)
                )
            ).mappings()
            return [_turn(r) for r in rows]

    async def append(self, context: AccessContext, session: Session, turn: Turn) -> None:
        mine = {
            "tenant_id": context.tenant_id,
            "workspace_id": context.workspace_id,
            "user_id": context.principal_id,
        }
        async with self._bound(context) as db:
            if turn.seq == 1:
                await db.execute(
                    sa.insert(_S).values(
                        id=session.session_id,
                        title=session.title,
                        created_at=session.created_at,
                        last_turn_at=session.last_turn_at,
                        **mine,
                    )
                )
            focus = turn.focus
            await db.execute(
                sa.insert(_T).values(
                    session_id=turn.session_id,
                    seq=turn.seq,
                    asked_at=turn.asked_at,
                    question=turn.question,
                    kind=turn.kind.value,
                    reference=turn.reference,
                    answer=turn.answer,
                    cites=[{"case_id": str(c.case_id), "label": c.label} for c in turn.cites],
                    focus_case_id=focus.case_id if focus else None,
                    focus_label=focus.label if focus else None,
                    answered_by=turn.answered_by,
                    **mine,
                )
            )
            await db.execute(
                sa.update(_S)
                .where(_S.c.id == turn.session_id, *_mine(_S, context))
                .values(last_turn_at=turn.asked_at)
            )


@dataclass(frozen=True)
class SqlAssistantRetention:
    """Implements the worker's retention prune port: the database's window
    (`purchasing.prune_assistant_sessions()`, 30 days after a session's last
    turn), a bound on a working conversation like DW1's, not a legal term."""

    session_factory: async_sessionmaker[AsyncSession]

    async def prune(self) -> None:
        async with self.session_factory() as session, session.begin():
            await session.execute(sa.text("SELECT purchasing.prune_assistant_sessions()"))
