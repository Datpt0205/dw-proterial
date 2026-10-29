""" "Gửi cho khách": a case's send draft sent from the mailbox of the person who
pressed, through an outbox folder and their own Power Automate flow.

Đạt, 2026-10-29: no Graph API, and never a shared mailbox on the server. The
way mail reaches DW1 (ticket 43: each PIC's flow exports their Inbox into a
folder the plant syncs) is run the other way:

1. **The API** (`OutboundMailService.send`): the caller may prepare the case
   (`sales.quote.prepare` / `sales.order.prepare`); the artifact is the
   case's send draft at its current version, still downloadable; every
   recipient is one of the customer's contacts in the master data; the
   mailbox is the caller's own sign-in address, resolved by the server. Then
   one `queued` row and its audit event, in one transaction. One active mail
   per draft: a second press sends nothing more.
2. **The worker** (`OutboundLane`, lane `sales_outbound`), the only process
   that touches the share: a queued mail is written as a job into that
   mailbox's outbox folder (`OutboxFolderPort`), or fails `not_connected`
   when the person has no folder yet (no flow set up: until Proterial's
   rollout, everyone), and the person is told.
3. **Their flow** sends it from their Outlook (it lands in their Sent Items,
   replies come back to them) and writes a receipt.
4. **The worker** reads the receipt: `sent`, and a quotation is marked "Đã
   gửi KH" as the person who pressed (resolved again, cut to the prepare
   scope, through the same command the button uses); or `failed`, and they
   are told. A mail written and not receipted within `RECEIPT_WITHIN` is
   `stalled`, and they are told to send the `.eml` themselves.

Nothing is sent without a person pressing, and nothing a model wrote decides
who receives it. The lane audits as itself (ADR 0011).
"""

from __future__ import annotations

import html
import json
import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from email import message_from_bytes, policy
from email.message import EmailMessage
from email.utils import getaddresses
from typing import TYPE_CHECKING, Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict

from dw_kernel.errors import ConflictError, NotFoundError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.identity import context_from
from dw_platform.domain.audit import AuditEvent, lane_audit_event, system_actor
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.case_store import (
    OutboundError,
    OutboundMail,
    OutboundStatus,
    SalesUnitOfWork,
    SalesUnitOfWorkFactory,
)
from dw_sales.application.ports import (
    ArtifactBytesPort,
    MemberDirectoryPort,
    NotificationSenderPort,
    SalesCatalogPort,
    SalesScope,
)
from dw_sales.application.support import same_version, stored_order, stored_quote
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.orders import OrderCase
from dw_sales.domain.quotes import QuoteCase

if TYPE_CHECKING:
    from dw_sales.application.processing import RequesterAccessPort

logger = logging.getLogger("dw_sales.outbound_mail")

SALES_OUTBOUND_LANE: Final = "sales_outbound"
# The send drafts each lane may send, by artifact kind.
SENDABLE: Final[Mapping[CaseKind, frozenset[str]]] = {
    CaseKind.QUOTE: frozenset({"send_draft"}),
    CaseKind.ORDER: frozenset({"confirmation_draft"}),
}
# Who may send: whoever prepares the case.
_SEND_SCOPE: Final[Mapping[CaseKind, SalesScopes]] = {
    CaseKind.QUOTE: SalesScopes.QUOTE_PREPARE,
    CaseKind.ORDER: SalesScopes.ORDER_PREPARE,
}
# How long a written mail waits for its receipt before the person is told.
RECEIPT_WITHIN: Final = timedelta(minutes=30)
_RESOURCE: Final = "sales_outbound_mail"

_VIEW = ConfigDict(frozen=True)


class OutboundMailView(BaseModel):
    """Where one mail stands, for the case page."""

    model_config = _VIEW

    mail_id: uuid.UUID
    artifact_id: uuid.UUID
    mailbox: str
    status: OutboundStatus
    queued_at: datetime
    settled_at: datetime | None
    error: OutboundError | None


