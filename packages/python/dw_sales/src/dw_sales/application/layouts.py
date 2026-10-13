"""Onboarding a customer's PO form (ticket 30): a person maps it, a second
person approves it, and a model may pre-fill the mapping.

`LayoutChecks.check` is the one place a mapping is judged, whoever wrote it:
every label one cell of the form, the column titles on one row, the reader
end to end with no `line_total_mismatch` and a total, and each column
plausible (`domain.layouts`). A refused check names fields, never values.

`LayoutPrefiller.prefill` asks a local model, inside the DW1 run processing a
PO no layout reads, which label names which field (label names only), and
keeps its proposal only when every check passes: the onboarding screen then
opens pre-filled; otherwise it opens empty, as without a model. Asked only
where the tenant's rules turn it on (`model_assist.layout_proposal`).

`LayoutService` is the screen's: the form's cells (with the pre-fill DW1
stamped on the message), a preview of any mapping, and the proposal a person
makes (maker). The proposal opens a platform approval, `sales.layout`, in its
own transaction (dw_sales ADR 0004: a checker's decision is a platform
approval), stamped with `sales.layout.approve` and naming the proposer as its
maker, so `sales.`'s strict rule refuses them and wants a written comment.
No run waits on it, so the decision is announced as `sales.layout.decided`
(CLAUDE.md, "Approval pauses and resumes..."):

- **before it is recorded**, `LayoutDecisions.check` (the decision guard
  registered for `sales.layout`) refuses a decision the layout would refuse:
  not proposed any more, decided on another version, or by its maker;
- **once it is recorded**, the worker hands the event to
  `LayoutSettlement.settle`, which reads the outcome from the approval row
  and applies it to the layout as the decider (the domain and a CHECK both
  refuse the maker again).

An approved layout is tenant data under row security: it is read for this
tenant's workspace only, and never committed.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Final, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dw_agent_runtime.approval_flow import ProposedDecision
from dw_agent_runtime.contracts import RunContext
from dw_kernel.errors import ConflictError, DomainError, NotFoundError, PermissionDeniedError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ApprovalAudience
from dw_platform.domain.approval import ApprovalRequest, ApprovalStatus, decided_event_type
from dw_platform.domain.audit import AuditEvent
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.model_reading import (
    InterpretationPort,
    ModelUnavailableError,
    PromptRef,
    estimated_tokens,
)
from dw_sales.application.order_ports import OrderRulesPort
from dw_sales.application.ports import InboxPort, SalesCatalogPort, SalesScope
from dw_sales.application.support import decided
from dw_sales.domain.catalog import Customer
from dw_sales.domain.layouts import (
    LayoutMapping,
    LayoutPrefill,
    LayoutSample,
    LayoutSource,
    ModelLayoutProposal,
    PoLayout,
    Problem,
    check_labels,
    form_parts,
    pdf_columns,
    plausible,
)
from dw_sales.domain.messages import AttachmentContent
from dw_sales.domain.order_checks import IntakeCaps, OrderRules, check_document
from dw_sales.domain.orders import FindingCode, PoDocument, Unreadable

# The prompt a form is pre-filled with. Its file is
# `configs/prompts/sales/po_layout_proposal@1.0.0.yaml`; a test holds the two
# together, and a new wording is a new version here and a new file there.
LAYOUT_PROPOSAL: Final = PromptRef("sales.po_layout_proposal", "1.0.0")
# Seventeen short labels and three conventions: about 250 tokens measured.
_OUTPUT_TOKENS: Final = 700
# What the prompt itself costs, held above its rendered size by a test.
PROMPT_TOKENS: Final = 1800
# A trial read is stamped with no layout of the tenant's: nothing stores it.
PROBE_REF: Final = "po_layout:00000000-0000-0000-0000-000000000000@0"

_LAYOUT = "sales_po_layout"

# The platform approval a layout's proposal opens, and the event its decision
# is announced by. Under `sales.`, so the strict rule (a second person who is
# not the maker, and a written comment) holds for it as for every Sales one.
LAYOUT_APPROVAL: Final = "sales.layout"
LAYOUT_DECIDED: Final = decided_event_type(LAYOUT_APPROVAL)
_LAYOUT_REASON: Final = "Mẫu PO chờ duyệt: Sales lập, Trưởng bộ phận duyệt (ticket 30)"


class LayoutApprovalAsked(BaseModel):
    """The approval's payload: ids, codes and a version, never a label or a
    value of the form (the inbox serves it to whoever may decide it)."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    approval_type: Literal["sales.layout"]
    required_scope: str
    layout_id: uuid.UUID
    customer_code: str = Field(pattern=r"^[A-Z][A-Z0-9]{1,15}$")
    kind: Literal["excel", "pdf"]
    version: int = Field(ge=1)
    makers: tuple[uuid.UUID, ...]

    @classmethod
    def of(cls, layout: PoLayout) -> LayoutApprovalAsked:
        return cls(
            approval_type="sales.layout",
            required_scope=SalesScopes.LAYOUT_APPROVE.value,
            layout_id=layout.layout_id,
            customer_code=layout.customer_code,
            kind=layout.kind,
            version=layout.version,
            makers=(layout.proposed_by,),
        )


