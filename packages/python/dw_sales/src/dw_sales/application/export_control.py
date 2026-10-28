"""Export control, WIV-03-032 (2026-10-28): the page a person screens a
customer on, and what each result records.

Who reads: a holder of `sales.case.read`. Who records: a holder of
`sales.compliance.ack`, the export-control PIC's permission set, the one that
already accepts a `missing_noc_esf` finding. Every result is the latest per
customer and step (`ScreeningStorePort.put` replaces it) with its audit row
in the same transaction, so the history is the audit trail.

A result with a document (the customer's NOC, the signed ESF) is recorded with
its file: size, kind by its bytes and the malware scan, as every upload.
DW1 drafts what can be drafted, the NOEC mail and the ESF form, and decides
nothing: the order checks read the customer's compliance as these results
move it (`effective_compliance`, through `ScreenedCatalog`).
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from types import TracebackType
from typing import Final, Literal, Protocol, Self
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict

from dw_kernel.errors import ConflictError, DomainError, NotFoundError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.ports import AuditRepositoryPort
from dw_platform.domain.audit import AuditEvent
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.artifact_content import (
    EML,
    PDF,
    XLSX,
    ArtifactWriterPort,
    EmailDraft,
    Sheet,
    Workbook,
    day_text,
)
from dw_sales.application.drafting import ArtifactCopy, People
from dw_sales.application.malware import MalwareScanPort
from dw_sales.application.ports import (
    ArtifactBytesPort,
    MemberDirectoryPort,
    SalesCatalogPort,
    SalesScope,
)
from dw_sales.domain.catalog import Compliance, Customer, Item, fiscal_year
from dw_sales.domain.export_control import (
    EVIDENCE_REQUIRED,
    NOTE_MAX,
    OUTCOMES,
    Evidence,
    EvidenceType,
    SalesExportControl,
    ScreeningRecord,
    ScreeningStep,
    effective_compliance,
)
from dw_sales.domain.order_checks import OrderRules

EVIDENCE_MAX_BYTES: Final = 10 * 1024 * 1024
# What an evidence file may be, by its first bytes: a scan as PDF, or a photo.
_EVIDENCE_TYPES: Final[tuple[tuple[bytes, EvidenceType], ...]] = (
    (b"%PDF-", "application/pdf"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)
_EXTENSIONS: Final = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}
# A customer still buying, for the yearly renewal (WIV-03-032 step 6).
TRADED_WITHIN: Final = timedelta(days=365)
_VIEW = ConfigDict(frozen=True)


# ------------------------------------------------------------------ ports --


class ScreeningStorePort(Protocol):
    """The latest result per customer and step, in one workspace."""

    async def records(self) -> Sequence[ScreeningRecord]: ...

    async def put(self, record: ScreeningRecord) -> None:
        """Replace the customer's result of this step with ``record``."""
        ...


class ExportControlUnitOfWork(Protocol):
    """One transaction in one workspace; leaving without `commit` rolls back."""

    @property
    def screenings(self) -> ScreeningStorePort: ...

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


class ExportControlUnitOfWorkFactory(Protocol):
    def __call__(self, scope: SalesScope) -> ExportControlUnitOfWork: ...


class ExportControlPoliciesPort(Protocol):
    """The tenant's export-control policy, its order rules (the fiscal year,
    the denial list's age) and the copy a draft is sent with: the rule book."""

    async def export_control(self, scope: SalesScope) -> SalesExportControl: ...

    async def order_rules(self, scope: SalesScope) -> OrderRules: ...

    async def artifact_copy(self, scope: SalesScope, stamps: Sequence[str]) -> ArtifactCopy: ...


# ------------------------------------------------------------------ views --


class ScreeningView(BaseModel):
    model_config = _VIEW

    step: ScreeningStep
    outcome: str
    checked_on: date
    fiscal_year: int | None
    answers: dict[str, bool]
    note: str | None
    has_evidence: bool
    recorded_by: uuid.UUID
    recorded_at: AwareDatetime


