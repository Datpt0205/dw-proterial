"""A decided Bravo write, carried out (Sales ticket 53, ADR 0027).

`bravo_write.sales_order.decided` carries what every run-less decision
carries and, on an approval, the token the decision signed (`stamp.token`,
`ApproveAndResumeService.decision_stamps`). This handler hands both to
`BravoWriteSettlement`, which reads the outcome from the approval row, sends
the stored command to the gateway and keeps its answer. A gateway that did
not answer is retried, as any failed delivery; nothing is decided here.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dw_kernel.errors import ConflictError, DomainError, NotFoundError, PermissionDeniedError
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.outbox import OutboxEvent
from dw_worker.consumers.outbox import EventHandler, UndeliverableEventError

__all__ = ["BravoWriteDecidedPayload", "build_bravo_write_handler"]

_NO_PLAN = "background"


class _Stamp(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    token: str = Field(min_length=1, max_length=4096)


class BravoWriteDecidedPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    approval_id: uuid.UUID
    decision_id: uuid.UUID
    outcome: str
    decided_by: uuid.UUID
    # Only on an approval; a rejection carries none.
    stamp: _Stamp | None = None


class BravoWriteSettlementPort(Protocol):
    async def settle(
        self, approval_id: uuid.UUID, decider: AccessContext, token: str | None
    ) -> object: ...


def build_bravo_write_handler(settlement: BravoWriteSettlementPort) -> EventHandler:
    async def handle(event: OutboxEvent) -> str:
        try:
            payload = BravoWriteDecidedPayload.model_validate(event.payload)
        except ValidationError as exc:
            raise UndeliverableEventError.unparsable(exc) from None
        decider = AccessContext(
            tenant_id=event.tenant_id.value,
            workspace_id=event.workspace_id.value,
            principal_id=payload.decided_by,
            roles=frozenset(),
            scopes=frozenset(),
            plan_id=_NO_PLAN,
        )
        token = None if payload.stamp is None else payload.stamp.token
        try:
            status = await settlement.settle(payload.approval_id, decider, token)
        except (ConflictError, DomainError, NotFoundError, PermissionDeniedError) as exc:
            raise UndeliverableEventError(f"refused: {exc.message} {exc.details}") from exc
        return f"bravo write {status}"

    return handle
