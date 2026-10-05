"""Order cases in PostgreSQL: one case, every revision, its lines and findings.

The case is stored the way the domain holds it and read back through the
domain's own constructor, so a stored case that breaks an invariant fails on
read instead of reaching a handler.

- `order_cases`: one row, the case's stamps and status.
- `order_revisions`: the current revision and every one it superseded, each
  with its document (without its lines).
- `order_lines`: per revision, the printed line, its mapping and its check
  basis. A superseded revision keeps its lines as they last stood.
- `order_findings`: per revision, in the order raised. The current revision's
  are replaced on every save, as the domain replaces them.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import RowMapping
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_kernel.errors import ConflictError, DomainError
from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence._rows import (
    claim_version,
    record_event,
    refusals_named,
    scope_values,
)
from dw_sales.application.case_store import CaseEvent, CaseOrigin, Stored
from dw_sales.application.ports import SalesScope
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.orders import (
    Finding,
    LineBasis,
    LineMapping,
    OrderCase,
    OrderLine,
    PoDocument,
    PoLine,
    SupersededRevision,
)

_C = tables.order_cases
_R = tables.order_revisions
_L = tables.order_lines
_F = tables.order_findings

# The disposition's own fields, each stored as `disposition_<field>`.
_DISPOSITION_FIELDS = ("reason", "value", "source", "by", "at")


def _case_columns(case: OrderCase) -> dict[str, Any]:
    """Every column of `order_cases` the case decides, from the case."""
    return {
        "customer_code": case.customer_code,
        "po_no": case.header.po_no,
        "case_version": case.case_version,
        "status": case.status.value,
        "rules_version": case.rules_version,
        "catalog_as_of": case.catalog_as_of,
        "cross_check_required": case.cross_check_required,
        "export_control_mode": case.export_control_mode,
        "changes": [change.model_dump(mode="json") for change in case.changes],
        "duplicate_of_case": case.duplicate_of_case,
        "duplicate_of_so": case.duplicate_of_so,
        "base_so_no": case.base_so_no,
        "prepared_by": case.prepared_by,
        "prepared_at": case.prepared_at,
        "bravo_so_no": case.bravo_so_no,
        "bravo_recorded_by": case.bravo_recorded_by,
        "bravo_recorded_at": case.bravo_recorded_at,
        "bravo_entry_compared": case.bravo_entry_compared,
        "cross_checked_by": case.cross_checked_by,
        "cross_checked_at": case.cross_checked_at,
        "returned_reason": case.returned_reason,
        "returned_by": case.returned_by,
        "returned_at": case.returned_at,
        "confirmed_by": case.confirmed_by,
        "confirmed_at": case.confirmed_at,
        "close_reason": case.close_reason.value if case.close_reason else None,
        "closed_by": case.closed_by,
        "closed_at": case.closed_at,
        "superseded_by_case": case.superseded_by_case,
    }


def _line_columns(line: OrderLine) -> dict[str, Any]:
    """The columns of a line that a decision may change."""
    mapping = line.mapping
    return {
        "mapping_status": mapping.status.value,
        "prv_code": mapping.prv_code,
        "candidates": list(mapping.candidates),
        "mapping_confirmed_by": mapping.confirmed_by,
        "mapping_confirmed_at": mapping.confirmed_at,
        "check_basis": line.basis.model_dump(mode="json"),
        "suggested_delivery_date": line.suggested_delivery_date,
        "confirmed_delivery_date": line.confirmed_delivery_date,
        "pc_confirmed_by": line.pc_confirmed_by,
        "pc_confirmed_at": line.pc_confirmed_at,
    }


def _finding_columns(finding: Finding) -> dict[str, Any]:
    decided = finding.disposition.model_dump(exclude={"kind"})
    return {
        "code": finding.code.value,
        "severity": finding.severity.value,
        "line_no": finding.line_no,
        "expected": finding.expected,
        "actual": finding.actual,
        "rule_version": finding.rule_version,
        "disposition": finding.disposition.kind.value,
        **{f"disposition_{name}": decided.get(name) for name in _DISPOSITION_FIELDS},
    }


async def _insert_revision(
    session: AsyncSession,
    scope: SalesScope,
    case: OrderCase,
    seq: int,
) -> None:
    """The case's current revision: its document, lines and findings."""
    revision_id = uuid.uuid4()
    scoped = scope_values(scope)
    await session.execute(
        sa.insert(_R).values(
            id=revision_id,
            **scoped,
            case_id=case.case_id,
            seq=seq,
            message_id=case.message_id,
            received_at=case.received_at,
            document=case.document.model_dump(mode="json", exclude={"lines"}),
        )
    )
    await session.execute(
        sa.insert(_L),
        [
            {
                "id": uuid.uuid4(),
                **scoped,
                "revision_id": revision_id,
                "position": position,
                "po_line": line.po_line.model_dump(mode="json"),
                **_line_columns(line),
            }
            for position, line in enumerate(case.lines)
        ],
    )
    await _replace_findings(session, scope, revision_id, case.findings)


