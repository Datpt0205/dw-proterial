"""The platform's rule-version engine (ADR 0013 decision 3), with a registry
of its own: what every context's versions obey whatever the context is.
Sales' own suite (`test_rules.py`) runs the same engine through Sales."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Collection, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from dw_kernel.errors import ConflictError, DomainError, PermissionDeniedError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ApprovalAudience
from dw_platform.application.rule_versions import (
    ONE_OPEN_PROPOSAL,
    PLATFORM_VERSION_REUSED,
    RuleBook,
    RuleDecisionGuard,
    RuleRegistry,
    RuleScope,
    RuleStatus,
    RuleVersion,
    RuleVersionEngine,
    RuleVersionSettlement,
    Unready,
)
from dw_platform.domain.approval import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
    DecisionOutcome,
)
from dw_platform.domain.audit import AuditEvent

pytestmark = pytest.mark.unit

TENANT = uuid.UUID(int=1)
OTHER = uuid.UUID(int=2)
WORKSPACE = uuid.UUID(int=10)
MAKER = uuid.UUID(int=100)
CHECKER = uuid.UUID(int=101)
NOW = datetime(2026, 11, 1, 8, tzinfo=UTC)

REGISTRY = RuleRegistry(
    approval_type="ctx.rules",
    approve_scope="ctx.rules.approve",
    resource_type="ctx_rule_version",
    audit_prefix="ctx.rules",
    reason="Phiên bản quy tắc chờ duyệt",
)


class Limits(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str
    limit: int
    # Added in 1.1.0: a version written before reads the platform's value.
    tolerance: int = 0

    @property
    def ref(self) -> str:
        return f"ctx_limits@{self.version}"


PLATFORM = Limits(version="1.1.0", limit=100, tolerance=5)


def _context(principal: uuid.UUID, tenant: uuid.UUID = TENANT) -> AccessContext:
    return AccessContext(
        tenant_id=tenant,
        workspace_id=WORKSPACE,
        principal_id=principal,
        roles=frozenset({"ctx_head"}),
        scopes=frozenset({"ctx.rules.propose", "ctx.rules.approve", "approvals.decide"}),
        plan_id="standard",
    )


@dataclass
class Versions:
    """Every tenant's versions held apart, refusing what the table refuses."""

    held: dict[uuid.UUID, dict[uuid.UUID, RuleVersion]] = field(default_factory=dict)

    async def approved(self, scope: RuleScope, key: str) -> RuleVersion | None:
        own = self.held.get(scope.tenant_id.value, {}).values()
        return next((v for v in own if v.key == key and v.status == "approved"), None)

    async def find(self, scope: RuleScope, key: str, version: str) -> RuleVersion | None:
        own = self.held.get(scope.tenant_id.value, {}).values()
        return next((v for v in own if v.key == key and v.version == version), None)


@dataclass
class Store:
    own: dict[uuid.UUID, RuleVersion]

    async def list_all(
        self,
        *,
        keys: Collection[str] | None = None,
        statuses: Collection[RuleStatus] | None = None,
    ) -> Sequence[RuleVersion]:
        versions = [
            v
            for v in self.own.values()
            if (keys is None or v.key in keys) and (statuses is None or v.status in statuses)
        ]
        return sorted(versions, key=lambda v: v.proposed_at, reverse=True)

    async def get(self, version_id: uuid.UUID) -> RuleVersion | None:
        return self.own.get(version_id)

    def _refuse_twice(self, version: RuleVersion) -> None:
        if any(v.key == version.key and v.version == version.version for v in self.own.values()):
            raise ConflictError("refused", details={"constraint": "uq_rule_versions_key_version"})

    async def add(self, version: RuleVersion) -> None:
        self._refuse_twice(version)
        if any(v.key == version.key and v.status == "proposed" for v in self.own.values()):
            raise ConflictError("refused", details={"rule": ONE_OPEN_PROPOSAL})
        self.own[version.version_id] = version

    async def decide(self, version: RuleVersion, *, superseding: uuid.UUID | None) -> None:
        if self.own[version.version_id].status != "proposed":
            raise ConflictError("decided already")
        if superseding is not None:
            self.own[superseding] = self.own[superseding].model_copy(
                update={"status": "superseded"}
            )
        self.own[version.version_id] = version

    async def apply(self, version: RuleVersion, *, superseding: uuid.UUID | None) -> None:
        self._refuse_twice(version)
        if superseding is not None:
            self.own[superseding] = self.own[superseding].model_copy(
                update={"status": "superseded"}
            )
        self.own[version.version_id] = version


