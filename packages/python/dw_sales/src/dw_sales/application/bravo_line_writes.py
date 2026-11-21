"""A sales order line's change, written into Bravo under the approving PIC's
own Bravo user (ticket 53, ADR 0027).

**Proposed** (`BravoLineWrites.propose`): the change of one line of a case's
sales order, its confirmed date ("XN giao hàng") or its quantity, as the PIC
asks on the case page or the case assistant proposes it (ticket 56). DW
reads the SO from Bravo through the gateway (`so.by_number`), finds the one
Bravo row for the PO line, and builds the typed command with the row's
rowversion as read: a line changed in Bravo since is refused by the gateway.
A line Bravo holds as several rows (split) is not proposed: which row is a
split's is the split's own write, not yet traced (script 03c). The proposal
opens a platform approval, `bravo_write.sales_order`, carrying the exact
command, its hash, and Bravo's value beside the new one.

**Decided by one person, the one whose name goes on the save**
(`BravoWriteDecisions`, `BravoWriteStamp`). ADR 0027: "the PIC approves the
exact content on the portal", and the write is that person's own, under
their Bravo user, as when they type it into Bravo today. So the type is not
under `sales.`, whose approvals want a second person who made none of the
case: the PIC may approve their own proposal. What stops a wrong write is
the approver's own Bravo user and rights, checked by the gateway at the
write, and the kind's switch, off until UAT proof (ticket 63 g). On
approval, in the decision's transaction, the stamp resolves the decider's
employee code (ticket 64), asks Bravo for its one active user, and signs
the approval token. Any of those missing refuses the decision: nothing is
recorded, and the person is told why.

**Carried out** by the worker (`BravoWriteSettlement`): the decision's event
carries the token; the gateway's answer is recorded on the proposal and the
decider is told. A transport failure is retried; a refusal after one is
recorded as in doubt, since the gateway may have written before its answer
was lost.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from types import TracebackType
from typing import Annotated, Any, Final, Literal, Protocol, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from dw_agent_runtime.approval_flow import ProposedDecision
from dw_kernel.errors import ConflictError, NotFoundError, PermissionDeniedError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ApprovalAudience
from dw_platform.application.ports import AuditRepositoryPort
from dw_platform.domain.approval import ApprovalRequest, ApprovalStatus, decided_event_type
from dw_platform.domain.audit import AuditEvent
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.case_store import (
    STALE_CASE_VERSION,
    OrderCaseStorePort,
    RunLessApprovalsPort,
)
from dw_sales.application.ports import NotificationSenderPort, SalesScope

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

BRAVO_WRITE_APPROVAL: Final = "bravo_write.sales_order"
BRAVO_WRITE_DECIDED: Final = decided_event_type(BRAVO_WRITE_APPROVAL)
_REASON: Final = "Ghi thay đổi dòng SO vào Bravo, dưới user Bravo của người duyệt"

WriteStatus = Literal[
    "proposed", "rejected", "written", "written_with_differences", "refused", "in_doubt"
]
OPEN: Final = frozenset({"proposed"})


class BravoUnreachableError(Exception):
    """The gateway, or Bravo behind it, did not answer: nothing is decided."""


# ------------------------------------------------------------------ the change


class ConfirmedDateChange(BaseModel):
    """ "XN giao hàng": the line's confirmed delivery date."""

    model_config = _FROZEN

    field: Literal["confirmed_date"]
    value: date


class QuantityChange(BaseModel):
    """The line's quantity, in the sales unit Bravo's `Quantity9` holds."""

    model_config = _FROZEN

    field: Literal["quantity"]
    value: Decimal = Field(gt=0, max_digits=18, decimal_places=4)


LineChange = Annotated[ConfirmedDateChange | QuantityChange, Field(discriminator="field")]


def _text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


@dataclass(frozen=True)
class BravoSoLine:
    """One row of an SO's lines as Bravo holds it (`B30BizDocDetailSO`):
    `quantity` is `Quantity9`, `confirmed_date` `EstimatedTimeDelivery`."""

    line_id: int
    po_line: int
    item_code: str
    quantity: Decimal
    confirmed_date: date | None
    rowversion: str


@dataclass(frozen=True)
class BravoSo:
    so_id: int
    so_no: str
    lines: tuple[BravoSoLine, ...]