class LayoutReaderPort(Protocol):
    """The reader, as onboarding uses it: the form's cells, and a read with a
    mapping. Satisfied by `PoDocumentReaders`."""

    async def label_source(
        self, document: AttachmentContent, caps: IntakeCaps
    ) -> LayoutSource | None: ...

    async def read_with(
        self,
        document: AttachmentContent,
        mapping: LayoutMapping,
        caps: IntakeCaps,
        *,
        layout_ref: str,
    ) -> PoDocument | Unreadable: ...


@dataclass(frozen=True, slots=True)
class Checked:
    """A mapping as code judged it: with a PDF's titles in print order filled
    in, the PO the reader read with it, and every problem found."""

    mapping: LayoutMapping
    document: PoDocument | None
    problems: tuple[Problem, ...]

    @property
    def ok(self) -> bool:
        return not self.problems


@dataclass(frozen=True)
class LayoutChecks:
    """Judges a mapping against one form (module docstring)."""

    reader: LayoutReaderPort
    catalog: SalesCatalogPort

    async def check(
        self,
        scope: SalesScope,
        content: AttachmentContent,
        customer: Customer,
        mapping: LayoutMapping,
        rules: OrderRules,
        source: LayoutSource | None = None,
    ) -> Checked:
        source = source or await self.reader.label_source(content, rules.intake)
        if source is None or source.kind != mapping.kind:
            return Checked(mapping, None, (Problem(problem="unreadable"),))
        problems = check_labels(mapping, source)
        if mapping.kind == "pdf":
            columns = pdf_columns(mapping, source)
            if columns is None and not problems:
                problems.append(Problem(problem="columns_not_on_one_row"))
            mapping = mapping.model_copy(update={"pdf_columns": columns})
        if problems:
            return Checked(mapping, None, tuple(problems))
        read = await self.reader.read_with(content, mapping, rules.intake, layout_ref=PROBE_REF)
        if isinstance(read, Unreadable):
            return Checked(mapping, None, (Problem(problem="unreadable"),))
        if read.total is None:
            problems.append(Problem(problem="no_total", field="total_label"))
        elif any(f.code is FindingCode.LINE_TOTAL_MISMATCH for f in check_document(read, rules)):
            problems.append(Problem(problem="line_total_mismatch"))
        problems += plausible(
            read,
            quoted_prices=await self._quoted(scope, customer, read.header.currency),
            known_codes=await self._known(scope, customer, read),
        )
        return Checked(mapping, read, tuple(problems))

    async def _quoted(self, scope: SalesScope, customer: Customer, currency: str) -> list[Decimal]:
        quotations = (await self.catalog.quotations(scope)).data
        return [
            q.unit_price
            for q in quotations
            if q.customer_code == customer.code and q.currency == currency
        ]

    async def _known(
        self, scope: SalesScope, customer: Customer, document: PoDocument
    ) -> list[str]:
        """The line codes the convert list or the item master knows."""
        known: list[str] = []
        for line in document.lines:
            code = line.customer_item_code
            entry = (await self.catalog.convert_entry(scope, customer.code, code)).data
            item = (await self.catalog.item_by_prv_code(scope, code)).data
            if entry is not None or item is not None:
                known.append(code)
        return known


