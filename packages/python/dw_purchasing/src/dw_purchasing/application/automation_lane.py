"""DW2 takes each step on its own as far as the tenant's switches let it: the
worker's `purchasing_automation` lane (Đạt, 2026-11-01).

**Whose authority.** DW2's own service account in the tenant, "DW2 (tài khoản
dịch vụ)": a platform user (`dw2_subject`) whose membership holds the role
`purchasing_dw2`, resolved by the platform like any member and cut to the
scopes the lane needs (`LANE_CEILING`): it reads and receives requests,
sends them to their approver, drafts RFQs and orders. It decides nothing an
approver decides, sends no mail and records nothing in Bravo. No account, a
locked tenant, or a context for another workspace: the lane does nothing.

**One tick, per workspace with work** (its mailbox, or a case waiting on a
step), each step at the level the switch puts it at now
(`SwitchesService.level`: the level set, held to its ceiling, `ai_auto` only
once its model reading is measured):

1. **New mail** (`mail_sorting`, `pr_drafting`): at "Người làm" the buyers
   are told a mail arrived; otherwise DW2 reads it, through the door "DW2
   đọc" uses. At "AI làm, người duyệt" the case it opens waits for a person
   to look it over (`Review`); a mail that is no request goes to a person
   with its reason, and the buyers are told. The model down ends the mail
   for this tick: nothing is guessed, the next tick tries again.
2. **Received cases** (`submission`): at "AI tự làm" a case nobody still has
   to look over is sent to the approver its amount names; at "AI làm, người
   duyệt" the buyers are told it is ready to send.
3. **Approved cases** (`rfq`): at "AI làm, người duyệt" the RFQs are drafted
   and the buyers told to send them. Nothing is sent.
4. **Suppliers chosen** (`po_drafting`): at "AI tự làm" the orders and the
   Bravo file are drafted and the buyers told to import it; at "AI làm,
   người duyệt" they are told to draft it.

A step that refuses (no limits in the rules, a stand-in Bravo layout, a
supplier gone) is told to the buyers once with the refusal's own words,
never retried into a loop of notices. Every notice is once per case and
step (its source key).

**It audits as itself.** Each thing it did is one `lane_audit_event` from
`system_actor(LANE)`, naming the account it acted under; the services' own
rows name the account, never a person.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Protocol

from dw_kernel.errors import ConflictError, DomainError, InfrastructureError, NotFoundError
from dw_kernel.ids import TenantId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.identity import MembershipAccess, context_from, service_subject
from dw_platform.application.provisioning import ServiceAccount
from dw_platform.domain.audit import lane_audit_event
from dw_purchasing.application.access import PurchasingScopes
from dw_purchasing.application.ports import Disposition, NoticesPort, PurchasingUnitOfWork
from dw_purchasing.application.services import PurchasingServices
from dw_purchasing.domain.automation import AutomationLevel, AutomationStep
from dw_purchasing.domain.cases import CaseStatus, PurchaseCase
from dw_purchasing.domain.checks import MasterData

_LOG = logging.getLogger("dw_purchasing.automation")

LANE: Final = "purchasing_automation"
DW2_WORKER_ID: Final = "purchasing-dw2"
DW2_ROLE: Final = "purchasing_dw2"
DW2_SERVICE_ACCOUNT: Final = ServiceAccount(
    worker_id=DW2_WORKER_ID, display_name="DW2 (tài khoản dịch vụ)", role_keys=(DW2_ROLE,)
)
# What the lane does, and so all a context it acts under carries.
LANE_CEILING: Final = frozenset(
    {
        PurchasingScopes.REQUEST_READ.value,
        PurchasingScopes.REQUEST_INTAKE.value,
        PurchasingScopes.REQUEST_SUBMIT.value,
        PurchasingScopes.RFQ_PREPARE.value,
        PurchasingScopes.PO_PREPARE.value,
    }
)
# The most of each kind one tick takes, so a backlog is worked through over
# ticks rather than in one long transaction-free burst.
PER_TICK: Final = 20

# Why a mail goes to a person, as the buyers read it: CONTEXT.md's "Mail
# reasons" line, word for word (test_purchasing_screen_words.py).
_MAIL_REASONS: Final = {
    "sender_not_internal": "người gửi không thuộc công ty",
    "sender_unverified": "hệ thống thư không xác thực được người gửi",
    "no_pr_number": "thư không có số yêu cầu mua hàng",
    "no_department": "thư không nói bộ phận yêu cầu",
    "span_not_found": "DW2 đọc ra một giá trị không có trong thư",
    "line_unreadable": "DW2 không đọc trọn được một dòng hàng",
    "currency_unreadable": "không rõ đơn vị tiền",
    "need_by_unreadable": "không đọc được ngày cần hàng",
    "value_malformed": "một giá trị trong thư không đúng dạng",
    "no_lines": "thư không có dòng hàng nào",
    "too_many_lines": "thư có nhiều dòng hàng hơn quy tắc cho phép",
    "currency_not_allowed": "loại tiền quy tắc không cho phép",
}


def dw2_subject(tenant_id: uuid.UUID) -> str:
    """DW2's service account in one tenant: the subject its platform user has."""
    return service_subject(DW2_WORKER_ID, tenant_id)


