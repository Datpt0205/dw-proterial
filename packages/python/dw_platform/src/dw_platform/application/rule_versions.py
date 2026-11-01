"""A tenant's own versions of a context's rules: proposed, decided, resolved
(ADR 0013 decision 3; Sales ticket 19, where this engine was built first).

One deployment serves customers whose rules differ, and a customer's value
arrives as a version of its own at runtime, never as an edit to the checkout
(`CLAUDE.md`, "Per-tenant artifacts"). The platform layer is the file a
context ships in ``configs/``; a tenant's layer is a version a person
proposed and, unless the context lets its approver apply their own, a second
person approved.

This module is the part every context shares. A context **registers** what
is its own (`RuleRegistry`): its keys and the schema each is validated by,
the approval type its proposals open and the scope that decides them, its
audit names, and any further refusal its versions meet (`RuleChecksPort`:
Sales refuses a version that turns on a model step not yet measured). The
context's own service keeps its scope checks and its views; this engine
keeps the rules every version obeys:

- **One waiting per key**: a version is the whole document, so two proposals
  side by side would each undo the other when both are approved. A second is
  refused (409, `ONE_OPEN_PROPOSAL`) naming the waiting version, its proposer
  and when; `uq_rule_versions_one_proposed` holds it whatever writes the row.
- **Never a number the platform ships**, at proposal and at decision: a
  stamp of it would name two documents.
- **Decided by a holder of the approval's stamp, never its proposer**
  (`RuleDecisionGuard`, and `ck_rule_versions_checker_not_maker`), carried out
  by the worker from the approval row (`RuleVersionSettlement`), idempotent.
- **Resolved** through `TenantOverlay`: the tenant's approved version, else
  the platform's, never another tenant's (`RuleBook.current`); a stamp reads
  the version it names (`RuleBook.at`), and a version written before a field
  existed reads it as the platform's current version has it (`read_over`).
"""

from __future__ import annotations

import typing
import uuid
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Final, Literal, Protocol, Self
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, model_validator

from dw_kernel.errors import ConflictError, DomainError, NotFoundError, PermissionDeniedError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.overlay import TenantOverlay
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ApprovalAudience
from dw_platform.domain.approval import ApprovalDecision, ApprovalRequest, ApprovalStatus
from dw_platform.domain.audit import AuditEvent

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

RuleStatus = Literal["proposed", "approved", "rejected", "superseded"]
Layer = Literal["platform", "tenant"]
# The rule a refusal reports when a key already has a proposal waiting on its
# approval (`uq_rule_versions_one_proposed`).
ONE_OPEN_PROPOSAL: Final = "one_open_proposal"
# The rule a refusal reports when a version takes a number the platform ships.
PLATFORM_VERSION_REUSED: Final = "platform_version_reused"
# Worded here, where it is raised, for every context's settings page alike.
REUSED_WORDS: Final = (
    "Số phiên bản này trùng với một phiên bản nền tảng phát hành:"
    " đặt số khác cho phiên bản của công ty."
)
# What `rule_versions.comment` holds (`ck_rule_versions_comment`).
COMMENT_LIMIT: Final = 500
# The time a refusal names a proposal's moment in: the plant's.
_LOCAL: Final = ZoneInfo("Asia/Ho_Chi_Minh")
_KEY: Final = r"^[a-z][a-z0-9_]{0,63}$"


class Policy(Protocol):
    """A key's document as its schema reads it: a pydantic model that names
    itself ``<key>@<version>``."""

    @property
    def ref(self) -> str: ...

    def model_dump(self, *, mode: str = ..., by_alias: bool = ...) -> dict[str, Any]: ...


class RuleScope(Protocol):
    """Whose versions a read is bound to: the verified tenant and workspace."""

    @property
    def tenant_id(self) -> TenantId: ...

    @property
    def workspace_id(self) -> WorkspaceId: ...


