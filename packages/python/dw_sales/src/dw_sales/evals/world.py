"""DW1 in one process: the real Sales services over a sample set, cases in memory.

The eval smoke runs on every push without a database, so the graders cannot
reach PostgreSQL. What they need is the path the API serves: the services
`dw_sales.application.services.assemble` builds, the readers, the checks and
the policies the API loads (`load_sales_policies`). Only the case store is
replaced, by `MemoryStore` below, which keeps each scope's cases in memory,
one transaction at a time.

DW1's runs go through the agent runtime as in the API: the real runner and
approval flow over in-memory stores (`dw_agent_runtime.testing.memory_runtime`),
with DW1's graph, worker config and approval rules registered by the same
call the API makes (`dw_sales.workflows.graph.register`). A quotation approval
or a cross-check is decided on the platform approval the run paused on.

What this world does not show, and where it is shown instead: row-level
security, the store's own CHECK constraints (checker not a maker, approver
not the pricer) and grants are PostgreSQL's, tested by the `dw_sales` and
`apps/api` integration suites. A guard the domain, a service or the approval
flow holds is the same code here as in the API.

A **sample set** is a directory of master data and a mailbox in the mock
adapters' format (`adapters/mock/README.md`). The fictional set in git is the
default; Proterial's sample set, kept outside git, is the same layout in
another directory, so the graders run on it unchanged.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import uuid
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from dw_agent_runtime.ports import RunAllowancePort
from dw_agent_runtime.registry import parse_worker_file
from dw_agent_runtime.testing.memory_runtime import MemoryApprovals, MemoryRuntime
from dw_kernel.errors import ConflictError
from dw_kernel.ids import TenantId, WorkspaceId
from dw_kernel.pagination import Page, PageRequest
from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_observability.telemetry import NullTelemetry, TelemetryPort
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_platform.application.directory import WorkspaceMember
from dw_platform.domain.audit import AuditEntry, AuditEvent
from dw_sales.adapters.artifact_files import ArtifactFiles
from dw_sales.adapters.assembly import model_requests
from dw_sales.adapters.memory_rules import MemoryRuleVersions
from dw_sales.adapters.mock import MockInbox, MockSalesCatalog
from dw_sales.adapters.mock.fixtures import ATTACHMENTS_DIR, DATA_DIR
from dw_sales.adapters.order_rules import load_tenant_order_rules
from dw_sales.adapters.policy_files import SalesPolicies, load_sales_policies, rule_book
from dw_sales.adapters.readers import mock_po_readers
from dw_sales.adapters.rfq_excel import ExcelDesignReplyReader, ExcelQuoteForms, ExcelRfqReader
from dw_sales.adapters.runtime import RuntimeDw1Runs
from dw_sales.adapters.source_view import FileSourceView
from dw_sales.application.case_store import (
    ArtifactRecord,
    CaseEvent,
    CaseOrigin,
    LoggedEvent,
    LoggedMessage,
    SalesUnitOfWork,
    ServedSource,
    SourceRegion,
    Stored,
    WorkerState,
)
from dw_sales.application.handoffs import HandoffReader
from dw_sales.application.layouts import (
    LAYOUT_DECIDED,
    LayoutChecks,
    LayoutPrefiller,
    LayoutSettlement,
)
from dw_sales.application.malware import MalwareScanPort, ScannedInbox
from dw_sales.application.message_intent import IntentReader
from dw_sales.application.model_reading import DescriptionReader, InterpretationPort
from dw_sales.application.order_intake import OrderIntake
from dw_sales.application.ports import InboxPort, SalesScope
from dw_sales.application.quotation import QuotationService
from dw_sales.application.reply_intent import ReplyReader
from dw_sales.application.rules import RuleBookOrderRules
from dw_sales.application.runs import subject_of
from dw_sales.application.services import SalesServices, assemble
from dw_sales.application.source import required_regions
from dw_sales.application.threads import ThreadLinks
from dw_sales.application.views import MessageDispositionView
from dw_sales.domain.dispositions import CaseKind, DispositionKind, MessageDisposition
from dw_sales.domain.layouts import LayoutStatus, PoLayout
from dw_sales.domain.orders import OrderCase
from dw_sales.domain.quotes import QuoteCase
from dw_sales.evals.overview_memory import PythonOverviewReader
from dw_sales.testing.scanners import NoMalware
from dw_sales.workflows.graph import register

ALPHA = SalesScope(TenantId(uuid.UUID(int=0xA1FA)), WorkspaceId(uuid.UUID(int=0xA1FB)))
BETA = SalesScope(TenantId(uuid.UUID(int=0xBE7A)), WorkspaceId(uuid.UUID(int=0xBE7B)))
# After the last mock message arrived and the last LME month was published.
NOW = datetime(2026, 10, 5, 3, 0, tzinfo=UTC)


# ------------------------------------------------------------ sample set --


@dataclass(frozen=True, slots=True)
class SampleSet:
    """Master data and a mailbox in the mock adapters' layout."""

    data_dir: Path
    attachments_dir: Path

    @classmethod
    def of(cls, repo_root: Path, spec: dict[str, Any] | None) -> SampleSet:
        """The set a case names (``{"data_dir", "attachments_dir"}``,
        relative to the repository or absolute), else the fictional one."""
        if not spec:
            return cls(DATA_DIR, ATTACHMENTS_DIR)
        return cls(
            _path(repo_root, spec["data_dir"]),
            _path(repo_root, spec["attachments_dir"]),
        )