@dataclass(frozen=True)
class LayoutPrefiller:
    """A model's pre-fill of a form's mapping, kept only when it passes."""

    model: InterpretationPort
    checks: LayoutChecks

    async def prefill(
        self,
        scope: SalesScope,
        content: AttachmentContent,
        customer: Customer,
        rules: OrderRules,
        *,
        run: RunContext,
    ) -> LayoutPrefill | None:
        """The stamp of what the model proposed and code kept, or None for a
        file that is no form a layout can map (nothing was asked)."""
        source = await self.checks.reader.label_source(content, rules.intake)
        if source is None:
            return None
        stamp = {
            "prompt": str(LAYOUT_PROPOSAL),
            "model_profile": self.model.model_profile,
            "route": self.model.route,
            "rules": rules.version,
            "attachment_id": content.attachment.attachment_id,
        }
        inputs = self._inputs(source)
        try:
            answer = await self.model.interpret(
                LAYOUT_PROPOSAL,
                inputs,
                ModelLayoutProposal,
                run=run,
                max_output_tokens=_OUTPUT_TOKENS,
            )
        except ModelUnavailableError:
            return LayoutPrefill.model_validate({**stamp, "outcome": "unavailable"})
        mapping = answer.mapping(source.kind)
        if mapping is None:
            return LayoutPrefill.model_validate(
                {**stamp, "outcome": "refused", "problems": ("incomplete_proposal",)}
            )
        checked = await self.checks.check(scope, content, customer, mapping, rules, source)
        if not checked.ok:
            return LayoutPrefill.model_validate(
                {
                    **stamp,
                    "outcome": "refused",
                    "problems": tuple(str(p) for p in checked.problems)[:40],
                }
            )
        return LayoutPrefill.model_validate(
            {**stamp, "outcome": "proposed", "mapping": checked.mapping}
        )

    def _inputs(self, source: LayoutSource) -> dict[str, str]:
        """The form's parts as code-built JSON (`form_parts`), each cell cut
        to fit the route's room: a label is short, a description need not be
        whole for the column to be told."""
        parts = form_parts(source.rows)
        room = self.model.max_input_tokens - PROMPT_TOKENS
        width = 120
        while True:
            inputs = {
                "kind": source.kind,
                "header": _json(parts.header, width),
                "table": _json(parts.table, width),
                "footer": _json(parts.footer, width),
            }
            if estimated_tokens("".join(inputs.values())) <= room or width <= 20:
                return inputs
            width //= 2


def _json(rows: list[list[str]], width: int) -> str:
    return json.dumps([[cell[:width] for cell in row] for row in rows], ensure_ascii=False)


# --------------------------------------------------------------- the views --

_VIEW = ConfigDict(frozen=True)


class LabelCellView(BaseModel):
    model_config = _VIEW

    ref: str
    sheet: str
    row: int
    column: int
    text: str


class LayoutView(BaseModel):
    """One layout: its mapping, the PO it was mapped from, who proposed and
    who decided it, and the model pre-fill it started from, if any."""

    model_config = _VIEW

    layout_id: uuid.UUID
    customer_code: str
    kind: str
    version: int
    status: str
    mapping: LayoutMapping
    sample: LayoutSample
    proposed_by: uuid.UUID
    proposed_at: datetime
    # The platform approval it is decided on (`POST /approvals/{id}/decisions`).
    approval_id: uuid.UUID
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    prefill: LayoutPrefill | None


def layout_view(layout: PoLayout) -> LayoutView:
    return LayoutView(
        layout_id=layout.layout_id,
        customer_code=layout.customer_code,
        kind=layout.kind,
        version=layout.version,
        status=layout.status,
        mapping=layout.mapping,
        sample=layout.sample,
        proposed_by=layout.proposed_by,
        proposed_at=layout.proposed_at,
        approval_id=layout.approval_id,
        decided_by=layout.decided_by,
        decided_at=layout.decided_at,
        prefill=layout.prefill,
    )


class LayoutSourceView(BaseModel):
    """What the onboarding screen maps from: the form's cells, the pre-fill
    DW1 stamped on the message (a model's, where the step is on), and the
    customer's layout of this kind already approved, if any."""

    model_config = _VIEW

    message_id: str
    attachment_id: str
    customer_code: str
    kind: Literal["excel", "pdf"]
    cells: list[LabelCellView]
    prefill: LayoutPrefill | None
    approved: LayoutView | None


class PreviewLineView(BaseModel):
    model_config = _VIEW

    line_no: int
    customer_item_code: str
    description: str
    quantity: Decimal
    uom: str
    unit_price: Decimal
    amount: Decimal
    requested_date: date | None


