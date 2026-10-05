"""Ticket 06: every artifact rendered from the case, stored, and served only in
its state and for the version it was rendered at.

The cases are the mock mailbox's own, walked through the domain's moves; the
service runs over an in-memory unit of work, the shipped copy and policies,
and the real file writer. Per kind: rendered at its state with its template
``id@version``, case version and sha256; refused before its state; refused
after an edit that bumped the case version; and the bytes served are the
bytes recorded.
"""

from __future__ import annotations

import email
import hashlib
import io
import uuid
import zipfile
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from email import policy
from pathlib import Path
from types import TracebackType
from typing import Any, Self, cast

import pytest
from openpyxl import load_workbook
from pypdf import PdfReader

from dw_kernel.errors import (
    ConflictError,
    DomainError,
    InfrastructureError,
    NotFoundError,
    PermissionDeniedError,
)
from dw_kernel.ids import TenantId, WorkspaceId
from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_platform.application.directory import WorkspaceMember
from dw_platform.domain.audit import AuditEvent
from dw_sales.adapters.artifact_files import ArtifactFiles
from dw_sales.adapters.mock import MockInbox, MockSalesCatalog
from dw_sales.adapters.order_rules import PlatformOrderRules, load_order_rules
from dw_sales.adapters.policy_files import (
    load_artifact_copy,
    load_pricing,
    load_quote_rules,
)
from dw_sales.adapters.readers import mock_po_readers
from dw_sales.adapters.rfq_excel import ExcelDesignReplyReader, ExcelRfqReader
from dw_sales.application.access import Gate
from dw_sales.application.artifact_content import EML, PDF, XLSX, SalesEmailCopy
from dw_sales.application.artifacts_service import (
    ORDER_GATES,
    QUOTE_GATES,
    ArtifactService,
    ArtifactView,
)
from dw_sales.application.case_store import ArtifactRecord, CaseOrigin, Stored
from dw_sales.application.drafting import ArtifactCopy
from dw_sales.application.order_intake import OrderIntake
from dw_sales.application.ports import SalesScope
from dw_sales.application.quotation import QuotationService, ReplyAttached
from dw_sales.domain.catalog import LmeBand, LmeMonth, Quotation
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.orders import (
    Accepted,
    Actor,
    AskCustomer,
    Capability,
    CloseReason,
    CorrectedBySales,
    FindingCode,
    MappingStatus,
    OrderCase,
    OrderStatus,
)
from dw_sales.domain.quotes import (
    DeclineReason,
    LinePrice,
    PricingDecision,
    QuoteActor,
    QuoteCapability,
    QuoteCase,
)

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
POLICIES = REPO / "configs" / "policies"
COPY = REPO / "configs" / "copy"
SCOPE = SalesScope(TenantId(uuid.UUID(int=1)), WorkspaceId(uuid.UUID(int=2)))
OTHER = SalesScope(TenantId(uuid.UUID(int=9)), WorkspaceId(uuid.UUID(int=10)))

AN = uuid.UUID(int=0xA1)  # PIC đơn hàng, export control
DIEU = uuid.UUID(int=0xD1)  # PIC báo giá, cross-checks An's orders
GIANG = uuid.UUID(int=0x61)  # head, approves
MEMBERS = (
    WorkspaceMember(AN, "Nguyễn Văn An", "an.nguyen@alpha.local", ("sales_pic",), (), "sales"),
    WorkspaceMember(DIEU, "Hoàng Thị Diệu", "dieu.hoang@alpha.local", ("sales_pic",), (), "sales"),
    WorkspaceMember(GIANG, "Đỗ Minh Giang", "giang.do@alpha.local", ("sales_head",), (), "sales"),
)
T0 = datetime(2026, 10, 2, 2, 0, tzinfo=UTC)
NOW = datetime(2026, 10, 5, 3, 0, tzinfo=UTC)
CONFIRMED_ON = date(2026, 11, 27)
YCBG_M10 = "YCBG-2609-030"
QUOTE_NO = "Q26-0301"
BAND = LmeBand(low_usd_per_tonne=Decimal(10500), high_usd_per_tonne=Decimal(11000))
DECIDED = Decimal("0.6890")
# M10's evidence only Sales may see: other customers' prices and the reference.
INTERNAL_PRICES = ("0.7120", "0.6980", "0.7050")
GUIDANCE = "Chỉ đạo nội bộ: không thấp hơn giá khách khác"

QUOTE_RULES = load_quote_rules(POLICIES / "sales_quote_rules@1.1.0.yaml")
ARTIFACT_COPY = load_artifact_copy(
    emails=COPY / "sales_emails@1.0.0.yaml",
    documents=COPY / "sales_documents@1.0.0.yaml",
    upload=POLICIES / "sales_bravo_upload@1.0.0.yaml",
    quote_rules=QUOTE_RULES,
)
WRITER = ArtifactFiles()
GATE = Gate(ScopeAuthorizationService())

PIC_SCOPES = frozenset(
    {
        "sales.case.read",
        "sales.price.read",
        "sales.order.prepare",
        "sales.order.cross_check",
        "sales.quote.prepare",
    }
)


def context(
    principal: uuid.UUID = AN, scopes: frozenset[str] = PIC_SCOPES, scope: SalesScope = SCOPE
) -> AccessContext:
    return AccessContext(
        tenant_id=scope.tenant_id.value,
        workspace_id=scope.workspace_id.value,
        principal_id=principal,
        roles=frozenset({"sales_pic"}),
        scopes=scopes,
        plan_id="professional",
    )