def _path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


class SampleWith:
    """The fictional sample set with ``messages`` added to its mailbox, in a
    temporary copy (a context manager). A message names its ``message_id``,
    ``sender``, ``subject``, ``received_at``, ``body`` and ``authentication``,
    and may name ``internet_message_id`` and ``references`` (a reply in a
    thread, ticket 32)."""

    def __init__(self, messages: Sequence[Mapping[str, Any]]) -> None:
        self._messages = messages
        self._dir: tempfile.TemporaryDirectory[str] | None = None

    def __enter__(self) -> SampleSet:
        self._dir = tempfile.TemporaryDirectory()
        root = Path(self._dir.name)
        shutil.copytree(DATA_DIR, root / "data")
        shutil.copytree(ATTACHMENTS_DIR, root / "attachments")
        inbox = root / "data" / "inbox.json"
        listed = json.loads(inbox.read_text(encoding="utf-8"))
        for spec in self._messages:
            listed.append(
                {
                    "message_id": spec["message_id"],
                    "sender": {"address": spec["sender"], "display_name": ""},
                    "subject": spec["subject"],
                    "received_at": spec["received_at"],
                    "body_text": spec["body"],
                    "attachments": [],
                    "authentication": spec["authentication"],
                    "internet_message_id": spec.get("internet_message_id"),
                    "references": list(spec.get("references", ())),
                }
            )
        inbox.write_text(json.dumps(listed, ensure_ascii=False), encoding="utf-8")
        return SampleSet(root / "data", root / "attachments")

    def __exit__(self, *exc: object) -> None:
        assert self._dir is not None
        self._dir.cleanup()


# --------------------------------------------------------------- callers --


@dataclass(frozen=True, slots=True)
class Caller:
    """A person the eval acts as, described by the scopes they hold.

    Which role holds which scope is the sales migration's to say (tested
    against the database by `test_sales_roles.py`); an eval names the scopes
    a step needs, so a grader never restates a role.
    """

    user_id: uuid.UUID
    name: str
    email: str
    scopes: frozenset[str]

    def member(self) -> WorkspaceMember:
        return WorkspaceMember(self.user_id, self.name, self.email, (), (), "sales")

    def context(self, scope: SalesScope = ALPHA) -> AccessContext:
        return AccessContext(
            tenant_id=scope.tenant_id.value,
            workspace_id=scope.workspace_id.value,
            principal_id=self.user_id,
            roles=frozenset(),
            scopes=self.scopes,
            plan_id="professional",
        )


# --------------------------------------------------------- memory store --