Need = Literal[
    "noc_missing",
    "esf_due",
    "denial_due",
    "denial_match",
    "red_flag_missing",
    "red_flag_escalated",
    "products_unclassified",
    "products_listed",
]


class CustomerScreeningView(BaseModel):
    """One customer's export control, as the overview lists it."""

    model_config = _VIEW

    customer_code: str
    customer_name: str
    status: str
    noc_confirmed: bool
    esf_fiscal_year: int | None
    denial_list_checked_on: date | None
    denial_list_match: bool
    red_flag_escalated: bool
    # Bought within the last year: renews its ESF for the new fiscal year.
    traded_recently: bool
    needs: list[Need]


class ExportControlOverview(BaseModel):
    model_config = _VIEW

    fiscal_year: int
    denial_list_max_age_days: int
    policy_ref: str
    sample: bool
    customers: list[CustomerScreeningView]


class ProductView(BaseModel):
    model_config = _VIEW

    prv_code: str
    classification: Literal["applicable", "not_applicable"] | None


class RedFlagQuestionView(BaseModel):
    model_config = _VIEW

    id: str
    text: str


class CustomerDetailView(BaseModel):
    model_config = _VIEW

    summary: CustomerScreeningView
    screenings: list[ScreeningView]
    # PRV's screen of what the customer buys: their convert-list items and
    # those of their orders within the year (WIV-03-032 step 1).
    products: list[ProductView]
    red_flags: list[RedFlagQuestionView]
    esf_approvers: list[str]
    sample: bool


@dataclass(frozen=True, slots=True)
class Download:
    data: bytes
    content_type: str
    file_name: str


# --------------------------------------------------------------- service --