async def _replace_findings(
    session: AsyncSession, scope: SalesScope, revision_id: uuid.UUID, findings: Sequence[Finding]
) -> None:
    await session.execute(sa.delete(_F).where(_F.c.revision_id == revision_id))
    if findings:
        scoped = scope_values(scope)
        await session.execute(
            sa.insert(_F),
            [
                {
                    "id": uuid.uuid4(),
                    **scoped,
                    "revision_id": revision_id,
                    "position": position,
                    **_finding_columns(finding),
                }
                for position, finding in enumerate(findings)
            ],
        )


async def _update_lines(
    session: AsyncSession, scope: SalesScope, revision_id: uuid.UUID, lines: Sequence[OrderLine]
) -> None:
    """The current revision's lines: their printed values never change, only
    what was decided about them."""
    statement = pg_insert(_L)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[_L.c.tenant_id, _L.c.workspace_id, _L.c.revision_id, _L.c.line_no],
            set_={name: statement.excluded[name] for name in _line_columns(lines[0])},
        ),
        [
            {
                "id": uuid.uuid4(),
                **scope_values(scope),
                "revision_id": revision_id,
                "position": position,
                "po_line": line.po_line.model_dump(mode="json"),
                **_line_columns(line),
            }
            for position, line in enumerate(lines)
        ],
    )


# ---------------------------------------------------------------- reading --


def _document(row: RowMapping, lines: Iterable[RowMapping]) -> PoDocument:
    return PoDocument.model_validate(
        {**row["document"], "lines": [line["po_line"] for line in lines]}
    )


def _order_line(row: RowMapping) -> OrderLine:
    return OrderLine(
        po_line=PoLine.model_validate(row["po_line"]),
        mapping=LineMapping(
            status=row["mapping_status"],
            prv_code=row["prv_code"],
            candidates=tuple(row["candidates"]),
            confirmed_by=row["mapping_confirmed_by"],
            confirmed_at=row["mapping_confirmed_at"],
        ),
        basis=LineBasis.model_validate(row["check_basis"]),
        suggested_delivery_date=row["suggested_delivery_date"],
        confirmed_delivery_date=row["confirmed_delivery_date"],
        pc_confirmed_by=row["pc_confirmed_by"],
        pc_confirmed_at=row["pc_confirmed_at"],
    )


def _finding(row: RowMapping) -> Finding:
    decided = {
        name: row[f"disposition_{name}"]
        for name in _DISPOSITION_FIELDS
        if row[f"disposition_{name}"] is not None
    }
    return Finding.model_validate(
        {
            "code": row["code"],
            "severity": row["severity"],
            "line_no": row["line_no"],
            "expected": row["expected"],
            "actual": row["actual"],
            "rule_version": row["rule_version"],
            "disposition": {"kind": row["disposition"], **decided},
        }
    )


