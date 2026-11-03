"""A supplier's RFQ sent from the buyer's own mailbox ("Gửi từ hộp thư của tôi").

The way DW1 sends a quotation (`dw_sales.application.outbound_mail`), with
DW2's own queue (ADR 0014): no Graph API, never a shared mailbox on a server.

1. **The API** (`RfqMailService.send`): the caller prepares RFQs
   (`purchasing.rfq.prepare`); the case holds that supplier's RFQ with words
   (none still waiting for a person to write them); every recipient is still
   one of the supplier's contacts in the master data (refused otherwise,
   never trusted from the draft); the mailbox is the caller's own sign-in
   address, read from the directory by the server. One `queued` row and its
   audit event, in one transaction. One active mail per supplier of a case:
   a second press sends nothing more; a failed one may be sent again.
2. **The worker** (`RfqMailLane`, lane `purchasing_outbound`), the only
   process that touches the share: a queued mail is written as a job
   (`dw_platform.application.outbox_folder.flow_job`) into that mailbox's
   outbox folder, or fails `not_connected` when the person has no folder (no
   flow set up), and they are told.
3. **Their flow** sends it from their Outlook and writes a receipt; the
   supplier's reply comes back to their Inbox and reaches DW2 through the
   inbound flow.
4. **The worker** reads the receipts of DW2's jobs only (named `dw2.<tenant>.
   <workspace>.<mail>`; the folder and the flow are DW1's too): `sent`, or
   `failed` and the person is told. A mail written and not receipted within
   `RECEIPT_WITHIN` is `stalled`, and they are told to send it themselves.

Nothing is sent without a person pressing, and no model chooses who receives
it. The lane audits as itself (ADR 0011).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict

from dw_kernel.errors import ConflictError, NotFoundError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.outbox_folder import OutboxFolderPort, Receipt, flow_job
from dw_platform.application.rule_versions import ContextScope
from dw_platform.domain.audit import AuditEvent, lane_audit_event, system_actor
from dw_purchasing.application.access import Gate, PurchasingScopes
from dw_purchasing.application.ports import (
    MasterDataPort,
    NoticesPort,
    PeoplePort,
    PurchasingUnitOfWork,
)
from dw_purchasing.domain.cases import CaseStatus

OUTBOUND_LANE: Final = "purchasing_outbound"
QUEUED: Final = "purchasing.rfq.mail_queued"
SETTLED: Final = "purchasing.rfq.mail_settled"
_RESOURCE: Final = "purchasing_rfq_mail"
# How long a flow has to answer a job before the person is told to send it
# themselves: OneDrive's sync both ways and the flow's own run (DW1's bound).
RECEIPT_WITHIN: Final = timedelta(minutes=30)
_PREFIX: Final = "dw2"

MailStatus = Literal["queued", "written", "sent", "failed", "stalled"]
MailError = Literal["not_connected", "flow_failed", "no_receipt"]
NOT_ENABLED: Final = "gửi thư từ hộp thư chưa được bật trên hệ thống này: tải thư về và gửi tay"


class RfqMail(BaseModel):
    """One RFQ handed to a person's flow, and what became of it."""

    model_config = ConfigDict(frozen=True)

    mail_id: uuid.UUID
    case_id: uuid.UUID
    supplier_code: str
    mailbox: str
    recipients: tuple[str, ...]
    subject: str
    body: str
    status: MailStatus
    error: MailError | None = None
    queued_by: uuid.UUID
    queued_at: datetime
    written_at: datetime | None = None
    settled_at: datetime | None = None


class RfqMailView(BaseModel):
    """A mail as the case page lists it: never its words, which the case has."""

    model_config = ConfigDict(frozen=True)

    mail_id: uuid.UUID
    supplier_code: str
    mailbox: str
    status: MailStatus
    error: MailError | None
    queued_by: uuid.UUID
    queued_at: datetime
    settled_at: datetime | None


def _view(mail: RfqMail) -> RfqMailView:
    return RfqMailView(
        mail_id=mail.mail_id,
        supplier_code=mail.supplier_code,
        mailbox=mail.mailbox,
        status=mail.status,
        error=mail.error,
        queued_by=mail.queued_by,
        queued_at=mail.queued_at,
        settled_at=mail.settled_at,
    )


def job_name(scope: ContextScope, mail_id: uuid.UUID) -> str:
    """The job's file stem, which its receipt carries back."""
    return f"{_PREFIX}.{scope.tenant_id.value}.{scope.workspace_id.value}.{mail_id}"


def parse_job_name(name: str) -> tuple[ContextScope, uuid.UUID] | None:
    """The scope and mail a DW2 job names; None for anyone else's."""
    prefix, _, rest = name.partition(".")
    if prefix != _PREFIX:
        return None
    try:
        tenant, workspace, mail = (uuid.UUID(part) for part in rest.split("."))
    except ValueError:
        return None
    return ContextScope(TenantId(tenant), WorkspaceId(workspace)), mail