@dataclass
class Approvals:
    held: dict[uuid.UUID, ApprovalRequest] = field(default_factory=dict)
    decisions: dict[uuid.UUID, ApprovalDecision] = field(default_factory=dict)

    async def add(self, request: ApprovalRequest) -> None:
        self.held[request.id] = request

    async def get(
        self, request_id: uuid.UUID, *, workspace_id: uuid.UUID, audience: ApprovalAudience
    ) -> ApprovalRequest | None:
        request = self.held.get(request_id)
        if request is None or request.tenant_id.value != audience.context.tenant_id:
            return None
        return request

    async def latest_decision(
        self, request_id: uuid.UUID, *, workspace_id: uuid.UUID, audience: ApprovalAudience
    ) -> ApprovalDecision | None:
        return self.decisions.get(request_id)


@dataclass
class Audit:
    events: list[AuditEvent] = field(default_factory=list)

    async def append(self, event: AuditEvent) -> None:
        self.events.append(event)


@dataclass
class Work:
    approvals: Approvals
    audit: Audit
    rule_versions: Store

    async def commit(self) -> None:
        return None


@dataclass
class World:
    versions: Versions = field(default_factory=Versions)
    approvals: Approvals = field(default_factory=Approvals)
    audit: Audit = field(default_factory=Audit)
    refuse: Unready | None = None

    @asynccontextmanager
    async def work(self, context: AccessContext) -> AsyncIterator[Work]:
        yield Work(
            self.approvals,
            self.audit,
            Store(self.versions.held.setdefault(context.tenant_id, {})),
        )

    @property
    def book(self) -> RuleBook:
        released: Mapping[str, Any] = {"ctx_limits@1.0.0": Limits(version="1.0.0", limit=50)}
        return RuleBook(
            platform={"ctx_limits": PLATFORM},
            stored=self.versions,
            released=released,
            schemas={"ctx_limits": Limits},
        )

    async def unready(self, scope: RuleScope, key: str, policy: BaseModel) -> Unready | None:
        return self.refuse

    async def names(self, context: AccessContext) -> Mapping[uuid.UUID, str]:
        return {MAKER: "Lan"}

    def engine(self) -> RuleVersionEngine:
        return RuleVersionEngine(REGISTRY, self.work, self.book, _Clock(), _Ids(), self, self)

    def guard(self) -> RuleDecisionGuard:
        return RuleDecisionGuard(REGISTRY, self.work, self.book, self)

    def settlement(self) -> RuleVersionSettlement:
        return RuleVersionSettlement(REGISTRY, self.work, self.book, _Clock(), _Ids(), self)

    def decide(self, approval_id: uuid.UUID, *, approve: bool) -> None:
        request = self.approvals.held[approval_id]
        status = ApprovalStatus.APPROVED if approve else ApprovalStatus.REJECTED
        self.approvals.held[approval_id] = replace(request, status=status)
        self.approvals.decisions[approval_id] = ApprovalDecision(
            id=uuid.uuid4(),
            request_id=approval_id,
            tenant_id=request.tenant_id,
            workspace_id=request.workspace_id,
            decided_by=UserId(CHECKER),
            outcome=DecisionOutcome.APPROVED if approve else DecisionOutcome.REJECTED,
            comment="đồng ý" if approve else "chưa",
            decided_at=NOW,
        )


class _Clock:
    def now(self) -> datetime:
        return NOW


class _Ids:
    def new_uuid(self) -> uuid.UUID:
        return uuid.uuid4()


@dataclass(frozen=True)
class _Decision:
    approve: bool