# ------------------------------------------------------- the in-memory world --


@dataclass
class World:
    """The stores of every scope: cases, artifact records, objects, audit rows."""

    orders: dict[tuple[SalesScope, uuid.UUID], OrderCase] = field(default_factory=dict)
    quotes: dict[tuple[SalesScope, uuid.UUID], QuoteCase] = field(default_factory=dict)
    artifacts: dict[tuple[SalesScope, uuid.UUID], ArtifactRecord] = field(default_factory=dict)
    objects: dict[str, bytes] = field(default_factory=dict)
    audit: list[AuditEvent] = field(default_factory=list)
    commits: int = 0

    def put(self, case: OrderCase | QuoteCase, scope: SalesScope = SCOPE) -> None:
        if isinstance(case, OrderCase):
            self.orders[(scope, case.case_id)] = case
        else:
            self.quotes[(scope, case.case_id)] = case


class _Store[CaseT]:
    def __init__(self, held: dict[tuple[SalesScope, uuid.UUID], CaseT], scope: SalesScope):
        self.held, self.scope = held, scope

    async def get(self, case_id: uuid.UUID) -> Stored[CaseT] | None:
        case = self.held.get((self.scope, case_id))
        return None if case is None else Stored(case, CaseOrigin(None, None))


class _Artifacts:
    def __init__(self, world: World, scope: SalesScope) -> None:
        self.world, self.scope = world, scope
        self.pending: list[ArtifactRecord] = []

    async def add(self, artifact: ArtifactRecord) -> None:
        self.pending.append(artifact)

    async def get(self, artifact_id: uuid.UUID) -> ArtifactRecord | None:
        return self.world.artifacts.get((self.scope, artifact_id))

    async def for_case(self, case_kind: CaseKind, case_id: uuid.UUID) -> list[ArtifactRecord]:
        return [
            r
            for (scope, _), r in self.world.artifacts.items()
            if scope == self.scope and (r.case_kind, r.case_id) == (case_kind, case_id)
        ]


class _Audit:
    def __init__(self) -> None:
        self.pending: list[AuditEvent] = []

    async def append(self, event: AuditEvent) -> None:
        self.pending.append(event)


class Work:
    """One transaction: what it added is kept only when it commits."""

    def __init__(self, world: World, scope: SalesScope) -> None:
        self.world, self.scope = world, scope
        self.orders = _Store(world.orders, scope)
        self.quotes = _Store(world.quotes, scope)
        self.artifacts = _Artifacts(world, scope)
        self.audit = _Audit()

    async def commit(self) -> None:
        for record in self.artifacts.pending:
            self.world.artifacts[(self.scope, record.artifact_id)] = record
        self.world.audit += self.audit.pending
        self.world.commits += 1

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None


class Objects:
    def __init__(self, world: World) -> None:
        self.world = world

    async def put_object(self, key: str, data: bytes, content_type: str) -> str:
        self.world.objects[key] = data
        return key

    async def get_object(self, key: str) -> bytes:
        return self.world.objects[key]


class Directory:
    async def list_members(self, context: AccessContext) -> list[WorkspaceMember]:
        return list(MEMBERS)


class QuoteCases:
    def __init__(self) -> None:
        self.cases: list[QuoteCase] = []

    async def cases_for_ycbg(self, scope: SalesScope, ycbg_no: str) -> Sequence[QuoteCase]:
        return [c for c in self.cases if c.ycbg is not None and c.ycbg.ycbg_no == ycbg_no]


class OrderCases:
    def __init__(self) -> None:
        self.cases: dict[uuid.UUID, OrderCase] = {}

    async def cases_for_po(
        self, scope: SalesScope, customer_code: str, po_no: str
    ) -> Sequence[OrderCase]:
        return [
            c
            for c in self.cases.values()
            if (c.customer_code, c.header.po_no) == (customer_code, po_no)
        ]


def quotation_service(cases: QuoteCases | None = None) -> QuotationService:
    catalog = MockSalesCatalog.load(SCOPE)
    return QuotationService(
        catalog=catalog,
        inbox=MockInbox.load(SCOPE),
        rfq_reader=ExcelRfqReader(),
        reply_reader=ExcelDesignReplyReader(),
        cases=cases or QuoteCases(),
        ledger=catalog,
        rules=QUOTE_RULES,
        pricing=load_pricing(POLICIES / "sales_pricing@1.0.0.yaml"),
    )


def _factory(world: World) -> Any:
    """A unit of work per scope over ``world``: as much of the port as the
    service uses."""
    return lambda scope: Work(world, scope)


def service(world: World, copy: ArtifactCopy = ARTIFACT_COPY) -> ArtifactService:
    return ArtifactService(
        uow=_factory(world),
        gate=GATE,
        storage=Objects(world),
        clock=FixedClock(NOW),
        ids=Uuid4Generator(),
        writer=WRITER,
        copy=copy,
        catalog=MockSalesCatalog.load(SCOPE),
        directory=Directory(),
        design=quotation_service(),
    )


# ------------------------------------------------------------ order cases --

_INTAKE_RULES = PlatformOrderRules(load_order_rules(POLICIES / "sales_order_rules@1.0.0.yaml"))


