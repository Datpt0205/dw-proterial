"""Worked examples in PostgreSQL (ticket 38, migration d94bf01066d2).

`SqlSalesOrderExamples` is a unit of work's `examples`: the workspace's
examples and their two files until read. It rides the catalog unit of work
(`SqlCatalogUnitOfWork`), which already binds one workspace and carries the
platform's audit and outbox in its transaction.

`sales.salesorder_example*` is narrowed by tenant and workspace: RLS is what
keeps one workspace's examples from another; every query here names the
scope too.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from dw_sales.adapters.persistence import tables
from dw_sales.adapters.persistence._rows import refusals_named, scope_values
from dw_sales.application.ports import SalesScope
from dw_sales.application.salesorder_learning import (
    LearnProblem,
    Replay,
    SalesOrderExample,
)
from dw_sales.application.salesorder_rules import CustomerSalesOrderRules

_E = tables.salesorder_examples
_F = tables.salesorder_example_files


def _example(row: RowMapping) -> SalesOrderExample:
    return SalesOrderExample(
        example_id=row["id"],
        customer_code=row["customer_code"],
        status=row["status"],
        requested_by=row["requested_by"],
        requested_at=row["requested_at"],
        received_on=row["received_on"],
        po_file_name=row["po_file_name"],
        po_sha256=row["po_sha256"],
        po_size=row["po_size"],
        salesorder_file_name=row["salesorder_file_name"],
        salesorder_sha256=row["salesorder_sha256"],
        salesorder_size=row["salesorder_size"],
        rules=(
            None if row["rules"] is None else CustomerSalesOrderRules.model_validate(row["rules"])
        ),
        replay=None if row["replay"] is None else Replay.model_validate(row["replay"]),
        problems=tuple(LearnProblem.model_validate(p) for p in row["problems"]),
        error=row["error"],
        prompt_ref=row["prompt_ref"],
        model_profile=row["model_profile"],
        version_id=row["version_id"],
    )


def _outcome(example: SalesOrderExample) -> dict[str, object]:
    """What settling writes: everything but who asked for which pair, when."""
    return {
        "status": example.status,
        "rules": (
            None if example.rules is None else example.rules.model_dump(mode="json", by_alias=True)
        ),
        "replay": None if example.replay is None else example.replay.model_dump(mode="json"),
        "problems": [p.model_dump(mode="json") for p in example.problems],
        "error": example.error,
        "prompt_ref": example.prompt_ref,
        "model_profile": example.model_profile,
    }


@dataclass(frozen=True)
class SqlSalesOrderExamples:
    """Implements `ExampleStorePort` inside a unit of work."""

    session: AsyncSession
    scope: SalesScope

    def _mine(self, table: sa.Table) -> tuple[sa.ColumnElement[bool], ...]:
        return (
            table.c.tenant_id == self.scope.tenant_id.value,
            table.c.workspace_id == self.scope.workspace_id.value,
        )

    async def add(self, example: SalesOrderExample, po: bytes, salesorder: bytes) -> None:
        async with refusals_named(self.session, example_id=str(example.example_id)):
            await self.session.execute(
                sa.insert(_E).values(
                    id=example.example_id,
                    **scope_values(self.scope),
                    customer_code=example.customer_code,
                    requested_by=example.requested_by,
                    requested_at=example.requested_at,
                    received_on=example.received_on,
                    po_file_name=example.po_file_name,
                    po_sha256=example.po_sha256,
                    po_size=example.po_size,
                    salesorder_file_name=example.salesorder_file_name,
                    salesorder_sha256=example.salesorder_sha256,
                    salesorder_size=example.salesorder_size,
                    version_id=example.version_id,
                    **_outcome(example),
                )
            )
            await self.session.execute(
                sa.insert(_F),
                [
                    {
                        **scope_values(self.scope),
                        "example_id": example.example_id,
                        "kind": kind,
                        "content": content,
                    }
                    for kind, content in (("po", po), ("salesorder", salesorder))
                ],
            )

    async def get(self, example_id: uuid.UUID) -> SalesOrderExample | None:
        row = (
            (
                await self.session.execute(
                    sa.select(_E).where(*self._mine(_E), _E.c.id == example_id)
                )
            )
            .mappings()
            .first()
        )
        return None if row is None else _example(row)

    async def files(self, example_id: uuid.UUID) -> tuple[bytes, bytes] | None:
        rows = (
            await self.session.execute(
                sa.select(_F.c.kind, _F.c.content).where(
                    *self._mine(_F), _F.c.example_id == example_id
                )
            )
        ).all()
        found = {kind: bytes(content) for kind, content in rows}
        if set(found) != {"po", "salesorder"}:
            return None
        return found["po"], found["salesorder"]

    async def settle(self, example: SalesOrderExample) -> bool:
        async with refusals_named(self.session, example_id=str(example.example_id)):
            written = await self.session.execute(
                sa.update(_E)
                .where(*self._mine(_E), _E.c.id == example.example_id, _E.c.status == "queued")
                .values(**_outcome(example))
                .returning(_E.c.id)
            )
            if written.first() is None:
                return False
            # The files are kept only until they are read.
            await self.session.execute(
                sa.delete(_F).where(*self._mine(_F), _F.c.example_id == example.example_id)
            )
        return True

    async def submit(self, example_id: uuid.UUID, version_id: uuid.UUID) -> bool:
        async with refusals_named(self.session, example_id=str(example_id)):
            written = await self.session.execute(
                sa.update(_E)
                .where(*self._mine(_E), _E.c.id == example_id, _E.c.status == "replayed")
                .values(status="submitted", version_id=version_id)
                .returning(_E.c.id)
            )
            return written.first() is not None

    async def for_customer(self, customer_code: str, limit: int) -> Sequence[SalesOrderExample]:
        # `ix_salesorder_examples_customer` carries this.
        rows = (
            await self.session.execute(
                sa.select(_E)
                .where(*self._mine(_E), _E.c.customer_code == customer_code)
                .order_by(_E.c.requested_at.desc())
                .limit(limit)
            )
        ).mappings()
        return [_example(row) for row in rows]

    async def for_version(self, version_id: uuid.UUID) -> SalesOrderExample | None:
        row = (
            (
                await self.session.execute(
                    sa.select(_E).where(*self._mine(_E), _E.c.version_id == version_id)
                )
            )
            .mappings()
            .first()
        )
        return None if row is None else _example(row)

    async def prune(self, before: datetime) -> int:
        # `ix_salesorder_examples_requested` carries this; the files go by
        # cascade. A sent example stays: its approval shows its replay.
        pruned = await self.session.execute(
            sa.delete(_E)
            .where(*self._mine(_E), _E.c.requested_at < before, _E.c.status != "submitted")
            .returning(_E.c.id)
        )
        return len(pruned.all())