class OutboundMailsView(BaseModel):
    """Whether DW1 sends mail here at all, and the case's mails."""

    model_config = _VIEW

    # False until the deployment names an outbox share (Proterial's rollout).
    enabled: bool
    mails: list[OutboundMailView]


def mail_view(mail: OutboundMail) -> OutboundMailView:
    return OutboundMailView(
        mail_id=mail.mail_id,
        artifact_id=mail.artifact_id,
        mailbox=mail.mailbox,
        status=mail.status,
        queued_at=mail.queued_at,
        settled_at=mail.settled_at,
        error=mail.error,
    )


# --------------------------------------------------------------- the job --


@dataclass(frozen=True, slots=True)
class Receipt:
    """What a flow wrote back for one job."""

    mailbox: str
    name: str
    status: Literal["sent", "failed"]


class OutboxFolderPort(Protocol):
    """The share's outbox folders, one per mailbox (`adapters.outbox_folder`)."""

    def connected(self, mailbox: str) -> bool:
        """Whether ``mailbox`` has an outbox folder: its flow is set up."""
        ...

    def write(
        self, mailbox: str, name: str, job: bytes, attachments: Sequence[tuple[str, bytes]]
    ) -> None:
        """The job and its files, the job last: a flow sees it complete."""
        ...

    def receipts(self) -> Sequence[Receipt]: ...

    def forget(self, receipt: Receipt) -> None:
        """Move a handled receipt aside: it is not read again."""
        ...


def job_name(scope: SalesScope, mail_id: uuid.UUID) -> str:
    """The job's file stem, which its receipt carries back: the scope and the
    mail, so the lane settles it in its own tenant."""
    return f"{scope.tenant_id.value}.{scope.workspace_id.value}.{mail_id}"


def parse_job_name(name: str) -> tuple[SalesScope, uuid.UUID] | None:
    try:
        tenant, workspace, mail = (uuid.UUID(part) for part in name.split("."))
    except ValueError:
        return None
    return SalesScope(TenantId(tenant), WorkspaceId(workspace)), mail


def _draft(data: bytes) -> EmailMessage:
    parsed = message_from_bytes(data, policy=policy.default)
    assert isinstance(parsed, EmailMessage)
    return parsed


def recipients(data: bytes) -> list[str]:
    """The draft's To and Cc addresses, lowercase."""
    draft = _draft(data)
    pairs = getaddresses([str(v) for k in ("To", "Cc") for v in draft.get_all(k, [])])
    return [address.lower() for _, address in pairs if address]


def job_document(mail: OutboundMail, data: bytes) -> tuple[bytes, list[tuple[str, bytes]]]:
    """The flow's job (`job.json`) and the files it attaches, from the draft
    the person saw. The body is the draft's text, as HTML for Outlook."""
    draft = _draft(data)
    body = draft.get_body(preferencelist=("plain",))
    text = body.get_content() if body is not None else ""
    files: list[tuple[str, bytes]] = []
    for index, part in enumerate(draft.iter_attachments()):
        payload = part.get_payload(decode=True)
        if isinstance(payload, bytes):
            files.append((part.get_filename() or f"attachment-{index + 1}", payload))
    to = [a for _, a in getaddresses([str(v) for v in draft.get_all("To", [])]) if a]
    cc = [a for _, a in getaddresses([str(v) for v in draft.get_all("Cc", [])]) if a]
    job = {
        "job": str(mail.mail_id),
        "from": mail.mailbox,
        "to": ";".join(to),
        "cc": ";".join(cc),
        "subject": str(draft.get("Subject", "")),
        "body_html": html.escape(text).replace("\n", "<br>"),
        "attachments": [name for name, _ in files],
    }
    return json.dumps(job, ensure_ascii=False, indent=1).encode("utf-8"), files


# ----------------------------------------------------------- the API side --


