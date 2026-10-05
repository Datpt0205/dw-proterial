"""The sales records that are not cases: message dispositions, the case event
log, served sources, artifacts and the pause switch. Each implements its port
inside a unit of work's transaction."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import RowMapping
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence._rows import refusals_named, scope_values
from dw_sales.application.case_store import (
    ArtifactRecord,
    LoggedEvent,
    LoggedMessage,
    ServedSource,
    SourceRegion,
    WorkerState,
)
from dw_sales.application.ports import SalesScope
from dw_sales.domain.dispositions import CaseKind, MessageDisposition

_M = tables.messages
_S = tables.source_served
_A = tables.artifacts
_W = tables.worker_state
_E = tables.case_events


def _case_columns(kind: CaseKind | None, case_id: uuid.UUID | None) -> dict[str, uuid.UUID | None]:
    """A case reference as the two foreign keys a row holds, one of them set."""
    return {
        "order_case_id": case_id if kind is CaseKind.ORDER else None,
        "quote_case_id": case_id if kind is CaseKind.QUOTE else None,
    }


def _case_of(row: RowMapping) -> tuple[CaseKind, uuid.UUID] | None:
    if row["order_case_id"] is not None:
        return CaseKind.ORDER, row["order_case_id"]
    if row["quote_case_id"] is not None:
        return CaseKind.QUOTE, row["quote_case_id"]
    return None


@dataclass(frozen=True)
class SqlMessageLog:
    """Implements `MessageLogPort`."""

    session: AsyncSession
    scope: SalesScope

    async def record(self, disposition: MessageDisposition, processed_at: datetime) -> None:
        values = {
            "disposition": disposition.kind.value,
            **_case_columns(disposition.case_kind, disposition.case_id),
            "routing_reason": disposition.reason.value if disposition.reason else None,
            "detail": disposition.detail,
            "owner": disposition.owner,
            "customer_code": disposition.customer_code,
            "compliance": (
                disposition.compliance.model_dump(mode="json") if disposition.compliance else None
            ),
            "processed_at": processed_at,
        }
        statement = pg_insert(_M).values(
            id=uuid.uuid4(),
            **scope_values(self.scope),
            message_id=disposition.message_id,
            **values,
        )
        async with refusals_named(self.session, message_id=disposition.message_id):
            await self.session.execute(
                statement.on_conflict_do_update(
                    index_elements=[_M.c.tenant_id, _M.c.workspace_id, _M.c.message_id],
                    set_={name: statement.excluded[name] for name in values},
                )
            )

    async def get(self, message_id: str) -> MessageDisposition | None:
        row = (
            (await self.session.execute(sa.select(_M).where(_M.c.message_id == message_id)))
            .mappings()
            .first()
        )
        return None if row is None else _disposition(row)

    async def list_all(self) -> Sequence[LoggedMessage]:
        rows = (
            await self.session.execute(
                sa.select(_M).order_by(_M.c.processed_at.desc(), _M.c.id.desc())
            )
        ).mappings()
        return [LoggedMessage(_disposition(row), row["processed_at"]) for row in rows]


def _disposition(row: RowMapping) -> MessageDisposition:
    case = _case_of(row)
    return MessageDisposition.model_validate(
        {
            "message_id": row["message_id"],
            "kind": row["disposition"],
            "case_kind": case[0] if case else None,
            "case_id": case[1] if case else None,
            "reason": row["routing_reason"],
            "detail": row["detail"],
            "owner": row["owner"],
            "customer_code": row["customer_code"],
            "compliance": row["compliance"],
        }
    )


@dataclass(frozen=True)
class SqlCaseEventLog:
    """Implements `CaseEventLogPort`: the workspace's case events, read only.

    Written beside each case by the case repositories (`record_event`)."""

    session: AsyncSession
    scope: SalesScope

    async def list_all(self) -> Sequence[LoggedEvent]:
        rows = await self.session.execute(
            sa.select(
                _E.c.case_kind,
                _E.c.case_id,
                _E.c.case_version,
                _E.c.action,
                _E.c.from_status,
                _E.c.to_status,
                _E.c.actor_kind,
                _E.c.occurred_at,
            ).order_by(_E.c.occurred_at, _E.c.case_version, _E.c.id)
        )
        return [
            LoggedEvent(
                case_kind=CaseKind(r.case_kind),
                case_id=r.case_id,
                case_version=r.case_version,
                action=r.action,
                from_status=r.from_status,
                to_status=r.to_status,
                actor_kind=r.actor_kind,
                occurred_at=r.occurred_at,
            )
            for r in rows
        ]


@dataclass(frozen=True)
class SqlSourceServed:
    """Implements `SourceServedPort`."""

    session: AsyncSession
    scope: SalesScope

    async def record(self, served: ServedSource) -> None:
        async with refusals_named(self.session, case_id=str(served.case_id)):
            await self.session.execute(
                pg_insert(_S)
                .values(
                    id=uuid.uuid4(),
                    **scope_values(self.scope),
                    principal_id=served.principal_id,
                    **_case_columns(served.case_kind, served.case_id),
                    case_version=served.case_version,
                    attachment_id=served.attachment_id,
                    attachment_sha256=served.attachment_sha256,
                    page=served.page,
                    sheet=served.sheet,
                    served_at=served.served_at,
                )
                .on_conflict_do_nothing()
            )

    async def served(
        self, principal_id: uuid.UUID, case_kind: CaseKind, case_id: uuid.UUID, case_version: int
    ) -> frozenset[SourceRegion]:
        column = _S.c.order_case_id if case_kind is CaseKind.ORDER else _S.c.quote_case_id
        rows = await self.session.execute(
            sa.select(_S.c.attachment_id, _S.c.page, _S.c.sheet).where(
                column == case_id,
                _S.c.case_version == case_version,
                _S.c.principal_id == principal_id,
            )
        )
        return frozenset(SourceRegion(r.attachment_id, r.page, r.sheet) for r in rows)


@dataclass(frozen=True)
class SqlArtifactLog:
    """Implements `ArtifactLogPort`."""

    session: AsyncSession
    scope: SalesScope

    async def add(self, artifact: ArtifactRecord) -> None:
        async with refusals_named(self.session, artifact_id=str(artifact.artifact_id)):
            await self.session.execute(
                sa.insert(_A).values(
                    id=artifact.artifact_id,
                    **scope_values(self.scope),
                    **_case_columns(artifact.case_kind, artifact.case_id),
                    case_version=artifact.case_version,
                    kind=artifact.kind,
                    template_ref=artifact.template_ref,
                    object_key=artifact.object_key(self.scope),
                    sha256=artifact.sha256,
                    content_type=artifact.content_type,
                    size_bytes=artifact.size_bytes,
                    created_by=artifact.created_by,
                    created_at=artifact.created_at,
                )
            )

    async def get(self, artifact_id: uuid.UUID) -> ArtifactRecord | None:
        row = (
            (await self.session.execute(sa.select(_A).where(_A.c.id == artifact_id)))
            .mappings()
            .first()
        )
        if row is None:
            return None
        case = _case_of(row)
        assert case is not None  # ck_artifacts_one_case
        return ArtifactRecord(
            artifact_id=row["id"],
            case_kind=case[0],
            case_id=case[1],
            case_version=row["case_version"],
            kind=row["kind"],
            template_ref=row["template_ref"],
            sha256=row["sha256"],
            content_type=row["content_type"],
            size_bytes=row["size_bytes"],
            created_by=row["created_by"],
            created_at=row["created_at"],
        )


@dataclass(frozen=True)
class SqlWorkerSwitch:
    """Implements `WorkerSwitchPort`: one row per workspace, the last change."""

    session: AsyncSession
    scope: SalesScope

    async def state(self) -> WorkerState:
        scope = scope_values(self.scope)
        row = (
            (
                await self.session.execute(
                    sa.select(_W).where(
                        _W.c.tenant_id == scope["tenant_id"],
                        _W.c.workspace_id == scope["workspace_id"],
                    )
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            return WorkerState(paused=False)
        return WorkerState(
            paused=row["paused"],
            changed_by=row["changed_by"],
            changed_at=row["changed_at"],
            reason=row["reason"],
        )

    async def set(self, state: WorkerState) -> None:
        values = {
            "paused": state.paused,
            "changed_by": state.changed_by,
            "changed_at": state.changed_at,
            "reason": state.reason,
        }
        statement = pg_insert(_W).values(**scope_values(self.scope), **values)
        async with refusals_named(self.session, table="worker_state"):
            await self.session.execute(
                statement.on_conflict_do_update(
                    index_elements=[_W.c.tenant_id, _W.c.workspace_id],
                    set_={name: statement.excluded[name] for name in values},
                )
            )