@dataclass(frozen=True)
class ExportControlService:
    uow: ExportControlUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    ids: IdGenerator
    # The master data as approved: compliance before these results move it.
    catalog: SalesCatalogPort
    policies: ExportControlPoliciesPort
    storage: ArtifactBytesPort
    scanner: MalwareScanPort
    writer: ArtifactWriterPort
    directory: MemberDirectoryPort

    # ------------------------------------------------------------- reading --

    async def overview(self, context: AccessContext) -> ExportControlOverview:
        await self._read(context, None)
        scope, today = sales_scope(context), self._today()
        policy, rules = await self._policies(scope)
        customers = (await self.catalog.customers(scope)).data
        records = await self._records(scope)
        traded = await self._traded(scope, today)
        items = {i.prv_code: i for i in (await self.catalog.items(scope)).data}
        bought = await self._bought(scope, today)
        year = fiscal_year(today, start_month=rules.fiscal_year_start_month)
        return ExportControlOverview(
            fiscal_year=year,
            denial_list_max_age_days=rules.export_control.denial_list_max_age_days,
            policy_ref=policy.ref,
            sample=policy.sample,
            customers=[
                self._summary(
                    c,
                    records.get(c.code, ()),
                    traded=c.code in traded,
                    products=[items[p] for p in bought.get(c.code, ()) if p in items],
                    year=year,
                    rules=rules,
                    today=today,
                )
                for c in customers
            ],
        )

    async def customer(self, context: AccessContext, code: str) -> CustomerDetailView:
        await self._read(context, code)
        scope, today = sales_scope(context), self._today()
        policy, rules = await self._policies(scope)
        customer = await self._customer(scope, code)
        records = (await self._records(scope)).get(code, ())
        items = {i.prv_code: i for i in (await self.catalog.items(scope)).data}
        convert = (await self.catalog.convert_list(scope)).data
        codes = sorted(
            {e.prv_code for e in convert if e.customer_code == code}
            | set((await self._bought(scope, today)).get(code, ()))
        )
        products = [items[p] for p in codes if p in items]
        year = fiscal_year(today, start_month=rules.fiscal_year_start_month)
        traded = code in await self._traded(scope, today)
        return CustomerDetailView(
            summary=self._summary(
                customer,
                records,
                traded=traded,
                products=products,
                year=year,
                rules=rules,
                today=today,
            ),
            screenings=[_screening_view(r) for r in records],
            products=[
                ProductView(prv_code=i.prv_code, classification=i.export_classification)
                for i in products
            ],
            red_flags=[RedFlagQuestionView(id=q.id, text=q.text) for q in policy.red_flags],
            esf_approvers=list(policy.esf_approvers),
            sample=policy.sample,
        )

    async def evidence(self, context: AccessContext, code: str, step: ScreeningStep) -> Download:
        await self._read(context, code)
        scope = sales_scope(context)
        record = next(
            (r for r in (await self._records(scope)).get(code, ()) if r.step is step), None
        )
        if record is None or record.evidence is None:
            raise NotFoundError(
                "this step has no document for the customer",
                details={"customer_code": code, "step": step.value},
            )
        data = await self.storage.get_object(_object_key(scope, code, record.evidence.file_id))
        if hashlib.sha256(data).hexdigest() != record.evidence.sha256:
            raise ConflictError(
                "tệp lưu trữ không khớp mã băm đã ghi", details={"reason": "sha256_mismatch"}
            )
        return Download(
            data,
            record.evidence.content_type,
            f"{step.value}-{code}{_EXTENSIONS[record.evidence.content_type]}",
        )

    # ------------------------------------------------------------- drafting --

    async def esf_form(self, context: AccessContext, code: str, *, pdf: bool) -> Download:
        """The ESF prefilled with what DW1 holds, to print and sign by each
        level the policy names; its signed scan comes back with `record_esf`."""
        await self._read(context, code)
        scope, today = sales_scope(context), self._today()
        detail = await self.customer(context, code)
        _, rules = await self._policies(scope)
        year = fiscal_year(today, start_month=rules.fiscal_year_start_month)
        s = detail.summary
        latest = {r.step: r for r in detail.screenings}
        red = latest.get(ScreeningStep.RED_FLAG)
        sheet = Sheet(
            name="ESF",
            title=f"PHIẾU SÀNG LỌC XUẤT KHẨU (ESF) NĂM TÀI CHÍNH {year}"
            + (" — BẢN MẪU" if detail.sample else ""),
            heading=(
                ("Khách hàng", f"{s.customer_name} ({s.customer_code})"),
                ("NOC", "Đã xác nhận" if s.noc_confirmed else "Chưa có"),
                (
                    "Denial list",
                    "Có trong danh sách"
                    if s.denial_list_match
                    else day_text(s.denial_list_checked_on, "vi")
                    if s.denial_list_checked_on
                    else "Chưa tra",
                ),
                (
                    "Red flag",
                    "Chưa trả lời"
                    if red is None
                    else "Có câu trả lời Có"
                    if red.outcome == "escalated"
                    else "Không có dấu hiệu",
                ),
                ("Ngày lập", day_text(today, "vi")),
            ),
            columns=("Mã PRV", "Phân loại xuất khẩu"),
            rows=tuple((p.prv_code, _CLASS_TEXT[p.classification]) for p in detail.products),
            notes=(
                *(
                    f"{title}: ký, ghi rõ họ tên, ngày ______________"
                    for title in detail.esf_approvers
                ),
            ),
        )
        book = Workbook(
            sheets=(sheet,),
            language="vi",
            stamped_at=datetime.combine(today, datetime.min.time(), tzinfo=UTC),
        )
        if pdf:
            return Download(self.writer.pdf(book), PDF, f"ESF-{code}-FY{year}.pdf")
        return Download(self.writer.workbook(book), XLSX, f"ESF-{code}-FY{year}.xlsx")

    async def noec_draft(self, context: AccessContext, code: str) -> Download:
        """The NOEC mail, drafted to the customer's contacts in their
        language. Sent by the PIC from their own mailbox, then recorded as
        requested (`record_noc`)."""
        await self._write(context, code)
        scope, now = sales_scope(context), self.clock.now()
        policy, _ = await self._policies(scope)
        customer = await self._customer(scope, code)
        copy = await self.policies.artifact_copy(scope, [])
        people = People({m.user_id: m for m in await self.directory.list_members(context)})
        sender = copy.emails.sender
        language = customer.language
        values = {"customer_name": customer.name}
        draft = EmailDraft(
            sender=(
                people.address(context.principal_id)
                if sender.from_ == "drafting_pic"
                else sender.shared_sales
            ),
            reply_to=sender.shared_sales,
            to=customer.contacts,
            subject=policy.noec_email.subject[language].format_map(values),
            body=policy.noec_email.body[language].format_map(values),
            dated=now,
        )
        return Download(self.writer.email(draft), EML, f"NOEC-{code}.eml")

    # ------------------------------------------------------------ recording --

    async def record_denial(
        self,
        context: AccessContext,
        code: str,
        *,
        outcome: str,
        checked_on: date,
        note: str | None,
        evidence: bytes | None,
    ) -> ScreeningView:
        return await self._record(
            context, code, ScreeningStep.DENIAL_LIST, outcome, checked_on, note, evidence
        )

    async def record_red_flag(
        self,
        context: AccessContext,
        code: str,
        *,
        answers: Mapping[str, bool],
        checked_on: date,
        note: str | None,
    ) -> ScreeningView:
        await self._write(context, code)
        policy, _ = await self._policies(sales_scope(context))
        asked = {q.id for q in policy.red_flags}
        if set(answers) != asked:
            raise DomainError(
                "trả lời đủ mọi câu hỏi Red flag của bộ đang dùng",
                details={"rule": "red_flag_answers", "policy_ref": policy.ref},
            )
        outcome = "escalated" if any(answers.values()) else "clear"
        return await self._record(
            context,
            code,
            ScreeningStep.RED_FLAG,
            outcome,
            checked_on,
            note,
            None,
            answers=dict(answers),
        )

    async def record_noc(
        self,
        context: AccessContext,
        code: str,
        *,
        outcome: str,
        checked_on: date,
        note: str | None,
        evidence: bytes | None,
    ) -> ScreeningView:
        """The NOEC sent (``requested``), or the customer's NOC received with
        its document (``received``)."""
        return await self._record(
            context, code, ScreeningStep.NOC, outcome, checked_on, note, evidence
        )

    async def record_esf(
        self,
        context: AccessContext,
        code: str,
        *,
        fiscal_year: int,
        approved_on: date,
        note: str | None,
        evidence: bytes,
    ) -> ScreeningView:
        return await self._record(
            context,
            code,
            ScreeningStep.ESF,
            "approved",
            approved_on,
            note,
            evidence,
            fiscal_year=fiscal_year,
        )

    # ---------------------------------------------------------------- work --

    async def _record(
        self,
        context: AccessContext,
        code: str,
        step: ScreeningStep,
        outcome: str,
        checked_on: date,
        note: str | None,
        data: bytes | None,
        *,
        answers: dict[str, bool] | None = None,
        fiscal_year: int | None = None,
    ) -> ScreeningView:
        await self._write(context, code)
        if outcome not in OUTCOMES[step]:
            raise DomainError(
                "kết quả không thuộc bước này", details={"rule": "outcome", "step": step.value}
            )
        if checked_on > self._today():
            raise DomainError("ngày ghi nhận ở tương lai", details={"rule": "checked_on"})
        if (step, outcome) in EVIDENCE_REQUIRED and data is None:
            raise DomainError(
                "kết quả này cần tệp đính kèm (bản NOC hoặc ESF đã ký)",
                details={"rule": "evidence_required", "step": step.value},
            )
        if note is not None and len(note) > NOTE_MAX:
            raise DomainError("ghi chú quá 500 ký tự", details={"rule": "note"})
        scope, now = sales_scope(context), self.clock.now()
        await self._customer(scope, code)
        evidence = None if data is None else await self._evidence(data)
        if evidence is not None and data is not None:
            await self.storage.put_object(
                _object_key(scope, code, evidence.file_id), data, evidence.content_type
            )
        record = ScreeningRecord(
            customer_code=code,
            step=step,
            outcome=outcome,
            checked_on=checked_on,
            fiscal_year=fiscal_year,
            answers=answers or {},
            note=(note or "").strip() or None,
            evidence=evidence,
            recorded_by=context.principal_id,
            recorded_at=now,
        )
        await self._put(context, record)
        return _screening_view(record)

    async def _put(self, context: AccessContext, record: ScreeningRecord) -> None:
        async with self.uow(sales_scope(context)) as work:
            await work.screenings.put(record)
            await work.audit.append(_audit(context, self.ids, record))
            await work.commit()

    async def _evidence(self, data: bytes) -> Evidence:
        if not 0 < len(data) <= EVIDENCE_MAX_BYTES:
            raise DomainError("tệp phải nhỏ hơn 10 MB", details={"rule": "file_size"})
        content_type = next((t for magic, t in _EVIDENCE_TYPES if data.startswith(magic)), None)
        if content_type is None:
            raise DomainError("tệp là PDF hoặc ảnh JPG, PNG", details={"rule": "file_type"})
        verdict = await self.scanner.scan(data)
        if verdict.outcome != "clean":
            raise ConflictError(
                "tệp chưa qua bước quét mã độc nên không được lưu",
                details={"reason": f"scan_{verdict.outcome}"},
            )
        return Evidence(
            file_id=self.ids.new_uuid(),
            sha256=hashlib.sha256(data).hexdigest(),
            content_type=content_type,
            size_bytes=len(data),
        )

    async def _read(self, context: AccessContext, code: str | None) -> None:
        await self.gate.require(
            context, SalesScopes.CASE_READ, resource_type="sales_customer", resource_id=code
        )

    async def _write(self, context: AccessContext, code: str) -> None:
        await self.gate.require(
            context,
            SalesScopes.CASE_READ,
            SalesScopes.COMPLIANCE_ACK,
            resource_type="sales_customer",
            resource_id=code,
        )

    async def _customer(self, scope: SalesScope, code: str) -> Customer:
        customer = (await self.catalog.customer_by_code(scope, code)).data
        if customer is None:
            raise NotFoundError("no such customer", details={"customer_code": code})
        return customer

    async def _policies(self, scope: SalesScope) -> tuple[SalesExportControl, OrderRules]:
        return await self.policies.export_control(scope), await self.policies.order_rules(scope)

    async def _records(self, scope: SalesScope) -> dict[str, tuple[ScreeningRecord, ...]]:
        async with self.uow(scope) as work:
            records = await work.screenings.records()
        held: dict[str, list[ScreeningRecord]] = {}
        for record in records:
            held.setdefault(record.customer_code, []).append(record)
        return {code: tuple(rs) for code, rs in held.items()}

    async def _traded(self, scope: SalesScope, today: date) -> set[str]:
        """Who bought within the year, by the ERP's order export: the yearly
        screening's evidence (`SalesCatalogPort.orders_since`)."""
        orders = (await self.catalog.orders_since(scope, today - TRADED_WITHIN)).data
        return {order.customer_code for order in orders}

    async def _bought(self, scope: SalesScope, today: date) -> dict[str, list[str]]:
        """What each customer bought within the year, by PRV code."""
        orders = (await self.catalog.orders_since(scope, today - TRADED_WITHIN)).data
        bought: dict[str, set[str]] = {}
        for order in orders:
            bought.setdefault(order.customer_code, set()).update(
                line.prv_code for line in order.lines
            )
        return {code: sorted(codes) for code, codes in bought.items()}

    def _summary(
        self,
        customer: Customer,
        records: Sequence[ScreeningRecord],
        *,
        traded: bool,
        products: Sequence[Item],
        year: int,
        rules: OrderRules,
        today: date,
    ) -> CustomerScreeningView:
        compliance = effective_compliance(customer.compliance, records)
        steps = {r.step for r in records}
        return CustomerScreeningView(
            customer_code=customer.code,
            customer_name=customer.name,
            status=customer.status,
            noc_confirmed=compliance.noc_confirmed,
            esf_fiscal_year=compliance.esf_fiscal_year,
            denial_list_checked_on=compliance.denial_list_checked_on,
            denial_list_match=compliance.denial_list_match,
            red_flag_escalated=compliance.red_flag_escalated,
            traded_recently=traded,
            needs=_needs(
                compliance,
                answered=ScreeningStep.RED_FLAG in steps,
                products=products,
                year=year,
                max_age=rules.export_control.denial_list_max_age_days,
                today=today,
            ),
        )

    def _today(self) -> date:
        return self.clock.now().astimezone(_LOCAL).date()


