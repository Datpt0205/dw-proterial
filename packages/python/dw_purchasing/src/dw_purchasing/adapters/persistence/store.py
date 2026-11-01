"""The `purchasing` schema behind `PurchasingUnitOfWork` (migration 2d0c58dc3806).

One transaction per unit of work, bound to the verified context's tenant and
workspace (`bind_tenant`, set for the transaction only), so every policy on
`purchasing.*` narrows the rows and no query here names a tenant of its own.
The audit row and a run-less approval are written in the same transaction,
through the platform's repositories the composition root hands in as
factories: this package names no platform adapter it does not own.

A case's identity, version and status are columns; the `body` is the request
and its mail, the rest of the aggregate as columns (`ck_cases_body`).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_kernel.errors import ConflictError
from dw_kernel.ids import TenantId, WorkspaceId
from dw_kernel.naming import NAMING_CONVENTION
from dw_platform.adapters.persistence.rule_versions import SqlRuleVersionStore
from dw_platform.adapters.persistence.tenant_session import TenantScope, bind_tenant
from dw_platform.application.access_context import AccessContext
from dw_platform.application.ports import AuditRepositoryPort
from dw_platform.application.rule_versions import ContextScope
from dw_purchasing.application.ports import ApprovalsPort, Disposition, MessageOutcome
from dw_purchasing.domain.cases import PurchaseCase

metadata = sa.MetaData(schema="purchasing", naming_convention=NAMING_CONVENTION)
_TS = sa.TIMESTAMP(timezone=True)

cases = sa.Table(
    "cases",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
    sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
    sa.Column("case_version", sa.Integer, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("source", sa.Text, nullable=False),
    sa.Column("body", JSONB, nullable=False),
    sa.Column("pr_no", sa.Text, sa.Computed("body #>> '{request,pr_no}'")),
    sa.Column("source_ref", sa.Text, sa.Computed("body #>> '{source_ref}'")),
    sa.Column(
        "approval_id", UUID(as_uuid=True), sa.Computed("(body #>> '{approval,approval_id}')::uuid")
    ),
    sa.Column("rules_ref", sa.Text, nullable=False),
    sa.Column("requested_by", UUID(as_uuid=True), sa.Computed("(body #>> '{requested_by}')::uuid")),
    sa.Column("received_by", UUID(as_uuid=True), nullable=False),
    sa.Column("received_at", _TS, nullable=False),
)

mail_outcomes = sa.Table(
    "mail_outcomes",
    metadata,
    sa.Column("tenant_id", UUID(as_uuid=True), primary_key=True),
    sa.Column("workspace_id", UUID(as_uuid=True), primary_key=True),
    sa.Column("message_id", sa.Text, primary_key=True),
    sa.Column("disposition", sa.Text, nullable=False),
    sa.Column("reason", sa.Text),
    sa.Column("case_id", UUID(as_uuid=True)),
    sa.Column("settled_by", UUID(as_uuid=True), nullable=False),
    sa.Column("settled_at", _TS, nullable=False),
)

AuditFactory = Callable[[AsyncSession], AuditRepositoryPort]
ApprovalsFactory = Callable[[AsyncSession], ApprovalsPort]
_BODY_KEYS = (
    "request",
    "source_ref",
    "check",
    "approval",
    "decision",
    "rfq",
    "offers",
    "selection",
    "po",
    "requested_by",
    "review",
)


def _body(case: PurchaseCase) -> dict[str, Any]:
    return case.model_dump(mode="json", include=set(_BODY_KEYS))


def _case(row: Any) -> PurchaseCase:
    return PurchaseCase.model_validate(
        {
            **row.body,
            "case_id": row.id,
            "case_version": row.case_version,
            "status": row.status,
            "source": row.source,
            "rules_ref": row.rules_ref,
            "received_by": row.received_by,
            "received_at": row.received_at,
        }
    )


class _Cases:
    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self._session = session
        self._scope = scope

    async def add(self, case: PurchaseCase) -> None:
        await self._session.execute(
            sa.insert(cases).values(
                id=case.case_id,
                tenant_id=self._scope.tenant_id,
                workspace_id=self._scope.workspace_id,
                case_version=case.case_version,
                status=case.status.value,
                source=case.source.value,
                body=_body(case),
                rules_ref=case.rules_ref,
                received_by=case.received_by,
                received_at=case.received_at,
            )
        )

    async def get(self, case_id: uuid.UUID) -> PurchaseCase | None:
        row = (await self._session.execute(sa.select(cases).where(cases.c.id == case_id))).first()
        return _case(row) if row is not None else None

    async def save(self, case: PurchaseCase, *, expected_version: int) -> None:
        moved = await self._session.execute(
            sa.update(cases)
            .where(cases.c.id == case.case_id, cases.c.case_version == expected_version)
            .values(case_version=case.case_version, status=case.status.value, body=_body(case))
        )
        if moved.rowcount != 1:  # type: ignore[attr-defined]
            raise ConflictError(
                "hồ sơ đã thay đổi: tải lại",
                details={"case_id": str(case.case_id), "rule": "stale_version"},
            )

    async def by_approval(self, approval_id: uuid.UUID) -> PurchaseCase | None:
        row = (
            await self._session.execute(sa.select(cases).where(cases.c.approval_id == approval_id))
        ).first()
        return _case(row) if row is not None else None

    async def waiting(self, statuses: frozenset[str], *, limit: int) -> Sequence[PurchaseCase]:
        # `ix_cases_tenant_id_workspace_id_status_received_at` carries it.
        query = (
            sa.select(cases)
            .where(cases.c.status.in_(sorted(statuses)))
            .order_by(cases.c.received_at, cases.c.id)
            .limit(limit)
        )
        return [_case(row) for row in (await self._session.execute(query)).all()]

    async def page(
        self,
        *,
        limit: int,
        before: tuple[datetime, uuid.UUID] | None,
        requested_by: uuid.UUID | None = None,
    ) -> Sequence[PurchaseCase]:
        query = sa.select(cases).order_by(cases.c.received_at.desc(), cases.c.id.desc())
        if requested_by is not None:
            # `ix_cases_tenant_id_requested_by_received_at` carries it.
            query = query.where(cases.c.requested_by == requested_by)
        if before is not None:
            at, case_id = before
            query = query.where(
                sa.tuple_(cases.c.received_at, cases.c.id)
                < sa.tuple_(sa.literal(at, _TS), sa.literal(case_id, UUID(as_uuid=True)))
            )
        rows = (await self._session.execute(query.limit(limit))).all()
        return [_case(row) for row in rows]


class _Outcomes:
    def __init__(self, session: AsyncSession, scope: TenantScope) -> None:
        self._session = session
        self._scope = scope

    async def get(self, message_id: str) -> MessageOutcome | None:
        row = (
            await self._session.execute(
                sa.select(mail_outcomes).where(mail_outcomes.c.message_id == message_id)
            )
        ).first()
        return _outcome(row) if row is not None else None

    async def add(self, outcome: MessageOutcome) -> None:
        try:
            async with self._session.begin_nested():
                await self._session.execute(
                    sa.insert(mail_outcomes).values(
                        tenant_id=self._scope.tenant_id,
                        workspace_id=self._scope.workspace_id,
                        message_id=outcome.message_id,
                        disposition=outcome.disposition.value,
                        reason=outcome.reason,
                        case_id=outcome.case_id,
                        settled_by=outcome.settled_by,
                        settled_at=outcome.settled_at,
                    )
                )
        except IntegrityError as exc:
            if "pk_mail_outcomes" not in str(exc.orig):
                raise
            raise ConflictError(
                "thư đã được xử lý", details={"message_id": outcome.message_id}
            ) from exc

    async def all(self) -> Sequence[MessageOutcome]:
        rows = (await self._session.execute(sa.select(mail_outcomes))).all()
        return [_outcome(row) for row in rows]


def _outcome(row: Any) -> MessageOutcome:
    return MessageOutcome(
        message_id=row.message_id,
        disposition=Disposition(row.disposition),
        reason=row.reason,
        case_id=row.case_id,
        settled_by=row.settled_by,
        settled_at=row.settled_at,
    )


class _Work:
    def __init__(
        self,
        session: AsyncSession,
        scope: TenantScope,
        audit: AuditFactory,
        approvals: ApprovalsFactory,
    ) -> None:
        self.cases = _Cases(session, scope)
        self.outcomes = _Outcomes(session, scope)
        self.audit = audit(session)
        self.approvals = approvals(session)
        self.rule_versions = SqlRuleVersionStore(
            session, ContextScope(TenantId(scope.tenant_id), WorkspaceId(_bound(scope)))
        )

    async def commit(self) -> None:
        """The transaction commits as the unit of work closes."""


def _bound(scope: TenantScope) -> uuid.UUID:
    assert scope.workspace_id is not None  # a verified context always names one
    return scope.workspace_id


class SqlPurchasingStore:
    """Implements `PurchasingUnitOfWork` (call it with a verified context)."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        audit: AuditFactory,
        approvals: ApprovalsFactory,
    ) -> None:
        self._session_factory = session_factory
        self._audit = audit
        self._approvals = approvals

    @asynccontextmanager
    async def __call__(self, context: AccessContext) -> AsyncIterator[_Work]:
        scope = TenantScope.from_access_context(context)
        async with self._session_factory() as session, session.begin():
            await bind_tenant(session, scope)
            yield _Work(session, scope, self._audit, self._approvals)