@dataclass
class _ScopeState:
    """Everything one workspace keeps; copied into a transaction and back."""

    orders: dict[uuid.UUID, Stored[OrderCase]] = field(default_factory=dict)
    quotes: dict[uuid.UUID, Stored[QuoteCase]] = field(default_factory=dict)
    messages: dict[str, LoggedMessage] = field(default_factory=dict)
    events: list[LoggedEvent] = field(default_factory=list)
    served: set[ServedSource] = field(default_factory=set)
    artifacts: dict[uuid.UUID, ArtifactRecord] = field(default_factory=dict)
    worker: WorkerState = field(default_factory=lambda: WorkerState(paused=False))
    audit: list[AuditEvent] = field(default_factory=list)
    layouts: dict[uuid.UUID, PoLayout] = field(default_factory=dict)

    def copy(self) -> _ScopeState:
        # The values are frozen models; copying the containers is enough.
        return _ScopeState(
            orders=dict(self.orders),
            quotes=dict(self.quotes),
            messages=dict(self.messages),
            events=list(self.events),
            served=set(self.served),
            artifacts=dict(self.artifacts),
            worker=self.worker,
            audit=list(self.audit),
            layouts=dict(self.layouts),
        )


def _logged(
    kind: CaseKind, case: OrderCase | QuoteCase, was: str | None, event: CaseEvent
) -> LoggedEvent:
    return LoggedEvent(
        case_kind=kind,
        case_id=case.case_id,
        case_version=case.case_version,
        action=event.action,
        from_status=was,
        to_status=case.status.value,
        actor_kind=event.actor.kind,
        occurred_at=event.occurred_at,
    )


class _Cases[CaseT: (OrderCase, QuoteCase)]:
    """`OrderCaseStorePort` / `QuoteCaseStorePort` over one transaction's state.

    Refuses what the SQL store refuses: a case id, or a message, already on a
    stored case; a case opened with revisions; a save decided on another
    version than the stored one.
    """

    def __init__(
        self, held: dict[uuid.UUID, Stored[CaseT]], events: list[LoggedEvent], kind: CaseKind
    ) -> None:
        self._held: dict[uuid.UUID, Stored[CaseT]] = held
        self._events: list[LoggedEvent] = events
        self._kind = kind

    async def get(self, case_id: uuid.UUID) -> Stored[CaseT] | None:
        return self._held.get(case_id)

    async def list_all(self) -> Sequence[Stored[CaseT]]:
        return list(reversed(self._held.values()))

    async def add(self, case: CaseT, origin: CaseOrigin, event: CaseEvent) -> None:
        if case.case_id in self._held or any(
            _message_of(s.case) == _message_of(case) for s in self._held.values()
        ):
            raise ConflictError("the case or its message is already stored")
        if isinstance(case, OrderCase) and case.superseded:
            raise ConflictError("a case is opened with one revision")
        self._held[case.case_id] = Stored(case, origin)
        self._events.append(_logged(self._kind, case, None, event))

    async def save(self, case: CaseT, *, expected_version: int, event: CaseEvent) -> None:
        stored = self._held.get(case.case_id)
        if stored is None or stored.case.case_version != expected_version:
            raise ConflictError("the case changed since it was read")
        if case.case_version <= expected_version:
            raise ConflictError("a saved case moves to a later version")
        self._held[case.case_id] = Stored(case, stored.origin)
        self._events.append(_logged(self._kind, case, stored.case.status.value, event))

    async def assign(self, case_id: uuid.UUID, assigned_to: uuid.UUID | None) -> None:
        stored = self._held[case_id]
        origin = CaseOrigin(assigned_to, stored.origin.release_manifest_ref)
        self._held[case_id] = Stored(stored.case, origin)


def _message_of(case: OrderCase | QuoteCase) -> str:
    return case.message_id if isinstance(case, OrderCase) else case.request.message_id


