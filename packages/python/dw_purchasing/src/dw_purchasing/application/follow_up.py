"""Each drafted order followed to the goods (DW02 function 5).

- **Bravo's number** (`record_bravo_no`): typed by the buyer once the order
  is imported. Bravo has no connection here, so nothing reads it back.
- **The supplier's confirmation** (`read_confirmation`): the mail must come,
  verified, from the order's own supplier and name the order (its `po_ref`
  or Bravo's number): decided by code before any model is asked. The model
  copies spans (`purchasing.order_confirmation_reading`); code reads them
  (`domain.confirmation_reading`) and holds them to the order
  (`domain.tracking.differences`). It is kept unaccepted: a buyer accepts it
  (`accept_confirmation`), or the automation lane does when it differs in
  nothing and the step runs on its own.
- **What arrived** (`record_receipt`), recorded by the buyer, never more
  than is still owed. The receipt that completes every line of every order
  moves the case to `delivered` (Đã nhận đủ hàng): code's, nothing to press.
- **What is late** (`late`): every line past its date, counted in the
  plant's day, with less arrived than ordered, for the lane's notices and a
  person's brief.

All of it is the buyer's (`purchasing.po.prepare`), as drafting the order is.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Final
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from dw_agent_runtime.context import caller_run
from dw_agent_runtime.model.interpretation import (
    InterpretationPort,
    ModelUnavailableError,
    PromptRef,
    cut_to_tokens,
)
from dw_kernel.errors import ConflictError, InfrastructureError, NotFoundError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import AuditEvent
from dw_platform.domain.mail_parts import newest_part
from dw_purchasing.application.access import Gate, PurchasingScopes
from dw_purchasing.application.intake import NOT_READ_NOW, CaseChange, Worker
from dw_purchasing.application.ports import InboxPort, MasterDataPort, PurchasingUnitOfWork
from dw_purchasing.domain.cases import CaseStatus, PurchaseCase
from dw_purchasing.domain.checks import MasterData
from dw_purchasing.domain.confirmation_reading import (
    MAX_CONFIRMED_LINES,
    ModelConfirmation,
    read_confirmation_mail,
)
from dw_purchasing.domain.mail_reading import fold, occurrences
from dw_purchasing.domain.orders import PoDraft
from dw_purchasing.domain.tracking import (
    Confirmation,
    OrderTracking,
    Receipt,
    differences,
    due_lines,
    due_on,
    received,
)

ORDER_CONFIRMATION_READING: Final = PromptRef("purchasing.order_confirmation_reading", "1.0.0")
_RESOURCE: Final = "purchase_case"
_PROMPT_TOKENS: Final = 1200
_OUTPUT_TOKENS: Final = 120 * MAX_CONFIRMED_LINES + 100
# The drafted cases `late` looks through, oldest first: a bound, so a tick or
# a page never reads every case a tenant ever ordered.
FOLLOWED_CASES: Final = 500
# The day a date is late on: the plant's, never UTC's (7 hours behind).
_PLANT: Final = ZoneInfo("Asia/Ho_Chi_Minh")
_LOG = logging.getLogger("dw_purchasing.follow_up")


class LateLine(BaseModel):
    """One line past its date with less arrived than ordered."""

    model_config = ConfigDict(frozen=True)

    case_id: uuid.UUID
    pr_no: str
    po_ref: str
    supplier_code: str
    line_no: int
    due_on: date
    owed: Decimal


class ConfirmationMail(BaseModel):
    """A verified mail from the supplier of one of a case's orders that names
    the order, not read yet: what a buyer presses "DW2 đọc" on."""

    model_config = ConfigDict(frozen=True)

    message_id: str
    po_ref: str
    sender: str
    subject: str
    received_at: datetime


def named_order(case: PurchaseCase, master: MasterData, domain: str, text: str) -> PoDraft | None:
    """The order of ``case`` a supplier's mail is about, decided by code: an
    order of a supplier this domain is one of, which the mail names by its
    `po_ref` or Bravo's number. None for anything else, or for two."""
    if case.po is None:
        return None
    folded = fold(text)
    numbers = {t.po_ref: t.bravo_no for t in case.tracking}
    found = []
    for order in case.po.orders:
        supplier = master.supplier(order.supplier_code)
        if supplier is None or domain not in supplier.domains:
            continue
        names = [order.po_ref, *([numbers[order.po_ref]] if numbers.get(order.po_ref) else [])]
        if any(occurrences(folded, fold(name)) for name in names):  # type: ignore[arg-type]
            found.append(order)
    return found[0] if len(found) == 1 else None


