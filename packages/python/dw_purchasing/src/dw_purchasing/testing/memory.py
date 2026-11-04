"""An in-memory Purchasing store for tests and the eval smoke.

It honours what the SQL store promises: every transaction sees only its own
tenant and workspace (as RLS narrows them), a transaction that raises leaves
nothing behind, a message is settled once (`ConflictError` the second time),
an outcome names only a case already written, and a case id is never
written twice.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Collection, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from dw_kernel.errors import ConflictError
from dw_kernel.ids import UserId
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ApprovalAudience
from dw_platform.application.rule_versions import (
    ONE_OPEN_PROPOSAL,
    RuleScope,
    RuleStatus,
    RuleVersion,
)
from dw_platform.domain.approval import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
    DecisionOutcome,
)
from dw_platform.domain.audit import AuditEvent
from dw_purchasing.application.master_data import MasterImport
from dw_purchasing.application.ports import MessageOutcome
from dw_purchasing.application.rfq_mail import RfqMail
from dw_purchasing.domain.cases import PurchaseCase
from dw_purchasing.domain.master_lists import ParsedWorkbook

_Scope = tuple[uuid.UUID, uuid.UUID]


@dataclass
class _Rows:
    cases: dict[uuid.UUID, PurchaseCase] = field(default_factory=dict)
    outcomes: dict[str, MessageOutcome] = field(default_factory=dict)
    audit: list[AuditEvent] = field(default_factory=list)
    approvals: dict[uuid.UUID, ApprovalRequest] = field(default_factory=dict)
    decisions: dict[uuid.UUID, ApprovalDecision] = field(default_factory=dict)

    def copy(self) -> _Rows:
        return _Rows(
            dict(self.cases),
            dict(self.outcomes),
            list(self.audit),
            dict(self.approvals),
            dict(self.decisions),
        )


@dataclass
class _Cases:
    rows: _Rows

    async def add(self, case: PurchaseCase) -> None:
        if case.case_id in self.rows.cases:
            raise ConflictError("case exists", details={"case_id": str(case.case_id)})
        self.rows.cases[case.case_id] = case

    async def get(self, case_id: uuid.UUID) -> PurchaseCase | None:
        return self.rows.cases.get(case_id)

    async def save(self, case: PurchaseCase, *, expected_version: int) -> None:
        stored = self.rows.cases.get(case.case_id)
        if stored is None or stored.case_version != expected_version:
            raise ConflictError("hồ sơ đã thay đổi", details={"rule": "stale_version"})
        self.rows.cases[case.case_id] = case

    async def by_approval(self, approval_id: uuid.UUID) -> PurchaseCase | None:
        return next(
            (
                c
                for c in self.rows.cases.values()
                if (c.approval is not None and c.approval.approval_id == approval_id)
                or (c.reapproval is not None and c.reapproval.approval.approval_id == approval_id)
            ),
            None,
        )

    async def waiting(self, statuses: frozenset[str], *, limit: int) -> Sequence[PurchaseCase]:
        found = [c for c in self.rows.cases.values() if c.status in statuses]
        return sorted(found, key=lambda c: (c.received_at, c.case_id))[:limit]

    async def page(
        self,
        *,
        limit: int,
        before: tuple[datetime, uuid.UUID] | None,
        requested_by: uuid.UUID | None = None,
    ) -> Sequence[PurchaseCase]:
        ordered = sorted(
            (
                c
                for c in self.rows.cases.values()
                if requested_by is None or c.requested_by == requested_by
            ),
            key=lambda c: (c.received_at, c.case_id),
            reverse=True,
        )
        if before is not None:
            ordered = [c for c in ordered if (c.received_at, c.case_id) < before]
        return ordered[:limit]


@dataclass
class _Outcomes:
    rows: _Rows

    async def get(self, message_id: str) -> MessageOutcome | None:
        return self.rows.outcomes.get(message_id)

    async def add(self, outcome: MessageOutcome) -> None:
        if outcome.message_id in self.rows.outcomes:
            raise ConflictError("thư đã được xử lý", details={"message_id": outcome.message_id})
        if outcome.case_id is not None and outcome.case_id not in self.rows.cases:
            # `fk_mail_outcomes_case_id_cases`: the case is written first.
            raise ValueError("an outcome names a case that does not exist")
        self.rows.outcomes[outcome.message_id] = outcome

    async def all(self) -> Sequence[MessageOutcome]:
        return list(self.rows.outcomes.values())


@dataclass
class _Audit:
    rows: _Rows

    async def append(self, event: AuditEvent) -> None:
        self.rows.audit.append(event)


@dataclass
class _Approvals:
    """The platform's approvals as `ApprovalAudience` serves them: a stamped
    request is seen by who may decide it and by its requester only."""

    rows: _Rows

    async def add(self, request: ApprovalRequest) -> None:
        self.rows.approvals[request.id] = request

    async def get(
        self, request_id: uuid.UUID, *, workspace_id: uuid.UUID, audience: ApprovalAudience
    ) -> ApprovalRequest | None:
        request = self.rows.approvals.get(request_id)
        if request is None or request.workspace_id.value != workspace_id:
            return None
        return request if audience.may_see(request) else None

    async def latest_decision(
        self, request_id: uuid.UUID, *, workspace_id: uuid.UUID, audience: ApprovalAudience
    ) -> ApprovalDecision | None:
        if await self.get(request_id, workspace_id=workspace_id, audience=audience) is None:
            return None
        return self.rows.decisions.get(request_id)


@dataclass
class _Versions:
    """One tenant's rule versions, refusing what `platform.rule_versions`
    refuses: a number twice, a second proposal on a key."""

    held: dict[uuid.UUID, RuleVersion]

    async def list_all(
        self,
        *,
        keys: Collection[str] | None = None,
        statuses: Collection[RuleStatus] | None = None,
    ) -> Sequence[RuleVersion]:
        versions = [
            v
            for v in self.held.values()
            if (keys is None or v.key in keys) and (statuses is None or v.status in statuses)
        ]
        return sorted(versions, key=lambda v: (v.proposed_at, v.version_id), reverse=True)

    async def get(self, version_id: uuid.UUID) -> RuleVersion | None:
        return self.held.get(version_id)

    def _once(self, version: RuleVersion) -> None:
        if any(v.key == version.key and v.version == version.version for v in self.held.values()):
            raise ConflictError(
                "refused", details={"constraint": "uq_rule_versions_tenant_id_key_version"}
            )

    async def add(self, version: RuleVersion) -> None:
        self._once(version)
        if any(v.key == version.key and v.status == "proposed" for v in self.held.values()):
            raise ConflictError(
                "quy tắc này đã có một phiên bản chờ duyệt",
                details={"constraint": "uq_rule_versions_one_proposed", "rule": ONE_OPEN_PROPOSAL},
            )
        self.held[version.version_id] = version

    def _supersede(self, superseding: uuid.UUID | None) -> None:
        if superseding is not None and superseding in self.held:
            self.held[superseding] = self.held[superseding].model_copy(
                update={"status": "superseded"}
            )

    async def decide(self, version: RuleVersion, *, superseding: uuid.UUID | None) -> None:
        stored = self.held.get(version.version_id)
        if stored is None or stored.status != "proposed":
            raise ConflictError("the version is decided already")
        self._supersede(superseding)
        self.held[version.version_id] = version

    async def apply(self, version: RuleVersion, *, superseding: uuid.UUID | None) -> None:
        self._once(version)
        self._supersede(superseding)
        self.held[version.version_id] = version


@dataclass
class _Work:
    rows: _Rows
    versions: dict[uuid.UUID, RuleVersion] = field(default_factory=dict)

    @property
    def rule_versions(self) -> _Versions:
        return _Versions(self.versions)

    async def commit(self) -> None:
        return None

    @property
    def cases(self) -> _Cases:
        return _Cases(self.rows)

    @property
    def outcomes(self) -> _Outcomes:
        return _Outcomes(self.rows)

    @property
    def audit(self) -> _Audit:
        return _Audit(self.rows)

    @property
    def approvals(self) -> _Approvals:
        return _Approvals(self.rows)


@dataclass
class MemoryStore:
    """Implements `PurchasingUnitOfWork` (call it with a context)."""

    scopes: dict[_Scope, _Rows] = field(default_factory=dict)
    # Rule versions are the tenant's, whichever workspace proposed them.
    versions: dict[uuid.UUID, dict[uuid.UUID, RuleVersion]] = field(default_factory=dict)

    @asynccontextmanager
    async def __call__(self, context: AccessContext) -> AsyncIterator[_Work]:
        key = (context.tenant_id, context.workspace_id)
        working = self.scopes.get(key, _Rows()).copy()
        versions = dict(self.versions.get(context.tenant_id, {}))
        yield _Work(working, versions)
        self.scopes[key] = working
        self.versions[context.tenant_id] = versions

    async def approved(self, scope: RuleScope, key: str) -> RuleVersion | None:
        """`RuleVersionLookupPort`: the tenant's version in force, never another's."""
        held = self.versions.get(scope.tenant_id.value, {}).values()
        return next((v for v in held if v.key == key and v.status == "approved"), None)

    async def find(self, scope: RuleScope, key: str, version: str) -> RuleVersion | None:
        held = self.versions.get(scope.tenant_id.value, {}).values()
        return next((v for v in held if v.key == key and v.version == version), None)

    def rows(self, tenant_id: uuid.UUID, workspace_id: uuid.UUID) -> _Rows:
        return self.scopes.get((tenant_id, workspace_id), _Rows())

    def decide(
        self,
        approval_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        approved: bool,
        decided_by: uuid.UUID,
        at: datetime,
        comment: str = "",
    ) -> None:
        """What the platform's approval flow writes when a person decides:
        the request's status and its decision row (the run-less event is the
        caller's to deliver, as the worker does)."""
        rows = self.rows(tenant_id, workspace_id)
        request = rows.approvals[approval_id]
        request.status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        rows.decisions[approval_id] = ApprovalDecision(
            id=uuid.uuid4(),
            request_id=approval_id,
            tenant_id=request.tenant_id,
            workspace_id=request.workspace_id,
            decided_by=UserId(decided_by),
            outcome=DecisionOutcome.APPROVED if approved else DecisionOutcome.REJECTED,
            comment=comment,
            decided_at=at,
        )