@dataclass(frozen=True, slots=True)
class ContextScope:
    """A `RuleScope` built from a verified access context."""

    tenant_id: TenantId
    workspace_id: WorkspaceId

    @classmethod
    def of(cls, context: AccessContext) -> ContextScope:
        return cls(TenantId(context.tenant_id), WorkspaceId(context.workspace_id))


class RuleVersion(BaseModel):
    """One version of one key a person of the tenant proposed, and what was
    decided about it. ``document`` is the whole policy, never a patch."""

    model_config = _FROZEN

    version_id: uuid.UUID
    key: str = Field(pattern=_KEY)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    document: Mapping[str, Any]
    status: RuleStatus
    proposed_by: uuid.UUID
    proposed_at: AwareDatetime
    decided_by: uuid.UUID | None = None
    decided_at: AwareDatetime | None = None
    comment: str | None = Field(default=None, max_length=COMMENT_LIMIT)
    # The approval it is decided on; None on a version applied directly, or
    # (Sales) decided before ticket 38 moved decisions onto approvals.
    approval_id: uuid.UUID | None = None
    # Applied by the approver who wrote it, with no approval: the one version
    # its proposer decides, where the context allows it.
    applied_directly: bool = False

    @model_validator(mode="after")
    def _decided_by_another(self) -> Self:
        decided = self.decided_by is not None
        if (self.status == "proposed") == decided or decided != (self.decided_at is not None):
            raise ValueError("a decided version names who decided it and when")
        if self.applied_directly:
            if self.approval_id is not None or self.decided_by != self.proposed_by:
                raise ValueError("a version applied directly is decided by its proposer alone")
            if self.status not in ("approved", "superseded"):
                raise ValueError("a version applied directly is in force or superseded")
        elif self.decided_by is not None and self.decided_by == self.proposed_by:
            raise ValueError("the proposer of a version does not decide it")
        return self

    @property
    def ref(self) -> str:
        return f"{self.key}@{self.version}"


def read_over[P: BaseModel](schema: type[P], document: Mapping[str, Any], platform: BaseModel) -> P:
    """``document``, written under an earlier schema, read by today's.

    A field the document predates takes the value the platform's current
    version has: what the platform ships is what a tenant without its own
    version runs, so it is the default this deployment already stands behind.
    Only the schema's own shape is filled — its fields, at any depth, and the
    keys of a mapping over a closed set (a severity per finding code). A
    mapping of data (a customer's lead time, a template by name) is the
    version's own and is never topped up with the platform's entries.
    """
    base = platform.model_dump(mode="json", by_alias=True)
    return schema.model_validate(_predated(schema, document, base))


def _predated(
    model: type[BaseModel], document: Mapping[str, Any], base: Mapping[str, Any]
) -> dict[str, Any]:
    filled = dict(document)
    for name, spec in model.model_fields.items():
        key = spec.alias or name
        if key not in base:
            continue
        if key not in filled:
            filled[key] = base[key]
            continue
        mine, theirs = filled[key], base[key]
        if not (isinstance(mine, Mapping) and isinstance(theirs, Mapping)):
            continue
        if (nested := _model_in(spec.annotation)) is not None:
            filled[key] = _predated(nested, mine, theirs)
        elif _closed_keys(spec.annotation):
            filled[key] = {**theirs, **mine}
    return filled


def _model_in(annotation: Any) -> type[BaseModel] | None:
    for candidate in (annotation, *typing.get_args(annotation)):
        if isinstance(candidate, type) and issubclass(candidate, BaseModel):
            return candidate
    return None


def _closed_keys(annotation: Any) -> bool:
    """A mapping whose keys are an enum or a literal: every key is a field."""
    if typing.get_origin(annotation) not in (Mapping, dict):
        return False
    keys = typing.get_args(annotation)[0]
    return typing.get_origin(keys) is Literal or (isinstance(keys, type) and issubclass(keys, Enum))


