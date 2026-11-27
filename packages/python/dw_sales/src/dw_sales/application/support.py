"""What every Sales handler does around its decision.

A handler authorizes, loads the case in the caller's workspace, checks the
version the caller decided on, lets the case decide, then stores the next case
with its event and writes the platform audit row, all in one transaction
(ticket 04 G28). These are the pieces it does that with, so each handler
holds only its own decision.

Two rules hold here for every handler:

- **The time is the server's.** Every stamp (`decided_at`, `prepared_at`,
  an event's `occurred_at`) comes from the injected clock, never from the
  request (ticket 05 item 7).
- **An audit row carries ids, codes, transitions and the case version**,
  copied from the case event, which has no field an amount could travel in
  (spec decision 8). The person is the audit actor; for DW1's own work, the
  principal whose request started it (a person, or DW1's service account in
  the mailbox lane), with the worker named in the details.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime

from pydantic import ValidationError

from dw_kernel.errors import ConflictError, DomainError, NotFoundError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import AuditEvent, lane_audit_event
from dw_sales.application.case_store import (
    STALE_CASE_VERSION,
    CaseEvent,
    EventActor,
    SalesUnitOfWork,
    Stored,
)
from dw_sales.application.shadow import label_po_settled, label_reply_move
from dw_sales.application.visibility import sees_case
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.orders import OrderCase
from dw_sales.domain.quotes import QuoteCase

# DW1's own identity on the events it writes (spec "Actors", decision 5), and
# the worker its runs are recorded under: `configs/workers/sales.yaml` declares
# the same id and version, and `test_dw1_worker.py` holds the two together. A
# run's actor is the principal who started it, and DW1's events name them as
# `initiated_by`: the person who pressed "DW xử lý", or DW1's own service
# account when the worker's mailbox lane started it (`inbox_lane`, ticket 16).
DW1_WORKER_ID = "sales-dw1"
DW1_WORKER_VERSION = "1.0.0"


async def stored_order(
    work: SalesUnitOfWork,
    case_id: uuid.UUID,
    *,
    viewer: AccessContext | None,
    export_control: bool = False,
) -> Stored[OrderCase]:
    """The case, in the caller's workspace only: another tenant's or another
    workspace's id reads as not found, never as forbidden.

    ``viewer``: the person reading, who sees only what `sees_case` lets them
    (a case outside it reads as not found too); None for DW1's own lanes and
    a settlement, which act for the whole workspace. Required, so every
    caller says which it is.

    ``export_control``: True only for a read and for the NOC/ESF hold's own
    acknowledgement, the two things a hold lets the export-control PIC do
    on an order that is not theirs (ticket 78). Every other step leaves it
    False, so a hold opens no close, no self-check, no Bravo write."""
    stored = await work.orders.get(case_id)
    if stored is None or not seen_by(viewer, CaseKind.ORDER, stored, export_control=export_control):
        raise NotFoundError("no such order case", details={"case_id": str(case_id)})
    return stored


async def stored_quote(
    work: SalesUnitOfWork, case_id: uuid.UUID, *, viewer: AccessContext | None
) -> Stored[QuoteCase]:
    stored = await work.quotes.get(case_id)
    if stored is None or not seen_by(viewer, CaseKind.QUOTE, stored):
        raise NotFoundError("no such quote case", details={"case_id": str(case_id)})
    return stored


def seen_by(
    viewer: AccessContext | None,
    kind: CaseKind,
    stored: Stored[OrderCase] | Stored[QuoteCase],
    *,
    export_control: bool = False,
) -> bool:
    """``export_control``: as `stored_order`'s, True only where the caller
    reads (a list, a page) or acknowledges the hold."""
    case = stored.case
    return viewer is None or sees_case(
        viewer,
        kind,
        case.status.value,
        stored.origin.assigned_to,
        export_held=export_control and isinstance(case, OrderCase) and case.awaits_export_control,
    )


def same_version(case_id: uuid.UUID, current: int, decided_on: int) -> None:
    """A decision names the version it was made on; a stale one is refused."""
    if current != decided_on:
        raise ConflictError(
            STALE_CASE_VERSION,
            details={
                "case_id": str(case_id),
                "case_version": current,
                "decided_on": decided_on,
                "rule": "stale_case_version",
            },
        )


def decided[T](step: Callable[[], T]) -> T:
    """The case's own refusal of a value, as a validation error naming fields.

    A model refusing its input (a reason too long, a number that is not a
    sales-order number) is the caller's 422, not the server's 500, and names
    the fields, never the value (the models hide their input).
    """
    try:
        return step()
    except ValidationError as exc:
        fields = sorted({".".join(str(p) for p in e["loc"]) or "case" for e in exc.errors()})
        raise DomainError("the change is not valid", details={"fields": fields}) from None


def audit_row(
    context: AccessContext,
    ids: IdGenerator,
    *,
    case_kind: CaseKind,
    case_id: uuid.UUID,
    case_version: int,
    from_status: str | None,
    to_status: str,
    event: CaseEvent,
    run_id: uuid.UUID | None = None,
    approval_id: uuid.UUID | None = None,
    lane: str | None = None,
) -> AuditEvent:
    """The platform audit row for one case event, in the event's own terms.

    ``run_id`` is the DW1 run the event happened in, when it did: a decision
    applied when the run resumed names the run, and through it the approval.
    ``approval_id`` names the approval itself where the run is not enough to
    find it: a decision that was not applied (ticket 14). ``lane``: a
    background lane moved the case, and the row is that lane's (ADR 0011),
    never a person's.
    """
    actor = event.actor
    details: dict[str, object] = {
        "case_kind": case_kind.value,
        "case_version": case_version,
        "from_status": from_status,
        "to_status": to_status,
        "actor_kind": actor.kind,
    }
    if actor.kind == "worker":
        details |= {"worker_id": actor.worker_id, "worker_version": actor.worker_version}
    for name in ("finding_key", "field", "reason_code"):
        value = getattr(event, name)
        if value is not None:
            details[name] = value
    if approval_id is not None:
        details["approval_id"] = str(approval_id)
    if lane is not None:
        return lane_audit_event(
            lane=lane,
            event_id=ids.new_uuid(),
            tenant_id=TenantId(context.tenant_id),
            workspace_id=WorkspaceId(context.workspace_id),
            action=f"sales.{event.action}",
            resource_type=f"sales_{case_kind.value}_case",
            resource_id=str(case_id),
            run_id=run_id,
            occurred_at=event.occurred_at,
            details=details,
        )
    return AuditEvent(
        id=ids.new_uuid(),
        tenant_id=TenantId(context.tenant_id),
        workspace_id=WorkspaceId(context.workspace_id),
        actor_id=UserId(context.principal_id),
        action=f"sales.{event.action}",
        resource_type=f"sales_{case_kind.value}_case",
        resource_id=str(case_id),
        run_id=run_id,
        occurred_at=event.occurred_at,
        details=details,
    )


def worker_event(
    action: str, context: AccessContext, at: datetime, **fields: str | None
) -> CaseEvent:
    """An event DW1 wrote at the caller's request ("DW xử lý")."""
    return CaseEvent(
        action=action,
        actor=EventActor.worker(
            DW1_WORKER_ID, DW1_WORKER_VERSION, initiated_by=context.principal_id
        ),
        occurred_at=at,
        **fields,
    )