class LayoutPreviewView(BaseModel):
    """A mapping as code judged it: the problems, and what the reader read."""

    model_config = _VIEW

    ok: bool
    problems: list[str]
    po_no: str | None = None
    po_date: date | None = None
    currency: str | None = None
    revision: int | None = None
    total: Decimal | None = None
    lines: list[PreviewLineView] = []


def preview_view(checked: Checked) -> LayoutPreviewView:
    document = checked.document
    if document is None:
        return LayoutPreviewView(ok=False, problems=[str(p) for p in checked.problems])
    header = document.header
    return LayoutPreviewView(
        ok=checked.ok,
        problems=[str(p) for p in checked.problems],
        po_no=header.po_no,
        po_date=header.po_date,
        currency=header.currency,
        revision=header.revision,
        total=document.total.amount if document.total else None,
        lines=[
            PreviewLineView(
                line_no=line.line_no,
                customer_item_code=line.customer_item_code,
                description=line.description,
                quantity=line.quantity,
                uom=line.uom,
                unit_price=line.unit_price,
                amount=line.amount,
                requested_date=line.requested_date,
            )
            for line in document.lines
        ],
    )


# ------------------------------------------------------------ the service --


@dataclass(frozen=True)
class LayoutService:
    """The onboarding screen's routes (module docstring)."""

    uow: SalesUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    ids: IdGenerator
    inbox: InboxPort
    catalog: SalesCatalogPort
    rules: OrderRulesPort
    checks: LayoutChecks

    async def list(self, context: AccessContext) -> list[LayoutView]:
        await self.gate.require(context, SalesScopes.CASE_READ, resource_type=_LAYOUT)
        async with self.uow(sales_scope(context)) as work:
            return [layout_view(layout) for layout in await work.layouts.list_all()]

    async def source(
        self, context: AccessContext, message_id: str, attachment_id: str
    ) -> LayoutSourceView:
        """The form's cells. A PO shows prices: the caller maps orders and
        sees amounts."""
        await self._mapper(context, message_id)
        scope = sales_scope(context)
        content, customer, rules = await self._form(scope, message_id, attachment_id)
        source = await self.checks.reader.label_source(content, rules.intake)
        if source is None:
            raise ConflictError(
                "the file is no form a layout can map: a text PDF or an .xlsx",
                details={"message_id": message_id, "attachment_id": attachment_id},
            )
        async with self.uow(scope) as work:
            disposition = await work.messages.get(message_id)
            approved = [
                layout
                for layout in await work.layouts.list_all()
                if layout.customer_code == customer.code
                and layout.status == "approved"
                and layout.kind == source.kind
            ]
        prefill = disposition.layout_prefill if disposition is not None else None
        if prefill is not None and prefill.attachment_id != attachment_id:
            prefill = None
        return LayoutSourceView(
            message_id=message_id,
            attachment_id=attachment_id,
            customer_code=customer.code,
            kind=source.kind,
            cells=[LabelCellView(**dict(cell)) for cell in source.cells],
            prefill=prefill,
            approved=layout_view(approved[0]) if approved else None,
        )

    async def preview(
        self,
        context: AccessContext,
        message_id: str,
        attachment_id: str,
        mapping: LayoutMapping,
    ) -> LayoutPreviewView:
        await self._mapper(context, message_id)
        scope = sales_scope(context)
        content, customer, rules = await self._form(scope, message_id, attachment_id)
        return preview_view(await self.checks.check(scope, content, customer, mapping, rules))

    async def propose(
        self,
        context: AccessContext,
        message_id: str,
        attachment_id: str,
        mapping: LayoutMapping,
    ) -> LayoutView:
        """The caller's mapping of the form, once every check passes, stored
        with the platform approval a second person decides it on. The caller
        is its maker."""
        await self._mapper(context, message_id)
        scope = sales_scope(context)
        content, customer, rules = await self._form(scope, message_id, attachment_id)
        checked = await self.checks.check(scope, content, customer, mapping, rules)
        if not checked.ok:
            raise ConflictError(
                "the mapping does not read the form: correct the fields named",
                details={"problems": [str(p) for p in checked.problems]},
            )
        now = self.clock.now()
        async with self.uow(scope) as work:
            disposition = await work.messages.get(message_id)
            prefill = disposition.layout_prefill if disposition is not None else None
            earlier = [
                layout
                for layout in await work.layouts.list_all()
                if layout.customer_code == customer.code and layout.kind == mapping.kind
            ]
            layout = decided(
                lambda: PoLayout(
                    layout_id=self.ids.new_uuid(),
                    customer_code=customer.code,
                    version=1 + max((layout.version for layout in earlier), default=0),
                    mapping=checked.mapping,
                    sample=LayoutSample(
                        message_id=message_id,
                        attachment_id=attachment_id,
                        attachment_sha256=content.attachment.sha256,
                    ),
                    proposed_by=context.principal_id,
                    proposed_at=now,
                    approval_id=self.ids.new_uuid(),
                    prefill=(
                        prefill
                        if prefill is not None and prefill.attachment_id == attachment_id
                        else None
                    ),
                )
            )
            await work.approvals.add(
                ApprovalRequest(
                    id=layout.approval_id,
                    tenant_id=TenantId(context.tenant_id),
                    workspace_id=WorkspaceId(context.workspace_id),
                    approval_type=LAYOUT_APPROVAL,
                    requested_by=UserId(context.principal_id),
                    reason=_LAYOUT_REASON,
                    payload=LayoutApprovalAsked.of(layout).model_dump(mode="json"),
                    required_scope=SalesScopes.LAYOUT_APPROVE.value,
                )
            )
            # After its approval: the row names it (`fk_po_layouts_approval_requests`).
            await work.layouts.add(layout)
            await work.audit.append(
                _audit(self.ids, self.clock, context, "sales.layout.proposed", layout)
            )
            await work.commit()
        return layout_view(layout)

    # ------------------------------------------------------------- helpers --

    async def _mapper(self, context: AccessContext, message_id: str) -> None:
        await self.gate.require(
            context,
            SalesScopes.ORDER_PREPARE,
            SalesScopes.PRICE_READ,
            resource_type="sales_message",
            resource_id=message_id,
        )

    async def _form(
        self, scope: SalesScope, message_id: str, attachment_id: str
    ) -> tuple[AttachmentContent, Customer, OrderRules]:
        """The attachment, the customer its sender's domain is, and the rules."""
        message = await self.inbox.get_message(scope, message_id)
        content = await self.inbox.read_attachment(scope, message_id, attachment_id)
        if message is None or content is None:
            raise NotFoundError(
                "no such attachment",
                details={"message_id": message_id, "attachment_id": attachment_id},
            )
        customer = (await self.catalog.customer_by_email_domain(scope, message.sender.domain)).data
        if customer is None:
            raise ConflictError(
                "the sender is no customer: a layout is a customer's form",
                details={"message_id": message_id},
            )
        return content, customer, await self.rules.rules(scope)