def validated[P: BaseModel](schema: type[P], key: str, document: Mapping[str, Any]) -> P:
    """The document as the key's schema reads it; a refusal names where it
    failed, never a value of it."""
    try:
        return schema.model_validate(dict(document))
    except ValidationError as exc:
        raise DomainError(
            "the document is not a valid version of this key",
            details={
                "key": key,
                "errors": [".".join(str(part) for part in e["loc"]) for e in exc.errors()][:20],
            },
        ) from None


# ---------------------------------------------------------------- ports --


class RuleVersionLookupPort(Protocol):
    """The tenant's stored versions, as resolution reads them: one short read
    bound to the scope's tenant (RLS), never another's."""

    async def approved(self, scope: RuleScope, key: str) -> RuleVersion | None: ...

    async def find(self, scope: RuleScope, key: str, version: str) -> RuleVersion | None: ...


class RuleVersionStorePort(Protocol):
    """The tenant's versions inside a unit of work."""

    async def list_all(self) -> Sequence[RuleVersion]:
        """Every version of every key, newest proposed first."""
        ...

    async def get(self, version_id: uuid.UUID) -> RuleVersion | None: ...

    async def add(self, version: RuleVersion) -> None:
        """A proposal. Refused with a conflict when the key already has the
        version, or already has a proposal waiting (``details["rule"]`` is
        `ONE_OPEN_PROPOSAL`); approving or rejecting that one frees the key."""
        ...

    async def decide(self, version: RuleVersion, *, superseding: uuid.UUID | None) -> None:
        """The decision on a proposal (refused with a conflict when it is no
        longer one), and the approved version it replaces, superseded."""
        ...

    async def apply(self, version: RuleVersion, *, superseding: uuid.UUID | None) -> None:
        """A version applied directly, written in force, and the approved
        version it replaces, superseded. Refused with a conflict when the key
        already has the version."""
        ...


class RuleApprovalsPort(Protocol):
    """The platform's approvals, as a run-less rule decision uses them."""

    async def add(self, request: ApprovalRequest) -> None: ...

    async def get(
        self, request_id: uuid.UUID, *, workspace_id: uuid.UUID, audience: ApprovalAudience
    ) -> ApprovalRequest | None: ...

    async def latest_decision(
        self, request_id: uuid.UUID, *, workspace_id: uuid.UUID, audience: ApprovalAudience
    ) -> ApprovalDecision | None: ...


class RuleAuditPort(Protocol):
    async def append(self, event: AuditEvent) -> None: ...


class RuleWork(Protocol):
    """One transaction bound to one tenant and workspace: the context's own
    unit of work, which carries these three beside its other stores."""

    @property
    def approvals(self) -> RuleApprovalsPort: ...

    @property
    def audit(self) -> RuleAuditPort: ...

    @property
    def rule_versions(self) -> RuleVersionStorePort: ...

    async def commit(self) -> None: ...


RuleWorkFactory = Callable[[AccessContext], AbstractAsyncContextManager[RuleWork]]


class ProposerNamesPort(Protocol):
    """Who a waiting version's proposer is, by name, for the refusal."""

    async def names(self, context: AccessContext) -> Mapping[uuid.UUID, str]: ...


@dataclass(frozen=True, slots=True)
class Unready:
    """Why a version may not take effect, as the context words it: the 409 a
    proposal and a decision meet, and the code and comment a settlement
    records when it turns an approval into a rejection."""

    error: ConflictError
    rule: str
    comment: str


class RuleChecksPort(Protocol):
    """A context's own refusal of a version beyond its schema (Sales: a model
    step turned on before it is measured). None: nothing more to refuse."""

    async def unready(self, scope: RuleScope, key: str, policy: BaseModel) -> Unready | None: ...


@dataclass(frozen=True)
class NoMoreChecks:
    """Implements `RuleChecksPort` for a context whose schema says it all."""

    async def unready(self, scope: RuleScope, key: str, policy: BaseModel) -> Unready | None:
        return None


# ------------------------------------------------------------ the book --


@dataclass(frozen=True, slots=True)
class Resolved:
    policy: Any
    layer: Layer