def intake(cases: OrderCases) -> OrderIntake:
    return OrderIntake(
        catalog=MockSalesCatalog.load(SCOPE),
        inbox=MockInbox.load(SCOPE),
        reader=mock_po_readers(),
        rules=_INTAKE_RULES,
        cases=cases,
        new_case_id=uuid.uuid4,
    )


async def in_review(message_id: str, cases: OrderCases | None = None) -> OrderCase:
    """The order a message opened, handed to the PIC as DW1 does at intake."""
    cases = cases if cases is not None else OrderCases()
    message = await MockInbox.load(SCOPE).get_message(SCOPE, message_id)
    assert message is not None
    outcome = await intake(cases).process(SCOPE, message)
    assert outcome.case is not None, message_id
    case = outcome.case.start_review()
    cases.cases[case.case_id] = case
    return case


def decided_all(case: OrderCase, by: uuid.UUID = AN) -> OrderCase:
    """Every open finding decided the way its code allows, by ``by``."""
    actor = Actor(user_id=by, capabilities=frozenset({Capability.ACKNOWLEDGE_EXPORT_CONTROL}))
    for finding in case.findings:
        if not finding.is_open:
            continue
        if finding.code is FindingCode.VALUE_UNCERTAIN or finding.code is (
            FindingCode.CUSTOMER_UNKNOWN
        ):
            value = case.customer_code if finding.code is FindingCode.CUSTOMER_UNKNOWN else "6100"
            disposition: Any = CorrectedBySales(value=value, source="PO gốc", by=by, at=T0)
        else:
            disposition = Accepted(reason="đã xem", by=by, at=T0)
        case = case.dispose(finding.key, disposition, actor)
    return case


def prepared(case: OrderCase) -> OrderCase:
    return case.prepare(Actor(user_id=AN), T0)


def uploaded(case: OrderCase) -> OrderCase:
    return prepared(case).record_bravo_entry(
        "SO26-1001", Actor(user_id=AN), T0, entry_compared=True
    )


def cross_checked(case: OrderCase) -> OrderCase:
    return uploaded(case).cross_check(Actor(user_id=DIEU), T0)


def confirmed(case: OrderCase) -> OrderCase:
    checked = cross_checked(case)
    return checked.confirm(
        Actor(user_id=AN), T0, {line.line_no: CONFIRMED_ON for line in checked.lines}
    )


async def confirmed_m05() -> OrderCase:
    """M05 (KMH, Japanese): every line the convert list did not map gets the
    candidate Sales confirms."""
    case = await in_review("M05")
    for line in case.lines:
        if not line.mapping.ready:
            case = await intake(OrderCases()).confirm_mapping(
                SCOPE, case, line.line_no, line.mapping.candidates[0], Actor(user_id=AN), T0
            )
    return confirmed(decided_all(case))


async def correction_requested_m04() -> OrderCase:
    case = await in_review("M04")
    case = case.dispose("price_mismatch:2", AskCustomer(by=AN, at=T0), Actor(user_id=AN))
    return case.request_correction()


async def change_review_m07() -> OrderCase:
    """M04 in Bravo, then its Rev.1 (M07): a change to apply in Bravo."""
    cases = OrderCases()
    case = await in_review("M04", cases)
    case = await intake(cases).confirm_mapping(SCOPE, case, 3, "CB-2008", Actor(user_id=AN), T0)
    cases.cases[case.case_id] = uploaded(decided_all(case))
    message = await MockInbox.load(SCOPE).get_message(SCOPE, "M07")
    assert message is not None
    outcome = await intake(cases).process(SCOPE, message)
    assert outcome.case is not None and outcome.case.status is OrderStatus.CHANGE_REVIEW
    return outcome.case


async def cannot_supply_m01() -> OrderCase:
    return (await in_review("M01")).close(CloseReason.CANNOT_SUPPLY, Actor(user_id=AN), T0)


# ------------------------------------------------------------ quote cases --


def _decision() -> PricingDecision:
    return PricingDecision(
        decided_by=DIEU,
        decided_at=T0,
        lme=LmeMonth(month="2026-09", usd_per_tonne=Decimal(10870)),
        lines=(
            LinePrice(
                line_no=1,
                unit_price=DECIDED,
                moq=Decimal(3000),
                lead_time_days=45,
                copper_basis=BAND,
            ),
        ),
        management_guidance=GUIDANCE,
    )


async def m10(step: str) -> QuoteCase:
    """M10 (KMH, Japanese) walked to ``step``."""
    cases = QuoteCases()
    quotation = quotation_service(cases)
    case = await quotation.open_case(SCOPE, "M10", uuid.uuid4())
    if step == "received":
        return case
    case = case.draft_ycbg()
    if step == "ycbg_drafted":
        return case
    case = case.record_ycbg(YCBG_M10, by=DIEU, at=T0)
    if step == "ycbg_recorded":
        return case
    case = case.send_to_design()
    cases.cases.append(case)
    reply = await quotation.take_design_reply(SCOPE, "M25")
    assert isinstance(reply, ReplyAttached)
    case = reply.case
    if step == "design_replied":
        return case
    if step == "declined":
        return case.decline_request(by=DIEU, at=T0, reason=DeclineReason.DESIGN_CANNOT)
    if step == "spec_discussion":
        return case.discuss_spec()
    case = await quotation.decide_price(SCOPE, case, _decision(), by=DIEU)
    case = await quotation.submit(
        SCOPE, case, quote_no=QUOTE_NO, issued_on=T0.date(), by=DIEU, at=T0
    )
    if step == "pending_approval":
        return case
    assert case.submission is not None
    case = case.approve(
        QuoteActor(user_id=GIANG, capabilities=frozenset({QuoteCapability.APPROVE})),
        at=NOW,
        document_sha256=case.submission.document_sha256,
    )
    if step == "approved":
        return case
    case = case.mark_sent(by=DIEU, at=NOW)
    assert step == "sent"
    return case


