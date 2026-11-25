"""Readings a model step made in shadow, in PostgreSQL (ticket 67, migration
in `db/migrations`: `sales_shadow_readings`).

`sales.shadow_readings` holds what a step proposed for one item while it
read in shadow, until a person's decision takes it (deleted as it is
labelled) or the retention lane drops it past its term. Narrowed by tenant
and workspace, the shape every workspace table has. `dw_app` may SELECT,
INSERT and DELETE, never UPDATE: a reading is kept as it was read.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import RowMapping
from sqlalchemy.dialects.postgresql import JSONB, UUID, insert
from sqlalchemy.ext.asyncio import AsyncSession

from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence._rows import scope_values
from dw_sales.application.ports import SalesScope
from dw_sales.domain.order_checks import ModelStep
from dw_sales.domain.shadow import ShadowReading

_TS = sa.TIMESTAMP(timezone=True)

# Mirrors the migration; constraints, policies and grants are the migration's.
shadow_readings = sa.Table(
    "shadow_readings",
    tables.metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
    sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
    sa.Column("step", sa.Text, nullable=False),
    sa.Column("item_key", sa.Text, nullable=False),
    sa.Column("message_id", sa.Text, nullable=False),
    sa.Column("attachment_id", sa.Text),
    sa.Column("line_no", sa.Integer),
    sa.Column("field", sa.Text, nullable=False),
    sa.Column("proposed", JSONB(none_as_null=True), nullable=False),
    sa.Column("prompt", sa.Text, nullable=False),
    sa.Column("model_profile", sa.Text),
    sa.Column("rules", sa.Text),
    sa.Column("confidence", sa.Float),
    sa.Column("read_at", _TS, nullable=False),
    sa.Column("case_id", UUID(as_uuid=True)),
    sa.Column("match_key", sa.Text),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
)
_S = shadow_readings


def _values(scope: SalesScope, reading: ShadowReading) -> dict[str, object]:
    return {
        "id": reading.reading_id,
        **scope_values(scope),
        "step": reading.step.value,
        "item_key": reading.item_key,
        "message_id": reading.message_id,
        "attachment_id": reading.attachment_id,
        "line_no": reading.line_no,
        "field": reading.field,
        "proposed": reading.proposed,
        "prompt": reading.prompt,
        "model_profile": reading.model_profile,
        "rules": reading.rules,
        "confidence": reading.confidence,
        "read_at": reading.read_at,
        "case_id": reading.case_id,
        "match_key": reading.match_key,
    }


def _reading(row: RowMapping) -> ShadowReading:
    return ShadowReading(
        reading_id=row["id"],
        step=ModelStep(row["step"]),
        item_key=row["item_key"],
        message_id=row["message_id"],
        attachment_id=row["attachment_id"],
        line_no=row["line_no"],
        field=row["field"],
        proposed=row["proposed"],
        prompt=row["prompt"],
        model_profile=row["model_profile"],
        rules=row["rules"],
        confidence=row["confidence"],
        read_at=row["read_at"],
        case_id=row["case_id"],
        match_key=row["match_key"],
    )


class SqlShadowReadings:
    """Implements `ShadowReadingRepositoryPort` in the unit of work's
    transaction, under its RLS. The unique key the migration holds
    (`uq_shadow_readings_item`, led by what RLS supplies) carries `take`
    and refuses a second reading of one item for one step."""

    def __init__(self, session: AsyncSession, scope: SalesScope) -> None:
        self._session = session
        self._scope = scope

    async def keep(self, readings: Sequence[ShadowReading]) -> int:
        if not readings:
            return 0
        statement = (
            insert(_S)
            .values([_values(self._scope, r) for r in readings])
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "workspace_id", "step", "item_key"]
            )
            .returning(_S.c.id)
        )
        return len((await self._session.execute(statement)).all())

    async def take(self, step: ModelStep, item_key: str) -> ShadowReading | None:
        statement = (
            sa.delete(_S).where(_S.c.step == step.value, _S.c.item_key == item_key).returning(*_S.c)
        )
        row = (await self._session.execute(statement)).mappings().first()
        return None if row is None else _reading(row)

    async def take_for_case(
        self, steps: Sequence[ModelStep], case_id: uuid.UUID
    ) -> Sequence[ShadowReading]:
        statement = (
            sa.delete(_S)
            .where(_S.c.case_id == case_id, _S.c.step.in_([s.value for s in steps]))
            .returning(*_S.c)
        )
        return [_reading(row) for row in (await self._session.execute(statement)).mappings()]

    async def take_matching(self, step: ModelStep, match_key: str) -> Sequence[ShadowReading]:
        statement = (
            sa.delete(_S)
            .where(_S.c.step == step.value, _S.c.match_key == match_key)
            .returning(*_S.c)
        )
        return [_reading(row) for row in (await self._session.execute(statement)).mappings()]

    async def prune(self, before: datetime) -> int:
        statement = sa.delete(_S).where(_S.c.read_at < before).returning(_S.c.id)
        return len((await self._session.execute(statement)).all())