@dataclass(frozen=True)
class RuleBook:
    """The rules in force for a scope's tenant, and the ones a stamp names.

    ``platform`` holds each key's current platform version, ``schemas`` the
    model each key's documents are read by, ``released`` every platform
    version the checkout still ships, by ref, the current ones included: what
    a stamp made before a release resolves to after it."""

    platform: Mapping[Any, Any]
    stored: RuleVersionLookupPort
    released: Mapping[str, Any] = field(default_factory=dict)
    schemas: Mapping[Any, type[BaseModel]] = field(default_factory=dict)

    def schema_of(self, key: str) -> type[BaseModel]:
        schema = self.schemas.get(key)
        return type(self.platform[key]) if schema is None else schema

    def ships(self, key: str, ref: str) -> bool:
        """Whether ``ref`` is a number the platform layer has released."""
        return ref == self.platform[key].ref or ref in self.released

    def policy_of(self, version: RuleVersion) -> Any:
        """``version``'s document as today's schema reads it."""
        return read_over(self.schema_of(version.key), version.document, self.platform[version.key])

    async def current(self, scope: RuleScope, key: str) -> Resolved:
        """The tenant's approved version, or the platform's: never sideways."""
        overlay: TenantOverlay[str, Resolved] = TenantOverlay()
        overlay.put(key, Resolved(self.platform[key], "platform"))
        own = await self.stored.approved(scope, key)
        if own is not None:
            overlay.put(
                key, Resolved(self.policy_of(own), "tenant"), tenant_id=scope.tenant_id.value
            )
        resolved = overlay.get(key, tenant_id=scope.tenant_id.value)
        assert resolved is not None  # the platform layer is always put
        return resolved

    async def at(self, scope: RuleScope, key: str, ref: str) -> Any | None:
        """The version a stamp names: one of the tenant's (approved now or
        since superseded), else one the platform released. None for a number
        neither holds.

        The tenant's is asked first: a tenant version takes a number the
        platform had not released, so where the platform ships that number
        later, every stamp of it on this tenant's cases still means the
        tenant's document."""
        policy_id, _, version = ref.partition("@")
        if policy_id != key:
            return None
        own = await self.stored.find(scope, key, version)
        if own is not None and own.status in ("approved", "superseded"):
            return self.policy_of(own)
        platform = self.platform[key]
        return platform if ref == platform.ref else self.released.get(ref)

    def platform_versions(self, key: str) -> list[tuple[str, Any]]:
        """Every version of ``key`` the platform released, newest first."""
        current = self.platform[key]
        held = {ref: p for ref, p in self.released.items() if ref.partition("@")[0] == key}
        held[current.ref] = current
        return [(ref, held[ref]) for ref in sorted(held, key=_semver, reverse=True)]


def _semver(ref: str) -> tuple[int, ...]:
    return tuple(int(part) for part in ref.rpartition("@")[2].split("."))


# ----------------------------------------------------------- the engine --


@dataclass(frozen=True)
class RuleRegistry:
    """What one context registers: the approval its proposals open (strict
    under the context's prefix), the scope that decides it, its audit names,
    and the sentence the approval carries."""

    # The run-less approval a proposal opens: ``<context>.rules``.
    approval_type: str
    # The scope its decider holds, stamped on the approval.
    approve_scope: str
    # The audit rows' resource type and their action prefix
    # (``<prefix>.proposed``, ``.applied``, ``.approved``, ``.rejected``).
    resource_type: str
    audit_prefix: str
    # Why the approval exists, as the inbox shows it.
    reason: str

    @property
    def decided_event(self) -> str:
        return f"{self.approval_type}.decided"


class RuleApprovalAsked(BaseModel):
    """The approval's payload: ids, the key and the version, never the
    document (it can hold prices, and the inbox serves the payload to
    whoever may decide it)."""

    model_config = _FROZEN

    approval_type: str = Field(min_length=1, max_length=100)
    required_scope: str
    version_id: uuid.UUID
    key: str = Field(pattern=_KEY)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    makers: tuple[uuid.UUID, ...]