def person_event(
    action: str, context: AccessContext, at: datetime, **fields: str | None
) -> CaseEvent:
    """An event a person wrote: their decision."""
    return CaseEvent(
        action=action, actor=EventActor.person(context.principal_id), occurred_at=at, **fields
    )


async def save_order(
    work: SalesUnitOfWork,
    context: AccessContext,
    ids: IdGenerator,
    before: OrderCase,
    after: OrderCase,
    event: CaseEvent,
    *,
    run_id: uuid.UUID | None = None,
    approval_id: uuid.UUID | None = None,
    lane: str | None = None,
) -> None:
    """The order's next state, its event and its audit row, in the open
    transaction; the caller commits; ``lane``: moved by that background lane
    (`audit_row`). A person's move labels what the reply
    readers read in shadow (ticket 67), in the same transaction."""
    await work.orders.save(after, expected_version=before.case_version, event=event)
    if run_id is None and before.status is not after.status:
        await label_reply_move(
            work,
            context,
            ids,
            case_kind=CaseKind.ORDER,
            case_id=after.case_id,
            customer_code=after.customer_code,
            from_status=before.status.value,
            to_status=after.status.value,
            at=event.occurred_at,
        )
        await label_po_settled(work, context, ids, before=before, after=after, at=event.occurred_at)
    await work.audit.append(
        audit_row(
            context,
            ids,
            case_kind=CaseKind.ORDER,
            case_id=after.case_id,
            case_version=after.case_version,
            from_status=before.status.value,
            to_status=after.status.value,
            event=event,
            run_id=run_id,
            approval_id=approval_id,
            lane=lane,
        )
    )


async def save_quote(
    work: SalesUnitOfWork,
    context: AccessContext,
    ids: IdGenerator,
    before: QuoteCase,
    after: QuoteCase,
    event: CaseEvent,
    *,
    run_id: uuid.UUID | None = None,
) -> None:
    await work.quotes.save(after, expected_version=before.case_version, event=event)
    if run_id is None and before.status is not after.status:
        await label_reply_move(
            work,
            context,
            ids,
            case_kind=CaseKind.QUOTE,
            case_id=after.case_id,
            customer_code=after.customer_code,
            from_status=before.status.value,
            to_status=after.status.value,
            at=event.occurred_at,
        )
    await work.audit.append(
        audit_row(
            context,
            ids,
            case_kind=CaseKind.QUOTE,
            case_id=after.case_id,
            case_version=after.case_version,
            from_status=before.status.value,
            to_status=after.status.value,
            event=event,
            run_id=run_id,
        )
    )
