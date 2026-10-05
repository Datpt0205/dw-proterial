"""What every sales repository shares: the scope columns, the event row, and
how a database refusal is reported.

**A refusal never echoes the row.** Postgres reports a CHECK violation with
the whole failing row in its DETAIL, and a sales row holds prices and a
customer's text. So an integrity error becomes a `ConflictError` naming the
constraint, raised `from None`: the driver's message, and its DETAIL, do not
ride along in the traceback into a log (spec decision 8).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from dw_kernel.errors import ConflictError, DomainError, NotFoundError
from dw_sales.adapters.persistence import tables
from dw_sales.application.case_store import CaseEvent
from dw_sales.application.ports import SalesScope
from dw_sales.domain.dispositions import CaseKind


def scope_values(scope: SalesScope) -> dict[str, uuid.UUID]:
    return {"tenant_id": scope.tenant_id.value, "workspace_id": scope.workspace_id.value}


def constraint_of(error: IntegrityError) -> str | None:
    """The constraint the database named, or None when the driver gave none."""
    # asyncpg's own exception carries it; SQLAlchemy wraps it as the cause.
    cause = getattr(error.orig, "__cause__", None)
    name = getattr(cause, "constraint_name", None)
    return name if isinstance(name, str) else None


# The separation-of-duties constraints, by the rule a caller reports (spec
# decision 7): the same `rule` the domain's own refusal names.
_RULES = {
    "ck_order_cases_checker_not_maker": "maker_checker",
    "ck_quote_cases_approver_not_pricer": "approver_not_pricer",
}


@asynccontextmanager
async def refusals_named(session: AsyncSession, **details: object) -> AsyncIterator[None]:
    """Run writes in a savepoint; a refusal comes out as a conflict naming
    the constraint and ``details`` (ids only), and nothing the row held."""
    try:
        async with session.begin_nested():
            yield
    except IntegrityError as exc:
        constraint = constraint_of(exc) or "unknown"
        rule = _RULES.get(constraint)
        raise ConflictError(
            "separation of duties: a maker of the case cannot check it"
            if rule
            else "the sales store refused the change",
            details={**details, "constraint": constraint, **({"rule": rule} if rule else {})},
        ) from None


async def claim_version(
    session: AsyncSession,
    table: sa.Table,
    case_id: uuid.UUID,
    *,
    expected_version: int,
    new_version: int,
) -> str:
    """Lock the stored case and return its status, once it is at the version
    the decision was made on and the new state is a later one."""
    details = {"case_id": str(case_id), "expected_version": expected_version}
    stored = (
        await session.execute(
            sa.select(table.c.case_version, table.c.status)
            .where(table.c.id == case_id)
            .with_for_update()
        )
    ).first()
    if stored is None:
        raise NotFoundError("no such case", details={"case_id": str(case_id)})
    if stored.case_version != expected_version:
        raise ConflictError("the case changed since it was read", details=details)
    if new_version <= expected_version:
        raise DomainError("a saved case carries a new version", details=details)
    return str(stored.status)


async def record_event(
    session: AsyncSession,
    scope: SalesScope,
    *,
    case_kind: CaseKind,
    case_id: uuid.UUID,
    case_version: int,
    from_status: str | None,
    to_status: str,
    event: CaseEvent,
) -> None:
    actor = event.actor
    await session.execute(
        sa.insert(tables.case_events).values(
            id=uuid.uuid4(),
            **scope_values(scope),
            case_kind=case_kind.value,
            case_id=case_id,
            case_version=case_version,
            action=event.action,
            from_status=from_status,
            to_status=to_status,
            actor_kind=actor.kind,
            actor_id=actor.actor_id,
            worker_id=actor.worker_id,
            worker_version=actor.worker_version,
            initiated_by=actor.initiated_by,
            finding_key=event.finding_key,
            field=event.field,
            reason_code=event.reason_code,
            occurred_at=event.occurred_at,
        )
    )