def _audit(
    registry: RuleRegistry,
    ids: IdGenerator,
    clock: UtcClock,
    context: AccessContext,
    action: str,
    version: RuleVersion,
    *,
    refused: str | None = None,
) -> AuditEvent:
    """The key, the version, its status and its approval: never the document.
    ``refused`` names the rule that turned an approval into a rejection."""
    details: dict[str, object] = {
        "key": version.key,
        "version": version.version,
        "status": version.status,
    }
    if version.approval_id is not None:
        details["approval_id"] = str(version.approval_id)
    if refused is not None:
        details["rule"] = refused
    return AuditEvent(
        id=ids.new_uuid(),
        tenant_id=TenantId(context.tenant_id),
        workspace_id=WorkspaceId(context.workspace_id),
        actor_id=UserId(context.principal_id),
        action=f"{registry.audit_prefix}.{action}",
        resource_type=registry.resource_type,
        resource_id=str(version.version_id),
        occurred_at=clock.now(),
        details=details,
    )


@dataclass(frozen=True)
class RuleVersionEngine:
    """Propose a version: open its approval, or apply it directly when the
    context says its proposer may. The context checks who may first."""

    registry: RuleRegistry
    work: RuleWorkFactory
    book: RuleBook
    clock: UtcClock
    ids: IdGenerator
    names: ProposerNamesPort
    checks: RuleChecksPort = field(default_factory=NoMoreChecks)

    def validated(self, key: str, document: Mapping[str, Any]) -> Any:
        return validated(self.book.schema_of(key), key, document)

    async def list_all(self, context: AccessContext) -> Sequence[RuleVersion]:
        async with self.work(context) as work:
            return await work.rule_versions.list_all()

    async def propose(
        self,
        context: AccessContext,
        key: str,
        document: Mapping[str, Any],
        *,
        applies_directly: bool,
    ) -> RuleVersion:
        policy = self.validated(key, document)
        if self.book.ships(key, policy.ref):
            raise ConflictError(
                REUSED_WORDS,
                details={"key": key, "rule": PLATFORM_VERSION_REUSED},
            )
        unready = await self.checks.unready(ContextScope.of(context), key, policy)
        if unready is not None:
            raise unready.error
        if applies_directly:
            return await self._apply_directly(context, key, policy)
        version = RuleVersion(
            version_id=self.ids.new_uuid(),
            key=key,
            version=policy.ref.partition("@")[2],
            document=policy.model_dump(mode="json", by_alias=True),
            status="proposed",
            proposed_by=context.principal_id,
            proposed_at=self.clock.now(),
            approval_id=self.ids.new_uuid(),
        )
        approval_id = version.approval_id
        assert approval_id is not None
        asked = RuleApprovalAsked(
            approval_type=self.registry.approval_type,
            required_scope=self.registry.approve_scope,
            version_id=version.version_id,
            key=key,
            version=version.version,
            makers=(version.proposed_by,),
        )
        async with self.work(context) as work:
            await work.approvals.add(
                ApprovalRequest(
                    id=approval_id,
                    tenant_id=TenantId(context.tenant_id),
                    workspace_id=WorkspaceId(context.workspace_id),
                    approval_type=self.registry.approval_type,
                    requested_by=UserId(context.principal_id),
                    reason=self.registry.reason,
                    payload=asked.model_dump(mode="json"),
                    required_scope=self.registry.approve_scope,
                )
            )
            # After its approval: the row names it (`fk_rule_versions_approval_requests`).
            try:
                await work.rule_versions.add(version)
            except ConflictError as refused:
                if refused.details.get("rule") != ONE_OPEN_PROPOSAL:
                    raise
                waiting = next(
                    (
                        v
                        for v in await work.rule_versions.list_all()
                        if v.key == key and v.status == "proposed"
                    ),
                    None,
                )
                raise await self._one_open(context, key, waiting) from None
            await work.audit.append(
                _audit(self.registry, self.ids, self.clock, context, "proposed", version)
            )
            await work.commit()
        return version

    async def _apply_directly(self, context: AccessContext, key: str, policy: Any) -> RuleVersion:
        """The approver's own version, in force at once: an approval they
        could not decide would hold it forever. A proposal waiting on the key
        is decided first, so what someone else asked for is never overtaken
        unseen."""
        now = self.clock.now()
        version = RuleVersion(
            version_id=self.ids.new_uuid(),
            key=key,
            version=policy.ref.partition("@")[2],
            document=policy.model_dump(mode="json", by_alias=True),
            status="approved",
            proposed_by=context.principal_id,
            proposed_at=now,
            decided_by=context.principal_id,
            decided_at=now,
            applied_directly=True,
        )
        async with self.work(context) as work:
            versions = await work.rule_versions.list_all()
            waiting = next((v for v in versions if v.key == key and v.status == "proposed"), None)
            if waiting is not None:
                raise await self._one_open(context, key, waiting)
            current = next((v for v in versions if v.key == key and v.status == "approved"), None)
            await work.rule_versions.apply(
                version, superseding=current.version_id if current is not None else None
            )
            await work.audit.append(
                _audit(self.registry, self.ids, self.clock, context, "applied", version)
            )
            await work.commit()
        return version

    async def _one_open(
        self, context: AccessContext, key: str, waiting: RuleVersion | None
    ) -> ConflictError:
        """The refusal of a second proposal on ``key``, naming the version it
        waits behind, who proposed it and when. ``waiting`` is None when it
        was decided since the refusal.

        Worded for every case the refusal meets: the waiting version may come
        from another workspace of the tenant (the key is the tenant's), whose
        approval only that workspace's approver sees, so the sentence names
        the proposer's approver, not the caller's; and it may be decided
        already and not yet carried out by the worker, so it says what to do
        then. Either way the next proposal starts from the version in force by
        then: one resent from the form refused here would undo what was
        approved."""
        details: dict[str, object] = {"key": key, "rule": ONE_OPEN_PROPOSAL}
        if waiting is None:
            return ConflictError(
                "Phiên bản chờ duyệt của quy tắc này vừa được quyết định: tải lại trang"
                " và bắt đầu lại từ phiên bản đang áp dụng.",
                details=details,
            )
        if waiting.proposed_by == context.principal_id:
            who, whose = "bạn", "bạn"
        else:
            names = await self.names.names(context)
            who = names.get(waiting.proposed_by, "một người khác trong công ty")
            whose = "người đề xuất"
        when = waiting.proposed_at.astimezone(_LOCAL).strftime("%H:%M %d/%m/%Y")
        return ConflictError(
            f"Quy tắc này đã có phiên bản {waiting.version} chờ duyệt, do {who} đề xuất"
            f" lúc {when} (giờ Việt Nam), và mỗi quy tắc chỉ có một phiên bản chờ duyệt."
            f" Trưởng bộ phận của {whose} duyệt hoặc từ chối phiên bản đó ở trang Duyệt;"
            " sau đó, đề xuất lại bắt đầu từ phiên bản đang áp dụng. Nếu phiên bản đó"
            " vừa được quyết định, đợi một lát rồi tải lại trang.",
            details={
                **details,
                "version_id": str(waiting.version_id),
                "version": waiting.version,
                "proposed_by": str(waiting.proposed_by),
                "proposed_at": waiting.proposed_at.isoformat(),
                "approval_id": str(waiting.approval_id) if waiting.approval_id else None,
            },
        )


