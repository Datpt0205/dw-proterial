""" "Gửi cho khách": a case's send draft sent from the mailbox of the person who
pressed, through an outbox folder and their own Power Automate flow; and,
the same way, a request to Design or PC addressed only to the tenant's own
mailboxes for them (ticket 77).

Đạt, 2026-10-29: no Graph API, and never a shared mailbox on the server. The
way mail reaches DW1 (ticket 43: each PIC's flow exports their Inbox into a
folder the plant syncs) is run the other way:

1. **The API** (`OutboundMailService.send`): the caller may prepare the case
   (`sales.quote.prepare` / `sales.order.prepare`); the artifact is the
   case's send draft at its current version, still downloadable; every
   recipient is one of the customer's contacts in the master data, or, for
   a request to Design or PC, one of that team's mailboxes in the tenant's
   rules (`INTERNAL_SENDABLE`); the
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
4. **The worker** reads the receipt: `sent`, and where the sending is itself
   the case's step it is recorded as the person who pressed (resolved again,
   cut to the prepare scope, through the same command the button uses): a
   quotation "Đã gửi KH" or "Đã gửi Design", a change's answer "Ghi đã gửi
   khách", an order's request to PC "Ghi đã hỏi PC" (from when they pressed;
   where the case cannot take it any more they are told); or `failed`, and
   they are told. A mail written and not receipted within `RECEIPT_WITHIN` is
   `stalled`, and they are told to send the `.eml` themselves.

Nothing is sent without a person pressing, and nothing a model wrote decides
who receives it. The lane audits as itself (ADR 0011).
"""

from __future__ import annotations

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
from dw_platform.application.outbox_folder import OutboxFolderPort, Receipt, flow_job
from dw_platform.domain.audit import AuditEvent, lane_audit_event, system_actor
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.case_store import (
    OutboundError,
    OutboundMail,
    OutboundStatus,
    SalesUnitOfWork,
    SalesUnitOfWorkFactory,
)
from dw_sales.application.inbox_service import own_address
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
    from dw_sales.application.design_requests import DesignMailboxesPort
    from dw_sales.application.processing import RequesterAccessPort
    from dw_sales.domain.order_checks import OrderRules

logger = logging.getLogger("dw_sales.outbound_mail")

SALES_OUTBOUND_LANE: Final = "sales_outbound"
# The drafts a person may send to the customer from DW1, by artifact kind:
# every mail DW1 drafts to the customer (`Drafting.customer_email`, ticket
# 76); a request to Design or PC is `INTERNAL_SENDABLE`. Each opens only
# where its own gate does (artifacts_service).
SENDABLE: Final[Mapping[CaseKind, frozenset[str]]] = {
    CaseKind.QUOTE: frozenset({"send_draft", "spec_discussion_draft", "decline_draft"}),
    CaseKind.ORDER: frozenset(
        {
            "confirmation_draft",
            "correction_request",
            "change_can_do_draft",
            "change_options_draft",
            "internal_change_notice",
            "cannot_supply_draft",
        }
    ),
}
type Team = Literal["design", "pc"]
# The drafts a person may send to another team (ticket 77), and to which:
# addressed only to that team's mailboxes in the tenant's rules (Design's
# `QuoteRules.design_mailboxes`, PC's `OrderRules.pc_mailboxes`, the one
# setting that names each), never to a customer, and a customer draft never
# to them.
INTERNAL_SENDABLE: Final[Mapping[CaseKind, Mapping[str, Team]]] = {
    CaseKind.QUOTE: {"design_request_draft": "design"},
    CaseKind.ORDER: {"design_code_request": "design", "pc_request_draft": "pc"},
}
# Why a request to a team is refused: a recipient the team's setting does
# not name (moved since the draft was drawn, or never configured).
_NOT_TEAM: Final[Mapping[Team, tuple[str, str]]] = {
    "design": ("người nhận không phải hộp thư Design trong cấu hình", "recipient_not_design"),
    "pc": ("người nhận không phải hộp thư PC trong cấu hình", "recipient_not_pc"),
}
# The drafts whose sending is itself a step of the case, recorded on the
# receipt as the person who pressed, through the step's own button command.
# The others were recorded before the draft opened (a correction requested,
# a quotation declined), and the confirmation names each line's dates, which
# its own "Ghi đã gửi xác nhận" asks for.
_ANSWERS: Final = frozenset({"change_can_do_draft", "change_options_draft"})
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
    job = flow_job(
        job_id=str(mail.mail_id),
        mailbox=mail.mailbox,
        to=to,
        cc=cc,
        subject=str(draft.get("Subject", "")),
        body_text=text,
        attachments=[name for name, _ in files],
    )
    return job, files


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
    # The tenant's Design and PC mailboxes, the only recipients of a draft to
    # that team; None, or none configured, refuses every such draft.
    design: DesignMailboxesPort | None = None
    pc: PcMailboxesPort | None = None

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
                or record.kind not in SENDABLE[kind] | INTERNAL_SENDABLE[kind].keys()
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
            to = recipients(data)
            team = INTERNAL_SENDABLE[kind].get(record.kind)
            if team is not None:
                mailboxes = {a.lower() for a in await self._team_mailboxes(scope, team)}
                if not to or not set(to) <= mailboxes:
                    words, rule = _NOT_TEAM[team]
                    raise ConflictError(words, details={"rule": rule})
            else:
                customer = (await self.catalog.customer_by_code(scope, case.customer_code)).data
                contacts = {c.address.lower() for c in customer.contacts} if customer else set()
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

    async def _team_mailboxes(self, scope: SalesScope, team: Team) -> tuple[str, ...]:
        """The team's mailboxes in the tenant's rules in force now."""
        if team == "design":
            if self.design is None:
                return ()
            return (await self.design.quote_rules(scope)).design_mailboxes
        if self.pc is None:
            return ()
        return (await self.pc.order_rules(scope)).pc_mailboxes

    async def _case(
        self, work: SalesUnitOfWork, context: AccessContext, kind: CaseKind, case_id: uuid.UUID
    ) -> OrderCase | QuoteCase:
        """The case as the caller may see it: another's reads as not found."""
        if kind is CaseKind.ORDER:
            return (await stored_order(work, case_id, viewer=context)).case
        return (await stored_quote(work, case_id, viewer=context)).case

    async def _mailbox(self, context: AccessContext) -> str:
        """The caller's own sign-in address: the mailbox the mail goes from."""
        address = await own_address(self.directory, context)
        if address is None:
            raise ConflictError(
                "tài khoản của bạn chưa có địa chỉ thư để gửi",
                details={"rule": "no_mailbox"},
            )
        return address