class _Messages:
    def __init__(self, held: dict[str, LoggedMessage]) -> None:
        self._held = held

    async def record(self, disposition: MessageDisposition, processed_at: datetime) -> None:
        # Refuses what the SQL log refuses: only a routed message is replaced.
        earlier = self._held.get(disposition.message_id)
        if earlier is not None and earlier.disposition.kind is not DispositionKind.ROUTED_TO_SALES:
            raise ConflictError(
                "the message is already on a case",
                details={
                    "message_id": disposition.message_id,
                    "rule": "message_already_processed",
                },
            )
        self._held.pop(disposition.message_id, None)
        self._held[disposition.message_id] = LoggedMessage(disposition, processed_at)

    async def get(self, message_id: str) -> MessageDisposition | None:
        logged = self._held.get(message_id)
        return None if logged is None else logged.disposition

    async def list_all(self) -> Sequence[LoggedMessage]:
        return list(reversed(self._held.values()))


class _Served:
    def __init__(self, held: set[ServedSource]) -> None:
        self._held = held

    async def record(self, served: ServedSource) -> None:
        if not any(_region_key(s) == _region_key(served) for s in self._held):
            self._held.add(served)

    async def served(
        self, principal_id: uuid.UUID, case_kind: CaseKind, case_id: uuid.UUID, case_version: int
    ) -> frozenset[SourceRegion]:
        return frozenset(
            SourceRegion(s.attachment_id, s.page, s.sheet)
            for s in self._held
            if (s.principal_id, s.case_kind, s.case_id, s.case_version)
            == (principal_id, case_kind, case_id, case_version)
        )


def _region_key(s: ServedSource) -> tuple[object, ...]:
    return (
        s.principal_id,
        s.case_kind,
        s.case_id,
        s.case_version,
        s.attachment_id,
        s.page,
        s.sheet,
    )


class _Artifacts:
    def __init__(self, held: dict[uuid.UUID, ArtifactRecord]) -> None:
        self._held = held

    async def add(self, artifact: ArtifactRecord) -> None:
        if artifact.artifact_id in self._held:
            raise ConflictError("the artifact is already recorded")
        self._held[artifact.artifact_id] = artifact

    async def get(self, artifact_id: uuid.UUID) -> ArtifactRecord | None:
        return self._held.get(artifact_id)

    async def for_case(self, case_kind: CaseKind, case_id: uuid.UUID) -> Sequence[ArtifactRecord]:
        return [r for r in self._held.values() if (r.case_kind, r.case_id) == (case_kind, case_id)]


class _Worker:
    def __init__(self, state: _ScopeState) -> None:
        self._state = state

    async def state(self) -> WorkerState:
        return self._state.worker

    async def set(self, state: WorkerState) -> None:
        self._state.worker = state


class _Layouts:
    """`LayoutStorePort` over one transaction's state; refuses what the SQL
    store refuses: a second layout under one id, and a decision on a layout
    decided meanwhile."""

    def __init__(self, held: dict[uuid.UUID, PoLayout]) -> None:
        self._held = held

    async def get(self, layout_id: uuid.UUID) -> PoLayout | None:
        return self._held.get(layout_id)

    async def list_all(self) -> Sequence[PoLayout]:
        return list(reversed(self._held.values()))

    async def add(self, layout: PoLayout) -> None:
        if layout.layout_id in self._held:
            raise ConflictError("the layout is already stored")
        self._held[layout.layout_id] = layout

    async def save(self, layout: PoLayout, *, expected: LayoutStatus) -> None:
        stored = self._held.get(layout.layout_id)
        if stored is None or stored.status != expected:
            raise ConflictError("the layout was decided meanwhile")
        self._held[layout.layout_id] = layout


class _Audit:
    """The platform's audit port as a Sales transaction writes it."""

    def __init__(self, held: list[AuditEvent]) -> None:
        self._held = held

    async def append(self, event: AuditEvent) -> None:
        self._held.append(event)

    async def list_page(
        self,
        request: PageRequest,
        *,
        workspace_id: uuid.UUID,
        support_grant_id: uuid.UUID | None = None,
    ) -> Page[AuditEntry]:
        raise NotImplementedError("not exercised by the Sales services")

    async def list_for_run(
        self, run_id: uuid.UUID, *, workspace_id: uuid.UUID, limit: int = 100
    ) -> list[AuditEvent]:
        raise NotImplementedError("not exercised by the Sales services")