@dataclass
class MemoryMasterImports:
    """Implements `MasterImportsPort` as `SqlMasterImports` behaves: one open
    import per workspace, a file read only while queued, sent only once
    parsed, its bytes gone once read."""

    rows: dict[_Scope, dict[uuid.UUID, tuple[MasterImport, bytes | None]]] = field(
        default_factory=dict
    )
    audit: list[AuditEvent] = field(default_factory=list)

    def _of(self, tenant_id: uuid.UUID, workspace_id: uuid.UUID) -> dict[uuid.UUID, Any]:
        return self.rows.setdefault((tenant_id, workspace_id), {})

    def _seen(self, scope: RuleScope) -> dict[uuid.UUID, Any]:
        return self.rows.get((scope.tenant_id.value, scope.workspace_id.value), {})

    async def add(self, record: MasterImport, content: bytes, event: AuditEvent) -> None:
        held = self._of(event.tenant_id.value, event.workspace_id.value)
        for import_id, (other, _) in list(held.items()):
            if other.status in ("queued", "parsed"):
                del held[import_id]
        held[record.import_id] = (record, content)
        self.audit.append(event)

    async def recent(self, scope: RuleScope, *, limit: int) -> Sequence[MasterImport]:
        held = self._seen(scope).values()
        return sorted((r for r, _ in held), key=lambda r: r.uploaded_at, reverse=True)[:limit]

    async def get(self, scope: RuleScope, import_id: uuid.UUID) -> MasterImport | None:
        found = self._seen(scope).get(import_id)
        return None if found is None else found[0]

    async def submitted(
        self, record: MasterImport, *, ref: str, by: uuid.UUID, at: datetime, event: AuditEvent
    ) -> bool:
        held = self._of(event.tenant_id.value, event.workspace_id.value)
        found = held.get(record.import_id)
        if found is None or found[0].status != "parsed":
            return False
        held[record.import_id] = (
            found[0].model_copy(
                update={
                    "status": "submitted",
                    "version_ref": ref,
                    "submitted_by": by,
                    "submitted_at": at,
                }
            ),
            None,
        )
        self.audit.append(event)
        return True

    async def queued(self, scope: RuleScope, *, limit: int) -> Sequence[tuple[MasterImport, bytes]]:
        held = self._seen(scope).values()
        waiting = sorted(
            ((r, c) for r, c in held if r.status == "queued" and c is not None),
            key=lambda pair: pair[0].uploaded_at,
        )
        return waiting[:limit]

    async def read(
        self,
        scope: RuleScope,
        import_id: uuid.UUID,
        parsed: ParsedWorkbook,
        *,
        at: datetime,
        event: AuditEvent,
    ) -> None:
        held = self._of(scope.tenant_id.value, scope.workspace_id.value)
        found = held.get(import_id)
        if found is None or found[0].status != "queued":
            return
        held[import_id] = (
            found[0].model_copy(
                update={
                    "status": "failed" if parsed.failure else "parsed",
                    "read_at": at,
                    "lists": None if parsed.failure else parsed.lists,
                    "rejected": parsed.rejected,
                    "rejected_total": parsed.rejected_total,
                    "failure": parsed.failure,
                }
            ),
            None,
        )
        self.audit.append(event)

    async def forget(self, scope: RuleScope, *, read_before: datetime) -> int:
        held = self._of(scope.tenant_id.value, scope.workspace_id.value)
        gone = [
            i for i, (r, _) in held.items() if r.read_at is not None and r.read_at < read_before
        ]
        for import_id in gone:
            del held[import_id]
        return len(gone)