def _document(version: str, limit: int = 200) -> dict[str, Any]:
    return {"version": version, "limit": limit, "tolerance": 5}


async def test_a_proposal_waits_on_an_approval_stamped_with_the_registry_scope() -> None:
    world = World()
    version = await world.engine().propose(
        _context(MAKER), "ctx_limits", _document("2.0.0"), applies_directly=False
    )
    assert version.status == "proposed"
    request = world.approvals.held[version.approval_id or uuid.UUID(int=0)]
    assert request.approval_type == "ctx.rules"
    assert request.required_scope == "ctx.rules.approve"
    assert request.payload["makers"] == [str(MAKER)]
    assert "document" not in request.payload
    assert [e.action for e in world.audit.events] == ["ctx.rules.proposed"]


async def test_a_second_proposal_on_a_key_is_refused_naming_the_waiting_one() -> None:
    world = World()
    await world.engine().propose(
        _context(MAKER), "ctx_limits", _document("2.0.0"), applies_directly=False
    )
    with pytest.raises(ConflictError) as refused:
        await world.engine().propose(
            _context(CHECKER), "ctx_limits", _document("2.0.1"), applies_directly=False
        )
    assert refused.value.details["rule"] == ONE_OPEN_PROPOSAL
    assert refused.value.details["version"] == "2.0.0"
    assert "Lan" in str(refused.value)


async def test_a_number_the_platform_ships_is_refused() -> None:
    world = World()
    for shipped in ("1.1.0", "1.0.0"):
        with pytest.raises(ConflictError) as refused:
            await world.engine().propose(
                _context(MAKER), "ctx_limits", _document(shipped), applies_directly=False
            )
        assert refused.value.details["rule"] == PLATFORM_VERSION_REUSED


async def test_a_document_the_schema_refuses_names_where_never_the_value() -> None:
    with pytest.raises(DomainError) as refused:
        await (
            World()
            .engine()
            .propose(
                _context(MAKER),
                "ctx_limits",
                {"version": "2.0.0", "limit": "nhiều lắm"},
                applies_directly=False,
            )
        )
    assert refused.value.details["errors"] == ["limit"]
    assert "nhiều" not in str(refused.value.details)


async def test_the_context_checks_refuse_a_proposal_and_an_approval() -> None:
    world = World()
    version = await world.engine().propose(
        _context(MAKER), "ctx_limits", _document("2.0.0"), applies_directly=False
    )
    world.refuse = Unready(ConflictError("chưa đo"), "model_bar_unmet", "Chưa đo")
    with pytest.raises(ConflictError, match="chưa đo"):
        await world.engine().propose(
            _context(MAKER), "ctx_limits", _document("2.1.0"), applies_directly=True
        )
    request = world.approvals.held[version.approval_id or uuid.UUID(int=0)]
    with pytest.raises(ConflictError, match="chưa đo"):
        await world.guard().check(request, _Decision(approve=True), _context(CHECKER))
    # Rejecting is never refused by them.
    await world.guard().check(request, _Decision(approve=False), _context(CHECKER))


async def test_the_proposer_never_decides_their_own_version() -> None:
    world = World()
    version = await world.engine().propose(
        _context(MAKER), "ctx_limits", _document("2.0.0"), applies_directly=False
    )
    request = world.approvals.held[version.approval_id or uuid.UUID(int=0)]
    with pytest.raises(ConflictError) as refused:
        await world.guard().check(request, _Decision(approve=True), _context(MAKER))
    assert refused.value.details["rule"] == "maker_checker"


async def test_an_approval_another_registry_opened_is_not_this_ones() -> None:
    world = World()
    version = await world.engine().propose(
        _context(MAKER), "ctx_limits", _document("2.0.0"), applies_directly=False
    )
    request = world.approvals.held[version.approval_id or uuid.UUID(int=0)]
    foreign = replace(request, approval_type="other.rules")
    with pytest.raises(ConflictError):
        await world.guard().check(foreign, _Decision(approve=True), _context(CHECKER))
    restamped = replace(request, required_scope="other.approve")
    with pytest.raises(PermissionDeniedError):
        await world.guard().check(restamped, _Decision(approve=True), _context(CHECKER))


