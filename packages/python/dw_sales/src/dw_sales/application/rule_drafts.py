"""A rule version drafted from a company's own file ("Tạo từ tệp mẫu", phase 1),
or from a person's words (dw_sales ADR 0006, decision 3: `rule_words`).

The person uploads the Excel template their Bravo imports; DW1 drafts a
`sales_bravo_upload` document from it, which opens in the rules editor as a
start option. **Nothing here writes a rule version**: the person reviews the
diff and sends it through `POST /rules/{key}/versions`
(`rules.SalesRulesService.propose`), and the head approves it there as any
other proposal. Only `DRAFTABLE` keys are drafted; the copy templates
(emails, documents, hand-offs) are phase 2.

- **queued**: uploaded by a holder of `sales.rules.propose`
  (`RuleDraftService.request`, 202). The bytes are kept until they are read,
  and one outbox event, `sales.rule_draft.requested`, asks the worker to read
  them. **The API reads no customer file** (ticket 25). A request also drops
  the workspace's drafts older than `KEPT_FOR`: a draft is a starting point,
  not a record (the audit keeps who asked for what).
- The worker (`RuleDrafting.draft`) scans the file (`MalwareScanPort`), has
  the reader sandbox open its sheets (`TemplateSheetsPort`), picks the header
  row by code and drops hidden cells (`template_reading`), and asks the model
  through the one-call door, as the person who asked, resolved again now
  (`RequesterAccessPort`, cut to `DRAFT_CEILING`): a person who lost the scope
  since gets nothing drafted. The bytes are dropped with the outcome:
- **ready**: the mapping passed every check (`template_reading.verify`); the
  document is the version in force with the template's sheet and columns.
- **refused**: the model answered and code refused it (the fields named).
- **unavailable**: no usable answer (model down, not configured on this
  host, or the plan's day spent).
- refused and unavailable still carry a document a person can start from:
  the version in force with only the template's sheet, the template's
  headers offered as choices, nothing guessed (`template_reading.offered`).
- **failed**: no draft at all (the file infected, unreadable, without a
  header row, or the asker no longer permitted), with the reason; or still
  queued after `STALE_AFTER` (its event spent the outbox's retries, say),
  failed by the sweep with its file dropped.

**What no request has to come for** (`RuleDraftSweep`, the worker's
`RULE_DRAFT_LANE`): each workspace with a draft due, in its own unit of work,
fails the drafts queued past `STALE_AFTER` and drops the drafts older than
`KEPT_FOR`, with their files (failure-modes #6).

Every step is audited; the worker's as itself (`lane_audit_event`,
`system:sales_rule_drafts`): ids, the key, the status, the file's hash and
the problem codes, never a header or a value.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import TracebackType
from typing import Any, Final, Literal, Protocol, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from dw_agent_runtime.contracts import RunContext
from dw_kernel.errors import DomainError, InfrastructureError, NotFoundError, QuotaExceededError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.identity import context_from
from dw_platform.application.ports import AuditRepositoryPort
from dw_platform.domain.audit import AuditEvent, lane_audit_event
from dw_platform.domain.outbox import OutboxEvent
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.artifact_content import BravoUploadLayout
from dw_sales.application.catalog_imports import OutboxPort
from dw_sales.application.malware import MalwareScanPort
from dw_sales.application.model_reading import (
    InterpretationPort,
    ModelUnavailableError,
    PromptRef,
    estimated_tokens,
)
from dw_sales.application.ports import SalesScope
from dw_sales.application.processing import RequesterAccessPort
from dw_sales.application.rule_words import (
    MAX_REQUEST_CHARS,
    OUTPUT_TOKENS,
    RULE_CHANGE_IN_WORDS,
    ModelRuleChanges,
    WordsApplied,
    apply_changes,
    focus_of,
    leaf_paths,
)
from dw_sales.application.rule_words import PROMPT_TOKENS as WORDS_PROMPT_TOKENS
from dw_sales.application.rules import DRAFTABLE, PRICE_BEARING, Resolved, RuleKey, readable
from dw_sales.application.runs import WEB_CHANNEL
from dw_sales.application.source import SheetGrid
from dw_sales.application.template_reading import (
    MAX_SHEETS,
    DraftProblem,
    ModelBravoMapping,
    Proposal,
    Refused,
    TemplateRow,
    header_row,
    mapping_inputs,
    offered,
    verify,
)

logger = logging.getLogger("dw_sales.rule_drafts")

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
_RESOURCE: Final = "sales_rule_draft"

# What the upload announces, for the worker to read the file.
RULE_DRAFT_REQUESTED: Final = "sales.rule_draft.requested"
RULE_DRAFT_EVENT_SCHEMA: Final = "1.0.0"
# The worker's lane name for its audit rows (ADR 0011-a-background-lane-audits-as-itself).
RULE_DRAFT_LANE: Final = "sales_rule_drafts"
# What the drafting needs, and so all a context it builds carries.
DRAFT_CEILING: Final = frozenset({SalesScopes.RULES_PROPOSE.value})
# The prompt a template is mapped with. Its file is
# `configs/prompts/sales/bravo_template_mapping@1.0.0.yaml`; a test holds the
# two together, and a new wording is a new version here and a new file there.
BRAVO_TEMPLATE_MAPPING: Final = PromptRef("sales.bravo_template_mapping", "1.0.0")
# What the prompt itself costs, held above its rendered size by a test.
PROMPT_TOKENS: Final = 1500
# Fifteen short headers or nulls: about 300 tokens.
_OUTPUT_TOKENS: Final = 600

MAX_DRAFT_BYTES: Final = 2 * 1024 * 1024
DRAFT_EXTENSIONS: Final = (".xlsx", ".xls")
_FILE_NAME: Final = re.compile(r"^[^/\\\x00-\x1f]{1,200}$")
# The part of a document a request in words is about: a dotted path.
_FOCUS: Final = r"^[A-Za-z_][A-Za-z0-9_.]*$"
# What a request in words is kept as, for the worker to read.
_WORDS_FILE: Final = "yeu-cau.txt"
# How long a draft is kept: the sweep, and a new request, drop older ones.
KEPT_FOR: Final = timedelta(days=30)
# How long a draft may stay queued. The worker reads one in a minute or two;
# one queued longer was lost on the way, and its file would be kept for good.
STALE_AFTER: Final = timedelta(hours=1)

DraftStatus = Literal["queued", "ready", "refused", "unavailable", "failed"]


class RuleDraft(BaseModel):
    """One draft and what became of it (module docstring)."""

    model_config = _FROZEN

    draft_id: uuid.UUID
    rule_key: RuleKey
    status: DraftStatus
    requested_by: uuid.UUID
    requested_at: AwareDatetime
    file_name: str = Field(max_length=200)
    file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    file_size: int = Field(ge=1, le=MAX_DRAFT_BYTES)
    # The header row code read, with every visible header: what a person
    # picks from when the columns were not drafted.
    template: TemplateRow | None = None
    document: Mapping[str, Any] | None = None
    machine_read: tuple[str, ...] = ()
    evidence: Mapping[str, str] = Field(default_factory=dict)
    problems: tuple[DraftProblem, ...] = ()
    error: str | None = Field(default=None, max_length=500)
    prompt_ref: str | None = None
    model_profile: str | None = None
    # A draft from words (ADR 0006): what the person typed, and the part of
    # the document it is about (None: the whole of it).
    request: str | None = Field(default=None, max_length=MAX_REQUEST_CHARS)
    focus: str | None = Field(default=None, pattern=_FOCUS, max_length=200)


class RuleDraftView(BaseModel):
    """A draft as the rules editor reads it."""

    model_config = ConfigDict(frozen=True)

    draft_id: uuid.UUID
    rule_key: RuleKey
    status: DraftStatus
    requested_by: uuid.UUID
    requested_at: datetime
    file_name: str
    file_sha256: str
    template: TemplateRow | None
    # A whole document of the key, for every status but queued and failed.
    document: dict[str, Any] | None
    # Document paths (``columns.0.header``) the machine filled, and the cell
    # each came from (``Sheet!C1``).
    machine_read: list[str]
    evidence: dict[str, str]
    problems: list[DraftProblem]
    error: str | None
    prompt_ref: str | None
    model_profile: str | None
    request: str | None
    focus: str | None


def draft_view(draft: RuleDraft) -> RuleDraftView:
    return RuleDraftView(
        draft_id=draft.draft_id,
        rule_key=draft.rule_key,
        status=draft.status,
        requested_by=draft.requested_by,
        requested_at=draft.requested_at,
        file_name=draft.file_name,
        file_sha256=draft.file_sha256,
        template=draft.template,
        document=None if draft.document is None else dict(draft.document),
        machine_read=list(draft.machine_read),
        evidence=dict(draft.evidence),
        problems=list(draft.problems),
        error=draft.error,
        prompt_ref=draft.prompt_ref,
        model_profile=draft.model_profile,
        request=draft.request,
        focus=draft.focus,
    )


# ------------------------------------------------------------------ ports --


class RuleDraftStorePort(Protocol):
    """The workspace's drafts inside a unit of work (RLS-bound)."""

    async def add(self, draft: RuleDraft, content: bytes) -> None: ...

    async def get(self, draft_id: uuid.UUID) -> RuleDraft | None: ...

    async def content(self, draft_id: uuid.UUID) -> bytes | None:
        """The bytes of a file not read yet; None once read."""
        ...

    async def settle(self, draft: RuleDraft) -> bool:
        """Writes ``draft``'s outcome where the row is still queued, and drops
        its bytes: False, and nothing written, otherwise."""
        ...

    async def prune(self, before: datetime) -> int:
        """Drops the drafts requested before ``before``, with their bytes."""
        ...

    async def queued_before(self, before: datetime) -> list[RuleDraft]:
        """The drafts still queued that were requested before ``before``."""
        ...