@dataclass(frozen=True)
class OutboundMailService:
    """`POST /{orders,quotes}/{id}/artifacts/{artifact_id}/send` and the
    case's mails (module docstring, step 1)."""

    uow: SalesUnitOfWorkFactory
    gate: Gate
    catalog: SalesCatalogPort
    directory: MemberDirectoryPort
    artifact_bytes: ArtifactBytesPort
    clock: UtcClock
    ids: IdGenerator
    # Whether the deployment names an outbox share: until then nothing is
    # queued, and the page says so.
    enabled: bool

    async def mails(
        self, context: AccessContext, kind: CaseKind, case_id: uuid.UUID
    ) -> OutboundMailsView:
        await self.gate.require(
            context, SalesScopes.CASE_READ, resource_type=_RESOURCE, resource_id=str(case_id)
        )
        async with self.uow(sales_scope(context)) as work:
            await self._case(work, context, kind, case_id)
            held = await work.outbound.for_case(kind, case_id)
        return OutboundMailsView(enabled=self.enabled, mails=[mail_view(m) for m in held])

    async def send(
        self,
        context: AccessContext,
        kind: CaseKind,
        case_id: uuid.UUID,
        artifact_id: uuid.UUID,
        *,
        case_version: int,
    ) -> OutboundMailView:
        """Queue the draft, as the case stood when the caller pressed
        (``case_version``): a case that moved since is refused (409)."""
        from dw_sales.application.artifacts_service import ORDER_GATES, QUOTE_GATES

        await self.gate.require(
            context, _SEND_SCOPE[kind], resource_type=_RESOURCE, resource_id=str(case_id)
        )
        if not self.enabled:
            raise ConflictError(
                "DW1 chưa được nối để gửi thư: tải tệp .eml và gửi từ hộp thư của bạn",
                details={"rule": "outbox_not_configured"},
            )
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            case = await self._case(work, context, kind, case_id)
            same_version(case_id, case.case_version, case_version)
            record = await work.artifacts.get(artifact_id)
            if (
                record is None
                or record.case_kind is not kind
                or record.case_id != case_id
                or record.kind not in SENDABLE[kind]
            ):
                raise NotFoundError("no such send draft", details={"artifact_id": str(artifact_id)})
            gates = QUOTE_GATES if kind is CaseKind.QUOTE else ORDER_GATES
            if record.case_version != case.case_version or not gates[record.kind].open_in(
                case,  # type: ignore[arg-type]
                context,
                self.gate,
            ):
                raise ConflictError(
                    "thư nháp này không còn là bản hiện tại của hồ sơ: mở lại hồ sơ rồi gửi",
                    details={"rule": "draft_not_current", "case_version": case.case_version},
                )
            data = await self.artifact_bytes.get_object(record.object_key(scope))
            customer = (await self.catalog.customer_by_code(scope, case.customer_code)).data
            contacts = {c.address.lower() for c in customer.contacts} if customer else set()
            to = recipients(data)
            if not to or not set(to) <= contacts:
                raise ConflictError(
                    "người nhận không nằm trong danh bạ khách ở dữ liệu chủ",
                    details={"rule": "recipient_not_a_contact"},
                )
            mailbox = await self._mailbox(context)
            now = self.clock.now()
            mail = OutboundMail(
                mail_id=self.ids.new_uuid(),
                case_kind=kind,
                case_id=case_id,
                artifact_id=artifact_id,
                requested_by=context.principal_id,
                mailbox=mailbox,
                status="queued",
                queued_at=now,
            )
            held = await work.outbound.add(mail)
            if held.mail_id == mail.mail_id:
                await work.audit.append(
                    AuditEvent(
                        id=self.ids.new_uuid(),
                        tenant_id=TenantId(context.tenant_id),
                        workspace_id=WorkspaceId(context.workspace_id),
                        actor_id=UserId(context.principal_id),
                        action="sales.mail.send_requested",
                        resource_type=_RESOURCE,
                        resource_id=str(mail.mail_id),
                        occurred_at=now,
                        details={
                            "case_kind": kind.value,
                            "case_id": str(case_id),
                            "artifact_id": str(artifact_id),
                            "recipients": len(to),
                        },
                    )
                )
                await work.commit()
        return mail_view(held)

    async def _case(
        self, work: SalesUnitOfWork, context: AccessContext, kind: CaseKind, case_id: uuid.UUID
    ) -> OrderCase | QuoteCase:
        """The case as the caller may see it: another's reads as not found."""
        if kind is CaseKind.ORDER:
            return (await stored_order(work, case_id, viewer=context)).case
        return (await stored_quote(work, case_id, viewer=context)).case

    async def _mailbox(self, context: AccessContext) -> str:
        """The caller's own sign-in address: the mailbox the mail goes from."""
        members = await self.directory.list_members(context)
        me = next((m for m in members if m.user_id == context.principal_id), None)
        if me is None or not me.email:
            raise ConflictError(
                "tài khoản của bạn chưa có địa chỉ thư để gửi",
                details={"rule": "no_mailbox"},
            )
        return me.email.lower()