async def _load(session: AsyncSession, where: sa.ColumnElement[bool]) -> list[Stored[OrderCase]]:
    """Every case matching ``where``, oldest first, rebuilt through the domain."""
    cases = (
        (await session.execute(sa.select(_C).where(where).order_by(_C.c.created_at, _C.c.id)))
        .mappings()
        .all()
    )
    if not cases:
        return []
    case_ids = [row["id"] for row in cases]
    revisions = (
        (
            await session.execute(
                sa.select(_R).where(_R.c.case_id.in_(case_ids)).order_by(_R.c.case_id, _R.c.seq)
            )
        )
        .mappings()
        .all()
    )
    revision_ids = [row["id"] for row in revisions]
    lines: dict[uuid.UUID, list[RowMapping]] = {rid: [] for rid in revision_ids}
    for row in (
        (
            await session.execute(
                sa.select(_L)
                .where(_L.c.revision_id.in_(revision_ids))
                .order_by(_L.c.revision_id, _L.c.position)
            )
        )
        .mappings()
        .all()
    ):
        lines[row["revision_id"]].append(row)
    current_ids = [row["id"] for row in revisions if row["superseded_at"] is None]
    findings: dict[uuid.UUID, list[RowMapping]] = {rid: [] for rid in current_ids}
    for row in (
        (
            await session.execute(
                sa.select(_F)
                .where(_F.c.revision_id.in_(current_ids))
                .order_by(_F.c.revision_id, _F.c.position)
            )
        )
        .mappings()
        .all()
    ):
        findings[row["revision_id"]].append(row)

    by_case: dict[uuid.UUID, list[RowMapping]] = {cid: [] for cid in case_ids}
    for row in revisions:
        by_case[row["case_id"]].append(row)
    return [_rebuild(row, by_case[row["id"]], lines, findings) for row in cases]


def _rebuild(
    row: RowMapping,
    revisions: Sequence[RowMapping],
    lines: Mapping[uuid.UUID, Sequence[RowMapping]],
    findings: Mapping[uuid.UUID, Sequence[RowMapping]],
) -> Stored[OrderCase]:
    current = [r for r in revisions if r["superseded_at"] is None]
    if len(current) != 1:  # the partial unique index makes more than one impossible
        raise DomainError(
            "an order case has no current revision", details={"case_id": str(row["id"])}
        )
    (now,) = current
    case = OrderCase.model_validate(
        {
            **{name: row[name] for name in _CASE_FIELDS},
            "case_id": row["id"],
            "message_id": now["message_id"],
            "received_at": now["received_at"],
            "document": _document(now, lines[now["id"]]),
            "lines": [_order_line(line) for line in lines[now["id"]]],
            "findings": [_finding(f) for f in findings[now["id"]]],
            "superseded": [
                SupersededRevision(
                    message_id=r["message_id"],
                    received_at=r["received_at"],
                    document=_document(r, lines[r["id"]]),
                )
                for r in revisions
                if r["superseded_at"] is not None
            ],
            # Every preparer and Bravo recorder the trigger accumulated: the
            # case refuses a checker among them before the CHECK has to.
            "earlier_makers": frozenset(row["makers"]),
        }
    )
    if case.header.po_no != row["po_no"]:
        # The case's PO number is its identity; a revision of another PO
        # stored under it is a corrupt case, said loudly.
        raise DomainError(
            "an order case holds another PO's revision", details={"case_id": str(case.case_id)}
        )
    return Stored(
        case=case,
        origin=CaseOrigin(
            assigned_to=row["assigned_to"], release_manifest_ref=row["release_manifest_ref"]
        ),
    )


# `order_cases` columns that are `OrderCase` fields of the same name.
_CASE_FIELDS = (
    "customer_code",
    "case_version",
    "status",
    "rules_version",
    "catalog_as_of",
    "cross_check_required",
    "export_control_mode",
    "changes",
    "duplicate_of_case",
    "duplicate_of_so",
    "base_so_no",
    "prepared_by",
    "prepared_at",
    "bravo_so_no",
    "bravo_recorded_by",
    "bravo_recorded_at",
    "bravo_entry_compared",
    "cross_checked_by",
    "cross_checked_at",
    "returned_reason",
    "returned_by",
    "returned_at",
    "confirmed_by",
    "confirmed_at",
    "close_reason",
    "closed_by",
    "closed_at",
    "superseded_by_case",
)


def _for_po(customer_code: str, po_no: str) -> sa.ColumnElement[bool]:
    return sa.and_(_C.c.customer_code == customer_code, _C.c.po_no == po_no)