class RuleDraftUnitOfWork(Protocol):
    """One transaction in one workspace; leaving without `commit` rolls back."""

    @property
    def drafts(self) -> RuleDraftStorePort: ...

    @property
    def audit(self) -> AuditRepositoryPort: ...

    @property
    def outbox(self) -> OutboxPort: ...

    async def commit(self) -> None: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...


class RuleDraftUnitOfWorkFactory(Protocol):
    def __call__(self, scope: SalesScope) -> RuleDraftUnitOfWork: ...


class TemplateSheetsPort(Protocol):
    """A workbook's sheets, opened in the reader sandbox (`ClientSourceView`).
    ``kind`` reads magic numbers only, in this process. The two reads raise
    `DomainError` for a file the reader could not open, and an
    `InfrastructureError` when the sandbox does not answer."""

    def kind(self, data: bytes) -> Literal["pdf", "xlsx"] | None: ...

    async def sheet_names(self, data: bytes) -> list[str]: ...

    async def sheet_grid(self, data: bytes, sheet: str) -> SheetGrid | None: ...


class RuleDraftScopesPort(Protocol):
    """Every workspace with a draft due for the sweep, ids only, across
    tenants (`sales.rule_draft_scopes_due`): one still queued that was
    requested before ``queued_before``, or any requested before
    ``requested_before``."""

    async def scopes_due(
        self, queued_before: datetime, requested_before: datetime
    ) -> Sequence[SalesScope]: ...