# ----------------------------------------------------------- the decision --


def _asked(request: ApprovalRequest) -> LayoutApprovalAsked:
    """The approval as a proposal opened it, or a refusal: its payload
    unreadable, or stamped with a scope other than `sales.layout.approve`
    (the column, which the platform's decision enforced)."""
    try:
        asked = LayoutApprovalAsked.model_validate(request.payload)
    except ValidationError:
        raise ConflictError(
            "the approval is not one a layout proposal opened",
            details={"approval_id": str(request.id)},
        ) from None
    if request.approval_type != LAYOUT_APPROVAL:
        raise ConflictError(
            "the approval is not one a layout proposal opened",
            details={"approval_id": str(request.id)},
        )
    if request.required_scope != SalesScopes.LAYOUT_APPROVE.value or (
        asked.required_scope != request.required_scope
    ):
        raise PermissionDeniedError(
            "a layout is decided with sales.layout.approve",
            details={"approval_type": request.approval_type},
        )
    return asked


def _waiting(layout: PoLayout | None, request: ApprovalRequest) -> PoLayout:
    """The layout this approval was opened for, still waiting on it."""
    if layout is None:
        raise NotFoundError("no such layout", details={"approval_id": str(request.id)})
    if layout.approval_id != request.id or layout.status != "proposed":
        raise ConflictError(
            "mẫu PO không còn chờ quyết định này",
            details={
                "layout_id": str(layout.layout_id),
                "status": layout.status,
                "rule": "decision_stale",
            },
        )
    return layout