# Per kind: the case at the kind's state, and one before it.
type Builder = Callable[[], Awaitable[OrderCase | QuoteCase]]


async def _m01() -> OrderCase:
    return await in_review("M01")


async def _m04() -> OrderCase:
    return await in_review("M04")


async def _confirmed_m01() -> OrderCase:
    return confirmed(await in_review("M01"))


async def _confirmed_m13() -> OrderCase:
    return confirmed(decided_all(await in_review("M13")))


async def _uploaded_m27() -> OrderCase:
    return uploaded(decided_all(await in_review("M27")))


async def _candidate_m05() -> OrderCase:
    case = await in_review("M05")
    (line,) = [line for line in case.lines if line.mapping.status is MappingStatus.AMBIGUOUS]
    return await intake(OrderCases()).confirm_mapping(
        SCOPE, case, line.line_no, line.mapping.candidates[0], Actor(user_id=AN), T0
    )


def _quote(step: str) -> Builder:
    async def build() -> QuoteCase:
        return await m10(step)

    return build


KINDS: dict[str, tuple[Builder, Builder]] = {
    "bravo_upload": (lambda: _prepared_m01(), _m01),
    "cross_check_sheet": (_uploaded_m27, _m01),
    "confirmation_draft": (_confirmed_m01, lambda: _cross_checked_m01()),
    "portal_checklist": (_confirmed_m13, lambda: _uploaded_m13()),
    "correction_request": (correction_requested_m04, _m04),
    "change_summary": (change_review_m07, _m04),
    "convert_list_proposal": (_candidate_m05, _m01),
    "design_code_request": (_m04, _m01),
    "cannot_supply_draft": (cannot_supply_m01, _m01),
    "ycbg_draft": (_quote("ycbg_drafted"), _quote("received")),
    "design_request_draft": (_quote("ycbg_recorded"), _quote("ycbg_drafted")),
    "spec_discussion_draft": (_quote("spec_discussion"), _quote("design_replied")),
    "decline_draft": (_quote("declined"), _quote("design_replied")),
    "quotation_preview": (_quote("pending_approval"), _quote("design_replied")),
    "quotation_final": (_quote("approved"), _quote("pending_approval")),
    "send_draft": (_quote("approved"), _quote("pending_approval")),
    "master_list_update": (_quote("sent"), _quote("approved")),
}


async def _prepared_m01() -> OrderCase:
    return prepared(await in_review("M01"))


async def _cross_checked_m01() -> OrderCase:
    return cross_checked(await in_review("M01"))


async def _uploaded_m13() -> OrderCase:
    return cross_checked(decided_all(await in_review("M13")))


def _kind_of(case: OrderCase | QuoteCase) -> CaseKind:
    return CaseKind.ORDER if isinstance(case, OrderCase) else CaseKind.QUOTE


async def render(
    world: World,
    case: OrderCase | QuoteCase,
    kind: str,
    *,
    as_: AccessContext | None = None,
    svc: ArtifactService | None = None,
) -> list[ArtifactView]:
    world.put(case)
    svc = svc or service(world)
    who = as_ or context(DIEU if kind == "quotation_preview" else AN)
    if isinstance(case, OrderCase):
        return await svc.render_order(who, case.case_id, kind=kind, case_version=case.case_version)
    return await svc.render_quote(who, case.case_id, kind=kind, case_version=case.case_version)


async def download(
    world: World, case: OrderCase | QuoteCase, artifact_id: uuid.UUID, *, as_: AccessContext
) -> bytes:
    svc = service(world)
    if isinstance(case, OrderCase):
        return (await svc.order_artifact(as_, case.case_id, artifact_id)).data
    return (await svc.quote_artifact(as_, case.case_id, artifact_id)).data


def _record(case: OrderCase | QuoteCase, kind: str) -> ArtifactRecord:
    return ArtifactRecord(
        artifact_id=uuid.uuid4(),
        case_kind=_kind_of(case),
        case_id=case.case_id,
        case_version=case.case_version,
        kind=kind,
        template_ref="sales_test@1.0.0",
        sha256=hashlib.sha256(b"file").hexdigest(),
        content_type="application/octet-stream",
        size_bytes=4,
        created_by=AN,
        created_at=T0,
    )


def _bumped[CaseT: OrderCase | QuoteCase](case: CaseT) -> CaseT:
    """The same case one edit later, still in its state: what any change to
    a value, a mapping or a disposition does to the version."""
    bumped = type(case).model_validate({**dict(case), "case_version": case.case_version + 1})
    return cast(CaseT, bumped)


def _who(kind: str) -> AccessContext:
    return context(DIEU if kind == "quotation_preview" else AN)


# --------------------------------------------------------------- the table --


def test_every_kind_in_the_gate_tables_is_tested_here() -> None:
    assert set(KINDS) == set(ORDER_GATES) | set(QUOTE_GATES)


