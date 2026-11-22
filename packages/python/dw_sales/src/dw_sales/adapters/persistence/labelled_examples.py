"""Decided description lines read back as examples (ticket 43 part 2;
`dw_sales.application.examples`).

A labelled case of `description_attributes` holds the line by reference (the
case, the message, the line number) and the kept PRV code; the description is
the order line's own, read here by joining the case's revision for that
message and its line. Every read is bound to one scope and runs under its RLS,
so an id the examples index handed back for another tenant or workspace reads
as nothing (acceptance 1 at the reading).

Only the newest label of a line counts: a code confirmed and later undone, or
corrected again, is the later decision's. Only a kept value is an example: a
rejection keeps nothing.

The line's reading, where the model read it and code accepted the reading, is
read from the same line's check basis: its spans go with the example, and
`model_reading.shown_lines` decides whether they fit the kept item.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import RowMapping
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence.labelled_cases import labelled_cases
from dw_sales.application.examples import STEP, DescriptionExample
from dw_sales.application.ports import SalesScope
from dw_sales.domain.description_reading import DescriptionReading, SpanRead

_L = labelled_cases
_N = labelled_cases.alias("later")
_R = tables.order_revisions
_OL = tables.order_lines

_DESCRIPTION = _OL.c.po_line["description"].astext
_TS = sa.TIMESTAMP(timezone=True)


def _bound(scope: SalesScope) -> TenantScope:
    return TenantScope(tenant_id=scope.tenant_id.value, workspace_id=scope.workspace_id.value)


def _examples() -> sa.Select[tuple[object, ...]]:
    """The newest kept label of each decided line, with its description."""
    later = (
        sa.select(sa.literal(1))
        .where(
            _N.c.step == _L.c.step,
            _N.c.case_id == _L.c.case_id,
            _N.c.message_id == _L.c.message_id,
            _N.c.line_no == _L.c.line_no,
            sa.tuple_(_N.c.decided_at, _N.c.id) > sa.tuple_(_L.c.decided_at, _L.c.id),
        )
        .exists()
    )
    return (
        sa.select(
            _L.c.id,
            _L.c.case_id,
            _L.c.customer_code,
            _L.c.decided_at,
            _L.c.kept,
            _DESCRIPTION.label("description"),
            _OL.c.check_basis["description_reading"].label("reading"),
        )
        .join(_R, sa.and_(_R.c.case_id == _L.c.case_id, _R.c.message_id == _L.c.message_id))
        .join(_OL, sa.and_(_OL.c.revision_id == _R.c.id, _OL.c.line_no == _L.c.line_no))
        .where(
            _L.c.step == STEP.value,
            _L.c.verdict.in_(("confirmed", "corrected")),
            sa.func.length(sa.func.trim(_DESCRIPTION)) > 0,
            ~later,
        )
    )


def _example(row: RowMapping) -> DescriptionExample | None:
    """The row as an example, or None where it is not one: a kept value that
    is not one code, or a description the model would not have been sent."""
    kept = row["kept"]
    if not isinstance(kept, list) or len(kept) != 1 or not isinstance(kept[0], str):
        return None
    try:
        return DescriptionExample(
            label_id=row["id"],
            case_id=row["case_id"],
            customer_code=row["customer_code"],
            decided_at=row["decided_at"],
            description=row["description"],
            prv_code=kept[0],
            spans=_spans(row["reading"]),
        )
    except ValidationError:
        return None


def _spans(stored: object) -> tuple[SpanRead, ...]:
    """The spans of the line's reading, where one was taken; none where
    there is none or it no longer reads (an example without them is shown as
    its item)."""
    if not isinstance(stored, dict):
        return ()
    try:
        reading = DescriptionReading.model_validate(stored)
    except ValidationError:
        return ()
    return reading.spans if reading.outcome == "read" else ()


def _all(rows: Sequence[RowMapping]) -> list[DescriptionExample]:
    return [example for row in rows if (example := _example(row)) is not None]


@dataclass(frozen=True)
class SqlDescriptionExamples:
    """Implements `DescriptionExamplesPort`."""

    session_factory: async_sessionmaker[AsyncSession]

    async def by_ids(
        self, scope: SalesScope, ids: Sequence[uuid.UUID]
    ) -> Sequence[DescriptionExample]:
        if not ids:
            return []
        query = _examples().where(_L.c.id.in_(list(ids)))
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            return _all(list((await session.execute(query)).mappings()))

    async def after(
        self, scope: SalesScope, position: tuple[datetime, uuid.UUID] | None, limit: int
    ) -> Sequence[DescriptionExample]:
        query = _examples()
        if position is not None:
            at, label = position
            query = query.where(
                sa.tuple_(_L.c.decided_at, _L.c.id)
                > sa.tuple_(sa.literal(at, _TS), sa.literal(label, UUID(as_uuid=True)))
            )
        query = query.order_by(_L.c.decided_at, _L.c.id).limit(limit)
        async with tenant_session(self.session_factory, _bound(scope)) as session:
            return _all(list((await session.execute(query)).mappings()))