@dataclass(frozen=True)
class LayoutDecisions:
    """The platform's `ApprovalDecisionGuard` for `sales.layout`: the decision
    as the layout would take it, refused or not, unwritten. Called after the
    decider's scope and the separation of duties, before it is recorded."""

    uow: SalesUnitOfWorkFactory
    clock: UtcClock

    async def check(
        self, request: ApprovalRequest, decision: ProposedDecision, context: AccessContext
    ) -> None:
        asked = _asked(request)
        if decision.subject_version != asked.version:
            raise DomainError(
                "quyết định mẫu PO nêu phiên bản đã xem: mở trang Mẫu PO để quyết định",
                details={"field": "subject_version"},
            )
        async with self.uow(sales_scope(context)) as work:
            layout = _waiting(await work.layouts.get(asked.layout_id), request)
        by, now = context.principal_id, self.clock.now()
        decided(lambda: layout.approve(by, now) if decision.approve else layout.reject(by, now))


@dataclass(frozen=True)
class LayoutSettlement:
    """Carries out a decided `sales.layout` approval: the worker's handler
    for `LAYOUT_DECIDED` calls it with the decider's tenancy and identity,
    from the event's envelope."""

    uow: SalesUnitOfWorkFactory
    clock: UtcClock
    ids: IdGenerator

    async def settle(self, approval_id: uuid.UUID, decider: AccessContext) -> LayoutView:
        """The decision on the layout, as its decider. What was decided is
        read from the approval row, which the decision wrote, not from the
        event. Idempotent: a redelivery finds the layout decided on this
        approval and writes nothing. Raises the refusals the layout makes
        (409, 404); none changes on a retry."""
        # Read as the decider holding the stamp the platform required of them
        # when they decided: nobody reaches here but through that decision.
        audience = ApprovalAudience(
            context=decider.model_copy(
                update={"scopes": frozenset({SalesScopes.LAYOUT_APPROVE.value})}
            ),
            holds_decide=True,
        )
        now = self.clock.now()
        async with self.uow(sales_scope(decider)) as work:
            request = await work.approvals.get(
                approval_id, workspace_id=decider.workspace_id, audience=audience
            )
            if request is None:
                raise NotFoundError(
                    "layout approval not found", details={"approval_id": str(approval_id)}
                )
            asked = _asked(request)
            stored = await work.layouts.get(asked.layout_id)
            # Settled already, by an earlier delivery of the same event.
            if (
                stored is not None
                and stored.approval_id == request.id
                and stored.status != "proposed"
            ):
                return layout_view(stored)
            layout = _waiting(stored, request)
            if request.status is ApprovalStatus.PENDING:
                raise ConflictError(
                    "the layout approval is not decided yet",
                    details={"approval_id": str(approval_id)},
                )
            by = decider.principal_id
            if request.status is ApprovalStatus.APPROVED:
                after = decided(lambda: layout.approve(by, now))
                for earlier in await work.layouts.list_all():
                    same = (earlier.customer_code, earlier.kind) == (
                        after.customer_code,
                        after.kind,
                    )
                    if same and earlier.status == "approved":
                        await work.layouts.save(earlier.supersede(), expected="approved")
                action = "sales.layout.approved"
            else:
                after = decided(lambda: layout.reject(by, now))
                action = "sales.layout.rejected"
            await work.layouts.save(after, expected="proposed")
            await work.audit.append(
                _audit(self.ids, self.clock, decider, action, after, approval_id=request.id)
            )
            await work.commit()
        return layout_view(after)


def _audit(
    ids: IdGenerator,
    clock: UtcClock,
    context: AccessContext,
    action: str,
    layout: PoLayout,
    *,
    approval_id: uuid.UUID | None = None,
) -> AuditEvent:
    """Ids, codes and a version: no label or value of the form."""
    details: dict[str, object] = {
        "customer_code": layout.customer_code,
        "kind": layout.kind,
        "version": layout.version,
        "status": layout.status,
    }
    if approval_id is not None:
        details["approval_id"] = str(approval_id)
    return AuditEvent(
        id=ids.new_uuid(),
        tenant_id=TenantId(context.tenant_id),
        workspace_id=WorkspaceId(context.workspace_id),
        actor_id=UserId(context.principal_id),
        action=action,
        resource_type=_LAYOUT,
        resource_id=str(layout.layout_id),
        occurred_at=clock.now(),
        details=details,
    )