# -------------------------------------------------------- the worker side --


class OutboundScopesPort(Protocol):
    async def scopes(self) -> Sequence[SalesScope]: ...


class QuoteSentPort(Protocol):
    """ "Đã gửi KH", as the person who pressed (`QuoteCommands.sent`)."""

    async def sent(
        self, context: AccessContext, case_id: uuid.UUID, *, case_version: int
    ) -> object: ...


# The person's access when their quotation is marked sent: nothing more.
_SENT_CEILING: Final = frozenset({SalesScopes.QUOTE_PREPARE.value, SalesScopes.CASE_READ.value})

_TOLD: Final[Mapping[str, tuple[str, str]]] = {
    "not_connected": (
        "Chưa gửi được thư cho khách",
        "Hộp thư của bạn chưa được nối để DW1 gửi thư. Tải tệp .eml trong hồ sơ và gửi từ "
        'Outlook, rồi bấm "Đã gửi KH".',
    ),
    "write_failed": (
        "Chưa gửi được thư cho khách",
        "DW1 không ghi được thư vào thư mục gửi. Thử lại, hoặc gửi tệp .eml từ Outlook.",
    ),
    "flow_failed": (
        "Thư cho khách bị báo lỗi khi gửi",
        "Luồng gửi thư của bạn báo lỗi. Kiểm tra kết nối Power Automate, hoặc gửi tệp .eml "
        "từ Outlook.",
    ),
    "no_receipt": (
        "Thư cho khách chưa có xác nhận đã gửi",
        "Sau 30 phút luồng gửi thư chưa xác nhận. Xem mục Thư đã gửi trong Outlook; nếu "
        'không có, gửi tệp .eml rồi bấm "Đã gửi KH".',
    ),
}


def _lane_context(scope: SalesScope) -> AccessContext:
    return AccessContext(
        tenant_id=scope.tenant_id.value,
        workspace_id=scope.workspace_id.value,
        principal_id=system_actor(SALES_OUTBOUND_LANE).value,
        roles=frozenset(),
        scopes=frozenset(),
        plan_id="background",
    )


@dataclass(frozen=True)
class OutboundTick:
    written: int = 0
    settled: int = 0


