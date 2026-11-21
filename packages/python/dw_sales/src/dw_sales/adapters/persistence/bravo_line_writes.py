"""`BravoLineWriteStorePort` inside a Sales unit of work's transaction
(ticket 53, migration af89f3f5d27d). The partial unique index holds one open
proposal per line whatever writes the row; a refusal is a `ConflictError`
naming it (`refusals_named`)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from dw_kernel.errors import ConflictError
from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence._rows import refusals_named, scope_values
from dw_sales.application.bravo_line_writes import BravoLineWrite, WriteStatus
from dw_sales.application.ports import SalesScope

_W = tables.bravo_line_writes


def _columns(write: BravoLineWrite) -> dict[str, Any]:
    return {
        "case_id": write.case_id,
        "line_no": write.line_no,
        "so_no": write.so_no,
        "item_code": write.item_code,
        "field": write.field,
        "before_value": write.before,
        "after_value": write.after,
        "kind": write.kind,
        "command": write.command,
        "content_hash": write.content_hash,
        "status": write.status,
        "check_name": write.check,
        "reason": write.reason,
        "warnings": list(write.warnings),
        "transport_failures": write.transport_failures,
        "proposed_by": write.proposed_by,
        "proposed_at": write.proposed_at,
        "decided_by": write.decided_by,
        "settled_at": write.settled_at,
    }


def _write(row: sa.RowMapping) -> BravoLineWrite:
    return BravoLineWrite(
        approval_id=row["approval_id"],
        case_id=row["case_id"],
        line_no=row["line_no"],
        so_no=row["so_no"],
        item_code=row["item_code"],
        field=row["field"],
        before=row["before_value"],
        after=row["after_value"],
        kind=row["kind"],
        command=row["command"],
        content_hash=row["content_hash"],
        status=row["status"],
        check=row["check_name"],
        reason=row["reason"],
        warnings=tuple(row["warnings"]),
        transport_failures=row["transport_failures"],
        proposed_by=row["proposed_by"],
        proposed_at=row["proposed_at"],
        decided_by=row["decided_by"],
        settled_at=row["settled_at"],
    )


@dataclass(frozen=True)
class SqlBravoLineWrites:
    session: AsyncSession
    scope: SalesScope

    async def get(self, approval_id: uuid.UUID) -> BravoLineWrite | None:
        row = (
            (await self.session.execute(sa.select(_W).where(_W.c.approval_id == approval_id)))
            .mappings()
            .first()
        )
        return None if row is None else _write(row)

    async def add(self, write: BravoLineWrite) -> None:
        async with refusals_named(self.session, approval_id=str(write.approval_id)):
            await self.session.execute(
                sa.insert(_W).values(
                    approval_id=write.approval_id, **scope_values(self.scope), **_columns(write)
                )
            )

    async def save(self, write: BravoLineWrite, *, expected: WriteStatus) -> None:
        async with refusals_named(self.session, approval_id=str(write.approval_id)):
            written = await self.session.execute(
                sa.update(_W)
                .where(_W.c.approval_id == write.approval_id, _W.c.status == expected)
                .values(**_columns(write))
                .returning(_W.c.approval_id)
            )
        if written.first() is None:
            raise ConflictError(
                "the Bravo write was settled meanwhile",
                details={"approval_id": str(write.approval_id), "rule": "write_settled"},
            )

    async def of_case(self, case_id: uuid.UUID) -> Sequence[BravoLineWrite]:
        rows = await self.session.execute(
            sa.select(_W).where(_W.c.case_id == case_id).order_by(_W.c.proposed_at.desc())
        )
        return [_write(row) for row in rows.mappings()]