@pytest.mark.parametrize("kind", sorted(KINDS))
async def test_each_kind_renders_at_its_state_with_template_version_and_hash(kind: str) -> None:
    world = World()
    case = await KINDS[kind][0]()

    views = await render(world, case, kind)

    assert views
    for view in views:
        record = world.artifacts[(SCOPE, view.artifact_id)]
        data = world.objects[record.object_key(SCOPE)]
        assert record.object_key(SCOPE) == (
            f"{SCOPE.tenant_id}/{SCOPE.workspace_id}/sales/{case.case_id}/{record.artifact_id}"
        )
        assert (record.kind, record.case_version) == (kind, case.case_version)
        assert record.sha256 == hashlib.sha256(data).hexdigest() == view.sha256
        assert record.size_bytes == len(data)
        assert record.template_ref.endswith("@1.0.0"), record.template_ref
        assert record.content_type in (XLSX, PDF, EML)
        served = await download(world, case, record.artifact_id, as_=_who(kind))
        assert served == data
    assert [e.action for e in world.audit].count("sales.artifact.rendered") == len(views)


@pytest.mark.parametrize("kind", sorted(KINDS))
async def test_each_kind_is_refused_before_its_state(kind: str) -> None:
    world = World()
    before = await KINDS[kind][1]()
    world.put(before)
    stored = _record(before, kind)
    world.artifacts[(SCOPE, stored.artifact_id)] = stored
    world.objects[stored.object_key(SCOPE)] = b"file"

    with pytest.raises(ConflictError) as rendering:
        await render(world, before, kind)
    with pytest.raises(ConflictError) as downloading:
        await download(world, before, stored.artifact_id, as_=_who(kind))

    assert rendering.value.details["kind"] == kind
    assert downloading.value.details["kind"] == kind
    assert "reason" not in downloading.value.details  # the gate, not the version


@pytest.mark.parametrize("kind", sorted(KINDS))
async def test_each_kind_is_refused_after_an_edit_bumped_the_case_version(kind: str) -> None:
    world = World()
    case = await KINDS[kind][0]()
    (view, *_) = await render(world, case, kind)
    world.put(_bumped(case))

    with pytest.raises(ConflictError) as refused:
        await download(world, case, view.artifact_id, as_=_who(kind))

    assert refused.value.details["reason"] == "stale_artifact"
    assert refused.value.details["artifact_case_version"] == case.case_version
    # Rendered again at the new version, it is served.
    (fresh, *_) = await render(world, _bumped(case), kind)
    assert fresh.case_version == case.case_version + 1
    assert await download(world, case, fresh.artifact_id, as_=_who(kind))


async def test_a_render_names_the_version_the_caller_saw() -> None:
    world = World()
    case = await _prepared_m01()
    world.put(_bumped(case))

    with pytest.raises(ConflictError, match="đã thay đổi"):
        await service(world).render_order(
            context(), case.case_id, kind="bravo_upload", case_version=case.case_version
        )


async def test_rendering_again_at_the_same_version_returns_what_is_stored() -> None:
    world = World()
    case = await _prepared_m01()

    first = await render(world, case, "bravo_upload")
    again = await render(world, case, "bravo_upload")

    assert [v.artifact_id for v in again] == [v.artifact_id for v in first]
    assert len(world.objects) == 1


async def test_an_unknown_kind_is_refused() -> None:
    with pytest.raises(DomainError):
        await render(World(), await _prepared_m01(), "invoice")


async def test_a_bravo_upload_is_not_rendered_for_a_change_to_apply_in_bravo() -> None:
    """A revision of an order in Bravo is applied there; a new upload file
    would key the order a second time."""
    with pytest.raises(ConflictError):
        await render(World(), await change_review_m07(), "bravo_upload")


# ------------------------------------------------------ price and tenancy --


async def test_a_price_bearing_kind_needs_the_price_scope_to_render_or_download() -> None:
    world = World()
    case = await _prepared_m01()
    (view,) = await render(world, case, "bravo_upload")
    no_prices = context(AN, PIC_SCOPES - {"sales.price.read"})

    with pytest.raises(PermissionDeniedError) as rendering:
        await render(world, case, "bravo_upload", as_=no_prices)
    with pytest.raises(PermissionDeniedError) as downloading:
        await download(world, case, view.artifact_id, as_=no_prices)

    assert rendering.value.details["action"] == downloading.value.details["action"]
    assert downloading.value.details["action"] == "sales.price.read"


async def test_a_kind_without_prices_needs_no_price_scope() -> None:
    world = World()
    case = await _candidate_m05()
    no_prices = context(AN, PIC_SCOPES - {"sales.price.read"})

    (view,) = await render(world, case, "convert_list_proposal", as_=no_prices)

    assert await download(world, case, view.artifact_id, as_=no_prices)


async def test_another_tenants_case_and_artifact_are_not_found() -> None:
    world = World()
    case = await _prepared_m01()
    (view,) = await render(world, case, "bravo_upload")
    beta = context(AN, scope=OTHER)

    with pytest.raises(NotFoundError):
        await download(world, case, view.artifact_id, as_=beta)
    with pytest.raises(NotFoundError):
        await service(world).render_order(
            beta, case.case_id, kind="bravo_upload", case_version=case.case_version
        )