class RfqMailsPort(Protocol):
    """DW2's queue of RFQ mails, bound to the scope asked about."""

    async def add(self, mail: RfqMail, event: AuditEvent) -> None:
        """Refuses (`ConflictError`, rule ``already_sent``) a supplier of a
        case that already has a mail queued, written or sent."""
        ...

    async def of_case(self, scope: ContextScope, case_id: uuid.UUID) -> Sequence[RfqMail]: ...

    async def get(self, scope: ContextScope, mail_id: uuid.UUID) -> RfqMail | None: ...

    async def pending(self, scope: ContextScope) -> Sequence[RfqMail]:
        """Oldest first, the mails queued or written and not yet settled."""
        ...

    async def written(self, scope: ContextScope, mail_id: uuid.UUID, *, at: datetime) -> bool: ...

    async def settle(
        self,
        scope: ContextScope,
        mail_id: uuid.UUID,
        *,
        status: Literal["sent", "failed", "stalled"],
        error: MailError | None,
        at: datetime,
        event: AuditEvent,
    ) -> bool:
        """Settles a mail still queued or written; False when it was settled."""
        ...


# --------------------------------------------------------------- the API --


@dataclass(frozen=True)
class RfqMailService:
    uow: PurchasingUnitOfWork
    gate: Gate
    mails: RfqMailsPort
    master: MasterDataPort
    people: PeoplePort
    clock: UtcClock
    ids: IdGenerator
    # Whether this deployment has an outbox share at all.
    enabled: bool

    async def send(
        self, context: AccessContext, case_id: uuid.UUID, supplier_code: str
    ) -> RfqMailView:
        await self.gate.require(
            context, PurchasingScopes.RFQ_PREPARE, resource_type=_RESOURCE, resource_id=str(case_id)
        )
        async with self.uow(context) as work:
            case = await work.cases.get(case_id)
        if case is None:
            raise NotFoundError("không có yêu cầu mua hàng này", details={"case_id": str(case_id)})
        if not self.enabled:
            raise ConflictError(NOT_ENABLED, details={"rule": "outbox_disabled"})
        if case.status is not CaseStatus.RFQ_DRAFTED or case.rfq is None:
            raise ConflictError(
                "hồ sơ không ở bước hỏi giá", details={"case_id": str(case_id), "rule": "status"}
            )
        draft = case.rfq.asked(supplier_code)
        if draft is None:
            raise NotFoundError(
                "nhà cung cấp này không có thư hỏi giá trong hồ sơ",
                details={"case_id": str(case_id), "supplier_code": supplier_code},
            )
        if draft.written_by == "pending":
            raise ConflictError(
                "thư hỏi giá này chưa có nội dung: viết thư trước rồi gửi",
                details={"case_id": str(case_id), "rule": "rfq_words_pending"},
            )
        supplier = (await self.master.for_context(context)).supplier(supplier_code)
        listed = {c.lower() for c in supplier.contacts} if supplier is not None else set()
        recipients = tuple(a.lower() for a in draft.to)
        if not recipients or not set(recipients) <= listed:
            raise ConflictError(
                "người nhận không còn là liên hệ của nhà cung cấp trong dữ liệu chủ: soạn lại thư",
                details={"case_id": str(case_id), "rule": "recipient_not_listed"},
            )
        person = await self.people.person(context, context.principal_id)
        if person is None or not person.email:
            raise ConflictError(
                "tài khoản của bạn chưa có địa chỉ thư: nhờ quản trị bổ sung",
                details={"rule": "no_mailbox"},
            )
        mail = RfqMail(
            mail_id=self.ids.new_uuid(),
            case_id=case_id,
            supplier_code=supplier_code,
            mailbox=person.email.lower(),
            recipients=recipients,
            subject=draft.subject,
            body=draft.body,
            status="queued",
            queued_by=context.principal_id,
            queued_at=self.clock.now(),
        )
        await self.mails.add(
            mail,
            AuditEvent(
                id=self.ids.new_uuid(),
                tenant_id=TenantId(context.tenant_id),
                workspace_id=WorkspaceId(context.workspace_id),
                actor_id=UserId(context.principal_id),
                action=QUEUED,
                resource_type=_RESOURCE,
                resource_id=str(mail.mail_id),
                occurred_at=mail.queued_at,
                details={
                    "case_id": str(case_id),
                    "supplier": supplier_code,
                    "recipients": len(recipients),
                },
            ),
        )
        return _view(mail)

    async def of_case(self, context: AccessContext, case_id: uuid.UUID) -> list[RfqMailView]:
        await self.gate.require_any(
            context,
            PurchasingScopes.REQUEST_READ,
            PurchasingScopes.RFQ_PREPARE,
            resource_type=_RESOURCE,
        )
        return [_view(m) for m in await self.mails.of_case(ContextScope.of(context), case_id)]