# ------------------------------------------------------------ repositories --


@dataclass(frozen=True)
class SqlOrderCaseRepository:
    """Implements `OrderCaseStorePort` inside a unit of work's transaction."""

    session: AsyncSession
    scope: SalesScope

    async def get(self, case_id: uuid.UUID) -> Stored[OrderCase] | None:
        loaded = await _load(self.session, _C.c.id == case_id)
        return loaded[0] if loaded else None

    async def list_all(self) -> Sequence[Stored[OrderCase]]:
        return list(reversed(await _load(self.session, sa.true())))

    async def cases_for_po(self, customer_code: str, po_no: str) -> Sequence[OrderCase]:
        return [found.case for found in await _load(self.session, _for_po(customer_code, po_no))]

    async def add(self, case: OrderCase, origin: CaseOrigin, event: CaseEvent) -> None:
        if case.superseded:
            raise DomainError(
                "a case is opened with one revision; later ones join it by save",
                details={"case_id": str(case.case_id)},
            )
        async with refusals_named(self.session, case_id=str(case.case_id)):
            await self.session.execute(
                sa.insert(_C).values(
                    id=case.case_id,
                    **scope_values(self.scope),
                    **_case_columns(case),
                    assigned_to=origin.assigned_to,
                    release_manifest_ref=origin.release_manifest_ref,
                )
            )
            await _insert_revision(self.session, self.scope, case, seq=1)
            await self._event(case, None, event)

    async def save(self, case: OrderCase, *, expected_version: int, event: CaseEvent) -> None:
        was = await claim_version(
            self.session,
            _C,
            case.case_id,
            expected_version=expected_version,
            new_version=case.case_version,
        )
        details: dict[str, object] = {"case_id": str(case.case_id)}
        async with refusals_named(self.session, **details):
            await self.session.execute(
                sa.update(_C).where(_C.c.id == case.case_id).values(**_case_columns(case))
            )
            await self._save_revisions(case, event.occurred_at, details)
            await self._event(case, was, event)

    async def _save_revisions(
        self, case: OrderCase, at: datetime, details: dict[str, object]
    ) -> None:
        revisions = (
            await self.session.execute(
                sa.select(_R.c.id, _R.c.message_id, _R.c.superseded_at)
                .where(_R.c.case_id == case.case_id)
                .order_by(_R.c.seq)
            )
        ).all()
        stored_ids = [r.message_id for r in revisions]
        history = [old.message_id for old in case.superseded]
        current = next(r for r in revisions if r.superseded_at is None)
        if current.message_id == case.message_id:
            if stored_ids[:-1] != history:
                raise ConflictError("the case's revisions are not the stored ones", details=details)
            await _update_lines(self.session, self.scope, current.id, case.lines)
            await _replace_findings(self.session, self.scope, current.id, case.findings)
            return
        # A revision joined: what was current is now history, kept as it stood.
        if stored_ids != history:
            raise ConflictError("the case's revisions are not the stored ones", details=details)
        await self.session.execute(
            sa.update(_R).where(_R.c.id == current.id).values(superseded_at=at)
        )
        await _insert_revision(self.session, self.scope, case, seq=len(revisions) + 1)

    async def _event(self, case: OrderCase, from_status: str | None, event: CaseEvent) -> None:
        await record_event(
            self.session,
            self.scope,
            case_kind=CaseKind.ORDER,
            case_id=case.case_id,
            case_version=case.case_version,
            from_status=from_status,
            to_status=case.status.value,
            event=event,
        )


@dataclass(frozen=True)
class SqlOrderCaseLookup:
    """Implements `OrderCaseLookupPort`: one short read transaction per call,
    bound to the scope it is asked about."""

    session_factory: async_sessionmaker[AsyncSession]

    async def cases_for_po(
        self, scope: SalesScope, customer_code: str, po_no: str
    ) -> Sequence[OrderCase]:
        bound = TenantScope(tenant_id=scope.tenant_id.value, workspace_id=scope.workspace_id.value)
        async with tenant_session(self.session_factory, bound) as session:
            return await SqlOrderCaseRepository(session, scope).cases_for_po(customer_code, po_no)