async def test_another_cases_artifact_is_not_found() -> None:
    world = World()
    first = await _prepared_m01()
    second = await _prepared_m01()
    world.put(second)
    (view,) = await render(world, first, "bravo_upload")

    with pytest.raises(NotFoundError):
        await download(world, second, view.artifact_id, as_=context())


async def test_bytes_that_are_not_the_recorded_ones_are_never_served() -> None:
    world = World()
    case = await _prepared_m01()
    (view,) = await render(world, case, "bravo_upload")
    record = world.artifacts[(SCOPE, view.artifact_id)]
    world.objects[record.object_key(SCOPE)] += b"tampered"

    with pytest.raises(InfrastructureError):
        await download(world, case, view.artifact_id, as_=context())


async def test_render_and_download_are_audited_with_ids_and_hashes_only() -> None:
    world = World()
    case = await _prepared_m01()
    (view,) = await render(world, case, "bravo_upload")
    await download(world, case, view.artifact_id, as_=context())

    rendered, downloaded = world.audit
    assert (rendered.action, downloaded.action) == (
        "sales.artifact.rendered",
        "sales.artifact.downloaded",
    )
    assert set(downloaded.details) == {
        "case_kind",
        "case_id",
        "case_version",
        "kind",
        "template_ref",
        "sha256",
    }
    text = repr([e.details for e in world.audit])
    for line in case.lines:
        assert str(line.po_line.unit_price) not in text


# ----------------------------------------------------------------- contents --


def _sheet_rows(data: bytes, sheet: int = 0) -> list[list[Any]]:
    book = load_workbook(io.BytesIO(data))
    return [[c.value for c in row] for row in book.worksheets[sheet].iter_rows()]


def _xlsx_text(data: bytes) -> str:
    book = load_workbook(io.BytesIO(data))
    return "\n".join(
        str(cell.value)
        for sheet in book.worksheets
        for row in sheet.iter_rows()
        for cell in row
        if cell.value is not None
    )


def _eml(data: bytes) -> email.message.EmailMessage:
    message = email.message_from_bytes(data, policy=policy.default)
    assert isinstance(message, email.message.EmailMessage)
    return message


def _body(data: bytes) -> str:
    part = _eml(data).get_body(("plain",))
    assert part is not None
    return str(part.get_content())


async def _rendered(case: OrderCase | QuoteCase, kind: str) -> list[tuple[ArtifactRecord, bytes]]:
    world = World()
    views = await render(world, case, kind)
    records = [world.artifacts[(SCOPE, v.artifact_id)] for v in views]
    return [(r, world.objects[r.object_key(SCOPE)]) for r in records]


async def _one(case: OrderCase | QuoteCase, kind: str) -> bytes:
    ((_, data),) = await _rendered(case, kind)
    return data


async def test_the_upload_file_holds_the_decided_lines_in_the_mock_layout() -> None:
    case = await _prepared_m01()
    data = await _one(case, "bravo_upload")

    header, *rows = _sheet_rows(data)
    layout = ARTIFACT_COPY.upload
    assert header == [c.header for c in layout.columns]
    fields = [c.field for c in layout.columns]
    assert len(rows) == len(case.lines)
    for row, line in zip(rows, case.lines, strict=True):
        values = dict(zip(fields, row, strict=True))
        assert values["prv_code"] == line.mapping.prv_code
        assert values["po_no"] == case.header.po_no
        assert Decimal(str(values["quantity"])) == line.po_line.quantity
        assert Decimal(str(values["unit_price"])) == line.po_line.unit_price
    assert "MOCK" in _xlsx_text(data)


async def test_a_description_starting_with_an_equals_sign_is_written_as_text() -> None:
    """M20 line 3's description is ``=HYPERLINK(...)``: a cell of type text
    with the quote prefix, never a formula (G29)."""
    case = await _prepared_m01_like("M20")
    data = await _one(case, "bravo_upload")

    sheet = load_workbook(io.BytesIO(data)).worksheets[0]
    column = [c.field for c in ARTIFACT_COPY.upload.columns].index("description") + 1
    cell = sheet.cell(row=1 + 3, column=column)
    assert str(cell.value).startswith("=HYPERLINK(")
    assert cell.data_type == "s"
    assert cell.quotePrefix is True
    raw = zipfile.ZipFile(io.BytesIO(data)).read("xl/worksheets/sheet1.xml")
    assert b"<f>" not in raw


async def _prepared_m01_like(message_id: str) -> OrderCase:
    return prepared(decided_all(await in_review(message_id)))


async def test_the_cross_check_sheet_names_who_typed_and_who_recorded_the_entry() -> None:
    case = await _uploaded_m27()
    data = await _one(case, "cross_check_sheet")
    text = _xlsx_text(data)

    assert "SO26-1001" in text
    assert "Nguyễn Văn An" in text  # recorded the Bravo entry and typed values
    rows = _sheet_rows(data)
    header_at = next(i for i, row in enumerate(rows) if row[:2] == ["Dòng", "Giá trị"])
    typed = {row[0] for row in rows[header_at + 1 :] if row[7] == "Nguyễn Văn An"}
    assert typed == {2, 4, 5, 6}  # the lines whose value_uncertain Sales corrected
    upload = {(row[0], row[1]): row[4] for row in rows[header_at + 1 :] if row[1] == "Đơn giá"}
    for line in case.lines:
        assert Decimal(str(upload[(line.line_no, "Đơn giá")])) == line.po_line.unit_price