# --------------------------------------------------------------- the lane --


@dataclass(frozen=True)
class OutboundTick:
    written: int
    settled: int


class RfqMailNoticePort(Protocol):
    async def unsent(self, scope: ContextScope, mail: RfqMail, why: MailError) -> None: ...


@dataclass(frozen=True)
class RfqMailNotices:
    """`RfqMailNoticePort` as an in-app notice to who pressed, once per mail."""

    notices: NoticesPort

    async def unsent(self, scope: ContextScope, mail: RfqMail, why: MailError) -> None:
        reason = {
            "not_connected": "bạn chưa có thư mục gửi thư (luồng gửi thư chưa được cài)",
            "flow_failed": "luồng gửi thư báo lỗi",
            "no_receipt": "sau 30 phút luồng gửi thư vẫn chưa trả lời",
        }[why]
        await self.notices.tell(
            AccessContext(
                tenant_id=scope.tenant_id.value,
                workspace_id=scope.workspace_id.value,
                principal_id=system_actor(OUTBOUND_LANE).value,
                roles=frozenset(),
                scopes=frozenset(),
                plan_id="background",
            ),
            scopes=frozenset(),
            people=(mail.queued_by,),
            source_key=f"purchasing.rfq.unsent:{mail.mail_id}",
            title=f"Thư hỏi giá gửi {mail.supplier_code} chưa đi",
            body=(
                f"DW2 chưa gửi được thư hỏi giá cho {mail.supplier_code}: {reason}."
                " Mở hồ sơ để gửi lại, hoặc gửi thư từ Outlook của bạn."
            ),
            link=f"/purchasing/requests/{mail.case_id}",
        )


@dataclass(frozen=True)
class RfqMailLane:
    """The worker's `purchasing_outbound` lane over one scope."""

    mails: RfqMailsPort
    outbox: OutboxFolderPort
    notices: RfqMailNoticePort
    clock: UtcClock
    ids: IdGenerator

    async def tick(self, scope: ContextScope) -> OutboundTick:
        settled = 0
        for receipt in self.outbox.receipts():
            parsed = parse_job_name(receipt.name)
            # Another context's job, or another scope's: theirs to settle.
            if parsed is None or parsed[0] != scope:
                continue
            settled += await self._receipt(scope, parsed[1], receipt)
            self.outbox.forget(receipt)
        written = 0
        for mail in await self.mails.pending(scope):
            if mail.status == "queued":
                written += await self._write(scope, mail)
            elif mail.written_at and self.clock.now() - mail.written_at >= RECEIPT_WITHIN:
                settled += await self._settle(scope, mail, "stalled", "no_receipt")
        return OutboundTick(written=written, settled=settled)

    async def _write(self, scope: ContextScope, mail: RfqMail) -> int:
        if not self.outbox.connected(mail.mailbox):
            return await self._settle(scope, mail, "failed", "not_connected")
        job = flow_job(
            job_id=str(mail.mail_id),
            mailbox=mail.mailbox,
            to=mail.recipients,
            cc=(),
            subject=mail.subject,
            body_text=mail.body,
            attachments=(),
        )
        self.outbox.write(mail.mailbox, job_name(scope, mail.mail_id), job, ())
        return int(await self.mails.written(scope, mail.mail_id, at=self.clock.now()))

    async def _receipt(self, scope: ContextScope, mail_id: uuid.UUID, receipt: Receipt) -> int:
        mail = await self.mails.get(scope, mail_id)
        # A receipt in another person's folder settles nothing.
        if mail is None or mail.status != "written" or mail.mailbox != receipt.mailbox:
            return 0
        if receipt.status == "failed":
            return await self._settle(scope, mail, "failed", "flow_failed")
        return await self._settle(scope, mail, "sent", None)

    async def _settle(
        self,
        scope: ContextScope,
        mail: RfqMail,
        status: Literal["sent", "failed", "stalled"],
        error: MailError | None,
    ) -> int:
        now = self.clock.now()
        done = await self.mails.settle(
            scope,
            mail.mail_id,
            status=status,
            error=error,
            at=now,
            event=lane_audit_event(
                lane=OUTBOUND_LANE,
                event_id=self.ids.new_uuid(),
                tenant_id=TenantId(scope.tenant_id.value),
                workspace_id=WorkspaceId(scope.workspace_id.value),
                action=SETTLED,
                resource_type=_RESOURCE,
                resource_id=str(mail.mail_id),
                occurred_at=now,
                details={"status": status, "error": error, "case_id": str(mail.case_id)},
            ),
        )
        if done and error is not None:
            await self.notices.unsent(scope, mail, error)
        return int(done)