class RulesInForcePort(Protocol):
    """The tenant's rule in force for a key (`TenantRuleBook.current`)."""

    async def current(self, scope: SalesScope, key: RuleKey) -> Resolved: ...


# ---------------------------------------------------------------- service --


def _details(draft: RuleDraft) -> dict[str, object]:
    return {
        "rule_key": draft.rule_key.value,
        "status": draft.status,
        "file_sha256": draft.file_sha256,
        "problems": sorted({p.code for p in draft.problems}),
    }


@dataclass(frozen=True)
class RuleDraftService:
    """The editor's side: request a draft, read it."""

    uow: RuleDraftUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    ids: IdGenerator

    async def request(
        self, context: AccessContext, key: RuleKey, file_name: str, data: bytes
    ) -> RuleDraftView:
        """A template to draft from: kept, queued for the worker (202)."""
        await self.gate.require(context, SalesScopes.RULES_PROPOSE, resource_type=_RESOURCE)
        if key not in DRAFTABLE:
            raise DomainError(
                "chỉ tạo được từ tệp mẫu cho Mẫu tệp nhập Bravo",
                details={"rule": "key_not_draftable", "key": key.value},
            )
        name = file_name.strip()
        if not _FILE_NAME.match(name):
            raise DomainError("tên tệp không hợp lệ", details={"rule": "file_name"})
        if not name.casefold().endswith(DRAFT_EXTENSIONS):
            raise DomainError("chỉ nhận tệp mẫu .xlsx hoặc .xls", details={"rule": "file_type"})
        if not data:
            raise DomainError("tệp rỗng", details={"rule": "file_empty"})
        if len(data) > MAX_DRAFT_BYTES:
            raise DomainError(
                f"tệp lớn hơn {MAX_DRAFT_BYTES // (1024 * 1024)} MB", details={"rule": "file_size"}
            )
        draft = RuleDraft(
            draft_id=self.ids.new_uuid(),
            rule_key=key,
            status="queued",
            requested_by=context.principal_id,
            requested_at=self.clock.now(),
            file_name=name,
            file_sha256=hashlib.sha256(data).hexdigest(),
            file_size=len(data),
        )
        return await self._queue(context, draft, data)

    async def request_words(
        self, context: AccessContext, key: RuleKey, request: str, focus: str | None = None
    ) -> RuleDraftView:
        """What a person wants changed, in their words, for any key they may
        propose a version of and read (a price-bearing key asks for
        `sales.price.read` too): kept, queued for the worker (202)."""
        await self.gate.require(context, SalesScopes.RULES_PROPOSE, resource_type=_RESOURCE)
        if not readable(self.gate, context, key):
            await self.gate.require(context, SalesScopes.PRICE_READ, resource_type=_RESOURCE)
        words = request.strip()
        if not words:
            raise DomainError("hãy viết điều cần đổi", details={"rule": "request_empty"})
        if len(words) > MAX_REQUEST_CHARS:
            raise DomainError(
                f"yêu cầu dài hơn {MAX_REQUEST_CHARS} ký tự", details={"rule": "request_long"}
            )
        if focus is not None and not re.fullmatch(_FOCUS, focus):
            raise DomainError("phần cần sửa không hợp lệ", details={"rule": "focus"})
        data = words.encode("utf-8")
        draft = RuleDraft(
            draft_id=self.ids.new_uuid(),
            rule_key=key,
            status="queued",
            requested_by=context.principal_id,
            requested_at=self.clock.now(),
            file_name=_WORDS_FILE,
            file_sha256=hashlib.sha256(data).hexdigest(),
            file_size=len(data),
            request=words,
            focus=focus,
        )
        return await self._queue(context, draft, data)

    async def _queue(self, context: AccessContext, draft: RuleDraft, data: bytes) -> RuleDraftView:
        now = draft.requested_at
        async with self.uow(sales_scope(context)) as work:
            await work.drafts.prune(now - KEPT_FOR)
            await work.drafts.add(draft, data)
            await work.outbox.add(
                OutboxEvent(
                    id=self.ids.new_uuid(),
                    tenant_id=TenantId(context.tenant_id),
                    workspace_id=WorkspaceId(context.workspace_id),
                    event_type=RULE_DRAFT_REQUESTED,
                    schema_version=RULE_DRAFT_EVENT_SCHEMA,
                    aggregate_id=draft.draft_id,
                    occurred_at=now,
                    payload={"draft_id": str(draft.draft_id)},
                    actor_id=context.principal_id,
                )
            )
            await work.audit.append(
                AuditEvent(
                    id=self.ids.new_uuid(),
                    tenant_id=TenantId(context.tenant_id),
                    workspace_id=WorkspaceId(context.workspace_id),
                    actor_id=UserId(context.principal_id),
                    action="sales.rule_draft.requested",
                    resource_type=_RESOURCE,
                    resource_id=str(draft.draft_id),
                    occurred_at=now,
                    details=_details(draft) | {"file_size": len(data)},
                )
            )
            await work.commit()
        return draft_view(draft)

    async def get(self, context: AccessContext, draft_id: uuid.UUID) -> RuleDraftView:
        """The draft, to whoever may propose. Another workspace's is not
        found: RLS leaves it out of every read here."""
        await self.gate.require(context, SalesScopes.RULES_PROPOSE, resource_type=_RESOURCE)
        async with self.uow(sales_scope(context)) as work:
            draft = await work.drafts.get(draft_id)
        if draft is None:
            raise NotFoundError("no such draft", details={"draft_id": str(draft_id)})
        return draft_view(draft)


