"""A decided run-less Sales approval, carried out (Sales tickets 30 and 38).

A PO layout's proposal (`sales.layout`) and a tenant's rule version
(`sales.rules`) each open a platform approval with no run (dw_sales ADR 0004);
the approval flow announces its decision as `<approval_type>.decided`, in the
decision's transaction, and this handler hands it to that type's settlement
(`LayoutSettlement`, `RuleSettlement`), which reads the outcome from the
approval row and applies it as the decider. Nothing is decided here: the
payload is parsed, the tenancy taken from the envelope.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from dw_kernel.errors import ConflictError, DomainError, NotFoundError, PermissionDeniedError
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.outbox import OutboxEvent
from dw_worker.consumers.outbox import EventHandler, UndeliverableEventError

__all__ = ["DecidedPayload", "SettlementPort", "build_decided_handler"]

# No plan: carrying out a decision starts no run and spends nothing, and a
# context with an unknown plan refuses anything that would read one.
_NO_PLAN = "background"


class DecidedPayload(BaseModel):
    """The body `ApproveAndResumeService` writes for a run-less decision.

    Only `approval_id` is acted on, and `decided_by` names who is accountable;
    the outcome is read again from the approval row by the settlement.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    approval_id: uuid.UUID
    decision_id: uuid.UUID
    outcome: str
    decided_by: uuid.UUID


class SettlementPort(Protocol):
    """A run-less approval type's settlement, as this handler calls it."""

    async def settle(self, approval_id: uuid.UUID, decider: AccessContext) -> object: ...


def build_decided_handler(settlement: SettlementPort, *, applied: str) -> EventHandler:
    """The handler to wire under one type's decided event (`LAYOUT_DECIDED`,
    `RULES_DECIDED`); ``applied`` is what it reports once settled."""

    async def handle(event: OutboxEvent) -> str:
        try:
            payload = DecidedPayload.model_validate(event.payload)
        except ValidationError as exc:
            raise UndeliverableEventError(f"payload does not parse: {exc}") from exc
        decider = AccessContext(
            tenant_id=event.tenant_id.value,
            workspace_id=event.workspace_id.value,
            principal_id=payload.decided_by,
            roles=frozenset(),
            scopes=frozenset(),
            plan_id=_NO_PLAN,
        )
        try:
            await settlement.settle(payload.approval_id, decider)
        except (ConflictError, DomainError, NotFoundError, PermissionDeniedError) as exc:
            # A subject decided meanwhile, an approval this workspace cannot
            # see, a maker as decider: none changes on a retry.
            raise UndeliverableEventError(f"refused: {exc.message} {exc.details}") from exc
        return applied

    return handle
