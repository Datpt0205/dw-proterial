"""Change requests on order cases in PostgreSQL (ticket 27, migration c7d0730fcccd).

The request is stored the way the domain holds it (`record`) and read back
through its own constructor, so a stored request that breaks an invariant
fails on read instead of reaching a handler. The columns beside it are what
a constraint or a query reads: the case, the mail, the state (one open per
case, a partial unique index) and the version a save claims.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from dw_kernel.errors import ConflictError
from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence._rows import refusals_named, scope_values
from dw_sales.application.ports import SalesScope
from dw_sales.domain.change_requests import ChangeRequest

_CR = tables.change_requests


def _columns(request: ChangeRequest) -> dict[str, object]:
    return {
        "state": request.state,
        "version": request.version,
        "record": request.model_dump(mode="json"),
    }


@dataclass(frozen=True)
class SqlChangeRequests:
    """Implements `ChangeRequestStorePort` inside a unit of work's transaction."""

    session: AsyncSession
    scope: SalesScope

    async def for_case(self, case_id: uuid.UUID) -> Sequence[ChangeRequest]:
        rows = await self.session.execute(
            sa.select(_CR.c.record)
            .where(
                _CR.c.workspace_id == self.scope.workspace_id.value,
                _CR.c.case_id == case_id,
            )
            .order_by(_CR.c.number)
        )
        return [ChangeRequest.model_validate(record) for (record,) in rows]

    async def add(self, request: ChangeRequest) -> None:
        details = {"case_id": str(request.case_id), "request_id": str(request.request_id)}
        async with refusals_named(self.session, **details):
            await self.session.execute(
                sa.insert(_CR).values(
                    id=request.request_id,
                    **scope_values(self.scope),
                    case_id=request.case_id,
                    number=request.number,
                    message_id=request.message_id,
                    opened_by=request.opened_by,
                    opened_at=request.opened_at,
                    **_columns(request),
                )
            )

    async def save(self, request: ChangeRequest, *, expected_version: int) -> None:
        details = {"case_id": str(request.case_id), "request_id": str(request.request_id)}
        async with refusals_named(self.session, **details):
            saved = await self.session.execute(
                sa.update(_CR)
                .where(
                    _CR.c.id == request.request_id,
                    _CR.c.case_id == request.case_id,
                    _CR.c.version == expected_version,
                )
                .values(**_columns(request))
                .returning(_CR.c.id)
            )
            if saved.first() is None:
                raise ConflictError(
                    "yêu cầu thay đổi đã đổi từ khi bạn mở: tải lại để xem",
                    details={**details, "rule": "stale_change_request"},
                )