# ---------------------------------------------------------- the drafting --


def _failed(draft: RuleDraft, reason: str) -> RuleDraft:
    return draft.model_copy(update={"status": "failed", "error": reason[:500]})


def _unopened(refused: DomainError) -> str:
    """Why the template could not be opened. A reader of another version
    than this process says so in its own words, since the fix is the
    reader's, not the file's (Sales defect B: it was retried until the
    sweep); any other refusal is the file's."""
    if refused.details.get("reason_code") == "reader_version_mismatch":
        return f"không mở được tệp mẫu: {refused.message}"
    return "không mở được tệp mẫu"


@dataclass(frozen=True)
class RuleDrafting:
    """The worker's side of a request: `RULE_DRAFT_REQUESTED`, carried out.

    ``model`` is the one-call door to DW1's model (the plan's daily allowance
    checked first); None on a host with no model server for DW1's profile,
    where every draft is `unavailable`. ``worker_id`` and ``worker_version``
    are DW1's (`configs/workers/sales.yaml`): what the call is recorded under."""

    uow: RuleDraftUnitOfWorkFactory
    sheets: TemplateSheetsPort
    scanner: MalwareScanPort
    rules: RulesInForcePort
    access: RequesterAccessPort
    model: InterpretationPort | None
    clock: UtcClock
    ids: IdGenerator
    worker_id: str
    worker_version: str

    async def draft(self, scope: SalesScope, draft_id: uuid.UUID) -> str:
        """Drafts one queued request; what it did, for the log. Idempotent: a
        draft no longer queued is left alone. Raises `InfrastructureError`
        when the scanner or the reader did not answer, so the outbox delivers
        it again."""
        async with self.uow(scope) as work:
            draft = await work.drafts.get(draft_id)
            content = None if draft is None else await work.drafts.content(draft_id)
        if draft is None or draft.status != "queued":
            return "draft not queued"
        settled = (
            _failed(draft, "tệp không còn để đọc")
            if content is None
            else await self._settle(scope, draft, content)
        )
        async with self.uow(scope) as work:
            if not await work.drafts.settle(settled):
                return "draft changed meanwhile"
            await work.audit.append(
                lane_audit_event(
                    lane=RULE_DRAFT_LANE,
                    event_id=self.ids.new_uuid(),
                    tenant_id=TenantId(scope.tenant_id.value),
                    workspace_id=WorkspaceId(scope.workspace_id.value),
                    action=f"sales.rule_draft.{settled.status}",
                    resource_type=_RESOURCE,
                    resource_id=str(draft_id),
                    occurred_at=self.clock.now(),
                    details=_details(settled) | {"requested_by": str(draft.requested_by)},
                )
            )
            await work.commit()
        return f"draft {settled.status}"

    async def _settle(self, scope: SalesScope, draft: RuleDraft, content: bytes) -> RuleDraft:
        if draft.request is not None:
            return await self._settle_words(scope, draft, draft.request)
        verdict = await self.scanner.scan(content)
        if verdict.outcome == "unavailable":
            raise InfrastructureError(
                "chưa quét được tệp, thử lại", details={"reason_code": "scanner_unavailable"}
            )
        if verdict.outcome == "infected":
            return _failed(draft, "tệp bị trình quét mã độc chặn")
        context = await self._asker(scope, draft)
        if context is None:
            return _failed(draft, "người tải tệp không còn quyền đề xuất quy tắc")
        if self.sheets.kind(content) != "xlsx":
            return _failed(draft, "tệp không phải bảng tính Excel")
        try:
            row = await self._header_row(content)
        except DomainError as refused:
            return _failed(draft, _unopened(refused))
        if row is None:
            return _failed(
                draft, "không tìm thấy hàng tiêu đề: cần một hàng có ít nhất 4 ô tiêu đề hiện"
            )
        base = (await self.rules.current(scope, draft.rule_key)).policy
        assert isinstance(base, BravoUploadLayout)  # the only key in `DRAFTABLE`
        drafted = draft.model_copy(update={"template": row})
        if self.model is None:
            return self._without_mapping(drafted, row, base, "unavailable", "model_not_configured")
        stamped = drafted.model_copy(
            update={
                "prompt_ref": str(BRAVO_TEMPLATE_MAPPING),
                "model_profile": self.model.model_profile,
            }
        )
        try:
            answer = await self.model.interpret(
                BRAVO_TEMPLATE_MAPPING,
                mapping_inputs(row, self.model.max_input_tokens - PROMPT_TOKENS),
                ModelBravoMapping,
                run=self._run(context, draft),
                max_output_tokens=_OUTPUT_TOKENS,
            )
        except ModelUnavailableError:
            return self._without_mapping(stamped, row, base, "unavailable", "model_unavailable")
        except QuotaExceededError:
            return self._without_mapping(stamped, row, base, "unavailable", "model_quota")
        checked = verify(answer.model_dump(), row, base)
        if isinstance(checked, Refused):
            fallback = offered(row, base)
            return _with(stamped, "refused", fallback, (*checked.problems, *fallback.problems))
        return _with(stamped, "ready", checked, checked.problems)

    async def _settle_words(self, scope: SalesScope, draft: RuleDraft, request: str) -> RuleDraft:
        """A request in words (`rule_words`): the model proposes changes to the
        part asked about, code applies and checks them. Typed by the person,
        not a customer's file, so nothing is scanned or opened in the reader."""
        price = draft.rule_key in PRICE_BEARING
        context = await self._asker(scope, draft, price=price)
        if context is None:
            return _failed(draft, "người yêu cầu không còn quyền đề xuất quy tắc này")
        base = (await self.rules.current(scope, draft.rule_key)).policy.model_dump(
            mode="json", by_alias=True
        )
        try:
            part = focus_of(base, draft.focus)
        except (KeyError, IndexError, ValueError):
            return _failed(draft, "quy tắc không có phần được yêu cầu sửa")
        in_force = Proposal(document=base, machine_read=(), evidence={})
        if self.model is None:
            return _with(draft, "unavailable", in_force, (_problem("model_not_configured"),))
        inputs = {
            "rule_name": draft.rule_key.value,
            "document": json.dumps(part, ensure_ascii=False, indent=1),
            "paths": "\n".join(leaf_paths(part)),
            "request": request,
        }
        room = self.model.max_input_tokens - WORDS_PROMPT_TOKENS
        if estimated_tokens("".join(inputs.values())) > room:
            return _failed(draft, "phần cần sửa quá dài cho một lần đọc: chọn phần nhỏ hơn")
        stamped = draft.model_copy(
            update={
                "prompt_ref": str(RULE_CHANGE_IN_WORDS),
                "model_profile": self.model.model_profile,
            }
        )
        try:
            answer = await self.model.interpret(
                RULE_CHANGE_IN_WORDS,
                inputs,
                ModelRuleChanges,
                run=self._run(context, draft),
                max_output_tokens=OUTPUT_TOKENS,
            )
        except ModelUnavailableError:
            return _with(stamped, "unavailable", in_force, (_problem("model_unavailable"),))
        except QuotaExceededError:
            return _with(stamped, "unavailable", in_force, (_problem("model_quota"),))
        applied = apply_changes(draft.rule_key, base, answer, request=request, focus=draft.focus)
        if not isinstance(applied, WordsApplied):
            problems = tuple(_problem(p.code, p.path) for p in applied.problems)
            return _with(stamped, "refused", in_force, problems)
        drafted = Proposal(
            document=applied.document,
            machine_read=applied.changed,
            evidence=dict.fromkeys(applied.changed, "yêu cầu"),
        )
        return _with(stamped, "ready", drafted, ())

    def _without_mapping(
        self,
        draft: RuleDraft,
        row: TemplateRow,
        base: BravoUploadLayout,
        status: DraftStatus,
        why: Literal["model_unavailable", "model_not_configured", "model_quota"],
    ) -> RuleDraft:
        fallback = offered(row, base)
        return _with(draft, status, fallback, (DraftProblem(code=why), *fallback.problems))

    async def _asker(
        self, scope: SalesScope, draft: RuleDraft, *, price: bool = False
    ) -> AccessContext | None:
        """Who asked, as the platform resolves them now, cut to the ceiling;
        None when they may no longer propose, or the context is another
        workspace's. ``price``: the key holds prices, so the asker must still
        read them too."""
        ceiling = DRAFT_CEILING | ({SalesScopes.PRICE_READ.value} if price else frozenset())
        access = await self.access.find_linked_access(
            draft.requested_by, scope.tenant_id.value, scope.workspace_id.value, ceiling
        )
        if access is None:
            return None
        context = context_from(access)
        if sales_scope(context) != scope or not ceiling <= context.scopes:
            return None
        return context

    async def _header_row(self, content: bytes) -> TemplateRow | None:
        for name in (await self.sheets.sheet_names(content))[:MAX_SHEETS]:
            grid = await self.sheets.sheet_grid(content, name)
            row = None if grid is None else header_row(grid)
            if row is not None:
                return row
        return None

    def _run(self, context: AccessContext, draft: RuleDraft) -> RunContext:
        """The one call's run, as the asker: their plan is what the allowance
        checks, and the call is recorded under DW1's worker."""
        run_id = self.ids.new_uuid()
        return RunContext(
            run_id=run_id,
            tenant_id=context.tenant_id,
            workspace_id=context.workspace_id,
            actor_id=context.principal_id,
            worker_id=self.worker_id,
            worker_version=self.worker_version,
            channel=WEB_CHANNEL,
            plan_id=context.plan_id,
            roles=context.roles,
            scopes=context.scopes,
            clearance=context.clearance,
            record_visibility=context.record_visibility,
            visible_owners=context.visible_owners,
            autonomy_ceiling=context.max_autonomy_level,
            trace_id=f"sales-draft-{run_id.hex[:12]}",
            subject_ref=f"{_RESOURCE}:{draft.draft_id}",
        )