@dataclass(frozen=True)
class PreparedWrite:
    """A change as the gateway's contract types it: the kind (`kind@version`),
    the content both sides hash, its hash, and why the gateway would not run
    the kind yet (None: it runs it)."""

    kind: str
    content: dict[str, Any]
    content_hash: str
    pending: str | None = None


class BravoCommandsPort(Protocol):
    """The gateway's contract, owned by `dw_bravo.contract` and reached
    through an adapter (import-linter: a context's application never imports
    it)."""

    def prepare(
        self, change: ConfirmedDateChange | QuantityChange, so: BravoSo, line: BravoSoLine
    ) -> PreparedWrite: ...

    def hash_of(self, kind: str, content: dict[str, Any]) -> str:
        """The content's hash, once it reads back as a command of ``kind``;
        `ConflictError` when it does not."""
        ...


class ApprovalSignerPort(Protocol):
    """Signs the approval token the gateway trusts (`dw_bravo.approval_token`)."""

    def sign(
        self,
        *,
        approval_id: uuid.UUID,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        kind: str,
        content: dict[str, Any],
        bravo_user_id: int,
        employee_code: str,
        now: datetime,
    ) -> str: ...


def before_value(change: ConfirmedDateChange | QuantityChange, line: BravoSoLine) -> str | None:
    """Bravo's value the change replaces, as text. Refuses a change Bravo
    already holds."""
    held: object = line.confirmed_date if change.field == "confirmed_date" else line.quantity
    if held == change.value:
        raise ConflictError(
            "Bravo đã giữ giá trị này cho dòng: không có gì để ghi",
            details={"field": change.field, "rule": "nothing_to_write"},
        )
    return _text(held)


# ------------------------------------------------------------------- records


class BravoWriteAsked(BaseModel):
    """The approval's payload: the exact command decided on, its hash, and
    what a person reads to decide (the line, Bravo's value and the new one).
    `makers` is empty: the type is decided by one person (module docstring)."""

    model_config = _FROZEN

    approval_type: Literal["bravo_write.sales_order"]
    makers: tuple[uuid.UUID, ...] = ()
    case_id: uuid.UUID
    line_no: int = Field(ge=1, le=99_999)
    so_no: str = Field(min_length=1, max_length=64)
    item_code: str = Field(max_length=64)
    field: Literal["confirmed_date", "quantity"]
    before: str | None = Field(default=None, max_length=64)
    after: str = Field(max_length=64)
    kind: str = Field(max_length=64)
    command: dict[str, Any]
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    required_scope: Literal["sales.bravo.write"]


class BravoLineWrite(BaseModel):
    """One proposal and, once decided and carried out, what Bravo said."""

    model_config = _FROZEN

    approval_id: uuid.UUID
    case_id: uuid.UUID
    line_no: int = Field(ge=1, le=99_999)
    so_no: str
    item_code: str
    field: Literal["confirmed_date", "quantity"]
    before: str | None
    after: str
    kind: str
    command: dict[str, Any]
    content_hash: str
    status: WriteStatus = "proposed"
    check: str | None = None
    reason: str | None = Field(default=None, max_length=500)
    warnings: tuple[str, ...] = ()
    transport_failures: int = Field(default=0, ge=0)
    proposed_by: uuid.UUID
    proposed_at: AwareDatetime
    decided_by: uuid.UUID | None = None
    settled_at: AwareDatetime | None = None

    def asked(self) -> BravoWriteAsked:
        return BravoWriteAsked(
            approval_type=BRAVO_WRITE_APPROVAL,
            case_id=self.case_id,
            line_no=self.line_no,
            so_no=self.so_no,
            item_code=self.item_code,
            field=self.field,
            before=self.before,
            after=self.after,
            kind=self.kind,
            command=self.command,
            content_hash=self.content_hash,
            required_scope=SalesScopes.BRAVO_WRITE.value,
        )


class BravoLineWriteView(BaseModel):
    model_config = _FROZEN

    approval_id: uuid.UUID
    line_no: int
    field: Literal["confirmed_date", "quantity"]
    before: str | None
    after: str
    status: WriteStatus
    reason: str | None
    warnings: tuple[str, ...]
    proposed_at: AwareDatetime
    settled_at: AwareDatetime | None

    @classmethod
    def of(cls, write: BravoLineWrite) -> BravoLineWriteView:
        return cls(
            approval_id=write.approval_id,
            line_no=write.line_no,
            field=write.field,
            before=write.before,
            after=write.after,
            status=write.status,
            reason=write.reason,
            warnings=write.warnings,
            proposed_at=write.proposed_at,
            settled_at=write.settled_at,
        )


