"""DW applying a result by itself (dw_sales ADR 0015, ticket 44).

The first step that does: a line's PRV code, where a model read the
description, code verified the reading, exactly one item fits, and code's
gate let it (`DescriptionReading.gate` is "applied": the confidence cleared
the step's certified threshold, the step is not stopped, and the item was
not sampled for the audit). It is applied through the step's own service,
`OrderIntake.confirm_mapping`, which checks the line again against that item
under the case's rules, exactly as when a person confirms it; only the actor
differs: the `sales_auto_apply` lane (`autonomy.applied_by`), with a case
event of DW's and an audit row in the lane's name (ADR 0011).

**The tier is enforced here, at the effect** (failure-modes #5): whatever a
stamp says, a step whose tier is `person_approves` is refused before
anything is written, so a gate that went wrong, or a stamp from elsewhere,
cannot apply a step a person must approve.

What it does not do: learn the code into the customer's convert list. A
person's confirmation teaches the next PO (`OrderCommands.confirm_mapping`);
DW's own does not, or one result DW was not sure enough of would become a
fact every later PO maps by without asking.

A person undoes it (`OrderCommands.undo_applied_mapping`): the line is a
candidate again, and the undo is a labelled case.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from dw_kernel.errors import ConflictError, DomainError, PermissionDeniedError
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.domain.audit import lane_audit_event
from dw_sales.application.autonomy import AUTO_APPLY_LANE, applied_by
from dw_sales.application.case_store import CaseEvent, EventActor, SalesUnitOfWork
from dw_sales.application.order_intake import OrderIntake
from dw_sales.application.ports import SalesScope
from dw_sales.application.support import DW1_WORKER_ID, DW1_WORKER_VERSION
from dw_sales.domain.autonomy import Tier, tier_of
from dw_sales.domain.order_checks import ModelStep
from dw_sales.domain.orders import Actor, MappingStatus, OrderCase

_LOG = logging.getLogger("dw_sales.auto_apply")


@dataclass(frozen=True)
class AutoApply:
    intake: OrderIntake
    clock: UtcClock
    ids: IdGenerator

    async def apply(
        self,
        work: SalesUnitOfWork,
        scope: SalesScope,
        case: OrderCase,
        *,
        run_id: uuid.UUID | None,
    ) -> OrderCase:
        """Each line code's gate let apply itself, applied in ``work``'s
        transaction; the case as it then is. A line that cannot be applied
        after all (the case refuses it) stays a candidate for a person."""
        for line in case.lines:
            reading = line.basis.description_reading
            if reading is None or reading.gate != "applied":
                continue
            try:
                case = await self.apply_mapping(
                    work, scope, case, line.line_no, ModelStep.DESCRIPTION_ATTRIBUTES, run_id
                )
            except (ConflictError, DomainError, PermissionDeniedError) as refused:
                _LOG.warning(
                    "case %s line %d was not applied: %s",
                    case.case_id,
                    line.line_no,
                    type(refused).__name__,
                )
        return case

    async def apply_mapping(
        self,
        work: SalesUnitOfWork,
        scope: SalesScope,
        case: OrderCase,
        line_no: int,
        step: ModelStep,
        run_id: uuid.UUID | None,
    ) -> OrderCase:
        """One line's single candidate, confirmed as the lane. Refused for a
        step a person approves, and for a line the gate did not let apply."""
        details: dict[str, object] = {"case_id": str(case.case_id), "line": line_no}
        if tier_of(step) is Tier.PERSON_APPROVES:
            raise PermissionDeniedError(
                "a step a person approves never applies itself",
                details={**details, "step": step.value},
            )
        line = case.line(line_no)
        reading = line.basis.description_reading
        mapping = line.mapping
        if (
            reading is None
            or reading.gate != "applied"
            or reading.confidence is None
            or mapping.status is not MappingStatus.CANDIDATE
        ):
            raise ConflictError("the line was not let apply itself", details=details)
        now = self.clock.now()
        applied = await self.intake.confirm_mapping(
            scope, case, line_no, mapping.candidates[0], Actor(user_id=applied_by()), now
        )
        event = CaseEvent(
            action="order.mapping_applied",
            actor=EventActor.worker(DW1_WORKER_ID, DW1_WORKER_VERSION, initiated_by=None),
            occurred_at=now,
            field="prv_code",
        )
        await work.orders.save(applied, expected_version=case.case_version, event=event)
        await work.audit.append(
            lane_audit_event(
                lane=AUTO_APPLY_LANE,
                event_id=self.ids.new_uuid(),
                tenant_id=scope.tenant_id,
                workspace_id=scope.workspace_id,
                action="sales.order.mapping_applied",
                resource_type="sales_order_case",
                resource_id=str(case.case_id),
                occurred_at=now,
                run_id=run_id,
                details={
                    "case_kind": "order",
                    "case_version": applied.case_version,
                    "line": line_no,
                    "field": "prv_code",
                    "step": step.value,
                    "prompt": reading.prompt,
                    "confidence": reading.confidence,
                },
            )
        )
        return applied