async def test_settlement_puts_the_version_in_force_once_and_supersedes_the_last() -> None:
    world = World()
    engine = world.engine()
    first = await engine.propose(
        _context(CHECKER), "ctx_limits", _document("2.0.0", 300), applies_directly=True
    )
    proposed = await engine.propose(
        _context(MAKER), "ctx_limits", _document("2.1.0", 400), applies_directly=False
    )
    approval_id = proposed.approval_id or uuid.UUID(int=0)
    world.decide(approval_id, approve=True)
    settled = await world.settlement().settle(approval_id, _context(CHECKER))
    again = await world.settlement().settle(approval_id, _context(CHECKER))

    assert settled.status == "approved" and settled.comment == "đồng ý"
    assert again == settled
    assert world.versions.held[TENANT][first.version_id].status == "superseded"
    scope = _Scope(TenantId(TENANT), WorkspaceId(WORKSPACE))
    resolved = await world.book.current(scope, "ctx_limits")
    assert (resolved.layer, resolved.policy.limit) == ("tenant", 400)
    actions = [e.action for e in world.audit.events]
    assert actions == ["ctx.rules.applied", "ctx.rules.proposed", "ctx.rules.approved"]


async def test_an_approval_the_checks_now_refuse_is_recorded_rejected_with_why() -> None:
    world = World()
    proposed = await world.engine().propose(
        _context(MAKER), "ctx_limits", _document("2.0.0"), applies_directly=False
    )
    approval_id = proposed.approval_id or uuid.UUID(int=0)
    world.decide(approval_id, approve=True)
    world.refuse = Unready(ConflictError("chưa đo"), "model_bar_unmet", "Không áp dụng: chưa đo")
    settled = await world.settlement().settle(approval_id, _context(CHECKER))
    assert settled.status == "rejected"
    assert settled.comment == "Không áp dụng: chưa đo"
    assert world.audit.events[-1].details["rule"] == "model_bar_unmet"


@dataclass(frozen=True)
class _Scope:
    tenant_id: TenantId
    workspace_id: WorkspaceId


async def test_resolution_never_reads_another_tenants_version() -> None:
    world = World()
    await world.engine().propose(
        _context(CHECKER, OTHER), "ctx_limits", _document("2.0.0", 999), applies_directly=True
    )
    mine = await world.book.current(_Scope(TenantId(TENANT), WorkspaceId(WORKSPACE)), "ctx_limits")
    theirs = await world.book.current(_Scope(TenantId(OTHER), WorkspaceId(WORKSPACE)), "ctx_limits")
    assert (mine.layer, mine.policy.limit) == ("platform", 100)
    assert (theirs.layer, theirs.policy.limit) == ("tenant", 999)
    assert (
        await world.book.at(
            _Scope(TenantId(TENANT), WorkspaceId(WORKSPACE)), "ctx_limits", "ctx_limits@2.0.0"
        )
        is None
    )


async def test_a_stamp_reads_the_version_it_names_and_a_field_it_predates() -> None:
    world = World()
    scope = _Scope(TenantId(TENANT), WorkspaceId(WORKSPACE))
    old = await world.book.at(scope, "ctx_limits", "ctx_limits@1.0.0")
    assert old is not None and old.limit == 50
    world.versions.held[TENANT] = {}
    await world.engine().propose(
        _context(CHECKER), "ctx_limits", {"version": "2.0.0", "limit": 7}, applies_directly=True
    )
    stored = next(iter(world.versions.held[TENANT].values()))
    # Written before `tolerance` existed: read as the platform's current one has it.
    written = stored.model_copy(update={"document": {"version": "2.0.0", "limit": 7}})
    world.versions.held[TENANT][stored.version_id] = written
    read = await world.book.at(scope, "ctx_limits", "ctx_limits@2.0.0")
    assert read is not None and (read.limit, read.tolerance) == (7, 5)
    assert await world.book.at(scope, "ctx_limits", "other@2.0.0") is None