class PcMailboxesPort(Protocol):
    """Where PC is reached: the tenant's order rules in force, whose
    ``pc_mailboxes`` name the addresses PC is asked at and answers from."""

    async def order_rules(self, scope: SalesScope) -> OrderRules: ...


# -------------------------------------------------------- the worker side --


class OutboundScopesPort(Protocol):
    async def scopes(self) -> Sequence[SalesScope]: ...


class QuoteSentPort(Protocol):
    """ "Đã gửi KH" and "Đã gửi Design", as the person who pressed
    (`QuoteCommands.sent`, `QuoteCommands.design_sent`)."""

    async def sent(
        self, context: AccessContext, case_id: uuid.UUID, *, case_version: int
    ) -> object: ...

    async def design_sent(
        self, context: AccessContext, case_id: uuid.UUID, *, case_version: int
    ) -> object: ...


class AnswerSentPort(Protocol):
    """ "Ghi đã gửi khách" of a change's answer (`UpdateLoops.answer_sent`)."""

    async def answer_sent(
        self, context: AccessContext, case_id: uuid.UUID, *, case_version: int
    ) -> object: ...


class PcAskedPort(Protocol):
    """ "Ghi đã hỏi PC" as the person who pressed, from when they pressed
    (`PcRequests.ask`)."""

    async def ask(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        *,
        case_version: int,
        sent_at: datetime | None = None,
    ) -> object: ...


# The person's access when their case's step is recorded: nothing more.
_SENT_CEILING: Final = frozenset({SalesScopes.QUOTE_PREPARE.value, SalesScopes.CASE_READ.value})
_ANSWER_CEILING: Final = frozenset({SalesScopes.ORDER_PREPARE.value, SalesScopes.CASE_READ.value})