# --------------------------------------------------------------------- ports


class BravoLineWriteStorePort(Protocol):
    async def get(self, approval_id: uuid.UUID) -> BravoLineWrite | None: ...

    async def add(self, write: BravoLineWrite) -> None:
        """`ConflictError` while another proposal for the line is open."""
        ...

    async def save(self, write: BravoLineWrite, *, expected: WriteStatus) -> None:
        """`ConflictError` when the row is no longer ``expected``."""
        ...

    async def of_case(self, case_id: uuid.UUID) -> Sequence[BravoLineWrite]: ...


class BravoWriteWork(Protocol):
    """The part of Sales' unit of work these steps use."""

    @property
    def orders(self) -> OrderCaseStorePort: ...

    @property
    def approvals(self) -> RunLessApprovalsPort: ...

    @property
    def bravo_writes(self) -> BravoLineWriteStorePort: ...

    @property
    def audit(self) -> AuditRepositoryPort: ...

    async def commit(self) -> None: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...


class BravoWriteWorkFactory(Protocol):
    def __call__(self, scope: SalesScope) -> BravoWriteWork: ...


class BravoOrdersPort(Protocol):
    async def sales_order(self, tenant_id: uuid.UUID, so_no: str) -> BravoSo | None:
        """None when Bravo holds no SO by that number; `ConflictError` when it
        holds several; `BravoUnreachableError` when it was not asked."""
        ...


class BravoUsersPort(Protocol):
    async def bravo_user_ids(self, tenant_id: uuid.UUID, employee_code: str) -> tuple[int, ...]:
        """The active Bravo users carrying the code; `BravoUnreachableError`."""
        ...


class EmployeeCodesPort(Protocol):
    async def employee_code(self, tenant_id: uuid.UUID, subject: uuid.UUID) -> str | None:
        """The person's live link (ticket 64), or None."""
        ...


@dataclass(frozen=True)
class GatewayAnswer:
    outcome: str
    check: str | None = None
    reason: str | None = None
    warnings: tuple[str, ...] = ()
    differences: tuple[str, ...] = ()


class BravoGatewayPort(Protocol):
    async def write(self, kind: str, content: dict[str, Any], token: str) -> GatewayAnswer:
        """The gateway's answer; `BravoUnreachableError` when none came."""
        ...


class BravoNotConnected:
    """Every Bravo port, where no gateway is configured: a read could not
    ask (a proposal and a decision are refused), and a decided write is
    refused with that reason, never left waiting."""

    async def sales_order(self, tenant_id: uuid.UUID, so_no: str) -> BravoSo | None:
        raise BravoUnreachableError("no Bravo gateway is configured")

    async def bravo_user_ids(self, tenant_id: uuid.UUID, employee_code: str) -> tuple[int, ...]:
        raise BravoUnreachableError("no Bravo gateway is configured")

    async def write(self, kind: str, content: dict[str, Any], token: str) -> GatewayAnswer:
        return GatewayAnswer("refused", None, "no_bravo_gateway_configured")

    def prepare(
        self, change: ConfirmedDateChange | QuantityChange, so: BravoSo, line: BravoSoLine
    ) -> PreparedWrite:
        raise ConflictError("Bravo is not connected")

    def hash_of(self, kind: str, content: dict[str, Any]) -> str:
        raise ConflictError("Bravo is not connected")


# ------------------------------------------------------------------ proposing