async def test_the_confirmation_names_the_pic_the_checker_and_a_date_per_line() -> None:
    case = await _confirmed_m01()
    message = _eml(await _one(case, "confirmation_draft"))
    body = _body(await _one(case, "confirmation_draft"))

    assert "Nguyễn Văn An" in body and "Hoàng Thị Diệu" in body
    assert body.count(CONFIRMED_ON.strftime("%d/%m/%Y")) == len(case.lines)
    assert message["X-Unsent"] == "1"
    assert message["From"].addresses[0].addr_spec == "an.nguyen@alpha.local"
    assert message["Reply-To"].addresses[0].addr_spec == "sales@seller.example"
    customer = (await MockSalesCatalog.load(SCOPE).customer_by_code(SCOPE, "VLX")).data
    assert customer is not None
    assert {a.addr_spec for a in message["To"].addresses} == {c.address for c in customer.contacts}


async def test_a_customer_who_confirms_on_their_portal_gets_a_checklist_not_an_email() -> None:
    case = await _confirmed_m13()  # NRV confirms on its portal

    with pytest.raises(ConflictError) as refused:
        await _one(case, "confirmation_draft")
    data = await _one(case, "portal_checklist")

    assert refused.value.details["reason"] == "confirmation_channel"
    assert "Đã nhập trên portal" in _xlsx_text(data)
    listed = World()
    listed.put(case)
    available = (await service(listed).order_artifacts(context(), case.case_id)).available
    assert "portal_checklist" in available and "confirmation_draft" not in available


async def test_the_correction_request_lists_exactly_the_findings_sent_back() -> None:
    case = await correction_requested_m04()
    body = _body(await _one(case, "correction_request"))

    asked = [f for f in case.findings if f.disposition.kind.value == "ask_customer"]
    assert [f.key for f in asked] == ["price_mismatch:2"]
    assert "Line 2" in body and "0.658" in body and "0.6980" in body  # NRV writes English
    assert "NV-CB7-20-OR" not in body  # line 3's finding was not sent back
    assert body.count("\n- ") == 1


async def test_the_change_summary_lists_what_the_revision_changed() -> None:
    case = await change_review_m07()
    rows = _sheet_rows(await _one(case, "change_summary"))

    assert case.changes
    listed = {(row[0], row[2], row[3]) for row in rows if isinstance(row[0], int)}
    assert listed == {(c.line_no, c.before, c.after) for c in case.changes}


async def test_the_design_code_note_lists_the_line_without_a_code() -> None:
    body = _body(await _one(await _m04(), "design_code_request"))

    assert "NV-CB7-20-OR" in body
    assert "NV-HW22-BK" not in body  # mapped by the convert list


async def test_a_missing_language_refuses_to_render_and_stores_nothing() -> None:
    """KMH writes Japanese: with no ``ja`` send draft the copy refuses, with
    the reason, rather than sending Vietnamese (G33)."""
    emails = ARTIFACT_COPY.emails
    without_ja = SalesEmailCopy.model_validate(
        {
            **emails.model_dump(by_alias=True),
            "emails": {
                kind: {
                    lang: t
                    for lang, t in by_language.items()
                    if kind != "send_draft" or lang != "ja"
                }
                for kind, by_language in emails.model_dump(by_alias=True)["emails"].items()
            },
        }
    )
    copy = ArtifactCopy(
        emails=without_ja,
        documents=ARTIFACT_COPY.documents,
        upload=ARTIFACT_COPY.upload,
        design_mailboxes=ARTIFACT_COPY.design_mailboxes,
    )
    world = World()
    case = await m10("approved")

    with pytest.raises(ConflictError) as refused:
        await render(world, case, "send_draft", svc=service(world, copy))

    assert refused.value.details == {
        "kind": "send_draft",
        "language": "ja",
        "copy": "sales_emails@1.0.0",
        "reason": "template_missing",
    }
    assert not world.objects and not world.artifacts


@pytest.mark.parametrize(
    ("build", "language", "expected"),
    [
        (_confirmed_m01, "vi", "Kính gửi"),
        (lambda: _confirmed_cvg(), "en", "Dear"),
        (confirmed_m05, "ja", "御中"),
    ],
)
async def test_an_order_confirmation_renders_in_each_language(
    build: Builder, language: str, expected: str
) -> None:
    body = _body(await _one(await build(), "confirmation_draft"))

    assert expected in body


async def _confirmed_cvg() -> OrderCase:
    return confirmed(decided_all(await in_review("M02")))


# ---------------------------------------------------------------- quotation --


async def test_m10_quotation_is_japanese_and_from_the_submitted_document_only() -> None:
    case = await m10("approved")
    files = {r.content_type: data for r, data in await _rendered(case, "quotation_final")}

    pdf_text = "".join(page.extract_text() for page in PdfReader(io.BytesIO(files[PDF])).pages)
    xlsx_text = _xlsx_text(files[XLSX])
    assert case.submission is not None and case.approval is not None
    for text in (pdf_text, xlsx_text):
        assert "御見積書" in text and QUOTE_NO in text
        assert "0.689" in text  # 0.6890: a number in the xlsx, printed in full in the PDF
        assert case.submission.document_sha256 in text
        assert "Đỗ Minh Giang" in text  # the approver, by name
    assert {r.template_ref for r, _ in await _rendered(case, "quotation_final")} == {
        "sales_documents.quotation.ja@1.0.0"
    }


