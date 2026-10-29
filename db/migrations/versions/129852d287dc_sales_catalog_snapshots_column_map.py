"""sales catalog snapshots column map: which file header each column was read from

Revision ID: 129852d287dc
Revises: c42ed45c73a2
Create Date: 2026-10-29 14:00:00.000000+00:00

The AI list, item 2. A master-data file in a layout the template's headers
do not match is now matched by a model (`dw_sales.application.column_mapping`)
and read through that match. The head approves the import seeing the
match, so the snapshot keeps it.

- **`sales.catalog_snapshots.column_map`**: `[[template header, file
  header], ...]`, empty when the file's headers matched the template's
  without a model. NOT NULL with an empty default, so every row written
  before reads as "matched by header", which is what it was.
"""

from __future__ import annotations

from alembic import op

revision = "129852d287dc"
down_revision = "c42ed45c73a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE sales.catalog_snapshots"
        " ADD COLUMN column_map jsonb DEFAULT '[]'::jsonb NOT NULL"
    )
    op.execute(
        "ALTER TABLE sales.catalog_snapshots ADD CONSTRAINT ck_catalog_snapshots_column_map"
        " CHECK (jsonb_typeof(column_map) = 'array' AND jsonb_array_length(column_map) <= 40)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE sales.catalog_snapshots DROP COLUMN column_map")