class _Work:
    """`SalesUnitOfWork`: one scope's state, copied in, written back on commit."""

    def __init__(self, store: MemoryStore, scope: SalesScope) -> None:
        self._store, self._scope = store, scope
        state = store.state(scope).copy()
        self._state = state
        self.orders: _Cases[OrderCase] = _Cases(state.orders, state.events, CaseKind.ORDER)
        self.quotes: _Cases[QuoteCase] = _Cases(state.quotes, state.events, CaseKind.QUOTE)
        self.messages = _Messages(state.messages)
        self.served = _Served(state.served)
        self.artifacts = _Artifacts(state.artifacts)
        self.worker = _Worker(state)
        self.audit = _Audit(state.audit)
        self.layouts = _Layouts(state.layouts)
        # The runtime's approvals, written at once (no rollback in memory): a
        # layout's proposal opens one here (ticket 30).
        self.approvals = store.approvals.scoped(scope.tenant_id.value)
        # Written at once, like the approvals: a tenant's, whatever workspace.
        self.rule_versions = store.rule_versions.for_tenant(scope.tenant_id.value)

    @property
    def overview(self) -> PythonOverviewReader:
        """The overview and the work list, computed in Python over what this
        transaction holds (the SQL reader is held to the same answers)."""
        state = self._state
        return PythonOverviewReader(
            orders=list(state.orders.values()),
            quotes=list(state.quotes.values()),
            messages=list(state.messages.values()),
            events=list(state.events),
        )

    async def commit(self) -> None:
        self._store.states[self._scope] = self._state
        self._state = self._state.copy()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None


class MemoryStore:
    """Implements `SalesUnitOfWorkFactory`, `OrderCaseLookupPort`,
    `QuoteCaseLookupPort` and `LayoutLookupPort` in memory, per scope: what one
    scope committed no other scope reads."""

    def __init__(self, approvals: MemoryApprovals | None = None) -> None:
        self.states: dict[SalesScope, _ScopeState] = {}
        self.approvals = approvals or MemoryApprovals(FixedClock(NOW))
        # A tenant's own rule versions: per tenant, not per workspace (ticket 19).
        self.rule_versions = MemoryRuleVersions()

    def state(self, scope: SalesScope) -> _ScopeState:
        return self.states.setdefault(scope, _ScopeState())

    def __call__(self, scope: SalesScope) -> SalesUnitOfWork:
        return _Work(self, scope)

    async def cases_for_po(
        self, scope: SalesScope, customer_code: str, po_no: str
    ) -> Sequence[OrderCase]:
        return [
            s.case
            for s in self.state(scope).orders.values()
            if s.case.customer_code == customer_code and s.case.header.po_no == po_no
        ]

    async def approved(self, scope: SalesScope, customer_code: str) -> Sequence[PoLayout]:
        return [
            layout
            for layout in self.state(scope).layouts.values()
            if layout.customer_code == customer_code and layout.status == "approved"
        ]

    async def read_count(self, scope: SalesScope, layout_ref: str) -> int:
        return sum(
            1
            for stored in self.state(scope).orders.values()
            if layout_ref
            in {stored.case.document.layout_ref}
            | {old.document.layout_ref for old in stored.case.superseded}
        )

    async def cases_for_ycbg(self, scope: SalesScope, ycbg_no: str) -> Sequence[QuoteCase]:
        return [
            s.case
            for s in self.state(scope).quotes.values()
            if s.case.ycbg is not None and s.case.ycbg.ycbg_no == ycbg_no
        ]


# ------------------------------------------------- the platform's pieces --


@dataclass
class Directory:
    """`MemberDirectoryPort` and `ScopeHoldersPort` over the eval's callers."""

    callers: tuple[Caller, ...]

    async def list_members(self, context: AccessContext) -> list[WorkspaceMember]:
        return [caller.member() for caller in self.callers]

    async def holding(
        self, tenant_id: uuid.UUID, workspace_id: uuid.UUID, scopes: frozenset[str]
    ) -> list[uuid.UUID]:
        return [c.user_id for c in self.callers if c.scopes & scopes]


@dataclass(frozen=True, slots=True)
class Delivered:
    recipients: tuple[uuid.UUID, ...]
    source_key: str
    title: str
    body: str
    link: str | None