# Said of any mail DW1 sends: to the customer, Design or PC alike.
_TOLD: Final[Mapping[str, tuple[str, str]]] = {
    "not_connected": (
        "Chưa gửi được thư",
        "Hộp thư của bạn chưa được nối để DW1 gửi thư. Tải tệp .eml trong hồ sơ, gửi từ "
        "Outlook, rồi ghi đã gửi trong hồ sơ.",
    ),
    "write_failed": (
        "Chưa gửi được thư",
        "DW1 không ghi được thư vào thư mục gửi. Thử lại, hoặc gửi tệp .eml từ Outlook.",
    ),
    "flow_failed": (
        "Thư bị báo lỗi khi gửi",
        "Luồng gửi thư của bạn báo lỗi. Kiểm tra kết nối Power Automate, hoặc gửi tệp .eml "
        "từ Outlook.",
    ),
    "no_receipt": (
        "Thư chưa có xác nhận đã gửi",
        "Sau 30 phút luồng gửi thư chưa xác nhận. Xem mục Thư đã gửi trong Outlook; nếu "
        "không có, gửi tệp .eml rồi ghi đã gửi trong hồ sơ.",
    ),
}
# Said when the request went to PC and the case could not record it asked.
_PC_NOT_RECORDED: Final = (
    "Thư hỏi PC đã gửi nhưng chưa ghi được",
    'Thư đã đi nhưng hồ sơ đã đổi nên DW1 chưa ghi "đã hỏi PC". Mở hồ sơ và bấm '
    '"Ghi đã hỏi PC" nếu đơn còn chờ PC.',
)


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
    answers: AnswerSentPort
    pc: PcAskedPort
    access: RequesterAccessPort
    notifications: NotificationSenderPort
    clock: UtcClock
    ids: IdGenerator

    async def tick(self) -> OutboundTick:
        settled = 0
        for receipt in self.outbox.receipts():
            # One folder and one flow serve every context: a receipt for a
            # job not DW1's is left for the lane whose job it is.
            if parse_job_name(receipt.name) is None:
                continue
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
        if not done:
            return done
        async with self.uow(scope) as work:
            record = await work.artifacts.get(mail.artifact_id)
        kind = None if record is None else record.kind
        if mail.case_kind is CaseKind.QUOTE and kind in ("send_draft", "design_request_draft"):
            await self._mark_sent(scope, mail, design=kind == "design_request_draft")
        elif mail.case_kind is CaseKind.ORDER and kind in _ANSWERS:
            await self._mark_answer_sent(scope, mail)
        elif mail.case_kind is CaseKind.ORDER and kind == "pc_request_draft":
            await self._mark_pc_asked(scope, mail)
        return done

    async def _mark_pc_asked(self, scope: SalesScope, mail: OutboundMail) -> None:
        """ "Ghi đã hỏi PC" as the person who pressed, from when they pressed
        (the mail's `queued_at`, so a reply PC wrote before the receipt came
        back still answers it). A case that already says so since the press
        (asked again by hand, or every line it would ask answered) is left as
        it is (`OrderCase.pc_asked_since`). A case that cannot take it any
        more (in Bravo meanwhile) is left, and the person is told: the mail
        went, and the case does not say so."""
        access = await self.access.find_linked_access(
            mail.requested_by, scope.tenant_id.value, scope.workspace_id.value, _ANSWER_CEILING
        )
        if access is None:
            return
        context = context_from(access)
        try:
            async with self.uow(scope) as work:
                case = (await stored_order(work, mail.case_id, viewer=context)).case
            if case.pc_asked_since(mail.queued_at):
                return
            await self.pc.ask(
                context, mail.case_id, case_version=case.case_version, sent_at=mail.queued_at
            )
        except (ConflictError, NotFoundError) as left:
            logger.info("sales_outbound: a request to PC was not recorded: %s", type(left).__name__)
            await self._tell(scope, mail, "pc_not_recorded", _PC_NOT_RECORDED)

    async def _mark_answer_sent(self, scope: SalesScope, mail: OutboundMail) -> None:
        """ "Ghi đã gửi khách" of a change's answer as the person who pressed;
        a case that moved on meanwhile (recorded by hand) is left."""
        access = await self.access.find_linked_access(
            mail.requested_by, scope.tenant_id.value, scope.workspace_id.value, _ANSWER_CEILING
        )
        if access is None:
            return
        context = context_from(access)
        try:
            async with self.uow(scope) as work:
                case = (await stored_order(work, mail.case_id, viewer=context)).case
            await self.answers.answer_sent(context, mail.case_id, case_version=case.case_version)
        except (ConflictError, NotFoundError) as left:
            logger.info("sales_outbound: a sent answer was not recorded: %s", type(left).__name__)

    async def _mark_sent(self, scope: SalesScope, mail: OutboundMail, *, design: bool) -> None:
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
            record = self.quotes.design_sent if design else self.quotes.sent
            await record(context, mail.case_id, case_version=case.case_version)
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
            await self._tell(scope, mail, status, _TOLD[error])
        return 1

    async def _tell(
        self, scope: SalesScope, mail: OutboundMail, what: str, words: tuple[str, str]
    ) -> None:
        title, body = words
        try:
            await self.notifications.deliver(
                _lane_context(scope),
                recipients=[mail.requested_by],
                source_key=f"{SALES_OUTBOUND_LANE}:{mail.mail_id}:{what}",
                title=title,
                body=body,
                link=f"/sales/{mail.case_kind.value}s/{mail.case_id}",
            )
        except Exception:
            logger.exception("sales_outbound: the person was not told")