# ---------------------------------------------------------------- helpers --

_LOCAL: Final = ZoneInfo("Asia/Ho_Chi_Minh")
_CLASS_TEXT: Final = {
    "applicable": "Thuộc danh mục kiểm soát",
    "not_applicable": "Không thuộc",
    None: "Chưa phân loại",
}


def _needs(
    compliance: Compliance,
    *,
    answered: bool,
    products: Sequence[Item],
    year: int,
    max_age: int,
    today: date,
) -> list[Need]:
    """What a person still has to do for the customer, in the steps' order."""
    checked = compliance.denial_list_checked_on
    needs: list[Need] = []
    if any(p.export_classification is None for p in products):
        needs.append("products_unclassified")
    if any(p.export_classification == "applicable" for p in products):
        needs.append("products_listed")
    if compliance.denial_list_match:
        needs.append("denial_match")
    elif checked is None or (today - checked).days > max_age:
        needs.append("denial_due")
    if compliance.red_flag_escalated:
        needs.append("red_flag_escalated")
    elif not answered:
        needs.append("red_flag_missing")
    if not compliance.noc_confirmed:
        needs.append("noc_missing")
    if compliance.esf_fiscal_year != year:
        needs.append("esf_due")
    return needs


def _object_key(scope: SalesScope, code: str, file_id: uuid.UUID) -> str:
    """Tenant and workspace first: offboarding purges by the prefix."""
    return f"{scope.tenant_id}/{scope.workspace_id}/sales/export-control/{code}/{file_id}"


def _screening_view(record: ScreeningRecord) -> ScreeningView:
    return ScreeningView(
        step=record.step,
        outcome=record.outcome,
        checked_on=record.checked_on,
        fiscal_year=record.fiscal_year,
        answers=dict(record.answers),
        note=record.note,
        has_evidence=record.evidence is not None,
        recorded_by=record.recorded_by,
        recorded_at=record.recorded_at,
    )


def _audit(context: AccessContext, ids: IdGenerator, record: ScreeningRecord) -> AuditEvent:
    """The step, its result, the year and the file's hash: never the note."""
    return AuditEvent(
        id=ids.new_uuid(),
        tenant_id=TenantId(context.tenant_id),
        workspace_id=WorkspaceId(context.workspace_id),
        actor_id=UserId(context.principal_id),
        action=f"sales.export_control.{record.step.value}.{record.outcome}",
        resource_type="sales_customer",
        resource_id=record.customer_code,
        occurred_at=record.recorded_at,
        details={
            "step": record.step.value,
            "outcome": record.outcome,
            "checked_on": record.checked_on.isoformat(),
            "fiscal_year": record.fiscal_year,
            "evidence_sha256": record.evidence.sha256 if record.evidence else None,
            "note": record.note is not None,
        },
    )