@dataclass
class MemoryRfqMails:
    """Implements `RfqMailsPort` as `SqlRfqMails` behaves: one active mail per
    supplier of a case, a mail written only while queued, settled once."""

    rows: dict[_Scope, dict[uuid.UUID, RfqMail]] = field(default_factory=dict)
    audit: list[AuditEvent] = field(default_factory=list)

    def _seen(self, scope: RuleScope) -> dict[uuid.UUID, RfqMail]:
        return self.rows.get((scope.tenant_id.value, scope.workspace_id.value), {})

    async def add(self, mail: RfqMail, event: AuditEvent) -> None:
        held = self.rows.setdefault((event.tenant_id.value, event.workspace_id.value), {})
        if any(
            m.case_id == mail.case_id
            and m.supplier_code == mail.supplier_code
            and m.status in ("queued", "written", "sent")
            for m in held.values()
        ):
            raise ConflictError("already sent", details={"rule": "already_sent"})
        held[mail.mail_id] = mail
        self.audit.append(event)

    async def of_case(self, scope: RuleScope, case_id: uuid.UUID) -> Sequence[RfqMail]:
        mails = [m for m in self._seen(scope).values() if m.case_id == case_id]
        return sorted(mails, key=lambda m: m.queued_at)

    async def get(self, scope: RuleScope, mail_id: uuid.UUID) -> RfqMail | None:
        return self._seen(scope).get(mail_id)

    async def pending(self, scope: RuleScope) -> Sequence[RfqMail]:
        mails = [m for m in self._seen(scope).values() if m.status in ("queued", "written")]
        return sorted(mails, key=lambda m: m.queued_at)

    async def written(self, scope: RuleScope, mail_id: uuid.UUID, *, at: datetime) -> bool:
        held = self._seen(scope)
        mail = held.get(mail_id)
        if mail is None or mail.status != "queued":
            return False
        held[mail_id] = mail.model_copy(update={"status": "written", "written_at": at})
        return True

    async def settle(
        self,
        scope: RuleScope,
        mail_id: uuid.UUID,
        *,
        status: str,
        error: str | None,
        at: datetime,
        event: AuditEvent,
    ) -> bool:
        held = self._seen(scope)
        mail = held.get(mail_id)
        if mail is None or mail.status not in ("queued", "written"):
            return False
        held[mail_id] = mail.model_copy(update={"status": status, "error": error, "settled_at": at})
        self.audit.append(event)
        return True