@dataclass(frozen=True)
class BravoLineWrites:
    uow: BravoWriteWorkFactory
    gate: Gate
    orders: BravoOrdersPort
    commands: BravoCommandsPort
    clock: UtcClock
    ids: IdGenerator

    async def propose(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        line_no: int,
        change: ConfirmedDateChange | QuantityChange,
        *,
        case_version: int,
    ) -> BravoLineWriteView:
        await self.gate.require(
            context,
            SalesScopes.CASE_READ,
            SalesScopes.BRAVO_WRITE,
            resource_type="sales_order_case",
            resource_id=str(case_id),
        )
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            stored = await work.orders.get(case_id)
        if stored is None:
            raise NotFoundError("no such order case", details={"case_id": str(case_id)})
        case = stored.case
        if case.case_version != case_version:
            raise ConflictError(STALE_CASE_VERSION, details={"rule": "stale_case_version"})
        if line_no not in {line.line_no for line in case.lines}:
            raise NotFoundError("no such line", details={"line_no": line_no})
        if case.bravo_so_no is None:
            raise ConflictError(
                "đơn chưa có số SO Bravo: chưa ghi được",
                details={"case_id": str(case_id), "rule": "no_bravo_so"},
            )
        try:
            so = await self.orders.sales_order(context.tenant_id, case.bravo_so_no)
        except BravoUnreachableError:
            raise ConflictError("chưa đọc được Bravo: thử lại sau") from None
        if so is None:
            raise ConflictError("Bravo không có SO số này", details={"so_no": case.bravo_so_no})
        rows = [row for row in so.lines if row.po_line == line_no]
        if len(rows) != 1:
            raise ConflictError(
                "dòng PO này không ứng với đúng một dòng SO trong Bravo",
                details={"bravo_rows": len(rows), "rule": "one_bravo_row"},
            )
        before = before_value(change, rows[0])
        prepared = self.commands.prepare(change, so, rows[0])
        if prepared.pending is not None:
            raise ConflictError(
                "loại ghi này chưa chạy được",
                details={"kind": prepared.kind, "pending": prepared.pending},
            )
        approval_id, now = self.ids.new_uuid(), self.clock.now()
        write = BravoLineWrite(
            approval_id=approval_id,
            case_id=case_id,
            line_no=line_no,
            so_no=so.so_no,
            item_code=rows[0].item_code,
            field=change.field,
            before=before,
            after=str(_text(change.value)),
            kind=prepared.kind,
            command=prepared.content,
            content_hash=prepared.content_hash,
            proposed_by=context.principal_id,
            proposed_at=now,
        )
        async with self.uow(scope) as work:
            await work.approvals.add(
                ApprovalRequest(
                    id=approval_id,
                    tenant_id=TenantId(context.tenant_id),
                    workspace_id=WorkspaceId(context.workspace_id),
                    approval_type=BRAVO_WRITE_APPROVAL,
                    requested_by=UserId(context.principal_id),
                    reason=_REASON,
                    payload=write.asked().model_dump(mode="json"),
                    required_scope=SalesScopes.BRAVO_WRITE.value,
                )
            )
            await work.bravo_writes.add(write)
            await work.audit.append(
                _audit(self.ids, context, "sales.bravo_write.proposed", write, now)
            )
            await work.commit()
        return BravoLineWriteView.of(write)

    async def of_case(
        self, context: AccessContext, case_id: uuid.UUID
    ) -> Sequence[BravoLineWriteView]:
        await self.gate.require(
            context,
            SalesScopes.CASE_READ,
            resource_type="sales_order_case",
            resource_id=str(case_id),
        )
        async with self.uow(sales_scope(context)) as work:
            return [BravoLineWriteView.of(w) for w in await work.bravo_writes.of_case(case_id)]


# ------------------------------------------------------------------ deciding


def asked_of(request: ApprovalRequest) -> BravoWriteAsked:
    """The approval as a proposal opened it, or a refusal."""
    if request.approval_type != BRAVO_WRITE_APPROVAL:
        raise ConflictError(
            "the approval is not a Bravo write", details={"approval_id": str(request.id)}
        )
    try:
        asked = BravoWriteAsked.model_validate(request.payload)
    except ValidationError:
        raise ConflictError(
            "the approval is not one a Bravo write proposal opened",
            details={"approval_id": str(request.id)},
        ) from None
    if request.required_scope != SalesScopes.BRAVO_WRITE.value:
        raise PermissionDeniedError(
            "a Bravo write is decided with sales.bravo.write",
            details={"approval_type": request.approval_type},
        )
    return asked


