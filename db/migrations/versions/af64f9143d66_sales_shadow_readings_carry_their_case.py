"""sales shadow readings carry their case

Revision ID: af64f9143d66
Revises: a201f3d7ad6f
Create Date: 2026-11-24

Sales ticket 67, slice 2: a customer's reply is read in shadow by both reply
readers, and labelled by the move the PIC takes next on the case, not by a
decision on the reply itself. So a reading carries the case it belongs to,
and the move's transaction takes the case's readings by it.

- **`case_id`**, nullable: a PO line's reading needs none (its decision is on
  the line). No foreign key: the case is an order case or a quote case, two
  tables, as `sales.labelled_cases.case_id` is; a reading of a case that
  leaves is dropped with the term.
- **The index the take reads**, led by what RLS supplies.
"""

from __future__ import annotations

from alembic import op

revision = "af64f9143d66"
down_revision = "a201f3d7ad6f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sales.shadow_readings ADD COLUMN case_id uuid")
    op.execute(
        "CREATE INDEX ix_shadow_readings_tenant_id_workspace_id_case_id"
        " ON sales.shadow_readings (tenant_id, workspace_id, case_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX sales.ix_shadow_readings_tenant_id_workspace_id_case_id")
    op.execute("ALTER TABLE sales.shadow_readings DROP COLUMN case_id")