def mail_reason(reason: str | None) -> str:
    if reason is None:
        return "không rõ lý do"
    if reason.startswith("missing:"):
        return f"thiếu {reason.removeprefix('missing:')} mà quy tắc của công ty đòi hỏi"
    return _MAIL_REASONS.get(reason, reason)


class ServiceAccessPort(Protocol):
    """A service account's access in one workspace, cut to a ceiling, as the
    platform resolves any member's (`SqlMembershipLookup.find_service_access`)."""

    async def find_service_access(
        self,
        subject: str,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        ceiling: frozenset[str],
    ) -> MembershipAccess | None: ...


class AutomationScopesPort(Protocol):
    """Every workspace with a case waiting on a step DW2 may take, ids only,
    across tenants (`purchasing.automation_scopes_due`)."""

    async def due(self) -> Sequence[tuple[uuid.UUID, uuid.UUID]]: ...


@dataclass(frozen=True, slots=True)
class Tick:
    """What one tick did, for the log: ids and codes only."""

    done: tuple[str, ...] = ()


@dataclass(frozen=True)
class AutomationLane:
    access: ServiceAccessPort
    scopes: AutomationScopesPort
    # The workspaces whose mailbox this host reads.
    mailboxes: tuple[tuple[uuid.UUID, uuid.UUID], ...]
    services: PurchasingServices
    uow: PurchasingUnitOfWork
    notices: NoticesPort
    clock: UtcClock
    ids: IdGenerator

    async def due(self) -> list[tuple[uuid.UUID, uuid.UUID]]:
        found = {*self.mailboxes, *await self.scopes.due()}
        return sorted(found, key=lambda s: (str(s[0]), str(s[1])))

    async def tick(self, tenant_id: uuid.UUID, workspace_id: uuid.UUID) -> Tick:
        access = await self.access.find_service_access(
            dw2_subject(tenant_id), tenant_id, workspace_id, LANE_CEILING
        )
        if access is None:
            return Tick(("no DW2 account",))
        context = context_from(access)
        if (context.tenant_id, context.workspace_id) != (tenant_id, workspace_id):
            return Tick(("account of another workspace",))
        done: list[str] = []
        if (tenant_id, workspace_id) in self.mailboxes:
            done += await self._mail(context)
        done += await self._submissions(context)
        done += await self._rfqs(context)
        done += await self._orders(context)
        return Tick(tuple(done))

    # ---------------------------------------------------------- the steps --

    async def _level(self, context: AccessContext, step: AutomationStep) -> AutomationLevel:
        return (await self.services.switches.level(context, step)).level

    async def _mail(self, context: AccessContext) -> list[str]:
        if await self._level(context, AutomationStep.MAIL_SORTING) is AutomationLevel.PERSON:
            return []
        drafting = await self._level(context, AutomationStep.PR_DRAFTING)
        unread = [m for m in await self.services.requests.mailbox(context) if m.disposition is None]
        master = await self.services.approvals.master.for_context(context)
        done: list[str] = []
        for item in unread[:PER_TICK]:
            message = await self.services.requests.inbox.get_message(context, item.message_id)
            verified = message is not None and message.authentication.verified
            supplier = _supplier_of(master, item.sender) if verified else None
            if supplier is not None:
                # A known supplier's mail, its sender verified by the mail
                # system: a quote, a confirmation or a question about an
                # order, never read as a request, and left for the buyer to
                # tie to its case (step 6 is not automated). An unverified one
                # is read as any mail is, and goes to a person.
                await self._tell(
                    context,
                    PurchasingScopes.RFQ_PREPARE,
                    f"purchasing.mail.supplier:{item.message_id}",
                    f"Thư của nhà cung cấp {supplier}: {item.subject}",
                    "Mở hồ sơ đang hỏi giá của nhà cung cấp này để DW2 đọc báo giá trong thư.",
                    "/purchasing/mail",
                )
                continue
            if drafting is AutomationLevel.PERSON:
                await self._tell(
                    context,
                    PurchasingScopes.REQUEST_INTAKE,
                    f"purchasing.mail.arrived:{item.message_id}",
                    f"Thư mới trong hộp thư Mua hàng: {item.subject}",
                    f"Từ {item.sender}. Mở hộp thư và bấm «DW2 đọc» nếu đó là yêu cầu mua hàng.",
                    "/purchasing/mail",
                )
                continue
            review = drafting is AutomationLevel.AI_REVIEW
            try:
                read = await self.services.requests.read_mail(
                    context, item.message_id, for_review=review
                )
            except InfrastructureError:
                # No model, or no usable answer: nothing guessed, the next
                # tick tries again.
                done.append("mail: model unavailable")
                break
            except ConflictError:
                continue
            await self._audit(
                context,
                "purchasing.automation.mail_read",
                item.message_id,
                {
                    "message_id": item.message_id,
                    "disposition": read.disposition.value if read.disposition else None,
                    "reason": read.reason,
                    "level": drafting.value,
                },
            )
            done.append(f"mail {item.message_id}: {read.disposition}")
            if read.disposition is Disposition.TO_PERSON:
                await self._tell(
                    context,
                    PurchasingScopes.REQUEST_INTAKE,
                    f"purchasing.mail.to_person:{item.message_id}",
                    f"Thư cần người xem: {item.subject}",
                    f"DW2 chưa mở hồ sơ vì {mail_reason(read.reason)}.",
                    "/purchasing/mail",
                )
            elif review and read.case_id is not None:
                case = await self.services.requests.case(context, read.case_id)
                await self._tell(
                    context,
                    PurchasingScopes.REQUEST_INTAKE,
                    f"purchasing.case.review:{case.case_id}",
                    f"Yêu cầu mua hàng {case.request.pr_no} DW2 đọc từ thư: xem lại",
                    "Xem lại các dòng DW2 đọc rồi bấm «Đã xem» để DW2 đi tiếp.",
                    _link(case),
                )
        return done

    async def _submissions(self, context: AccessContext) -> list[str]:
        level = await self._level(context, AutomationStep.SUBMISSION)
        if level is AutomationLevel.PERSON:
            return []
        done: list[str] = []
        for case in await self._waiting(context, CaseStatus.RECEIVED):
            if case.review is not None and case.review.pending:
                continue
            if level is AutomationLevel.AI_REVIEW:
                await self._tell(
                    context,
                    PurchasingScopes.REQUEST_SUBMIT,
                    f"purchasing.case.ready_to_submit:{case.case_id}",
                    f"Yêu cầu mua hàng {case.request.pr_no} sẵn sàng gửi duyệt",
                    "DW2 đã đối chiếu xong. Bấm «Gửi duyệt» để gửi người duyệt.",
                    _link(case),
                )
                continue
            try:
                await self.services.approvals.submit(
                    context, case.case_id, case_version=case.case_version
                )
            except (ConflictError, DomainError, NotFoundError) as refused:
                await self._refused(context, case, "submission", refused)
                continue
            await self._audit(context, "purchasing.automation.submitted", str(case.case_id), {})
            done.append(f"submitted {case.case_id}")
        return done

    async def _rfqs(self, context: AccessContext) -> list[str]:
        if await self._level(context, AutomationStep.RFQ) is AutomationLevel.PERSON:
            return []
        done: list[str] = []
        for case in await self._waiting(context, CaseStatus.APPROVED):
            try:
                await self.services.sourcing.draft_rfq(
                    context, case.case_id, case_version=case.case_version
                )
            except (ConflictError, DomainError, NotFoundError) as refused:
                await self._refused(context, case, "rfq", refused)
                continue
            await self._audit(context, "purchasing.automation.rfq_drafted", str(case.case_id), {})
            await self._tell(
                context,
                PurchasingScopes.RFQ_PREPARE,
                f"purchasing.case.rfq_drafted:{case.case_id}",
                f"Yêu cầu báo giá của {case.request.pr_no} đã soạn",
                "Xem các thư hỏi giá DW2 soạn cho từng nhà cung cấp rồi gửi đi.",
                _link(case),
            )
            done.append(f"rfq {case.case_id}")
        return done

    async def _orders(self, context: AccessContext) -> list[str]:
        level = await self._level(context, AutomationStep.PO_DRAFTING)
        if level is AutomationLevel.PERSON:
            return []
        done: list[str] = []
        for case in await self._waiting(context, CaseStatus.SUPPLIER_SELECTED):
            if level is AutomationLevel.AI_REVIEW:
                await self._tell(
                    context,
                    PurchasingScopes.PO_PREPARE,
                    f"purchasing.case.ready_for_po:{case.case_id}",
                    f"Đã chọn nhà cung cấp cho {case.request.pr_no}: soạn PO",
                    "Bấm «Soạn PO» để DW2 soạn PO nháp và file nhập Bravo.",
                    _link(case),
                )
                continue
            try:
                await self.services.orders.draft(
                    context, case.case_id, case_version=case.case_version
                )
            except (ConflictError, DomainError, NotFoundError) as refused:
                await self._refused(context, case, "po", refused)
                continue
            await self._audit(context, "purchasing.automation.po_drafted", str(case.case_id), {})
            await self._tell(
                context,
                PurchasingScopes.PO_PREPARE,
                f"purchasing.case.po_drafted:{case.case_id}",
                f"PO nháp của {case.request.pr_no} sẵn sàng",
                "Tải file nhập Bravo và nhập vào Bravo; DW2 không ghi gì vào Bravo.",
                _link(case),
            )
            done.append(f"po {case.case_id}")
        return done

    # ------------------------------------------------------------- helpers --

    async def _waiting(self, context: AccessContext, status: CaseStatus) -> Sequence[PurchaseCase]:
        async with self.uow(context) as work:
            return await work.cases.waiting(frozenset({status.value}), limit=PER_TICK)

    async def _refused(
        self, context: AccessContext, case: PurchaseCase, step: str, refused: Exception
    ) -> None:
        """A step the case refuses: told once, in the refusal's own words."""
        rule = getattr(refused, "details", {}).get("rule", type(refused).__name__)
        await self._tell(
            context,
            {
                "submission": PurchasingScopes.REQUEST_SUBMIT,
                "rfq": PurchasingScopes.RFQ_PREPARE,
                "po": PurchasingScopes.PO_PREPARE,
            }[step],
            f"purchasing.case.{step}_refused:{case.case_id}:{rule}",
            f"DW2 chưa làm tiếp được {case.request.pr_no}",
            str(getattr(refused, "message", "")) or "Bước này cần người làm.",
            _link(case),
        )
        _LOG.info("lane step %s refused for case %s: %s", step, case.case_id, rule)

    async def _tell(
        self,
        context: AccessContext,
        scope: PurchasingScopes,
        key: str,
        title: str,
        body: str,
        link: str,
    ) -> None:
        await self.notices.tell(
            context,
            scopes=frozenset({scope.value}),
            excluding=(context.principal_id,),
            source_key=key,
            title=title,
            body=body,
            link=link,
        )

    async def _audit(
        self, context: AccessContext, action: str, resource_id: str, details: dict[str, object]
    ) -> None:
        async with self.uow(context) as work:
            await work.audit.append(
                lane_audit_event(
                    lane=LANE,
                    event_id=self.ids.new_uuid(),
                    tenant_id=TenantId(context.tenant_id),
                    workspace_id=WorkspaceId(context.workspace_id),
                    action=action,
                    resource_type="purchase_case",
                    resource_id=resource_id,
                    occurred_at=self.clock.now(),
                    details={**details, "account": str(context.principal_id)},
                )
            )


def _supplier_of(master: MasterData, sender: str) -> str | None:
    """The master data's supplier a sender's domain belongs to, by name;
    None for anyone else, or when two suppliers share the domain."""
    domain = sender.rpartition("@")[2].lower()
    found = [s for s in master.suppliers if domain in s.domains]
    return found[0].name if len(found) == 1 else None


def _link(case: PurchaseCase) -> str:
    return f"/purchasing/requests/{case.case_id}"