@dataclass(frozen=True)
class BravoWriteDecisions:
    """`ApprovalDecisionGuard` for `bravo_write.sales_order`: the proposal is
    still open, and is the one the approval names."""

    uow: BravoWriteWorkFactory

    async def check(
        self, request: ApprovalRequest, decision: ProposedDecision, context: AccessContext
    ) -> None:
        asked = asked_of(request)
        async with self.uow(sales_scope(context)) as work:
            write = await work.bravo_writes.get(request.id)
        if write is None or write.case_id != asked.case_id:
            raise NotFoundError("no such Bravo write", details={"approval_id": str(request.id)})
        if write.status != "proposed" or write.content_hash != asked.content_hash:
            raise ConflictError(
                "đề xuất ghi Bravo không còn chờ quyết định này",
                details={"status": write.status, "rule": "decision_stale"},
            )


@dataclass(frozen=True)
class BravoWriteStamp:
    """`ApprovalDecisionStamp` for `bravo_write.sales_order`: the token the
    gateway trusts, signed for the decider's own Bravo user. Without a
    signing key, an employee code or exactly one active Bravo user, the
    decision is refused (fail closed)."""

    signer: ApprovalSignerPort | None
    commands: BravoCommandsPort
    codes: EmployeeCodesPort
    users: BravoUsersPort
    clock: UtcClock

    async def stamp(
        self, request: ApprovalRequest, decision: object, context: AccessContext
    ) -> dict[str, object]:
        asked = asked_of(request)
        if self.signer is None:
            raise ConflictError(
                "DW chưa có khoá ký phê duyệt ghi Bravo: chưa duyệt được",
                details={"rule": "no_signing_key"},
            )
        if self.commands.hash_of(asked.kind, asked.command) != asked.content_hash:
            raise ConflictError("lệnh ghi Bravo không khớp với nội dung đã đề xuất")
        code = await self.codes.employee_code(context.tenant_id, context.principal_id)
        if code is None:
            raise ConflictError(
                "tài khoản của bạn chưa liên kết mã nhân viên: nhờ quản trị liên kết rồi duyệt lại",
                details={"rule": "no_employee_code"},
            )
        try:
            users = await self.users.bravo_user_ids(context.tenant_id, code)
        except BravoUnreachableError:
            raise ConflictError("chưa hỏi được Bravo: thử lại sau") from None
        if len(users) != 1:
            raise ConflictError(
                "mã nhân viên của bạn không ứng với đúng một user Bravo đang hoạt động",
                details={"active_bravo_users": len(users), "rule": "one_bravo_user"},
            )
        token = self.signer.sign(
            approval_id=request.id,
            tenant_id=context.tenant_id,
            workspace_id=context.workspace_id,
            kind=asked.kind,
            content=asked.command,
            bravo_user_id=users[0],
            employee_code=code,
            now=self.clock.now(),
        )
        return {"token": token}


# ----------------------------------------------------------------- carrying out

_OUTCOMES: Final[dict[str, WriteStatus]] = {
    "written": "written",
    "already_written": "written",
    "written_with_differences": "written_with_differences",
    "refused": "refused",
    "in_doubt": "in_doubt",
}
_TOLD: Final[dict[WriteStatus, str]] = {
    "written": "Đã ghi vào Bravo",
    "written_with_differences": "Đã ghi vào Bravo, nhưng đọc lại thấy khác",
    "refused": "Bravo chưa nhận thay đổi",
    "in_doubt": "Chưa rõ đã ghi vào Bravo chưa: kiểm tra trong Bravo",
    "rejected": "Đã từ chối ghi vào Bravo",
}