# ----------------------------------------------------------- the decision --


def asked_of(registry: RuleRegistry, request: ApprovalRequest) -> RuleApprovalAsked:
    """The approval as a proposal opened it, or a refusal: its payload
    unreadable, or stamped with a scope other than the registry's (the
    column, which the platform's decision enforced)."""
    refused = ConflictError(
        "the approval is not one a rules proposal opened",
        details={"approval_id": str(request.id)},
    )
    if request.approval_type != registry.approval_type:
        raise refused
    try:
        asked = RuleApprovalAsked.model_validate(request.payload)
    except ValidationError:
        raise refused from None
    if asked.approval_type != registry.approval_type:
        raise refused
    if request.required_scope != registry.approve_scope or (
        asked.required_scope != request.required_scope
    ):
        raise PermissionDeniedError(
            f"a rule version is decided with {registry.approve_scope}",
            details={"approval_type": request.approval_type},
        )
    return asked


def waiting_on(version: RuleVersion | None, request: ApprovalRequest) -> RuleVersion:
    """The version this approval was opened for, still waiting on it."""
    if version is None:
        raise NotFoundError("no such rule version", details={"approval_id": str(request.id)})
    if version.approval_id != request.id or version.status != "proposed":
        raise ConflictError(
            "phiên bản quy tắc không còn chờ quyết định này",
            details={
                "version_id": str(version.version_id),
                "status": version.status,
                "rule": "decision_stale",
            },
        )
    return version