@dataclass
class MemoryAssistantStore:
    """Implements `AssistantStorePort` as RLS does: each tenant, workspace and
    person sees their own sessions only."""

    sessions_by_scope: dict[tuple[uuid.UUID, uuid.UUID, uuid.UUID], dict[uuid.UUID, Any]] = field(
        default_factory=dict
    )
    turns_by_session: dict[uuid.UUID, list[Any]] = field(default_factory=dict)

    def _mine(self, context: AccessContext) -> dict[uuid.UUID, Any]:
        key = (context.tenant_id, context.workspace_id, context.principal_id)
        return self.sessions_by_scope.setdefault(key, {})

    async def sessions(self, context: AccessContext, *, limit: int) -> Sequence[Any]:
        mine = sorted(self._mine(context).values(), key=lambda s: s.last_turn_at, reverse=True)
        return mine[:limit]

    async def session(self, context: AccessContext, session_id: uuid.UUID) -> Any:
        return self._mine(context).get(session_id)

    async def turns(self, context: AccessContext, session_id: uuid.UUID) -> Sequence[Any]:
        if session_id not in self._mine(context):
            return []
        return list(self.turns_by_session.get(session_id, []))

    async def append(self, context: AccessContext, session: Any, turn: Any) -> None:
        mine = self._mine(context)
        if session.user_id != context.principal_id:
            raise ConflictError("a turn is written to the asker's own session")
        mine[session.session_id] = session
        self.turns_by_session.setdefault(session.session_id, []).append(turn)