@dataclass(frozen=True)
class OutboundLane:
    """The worker's `sales_outbound` lane (module docstring, steps 2 and 4)."""

    uow: SalesUnitOfWorkFactory
    scopes: OutboundScopesPort
    outbox: OutboxFolderPort
    artifact_bytes: ArtifactBytesPort
    quotes: QuoteSentPort
    access: RequesterAccessPort
    notifications: NotificationSenderPort
    clock: UtcClock
    ids: IdGenerator

    async def tick(self) -> OutboundTick:
        settled = 0
        for receipt in self.outbox.receipts():
            settled += await self._receipt(receipt)
            self.outbox.forget(receipt)
        written = 0
        for scope in await self.scopes.scopes():
            async with self.uow(scope) as work:
                pending = await work.outbound.pending()
            for mail in pending:
                if mail.status == "queued":
                    written += await self._write(scope, mail)
                elif self.clock.now() - mail.queued_at >= RECEIPT_WITHIN:
                    settled += await self._settle(scope, mail, "stalled", "no_receipt")
        return OutboundTick(written=written, settled=settled)

    async def _write(self, scope: SalesScope, mail: OutboundMail) -> int:
        if not self.outbox.connected(mail.mailbox):
            return await self._settle(scope, mail, "failed", "not_connected")
        try:
            async with self.uow(scope) as work:
                record = await work.artifacts.get(mail.artifact_id)
            if record is None:
                return await self._settle(scope, mail, "failed", "gone")
            data = await self.artifact_bytes.get_object(record.object_key(scope))
            job, files = job_document(mail, data)
            self.outbox.write(mail.mailbox, job_name(scope, mail.mail_id), job, files)
        except Exception:
            logger.exception("sales_outbound: a mail was not written to its outbox")
            return await self._settle(scope, mail, "failed", "write_failed")
        return await self._settle(scope, mail, "written", None)

    async def _receipt(self, receipt: Receipt) -> int:
        parsed = parse_job_name(receipt.name)
        if parsed is None:
            logger.warning("sales_outbound: a receipt names no job of DW1's")
            return 0
        scope, mail_id = parsed
        async with self.uow(scope) as work:
            mail = await work.outbound.get(mail_id)
        if mail is None or mail.status != "written" or mail.mailbox != receipt.mailbox:
            return 0
        if receipt.status == "failed":
            return await self._settle(scope, mail, "failed", "flow_failed")
        done = await self._settle(scope, mail, "sent", None)
        if done and mail.case_kind is CaseKind.QUOTE:
            await self._mark_sent(scope, mail)
        return done

    async def _mark_sent(self, scope: SalesScope, mail: OutboundMail) -> None:
        """ "Đã gửi KH" as the person who pressed, through the button's own
        command; a case that moved on meanwhile (marked by hand) is left."""
        access = await self.access.find_linked_access(
            mail.requested_by, scope.tenant_id.value, scope.workspace_id.value, _SENT_CEILING
        )
        if access is None:
            return
        context = context_from(access)
        try:
            async with self.uow(scope) as work:
                case = (await stored_quote(work, mail.case_id, viewer=context)).case
            await self.quotes.sent(context, mail.case_id, case_version=case.case_version)
        except (ConflictError, NotFoundError) as left:
            logger.info("sales_outbound: a sent quotation was not marked: %s", type(left).__name__)

    async def _settle(
        self,
        scope: SalesScope,
        mail: OutboundMail,
        status: OutboundStatus,
        error: OutboundError | None,
    ) -> int:
        now = self.clock.now()
        async with self.uow(scope) as work:
            if not await work.outbound.settle(mail.mail_id, status, now, error):
                return 0
            await work.audit.append(
                lane_audit_event(
                    lane=SALES_OUTBOUND_LANE,
                    event_id=self.ids.new_uuid(),
                    tenant_id=scope.tenant_id,
                    workspace_id=scope.workspace_id,
                    action=f"sales.mail.{status}",
                    resource_type=_RESOURCE,
                    resource_id=str(mail.mail_id),
                    occurred_at=now,
                    details={"case_id": str(mail.case_id), **({"error": error} if error else {})},
                )
            )
            await work.commit()
        if error is not None and error in _TOLD:
            title, body = _TOLD[error]
            try:
                await self.notifications.deliver(
                    _lane_context(scope),
                    recipients=[mail.requested_by],
                    source_key=f"{SALES_OUTBOUND_LANE}:{mail.mail_id}:{status}",
                    title=title,
                    body=body,
                    link=f"/sales/{mail.case_kind.value}s/{mail.case_id}",
                )
            except Exception:
                logger.exception("sales_outbound: the person was not told")
        return 1