class _Decision(Protocol):
    @property
    def approve(self) -> bool: ...


@dataclass(frozen=True)
class RuleDecisionGuard:
    """The platform's `ApprovalDecisionGuard` for a context's rules approval:
    the decision as the version would take it, refused or not, unwritten.
    Called after the decider's scope and the separation of duties, before it
    is recorded. A version's document never changes after it is proposed, so
    a decision names no subject version."""

    registry: RuleRegistry
    work: RuleWorkFactory
    book: RuleBook
    checks: RuleChecksPort = field(default_factory=NoMoreChecks)

    async def check(
        self, request: ApprovalRequest, decision: _Decision, context: AccessContext
    ) -> None:
        asked = asked_of(self.registry, request)
        async with self.work(context) as work:
            version = waiting_on(await work.rule_versions.get(asked.version_id), request)
        if version.proposed_by == context.principal_id:
            raise ConflictError(
                "tách nhiệm: người đề xuất phiên bản quy tắc không tự quyết được",
                details={"version_id": str(version.version_id), "rule": "maker_checker"},
            )
        if decision.approve:
            if self.book.ships(version.key, version.ref):
                raise ConflictError(
                    REUSED_WORDS,
                    details={
                        "version_id": str(version.version_id),
                        "rule": PLATFORM_VERSION_REUSED,
                    },
                )
            policy = self.book.policy_of(version)
            unready = await self.checks.unready(ContextScope.of(context), version.key, policy)
            if unready is not None:
                raise unready.error


# Why an approved version was not applied: the platform shipped its number
# between the decision and its settlement (the approver's own comment stays
# whole on the approval).
_PLATFORM_SHIPPED: Final = (
    "Đã được duyệt nhưng không áp dụng: nền tảng đã phát hành số phiên bản {version}"
    " trước khi phiên bản này được áp dụng. Đề xuất lại với một số phiên bản khác."
)


def kept_comment(decision: ApprovalDecision | None) -> str | None:
    """The decider's comment as the version keeps it: None for none."""
    comment = "" if decision is None else decision.comment.strip()
    if not comment:
        return None
    if len(comment) <= COMMENT_LIMIT:
        return comment
    return comment[: COMMENT_LIMIT - 1] + "…"


