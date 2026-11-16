"""sales skill replays keyed by tenant and version

Revision ID: 456986ea413a
Revises: 711e8b760139
Create Date: 2026-11-16 02:12:40.214985+00:00

`sales.skill_replays` (e1b1e0cadb66) held one replay per skill version with a
unique index on `version_id` alone. Every unique key in `sales` leads with
the columns RLS supplies, so the planner can use it under the tenant policy
and a key never spans tenants (`test_sales_schema.py`); this one did not.
The table is tenant-wide (a skill version is the tenant's), so its key leads
with `tenant_id` alone, replacing the plain index on the same columns; the
foreign key on `version_id` keeps an index of its own. The adapter's ON
CONFLICT names the key's columns.
"""

from __future__ import annotations

from alembic import op

revision = "456986ea413a"
down_revision = "711e8b760139"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The plain (tenant_id, version_id) index becomes the unique key; the
    # foreign key on version_id, which the old unique index carried, gets
    # its own.
    op.execute("DROP INDEX sales.uq_skill_replays_version_id")
    op.execute("DROP INDEX sales.ix_skill_replays_tenant_id_version_id")
    op.execute(
        "CREATE UNIQUE INDEX uq_skill_replays_tenant_id_version_id"
        " ON sales.skill_replays (tenant_id, version_id)"
    )
    op.execute("CREATE INDEX ix_skill_replays_version_id ON sales.skill_replays (version_id)")


def downgrade() -> None:
    op.execute("DROP INDEX sales.ix_skill_replays_version_id")
    op.execute("DROP INDEX sales.uq_skill_replays_tenant_id_version_id")
    op.execute(
        "CREATE INDEX ix_skill_replays_tenant_id_version_id"
        " ON sales.skill_replays (tenant_id, version_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_skill_replays_version_id ON sales.skill_replays (version_id)"
    )
