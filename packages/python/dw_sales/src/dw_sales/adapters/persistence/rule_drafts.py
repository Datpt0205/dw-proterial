"""Rule drafts in PostgreSQL ("Tạo từ tệp mẫu", migration 42868d8c21c5).

`SqlRuleDrafts` is a unit of work's `drafts`: the workspace's drafts and
their files until read. It rides the catalog unit of work
(`SqlCatalogUnitOfWork`), which already binds one workspace and carries the
platform's audit and outbox in its transaction: the two Protocols are
separate (`CatalogUnitOfWork`, `RuleDraftUnitOfWork`), the transaction one.

`sales.rule_draft*` is narrowed by tenant and workspace: RLS is what keeps
one workspace's drafts from another; every query here names the scope too.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence._rows import refusals_named, scope_values
from dw_sales.application.ports import SalesScope
from dw_sales.application.rule_drafts import RuleDraft
from dw_sales.application.rules import RuleKey
from dw_sales.application.template_reading import DraftProblem, TemplateRow

_D = tables.rule_drafts
_F = tables.rule_draft_files
_SCOPES_DUE = sa.text(
    "SELECT tenant_id, workspace_id"
    " FROM sales.rule_draft_scopes_due(:queued_before, :requested_before)"
)


def _draft(row: RowMapping) -> RuleDraft:
    return RuleDraft(
        draft_id=row["id"],
        rule_key=RuleKey(row["rule_key"]),
        status=row["status"],
        requested_by=row["requested_by"],
        requested_at=row["requested_at"],
        file_name=row["file_name"],
        file_sha256=row["file_sha256"],
        file_size=row["file_size"],
        template=None if row["template"] is None else TemplateRow.model_validate(row["template"]),
        document=row["document"],
        machine_read=tuple(row["machine_read"]),
        evidence=dict(row["evidence"]),
        problems=tuple(DraftProblem.model_validate(p) for p in row["problems"]),
        error=row["error"],
        prompt_ref=row["prompt_ref"],
        model_profile=row["model_profile"],
        request=row["request"],
        focus=row["focus"],
    )


def _outcome(draft: RuleDraft) -> dict[str, object]:
    """What settling writes: everything but who asked for which file, when."""
    return {
        "status": draft.status,
        "template": None if draft.template is None else draft.template.model_dump(mode="json"),
        "document": None if draft.document is None else dict(draft.document),
        "machine_read": list(draft.machine_read),
        "evidence": dict(draft.evidence),
        "problems": [p.model_dump(mode="json") for p in draft.problems],
        "error": draft.error,
        "prompt_ref": draft.prompt_ref,
        "model_profile": draft.model_profile,
    }


@dataclass(frozen=True)
class SqlRuleDrafts:
    """Implements `RuleDraftStorePort` inside a unit of work."""

    session: AsyncSession
    scope: SalesScope

    def _mine(self, table: sa.Table) -> tuple[sa.ColumnElement[bool], ...]:
        return (
            table.c.tenant_id == self.scope.tenant_id.value,
            table.c.workspace_id == self.scope.workspace_id.value,
        )

    async def add(self, draft: RuleDraft, content: bytes) -> None:
        async with refusals_named(self.session, draft_id=str(draft.draft_id)):
            await self.session.execute(
                sa.insert(_D).values(
                    id=draft.draft_id,
                    **scope_values(self.scope),
                    rule_key=draft.rule_key.value,
                    requested_by=draft.requested_by,
                    requested_at=draft.requested_at,
                    file_name=draft.file_name,
                    file_sha256=draft.file_sha256,
                    file_size=draft.file_size,
                    request=draft.request,
                    focus=draft.focus,
                    **_outcome(draft),
                )
            )
            await self.session.execute(
                sa.insert(_F).values(
                    **scope_values(self.scope), draft_id=draft.draft_id, content=content
                )
            )

    async def get(self, draft_id: uuid.UUID) -> RuleDraft | None:
        row = (
            (await self.session.execute(sa.select(_D).where(*self._mine(_D), _D.c.id == draft_id)))
            .mappings()
            .first()
        )
        return None if row is None else _draft(row)

    async def content(self, draft_id: uuid.UUID) -> bytes | None:
        found = await self.session.scalar(
            sa.select(_F.c.content).where(*self._mine(_F), _F.c.draft_id == draft_id)
        )
        return None if found is None else bytes(found)

    async def settle(self, draft: RuleDraft) -> bool:
        async with refusals_named(self.session, draft_id=str(draft.draft_id)):
            written = await self.session.execute(
                sa.update(_D)
                .where(*self._mine(_D), _D.c.id == draft.draft_id, _D.c.status == "queued")
                .values(**_outcome(draft))
                .returning(_D.c.id)
            )
            if written.first() is None:
                return False
            # The file is kept only until it is read.
            await self.session.execute(
                sa.delete(_F).where(*self._mine(_F), _F.c.draft_id == draft.draft_id)
            )
        return True

    async def prune(self, before: datetime) -> int:
        # `ix_rule_drafts_requested` carries this; the files go by cascade.
        pruned = await self.session.execute(
            sa.delete(_D).where(*self._mine(_D), _D.c.requested_at < before).returning(_D.c.id)
        )
        return len(pruned.all())

    async def queued_before(self, before: datetime) -> list[RuleDraft]:
        rows = (
            await self.session.execute(
                sa.select(_D)
                .where(*self._mine(_D), _D.c.status == "queued", _D.c.requested_at < before)
                .order_by(_D.c.requested_at)
            )
        ).mappings()
        return [_draft(row) for row in rows]


@dataclass(frozen=True)
class SqlRuleDraftScopes:
    """Implements `RuleDraftScopesPort`: ids only, from the one SECURITY
    DEFINER read that crosses tenants (migration e8a1c3e8ed78)."""

    session_factory: async_sessionmaker[AsyncSession]

    async def scopes_due(
        self, queued_before: datetime, requested_before: datetime
    ) -> Sequence[SalesScope]:
        async with self.session_factory() as session:
            rows = (
                await session.execute(
                    _SCOPES_DUE,
                    {"queued_before": queued_before, "requested_before": requested_before},
                )
            ).all()
        return [SalesScope(TenantId(t), WorkspaceId(w)) for t, w in rows]