@dataclass(frozen=True)
class OrderFollowUp:
    uow: PurchasingUnitOfWork
    gate: Gate
    master: MasterDataPort
    inbox: InboxPort
    # None where the deployment has no model: a confirmation is then read by
    # the buyer, and nothing is recorded from it.
    model: InterpretationPort | None
    worker: Worker
    clock: UtcClock
    ids: IdGenerator

    async def record_bravo_no(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        po_ref: str,
        bravo_no: str,
        *,
        case_version: int,
    ) -> CaseChange:
        case = await self._case(context, case_id, case_version)
        tracking = _tracking(case, po_ref)
        if tracking.bravo_no is not None:
            raise ConflictError(
                "đơn này đã có số PO Bravo",
                details={"po_ref": po_ref, "rule": "bravo_no_set"},
            )
        now = self.clock.now()
        followed = tracking.model_copy(
            update={"bravo_no": bravo_no, "bravo_by": context.principal_id, "bravo_at": now}
        )
        # Validated whole: a number that is no code is refused here.
        followed = OrderTracking.model_validate(followed.model_dump())
        return await self._keep(
            context, case, followed, "purchasing.po.bravo_numbered", {"po_ref": po_ref}
        )

    async def read_confirmation(
        self, context: AccessContext, case_id: uuid.UUID, message_id: str, *, case_version: int
    ) -> CaseChange:
        case = await self._case(context, case_id, case_version)
        message = await self.inbox.get_message(context, message_id)
        if message is None:
            raise NotFoundError("không có thư này", details={"message_id": message_id})
        if any(
            t.confirmation is not None and t.confirmation.source_ref == message_id
            for t in case.tracking
        ):
            raise ConflictError(
                "thư xác nhận này đã được đọc", details={"message_id": message_id, "rule": "read"}
            )
        master = await self.master.for_context(context)
        text = f"{message.subject}\n{newest_part(message).text}"
        order = named_order(case, master, message.sender.domain, text)
        if order is None or not message.authentication.verified:
            raise ConflictError(
                "thư không phải của nhà cung cấp của một đơn trong hồ sơ, không nêu số đơn,"
                " hoặc chưa xác thực",
                details={
                    "message_id": message_id,
                    "rule": "order_not_named" if order is None else "sender_unverified",
                },
            )
        tracking = _tracking(case, order.po_ref)
        if tracking.confirmation is not None and tracking.confirmation.accepted_by is not None:
            raise ConflictError(
                "đơn này đã có xác nhận được chấp nhận",
                details={"po_ref": order.po_ref, "rule": "confirmed"},
            )
        if self.model is None:
            raise InfrastructureError(NOT_READ_NOW, details={"reason_code": "no_model"})
        shown = cut_to_tokens(
            newest_part(message).text,
            self.model.max_input_tokens - _PROMPT_TOKENS - _OUTPUT_TOKENS,
        )
        try:
            answer = await self.model.interpret(
                ORDER_CONFIRMATION_READING,
                {"mail": shown},
                ModelConfirmation,
                run=caller_run(
                    context,
                    run_id=self.ids.new_uuid(),
                    worker_id=self.worker.worker_id,
                    worker_version=self.worker.worker_version,
                    trace="dw2-order-confirmation",
                    subject_ref=f"purchasing_mail:{message_id}",
                ),
                max_output_tokens=_OUTPUT_TOKENS,
            )
        except ModelUnavailableError as exc:
            raise InfrastructureError(NOT_READ_NOW, details={"reason_code": "model"}) from exc
        verdict = read_confirmation_mail(
            shown,
            answer,
            ordered={
                line.item_code: line.line_no for line in order.lines if line.item_code is not None
            },
            received_on=message.received_at.date(),
        )
        if verdict.not_read is not None:
            raise ConflictError(
                "DW2 không đọc được xác nhận trong thư: người mua đọc",
                details={"message_id": message_id, "rule": verdict.not_read},
            )
        found = differences(order, verdict.lines)
        confirmation = Confirmation(
            source_ref=message_id,
            lines=verdict.lines,
            differences=found,
            read_by=context.principal_id,
            read_at=self.clock.now(),
        )
        return await self._keep(
            context,
            case,
            tracking.model_copy(update={"confirmation": confirmation}),
            "purchasing.po.confirmation_read",
            {"po_ref": order.po_ref, "message_id": message_id, "differences": len(found)},
        )

    async def confirmation_mails(
        self, context: AccessContext, case_id: uuid.UUID
    ) -> list[ConfirmationMail]:
        """The mails that confirm an order of the case, decided by code
        (`named_order`), newest first."""
        await self.gate.require(
            context, PurchasingScopes.PO_PREPARE, resource_type=_RESOURCE, resource_id=str(case_id)
        )
        async with self.uow(context) as work:
            case = await work.cases.get(case_id)
        if case is None:
            raise NotFoundError("không có yêu cầu mua hàng này", details={"case_id": str(case_id)})
        if case.po is None:
            return []
        read = {t.confirmation.source_ref for t in case.tracking if t.confirmation is not None}
        master = await self.master.for_context(context)
        found: list[ConfirmationMail] = []
        for message in await self.inbox.list_messages(context):
            if message.message_id in read or not message.authentication.verified:
                continue
            text = f"{message.subject}\n{newest_part(message).text}"
            order = named_order(case, master, message.sender.domain, text)
            if order is not None:
                found.append(
                    ConfirmationMail(
                        message_id=message.message_id,
                        po_ref=order.po_ref,
                        sender=message.sender.display_name or message.sender.address,
                        subject=message.subject,
                        received_at=message.received_at,
                    )
                )
        return sorted(found, key=lambda m: m.received_at, reverse=True)

    async def accept_confirmation(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        po_ref: str,
        *,
        case_version: int,
        only_if_same: bool = False,
    ) -> CaseChange:
        """``only_if_same``: the lane's call, refused when the confirmation
        differs from the order in anything."""
        case = await self._case(context, case_id, case_version)
        tracking = _tracking(case, po_ref)
        confirmation = tracking.confirmation
        if confirmation is None or confirmation.accepted_by is not None:
            raise ConflictError(
                "không có xác nhận nào đang chờ chấp nhận",
                details={"po_ref": po_ref, "rule": "nothing_to_accept"},
            )
        if only_if_same and confirmation.differences:
            raise ConflictError(
                "xác nhận khác đơn: người mua xem",
                details={"po_ref": po_ref, "rule": "differs"},
            )
        accepted = confirmation.model_copy(
            update={"accepted_by": context.principal_id, "accepted_at": self.clock.now()}
        )
        return await self._keep(
            context,
            case,
            tracking.model_copy(update={"confirmation": accepted}),
            "purchasing.po.confirmation_accepted",
            {"po_ref": po_ref, "differences": len(confirmation.differences)},
        )

    async def record_receipt(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        po_ref: str,
        *,
        line_no: int,
        quantity: Decimal,
        received_on: date,
        case_version: int,
    ) -> CaseChange:
        case = await self._case(context, case_id, case_version)
        tracking = _tracking(case, po_ref)
        order = _order(case, po_ref)
        line = next((li for li in order.lines if li.line_no == line_no), None)
        if line is None:
            raise NotFoundError(
                "đơn không có dòng này", details={"po_ref": po_ref, "line_no": line_no}
            )
        if received(tracking, line_no) + quantity > line.quantity:
            raise ConflictError(
                "nhận nhiều hơn số còn thiếu của dòng",
                details={"po_ref": po_ref, "line_no": line_no, "rule": "over_receipt"},
            )
        receipt = Receipt(
            line_no=line_no,
            quantity=quantity,
            received_on=received_on,
            recorded_by=context.principal_id,
            recorded_at=self.clock.now(),
        )
        return await self._keep(
            context,
            case,
            tracking.model_copy(update={"receipts": (*tracking.receipts, receipt)}),
            "purchasing.po.received",
            {"po_ref": po_ref, "line_no": line_no},
            close=True,
        )

    async def late(self, context: AccessContext, *, today: date | None = None) -> list[LateLine]:
        """Every line of every drafted order past its date (today, unless
        given), less arrived than ordered, oldest first."""
        await self.gate.require(context, PurchasingScopes.PO_PREPARE, resource_type=_RESOURCE)
        today = today if today is not None else self.clock.now().astimezone(_PLANT).date()
        async with self.uow(context) as work:
            cases = await work.cases.waiting(
                frozenset({CaseStatus.PO_DRAFTED.value}), limit=FOLLOWED_CASES
            )
        if len(cases) == FOLLOWED_CASES:
            # Past the bound (500 orders not all arrived), newer cases are not
            # looked at. Said, not hidden.
            _LOG.warning(
                "late lines read from the %d oldest drafted cases only (tenant %s)",
                FOLLOWED_CASES,
                context.tenant_id,
            )
        found: list[LateLine] = []
        for case in cases:
            assert case.po is not None
            for order in case.po.orders:
                tracking = _tracking(case, order.po_ref)
                lines = {line.line_no: line for line in order.lines}
                for line_no in due_lines(order, tracking, today=today):
                    on = due_on(order, tracking, line_no)
                    assert on is not None
                    found.append(
                        LateLine(
                            case_id=case.case_id,
                            pr_no=case.request.pr_no,
                            po_ref=order.po_ref,
                            supplier_code=order.supplier_code,
                            line_no=line_no,
                            due_on=on,
                            owed=lines[line_no].quantity - received(tracking, line_no),
                        )
                    )
        return sorted(found, key=lambda late: (late.due_on, late.po_ref, late.line_no))

    # --------------------------------------------------------- the case --

    async def _case(self, context: AccessContext, case_id: uuid.UUID, version: int) -> PurchaseCase:
        await self.gate.require(
            context, PurchasingScopes.PO_PREPARE, resource_type=_RESOURCE, resource_id=str(case_id)
        )
        async with self.uow(context) as work:
            case = await work.cases.get(case_id)
        if case is None:
            raise NotFoundError("không có yêu cầu mua hàng này", details={"case_id": str(case_id)})
        if case.case_version != version:
            raise ConflictError(
                "hồ sơ đã thay đổi: tải lại",
                details={"case_id": str(case_id), "rule": "stale_version"},
            )
        if case.status is not CaseStatus.PO_DRAFTED:
            raise ConflictError(
                "hồ sơ chưa có PO nháp",
                details={"case_id": str(case_id), "status": case.status.value},
            )
        return case

    async def _keep(
        self,
        context: AccessContext,
        case: PurchaseCase,
        tracking: OrderTracking,
        action: str,
        details: dict[str, object],
        *,
        close: bool = False,
    ) -> CaseChange:
        """``close``: a receipt, which moves the case to `delivered` once
        every line of every order arrived in full."""
        kept = [t for t in case.tracking if t.po_ref != tracking.po_ref]
        after = PurchaseCase.model_validate(
            {
                **case.model_dump(),
                "case_version": case.case_version + 1,
                "tracking": sorted([*kept, tracking], key=lambda t: t.po_ref),
            }
        )
        delivered = close and after.delivered_in_full
        if delivered:
            after = PurchaseCase.model_validate(
                {**after.model_dump(), "status": CaseStatus.DELIVERED}
            )
        async with self.uow(context) as work:
            await work.cases.save(after, expected_version=case.case_version)
            if delivered:
                await work.audit.append(
                    AuditEvent(
                        id=self.ids.new_uuid(),
                        tenant_id=TenantId(context.tenant_id),
                        workspace_id=WorkspaceId(context.workspace_id),
                        actor_id=UserId(context.principal_id),
                        action="purchasing.case.delivered",
                        resource_type=_RESOURCE,
                        resource_id=str(after.case_id),
                        occurred_at=self.clock.now(),
                        details={"case_version": after.case_version},
                    )
                )
            # Ids, refs and counts: no quantity, price or date.
            await work.audit.append(
                AuditEvent(
                    id=self.ids.new_uuid(),
                    tenant_id=TenantId(context.tenant_id),
                    workspace_id=WorkspaceId(context.workspace_id),
                    actor_id=UserId(context.principal_id),
                    action=action,
                    resource_type=_RESOURCE,
                    resource_id=str(after.case_id),
                    occurred_at=self.clock.now(),
                    details={"case_version": after.case_version, **details},
                )
            )
        return CaseChange(
            case_id=after.case_id, case_version=after.case_version, status=after.status
        )


def _order(case: PurchaseCase, po_ref: str) -> PoDraft:
    assert case.po is not None
    order = next((o for o in case.po.orders if o.po_ref == po_ref), None)
    if order is None:
        raise NotFoundError("hồ sơ không có đơn này", details={"po_ref": po_ref})
    return order


def _tracking(case: PurchaseCase, po_ref: str) -> OrderTracking:
    """What the case holds for ``po_ref``: an untouched order holds none yet."""
    _order(case, po_ref)
    found = next((t for t in case.tracking if t.po_ref == po_ref), None)
    return found if found is not None else OrderTracking(po_ref=po_ref)