def _problem(code: str, where: str | None = None) -> DraftProblem:
    return DraftProblem.model_validate({"code": code, "where": where})


def _with(
    draft: RuleDraft, status: DraftStatus, proposal: Proposal, problems: Sequence[DraftProblem]
) -> RuleDraft:
    return draft.model_copy(
        update={
            "status": status,
            "document": proposal.document,
            "machine_read": proposal.machine_read,
            "evidence": dict(proposal.evidence),
            "problems": tuple(problems)[:60],
        }
    )


# ------------------------------------------------------------- the sweep --

_STALE_REASON: Final = "DW1 không đọc xong tệp trong 1 giờ: hãy tải lại tệp mẫu"


@dataclass(frozen=True, slots=True)
class Swept:
    """What one workspace's sweep did: drafts failed as stale, and dropped."""

    expired: int
    pruned: int


@dataclass(frozen=True)
class RuleDraftSweep:
    """The worker's `RULE_DRAFT_LANE` (module docstring): ``due`` names the
    workspaces to visit, ``sweep`` visits one, as the lane."""

    uow: RuleDraftUnitOfWorkFactory
    scopes: RuleDraftScopesPort
    clock: UtcClock
    ids: IdGenerator

    async def due(self) -> Sequence[SalesScope]:
        now = self.clock.now()
        return await self.scopes.scopes_due(now - STALE_AFTER, now - KEPT_FOR)

    async def sweep(self, scope: SalesScope) -> Swept:
        """Fails the workspace's drafts queued past `STALE_AFTER`, dropping
        their files, then drops its drafts older than `KEPT_FOR`. A draft the
        worker settles meanwhile is left as it settled (`settle` writes only
        a queued one)."""
        now = self.clock.now()
        expired = 0
        async with self.uow(scope) as work:
            for draft in await work.drafts.queued_before(now - STALE_AFTER):
                failed = _failed(draft, _STALE_REASON)
                if not await work.drafts.settle(failed):
                    continue
                expired += 1
                await work.audit.append(
                    lane_audit_event(
                        lane=RULE_DRAFT_LANE,
                        event_id=self.ids.new_uuid(),
                        tenant_id=TenantId(scope.tenant_id.value),
                        workspace_id=WorkspaceId(scope.workspace_id.value),
                        action="sales.rule_draft.failed",
                        resource_type=_RESOURCE,
                        resource_id=str(draft.draft_id),
                        occurred_at=now,
                        details=_details(failed)
                        | {"requested_by": str(draft.requested_by), "reason": "stale"},
                    )
                )
            pruned = await work.drafts.prune(now - KEPT_FOR)
            await work.commit()
        return Swept(expired=expired, pruned=pruned)