@dataclass
class Notifications:
    """`NotificationSenderPort`, idempotent by source key, keeping what it sent."""

    sent: list[Delivered] = field(default_factory=list)

    async def deliver(
        self,
        context: AccessContext,
        *,
        recipients: Sequence[uuid.UUID],
        source_key: str,
        title: str,
        body: str,
        link: str | None,
    ) -> None:
        if any(d.source_key == source_key for d in self.sent):
            return
        self.sent.append(Delivered(tuple(recipients), source_key, title, body, link))


@dataclass
class Objects:
    """`ArtifactBytesPort` over a dict, by the key the record derived."""

    held: dict[str, bytes] = field(default_factory=dict)

    async def put_object(self, key: str, data: bytes, content_type: str) -> str:
        self.held[key] = data
        return key

    async def get_object(self, key: str) -> bytes:
        return self.held[key]


# ----------------------------------------------------------------- world --

type Between = Callable[[str, MessageDispositionView], Awaitable[None]]


@dataclass
class World:
    """The services, and what they wrote, for one eval case."""

    services: SalesServices
    store: MemoryStore
    catalog: MockSalesCatalog
    inbox: InboxPort
    notifications: Notifications
    objects: Objects
    policies: SalesPolicies
    sample: SampleSet
    runtime: MemoryRuntime
    runs: RuntimeDw1Runs
    layout_settlement: LayoutSettlement

    async def decide_layout(
        self,
        caller: Caller,
        layout_id: uuid.UUID,
        *,
        approve: bool,
        comment: str,
        scope: SalesScope = ALPHA,
    ) -> None:
        """A decision on the approval a layout's proposal opened, as the API's
        `POST /approvals/{id}/decisions` makes it, on the version shown; then
        carried out as the worker carries it out (`settle_layouts`)."""
        layout = self.store.state(scope).layouts[layout_id]
        await self.runtime.approval_flow.decide(
            approval_id=layout.approval_id,
            approve=approve,
            comment=comment,
            context=caller.context(scope),
            authorization=ScopeAuthorizationService(),
            subject_version=layout.version,
        )
        await self.settle_layouts()

    async def settle_layouts(self) -> None:
        """Each `sales.layout.decided` the decisions announced, handed to the
        settlement with the envelope's tenancy and the decider, as the
        worker's handler hands it (`dw_worker.consumers.sales_layouts`)."""
        events = self.runtime.outbox.events
        for event in [e for e in events if e.event_type == LAYOUT_DECIDED]:
            events.remove(event)
            decider = AccessContext(
                tenant_id=event.tenant_id.value,
                workspace_id=event.workspace_id.value,
                principal_id=uuid.UUID(str(event.payload["decided_by"])),
                roles=frozenset(),
                scopes=frozenset(),
                plan_id="background",
            )
            await self.layout_settlement.settle(
                uuid.UUID(str(event.payload["approval_id"])), decider
            )

    async def process_each(
        self,
        caller: Caller,
        message_ids: Iterable[str] | None = None,
        scope: SalesScope = ALPHA,
        *,
        between: Between | None = None,
    ) -> dict[str, tuple[MessageDispositionView, OrderCase | QuoteCase | None]]:
        """Every message (oldest first), or the ones named, processed one at
        a time; each with its disposition and the case as it stood right after.

        ``between`` is what Sales does after a message and before the next
        arrives (recording a YCBG, say), so a later message meets the case as
        the process leaves it rather than as DW1 opened it.
        """
        context = caller.context(scope)
        if message_ids is None:
            message_ids = [m.message_id for m in await self.inbox.list_messages(scope)]
        seen: dict[str, tuple[MessageDispositionView, OrderCase | QuoteCase | None]] = {}
        for message_id in message_ids:
            disposition = await self.services.dw1.process(context, message_id)
            seen[message_id] = (disposition, self.case(disposition, scope))
            if between is not None:
                await between(message_id, disposition)
        return seen

    def case(
        self, disposition: MessageDispositionView, scope: SalesScope = ALPHA
    ) -> OrderCase | QuoteCase | None:
        if disposition.case_id is None:
            return None
        state = self.store.state(scope)
        held = state.orders if disposition.case_kind is CaseKind.ORDER else state.quotes
        stored = held.get(disposition.case_id)
        return None if stored is None else stored.case

    def order(self, case_id: uuid.UUID, scope: SalesScope = ALPHA) -> OrderCase:
        return self.store.state(scope).orders[case_id].case

    def quote(self, case_id: uuid.UUID, scope: SalesScope = ALPHA) -> QuoteCase:
        return self.store.state(scope).quotes[case_id].case

    def audit(self, scope: SalesScope = ALPHA) -> list[AuditEvent]:
        return list(self.store.state(scope).audit)

    async def open_sources(self, caller: Caller, case_id: uuid.UUID) -> None:
        """Every region of the order's source `prepare` and the cross-check
        need, served to ``caller`` at the case's current version."""
        context = caller.context()
        for region in sorted(
            required_regions(self.order(case_id)),
            key=lambda r: (r.attachment_id, r.page or 0, r.sheet or ""),
        ):
            await self.services.sources.order_source(
                context, case_id, region.attachment_id, page=region.page, sheet=region.sheet
            )

    async def walk_to_uploaded(
        self, preparer: Caller, case_id: uuid.UUID, *, recorder: Caller | None = None
    ) -> OrderCase:
        """Prepared by ``preparer``, its Bravo entry recorded by ``recorder``."""
        await self.open_sources(preparer, case_id)
        await self.services.order_commands.prepare(
            preparer.context(), case_id, case_version=self.order(case_id).case_version
        )
        await self.services.dw1.record_bravo_entry(
            (recorder or preparer).context(),
            case_id,
            case_version=self.order(case_id).case_version,
            so_no="SO26-1001",
            entry_compared=True,
        )
        return self.order(case_id)

    async def cross_check(self, checker: Caller, case_id: uuid.UUID) -> OrderCase:
        await self.open_sources(checker, case_id)
        await self.decide(checker, CaseKind.ORDER, case_id, approve=True, comment="Đã đối chiếu")
        return self.order(case_id)

    async def decide(
        self,
        caller: Caller,
        kind: CaseKind,
        case_id: uuid.UUID,
        *,
        approve: bool,
        comment: str,
        reasons: dict[str, str] | None = None,
    ) -> None:
        """A decision on the approval the case's run waits on, as the API's
        `POST /approvals/{id}/decisions` makes it, on the version shown."""
        approval_id = await self.runs.pending(caller.context(), subject_of(kind, case_id))
        if approval_id is None:
            raise ConflictError("the case waits on no decision", details={"rule": "no_decision"})
        case = self.order(case_id) if kind is CaseKind.ORDER else self.quote(case_id)
        await self.runtime.approval_flow.decide(
            approval_id=approval_id,
            approve=approve,
            comment=comment,
            context=caller.context(),
            authorization=ScopeAuthorizationService(),
            reasons=reasons,
            subject_version=case.case_version,
        )

    async def confirm(self, pic: Caller, case_id: uuid.UUID, day: date) -> OrderCase:
        case = self.order(case_id)
        await self.services.order_commands.confirm(
            pic.context(),
            case_id,
            case_version=case.case_version,
            delivery_dates={line.line_no: day for line in case.lines},
        )
        return self.order(case_id)


