"""A customer's decided mail-PO values read back as examples (ticket 43's
second step; `dw_sales.application.po_body_examples`).

A labelled case of `po_body_extraction` names the case, the message, the line
and the field; the words are cut from the PO as it was read, the revision's
own document (its stored mail and anchors), never from what the person
typed. The revision row keeps the PO without its lines, which live in
`order_lines`, so a line's value is read with that one line. Only the newest
decision on a value counts. Every read runs under the
scope's RLS: another tenant's or workspace's cases are not there to read.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_platform.adapters.persistence.tenant_session import TenantScope, tenant_session
from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence.labelled_cases import labelled_cases
from dw_sales.application.po_body_examples import PoBodyExample
from dw_sales.application.ports import SalesScope
from dw_sales.domain.order_checks import ModelStep
from dw_sales.domain.orders import PoDocument
from dw_sales.domain.po_body_reading import written

_L = labelled_cases
_N = labelled_cases.alias("later")
_R = tables.order_revisions
_OL = tables.order_lines
# Rows read per example asked: some decided values are no example (the mail
# never wrote them), and the newest are wanted, not all.
_READ_AHEAD: Final = 4


def _query(customer_code: str, limit: int) -> sa.Select[tuple[object, ...]]:
    later = (
        sa.select(sa.literal(1))
        .where(
            _N.c.step == _L.c.step,
            _N.c.case_id == _L.c.case_id,
            _N.c.message_id == _L.c.message_id,
            _N.c.line_no.is_not_distinct_from(_L.c.line_no),
            _N.c.field == _L.c.field,
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
            _L.c.line_no,
            _L.c.field,
            _L.c.verdict,
            _R.c.document,
            _OL.c.po_line,
        )
        .join(_R, sa.and_(_R.c.case_id == _L.c.case_id, _R.c.message_id == _L.c.message_id))
        .outerjoin(_OL, sa.and_(_OL.c.revision_id == _R.c.id, _OL.c.line_no == _L.c.line_no))
        .where(
            _L.c.step == ModelStep.PO_BODY_EXTRACTION.value,
            _L.c.customer_code == customer_code,
            _L.c.verdict.in_(("confirmed", "corrected")),
            ~later,
        )
        .order_by(_L.c.decided_at.desc(), _L.c.id.desc())
        .limit(limit * _READ_AHEAD)
    )


def _example(row: RowMapping) -> PoBodyExample | None:
    try:
        lines = [] if row["po_line"] is None else [row["po_line"]]
        document = PoDocument.model_validate({**row["document"], "lines": lines})
    except ValidationError:
        return None
    found = written(document, row["line_no"], row["field"])
    if found is None:
        return None
    line, words = found
    try:
        return PoBodyExample(
            label_id=row["id"],
            case_id=row["case_id"],
            customer_code=row["customer_code"],
            decided_at=row["decided_at"],
            field=row["field"],
            line=line,
            words=words,
            right=row["verdict"] == "confirmed",
        )
    except ValidationError:
        return None


@dataclass(frozen=True)
class SqlPoBodyExamples:
    """Implements `PoBodyExamplesPort`."""

    session_factory: async_sessionmaker[AsyncSession]

    async def latest(
        self, scope: SalesScope, customer_code: str, limit: int
    ) -> Sequence[PoBodyExample]:
        bound = TenantScope(tenant_id=scope.tenant_id.value, workspace_id=scope.workspace_id.value)
        async with tenant_session(self.session_factory, bound) as session:
            rows = list((await session.execute(_query(customer_code, limit))).mappings())
        found = [example for row in rows if (example := _example(row)) is not None]
        return found[:limit]