async def test_the_preview_says_it_is_not_approved_and_is_only_for_pricer_and_approvers() -> None:
    case = await m10("pending_approval")
    files = {r.content_type: d for r, d in await _rendered(case, "quotation_preview")}
    assert "プレビュー" in _xlsx_text(files[XLSX])

    world = World()
    with pytest.raises(ConflictError):  # An neither priced it nor approves
        await render(world, case, "quotation_preview", as_=context(AN))
    assert await render(world, case, "quotation_preview", as_=context(DIEU))  # the pricer


async def test_the_send_draft_attaches_the_stored_final_files_and_names_the_spec() -> None:
    world = World()
    case = await m10("approved")
    finals = await render(world, case, "quotation_final")
    (draft,) = await render(world, case, "send_draft")

    message = _eml(world.objects[world.artifacts[(SCOPE, draft.artifact_id)].object_key(SCOPE)])
    attached = {
        hashlib.sha256(part.get_content()).hexdigest() for part in message.iter_attachments()
    }
    assert attached == {view.sha256 for view in finals}
    assert case.submission is not None
    (line,) = case.submission.document.lines
    assert line.spec_no in _body(
        world.objects[world.artifacts[(SCOPE, draft.artifact_id)].object_key(SCOPE)]
    )
    assert {a.addr_spec for a in message["To"].addresses} == {
        r.address for r in case.submission.document.recipients
    }


async def test_no_customer_facing_artifact_carries_another_customers_price_or_guidance() -> None:
    """M10's evidence holds other customers' prices and the reference, and its
    decision a management instruction: none reaches the customer."""
    texts: list[str] = []
    for step, kinds in (
        ("approved", ("quotation_final", "send_draft")),
        ("pending_approval", ("quotation_preview",)),
        ("spec_discussion", ("spec_discussion_draft",)),
        ("declined", ("decline_draft",)),
    ):
        case = await m10(step)
        for kind in kinds:
            for record, data in await _rendered(case, kind):
                if record.content_type == XLSX:
                    texts.append(_xlsx_text(data))
                elif record.content_type == PDF:
                    texts.append(
                        "".join(p.extract_text() for p in PdfReader(io.BytesIO(data)).pages)
                    )
                else:
                    message = _eml(data)
                    texts.append(_body(data))
                    for part in message.iter_attachments():
                        content = part.get_content()
                        texts.append(
                            _xlsx_text(content)
                            if str(part.get_filename()).endswith(".xlsx")
                            else "".join(
                                p.extract_text() for p in PdfReader(io.BytesIO(content)).pages
                            )
                        )
    joined = "\n".join(texts)
    assert "0.689" in joined  # the check can see a price when there is one
    for internal in INTERNAL_PRICES:
        # As printed, and as a spreadsheet number reads back (0.7120 -> 0.712).
        for form in (internal, str(Decimal(internal).normalize())):
            assert form not in joined, form
    assert GUIDANCE not in joined


async def test_the_master_list_update_holds_the_sent_quotation_rows() -> None:
    case = await m10("sent")
    text = _xlsx_text(await _one(case, "master_list_update"))

    rows: tuple[Quotation, ...] = case.master_list_rows()
    for row in rows:
        assert row.quote_no in text and row.prv_code in text
    assert "MOCK" in text


async def test_the_decline_draft_gives_the_reason_in_the_customers_language() -> None:
    body = _body(await _one(await m10("declined"), "decline_draft"))

    assert "弊社設計が対応できない" in body


async def test_the_ycbg_and_the_design_request_go_to_design_in_vietnamese() -> None:
    form = _xlsx_text(await _one(await m10("ycbg_recorded"), "ycbg_draft"))
    message = _eml(await _one(await m10("ycbg_recorded"), "design_request_draft"))

    assert YCBG_M10 in form and "MOCK" in form
    assert [a.addr_spec for a in message["To"].addresses] == list(ARTIFACT_COPY.design_mailboxes)
    assert YCBG_M10 in str(message["Subject"])


# ----------------------------------------------------------------- the copy --


def test_every_customer_draft_has_every_language_and_every_internal_one_vietnamese() -> None:
    customer = {
        "confirmation_draft",
        "correction_request",
        "cannot_supply_draft",
        "spec_discussion_draft",
        "decline_draft",
        "send_draft",
    }
    emails = ARTIFACT_COPY.emails.emails
    for kind in customer:
        assert set(emails[kind]) == {"vi", "en", "ja"}, kind
    for kind in set(emails) - customer:
        assert set(emails[kind]) == {"vi"}, kind
    assert set(ARTIFACT_COPY.documents.documents["quotation"]) == {"vi", "en", "ja"}


def test_a_template_naming_a_value_the_draft_lacks_refuses_to_render() -> None:
    from dw_sales.application.artifact_content import fill

    with pytest.raises(ConflictError) as refused:
        fill("Ngày ${confirmed_date}", {"po_no": "X"}, ref="t@1.0.0")

    assert refused.value.details["reason"] == "template_value_unknown"


def test_a_value_is_substituted_as_text_never_read_as_a_template() -> None:
    from dw_sales.application.artifact_content import fill

    assert fill("${a}", {"a": "${b} $c"}, ref="t@1.0.0") == "${b} $c"