def open_world(
    repo_root: Path,
    sample: SampleSet,
    callers: Sequence[Caller],
    *,
    bound_to: SalesScope = ALPHA,
    allowance: RunAllowancePort | None = None,
    telemetry: TelemetryPort | None = None,
    model: InterpretationPort | None = None,
    scanner: MalwareScanPort | None = None,
) -> World:
    """DW1 as `apps/api`'s `build_sales` assembles it, the store in memory and
    the mocks bound to ``bound_to``; runs unmetered unless ``allowance``
    names a plan's limits, and spans go nowhere unless ``telemetry`` takes
    them (the runtime's and Sales' alike). The bound tenant checks its orders
    under its own rules where the sample set holds them (``policies/``).

    ``model`` is what reads a description DW1's vocabulary does not (dw_sales
    ADR 0005): a recorded or scripted one in the smoke, the local model in the
    live lane. None, as in a process with no model server: no model is called
    at all."""
    telemetry = telemetry or NullTelemetry()
    policies = load_sales_policies(
        repo_root / "configs" / "policies", repo_root / "configs" / "copy"
    )
    clock = FixedClock(NOW)
    ids = Uuid4Generator()
    runtime = MemoryRuntime.build(clock=clock, ids=ids, allowance=allowance, telemetry=telemetry)
    store = MemoryStore(runtime.approvals)
    catalog = MockSalesCatalog.load(bound_to, sample.data_dir)
    readers = mock_po_readers()
    # The mailbox every service reads, at the door `build_dw1` puts in front of
    # it (ticket 25): scanned, then held to its names. Nothing is found in the
    # sample set unless ``scanner`` says so.
    inbox = ScannedInbox(
        MockInbox.load(bound_to, sample.data_dir, sample.attachments_dir),
        scanner or NoMalware(),
        readers,
    )
    # The bound tenant's own order rules, where the sample set holds them, as
    # a version two people approved (the API stores it through `/sales/rules`).
    own = load_tenant_order_rules(sample.data_dir / "policies")
    if own is not None:
        store.rule_versions.seed_approved(bound_to.tenant_id.value, own)
    book = rule_book(policies, store.rule_versions)
    order_rules = RuleBookOrderRules(book)
    layout_checks = LayoutChecks(readers, catalog)
    quotation = QuotationService(
        catalog=catalog,
        inbox=inbox,
        rfq_reader=ExcelRfqReader(),
        reply_reader=ExcelDesignReplyReader(),
        cases=store,
        ledger=catalog,
        rules=policies.quote_rules,
        pricing=policies.pricing,
        requests=(None if model is None else model_requests(model, catalog, order_rules)),
    )
    intake = OrderIntake(
        catalog=catalog,
        inbox=inbox,
        reader=readers,
        quote_forms=ExcelQuoteForms(),
        rules=order_rules,
        cases=store,
        new_case_id=ids.new_uuid,
        descriptions=None if model is None else DescriptionReader(model),
        intents=None if model is None else IntentReader(model, catalog, store),
        threads=ThreadLinks(store, inbox),
        replies=None if model is None else ReplyReader(model),
        handoffs=None if model is None else HandoffReader(model, catalog, store),
        layouts=store,
        layout_prefiller=None if model is None else LayoutPrefiller(model, layout_checks),
    )
    directory = Directory(tuple(callers))
    notifications = Notifications()
    objects = Objects()
    worker_file = repo_root / "configs" / "workers" / "sales.yaml"
    worker, _ = parse_worker_file(worker_file)
    runs = RuntimeDw1Runs(
        runtime.runner,
        runtime.approval_flow,
        runtime.runs,
        ids,
        worker.worker_id,
        worker.worker_version,
    )
    assembly = assemble(
        uow=store,
        authorization=ScopeAuthorizationService(),
        clock=clock,
        ids=ids,
        catalog=catalog,
        inbox=inbox,
        intake=intake,
        quotation=quotation,
        files=FileSourceView(policies.order_rules.intake),
        book=book,
        directory=directory,
        holders=directory,
        notifications=notifications,
        artifact_bytes=objects,
        artifact_writer=ArtifactFiles(),
        artifact_copy=policies.artifact_copy,
        handoff_copy=policies.handoff_copy,
        layout_checks=layout_checks,
        release_manifest_ref="sha256:eval",
        runs=runs,
        pending=runs,
        telemetry=telemetry,
    )
    register(
        graphs=runtime.graphs,
        workers=runtime.workers,
        approvals=runtime.approval_flow,
        steps=assembly.decisions,
        layouts=assembly.layout_decisions,
        worker_file=worker_file,
    )
    return World(
        assembly.services,
        store,
        catalog,
        inbox,
        notifications,
        objects,
        policies,
        sample,
        runtime,
        runs,
        LayoutSettlement(store, clock, ids),
    )


__all__ = [
    "ALPHA",
    "BETA",
    "Caller",
    "MemoryStore",
    "SampleSet",
    "SampleWith",
    "World",
    "open_world",
]