@dataclass(frozen=True)
class BravoWriteSettlement:
    """Carries out a decided `bravo_write.sales_order` approval: the worker's
    handler calls it with the decider's tenancy and identity and the token
    the decision signed, from the event."""

    uow: BravoWriteWorkFactory
    gateway: BravoGatewayPort
    notices: NotificationSenderPort
    clock: UtcClock
    ids: IdGenerator

    async def settle(
        self, approval_id: uuid.UUID, decider: AccessContext, token: str | None
    ) -> WriteStatus:
        """Idempotent: a proposal already settled is left as it is. Raises
        `BravoUnreachableError` for the worker to retry."""
        audience = ApprovalAudience(
            context=decider.model_copy(
                update={"scopes": frozenset({SalesScopes.BRAVO_WRITE.value})}
            ),
            holds_decide=True,
        )
        scope = sales_scope(decider)
        async with self.uow(scope) as work:
            request = await work.approvals.get(
                approval_id, workspace_id=decider.workspace_id, audience=audience
            )
            if request is None:
                raise NotFoundError("Bravo write approval not found")
            asked = asked_of(request)
            write = await work.bravo_writes.get(approval_id)
        if write is None or write.content_hash != asked.content_hash:
            raise NotFoundError("no such Bravo write", details={"approval_id": str(approval_id)})
        if write.status != "proposed":
            return write.status
        if request.status is ApprovalStatus.PENDING:
            raise ConflictError("the Bravo write is not decided yet")
        now = self.clock.now()
        if request.status is not ApprovalStatus.APPROVED:
            done = write.model_copy(
                update={"status": "rejected", "decided_by": decider.principal_id, "settled_at": now}
            )
        elif token is None:
            done = write.model_copy(
                update={
                    "status": "refused",
                    "check": "token",
                    "reason": "no_token_on_the_decision",
                    "decided_by": decider.principal_id,
                    "settled_at": now,
                }
            )
        else:
            done = await self._send(write, token, decider, now)
        async with self.uow(scope) as work:
            await work.bravo_writes.save(done, expected="proposed")
            await work.audit.append(
                _audit(self.ids, decider, f"sales.bravo_write.{done.status}", done, now)
            )
            await work.commit()
        await self.notices.deliver(
            decider,
            recipients=[decider.principal_id],
            source_key=f"sales.bravo_write:{approval_id}",
            title=_TOLD[done.status],
            body=f"SO {done.so_no}, dòng {done.line_no}: {done.after}"
            + (f" ({done.reason})" if done.reason else ""),
            link=f"/sales/orders/{done.case_id}",
        )
        return done.status

    async def _send(
        self, write: BravoLineWrite, token: str, decider: AccessContext, now: datetime
    ) -> BravoLineWrite:
        try:
            answer = await self.gateway.write(write.kind, write.command, token)
        except BravoUnreachableError:
            async with self.uow(sales_scope(decider)) as work:
                await work.bravo_writes.save(
                    write.model_copy(update={"transport_failures": write.transport_failures + 1}),
                    expected="proposed",
                )
                await work.commit()
            raise
        status = _OUTCOMES.get(answer.outcome, "in_doubt")
        reason = answer.reason
        if status == "refused" and write.transport_failures > 0:
            # An earlier send's answer was lost: the gateway may have written
            # then, and refuses now (an expired token, the ledger's claim).
            status, reason = "in_doubt", f"{answer.reason} after a lost answer"
        return write.model_copy(
            update={
                "status": status,
                "check": answer.check,
                "reason": None if reason is None else reason[:500],
                "warnings": answer.warnings + answer.differences,
                "decided_by": decider.principal_id,
                "settled_at": now,
            }
        )


def _audit(
    ids: IdGenerator, context: AccessContext, action: str, write: BravoLineWrite, at: datetime
) -> AuditEvent:
    return AuditEvent(
        id=ids.new_uuid(),
        tenant_id=TenantId(context.tenant_id),
        workspace_id=WorkspaceId(context.workspace_id),
        actor_id=UserId(context.principal_id),
        action=action,
        resource_type="sales_bravo_line_write",
        resource_id=str(write.approval_id),
        occurred_at=at,
        details={
            "case_id": str(write.case_id),
            "line_no": write.line_no,
            "kind": write.kind,
            "content_hash": write.content_hash,
            "status": write.status,
            **({"check": write.check} if write.check else {}),
        },
    )


__all__ = [
    "BRAVO_WRITE_APPROVAL",
    "BRAVO_WRITE_DECIDED",
    "ApprovalSignerPort",
    "BravoCommandsPort",
    "BravoGatewayPort",
    "BravoLineWrite",
    "BravoLineWriteStorePort",
    "BravoLineWriteView",
    "BravoLineWrites",
    "BravoNotConnected",
    "BravoOrdersPort",
    "BravoSo",
    "BravoSoLine",
    "BravoUnreachableError",
    "BravoUsersPort",
    "BravoWriteAsked",
    "BravoWriteDecisions",
    "BravoWriteSettlement",
    "BravoWriteStamp",
    "ConfirmedDateChange",
    "EmployeeCodesPort",
    "GatewayAnswer",
    "LineChange",
    "PreparedWrite",
    "QuantityChange",
    "before_value",
]