@dataclass(frozen=True)
class RuleVersionSettlement:
    """Carries out a decided rules approval: the worker's handler for the
    registry's decided event calls it with the decider's tenancy and
    identity, from the event's envelope."""

    registry: RuleRegistry
    work: RuleWorkFactory
    book: RuleBook
    clock: UtcClock
    ids: IdGenerator
    checks: RuleChecksPort = field(default_factory=NoMoreChecks)

    async def settle(self, approval_id: uuid.UUID, decider: AccessContext) -> RuleVersion:
        """The decision on the version, as its decider. What was decided is
        read from the approval row, which the decision wrote, not from the
        event; the reason given is the decision's comment, stamped on the
        version as the rules list shows it (cut to `COMMENT_LIMIT`; the
        approval keeps it whole). Idempotent: a redelivery finds the version
        decided on this approval and writes nothing, and so does one that
        lost a race with another delivery. Raises the refusals the version
        makes (409, 404); none changes on a retry. An approval whose number
        the platform has shipped since, or that the context's checks now
        refuse, is not refused: the version is recorded as rejected, saying
        why, so it never waits on a decision already taken."""
        # Read as the decider holding the stamp the platform required of them
        # when they decided: nobody reaches here but through that decision.
        audience = ApprovalAudience(
            context=decider.model_copy(update={"scopes": frozenset({self.registry.approve_scope})}),
            holds_decide=True,
        )
        try:
            return await self._settle(approval_id, decider, audience)
        except ConflictError:
            # Another delivery may have decided the version between this one's
            # read and its write (Sales CI run 38545009082: the seed and the worker).
            async with self.work(decider) as work:
                request = await work.approvals.get(
                    approval_id, workspace_id=decider.workspace_id, audience=audience
                )
                stored = (
                    None
                    if request is None
                    else await work.rule_versions.get(asked_of(self.registry, request).version_id)
                )
            if stored is None or stored.approval_id != approval_id or stored.status == "proposed":
                raise
            return stored

    async def _settle(
        self, approval_id: uuid.UUID, decider: AccessContext, audience: ApprovalAudience
    ) -> RuleVersion:
        async with self.work(decider) as work:
            request = await work.approvals.get(
                approval_id, workspace_id=decider.workspace_id, audience=audience
            )
            if request is None:
                raise NotFoundError(
                    "rules approval not found", details={"approval_id": str(approval_id)}
                )
            asked = asked_of(self.registry, request)
            stored = await work.rule_versions.get(asked.version_id)
            # Settled already, by an earlier delivery of the same event.
            if (
                stored is not None
                and stored.approval_id == request.id
                and stored.status != "proposed"
            ):
                return stored
            proposed = waiting_on(stored, request)
            if request.status is ApprovalStatus.PENDING:
                raise ConflictError(
                    "the rules approval is not decided yet",
                    details={"approval_id": str(approval_id)},
                )
            approve = request.status is ApprovalStatus.APPROVED
            decision = await work.approvals.latest_decision(
                approval_id, workspace_id=decider.workspace_id, audience=audience
            )
            superseding = None
            comment = kept_comment(decision)
            refused: str | None = None
            if approve and self.book.ships(proposed.key, proposed.ref):
                # Approved, then a deploy shipped the number before this ran:
                # nothing can apply it now (a stamp of it would name two
                # documents). Refusing here on every retry would leave it
                # waiting with no decision left to take, holding its key, so
                # it is recorded as not applied, with why.
                approve, refused = False, PLATFORM_VERSION_REUSED
                comment = _PLATFORM_SHIPPED.format(version=proposed.version)
            elif approve and (
                unready := await self.checks.unready(
                    ContextScope.of(decider), proposed.key, self.book.policy_of(proposed)
                )
            ):
                # Approved while the context's checks passed it, and what they
                # read changed before this ran: not applied, with why.
                approve, refused, comment = False, unready.rule, unready.comment
            if approve:
                current = next(
                    (
                        v
                        for v in await work.rule_versions.list_all()
                        if v.key == proposed.key and v.status == "approved"
                    ),
                    None,
                )
                superseding = current.version_id if current is not None else None
            decided = RuleVersion.model_validate(
                {
                    **proposed.model_dump(),
                    "status": "approved" if approve else "rejected",
                    "decided_by": decider.principal_id,
                    "decided_at": self.clock.now(),
                    "comment": comment,
                }
            )
            await work.rule_versions.decide(decided, superseding=superseding)
            action = "approved" if approve else "rejected"
            await work.audit.append(
                _audit(
                    self.registry, self.ids, self.clock, decider, action, decided, refused=refused
                )
            )
            await work.commit()
        return decided
