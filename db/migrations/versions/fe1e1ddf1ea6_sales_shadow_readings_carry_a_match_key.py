"""sales shadow readings carry a match key

Revision ID: fe1e1ddf1ea6
Revises: af64f9143d66
Create Date: 2026-11-25

Sales ticket 67, slice 3: a PO written in a mail going to a person is read
in shadow by `po_body_extraction`, and labelled value by value when an order
case of the same customer and PO number is prepared, from a file that
arrived later. So a reading carries the key that later case is found by.

- **`match_key`**, nullable, bounded by `char_length` (failure-modes #4):
  ``<customer code>:<PO number, trimmed and case-folded>``.
- **The index the take reads**, led by what RLS supplies.
"""

from __future__ import annotations

from alembic import op

revision = "fe1e1ddf1ea6"
down_revision = "af64f9143d66"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sales.shadow_readings ADD COLUMN match_key text")
    op.execute(
        "ALTER TABLE sales.shadow_readings ADD CONSTRAINT ck_shadow_readings_match_key"
        " CHECK (match_key IS NULL OR char_length(match_key) BETWEEN 1 AND 300)"
    )
    op.execute(
        "CREATE INDEX ix_shadow_readings_tenant_id_workspace_id_step_match_key"
        " ON sales.shadow_readings (tenant_id, workspace_id, step, match_key)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX sales.ix_shadow_readings_tenant_id_workspace_id_step_match_key")
    op.execute("ALTER TABLE sales.shadow_readings DROP CONSTRAINT ck_shadow_readings_match_key")
    op.execute("ALTER TABLE sales.shadow_readings DROP COLUMN match_key")
