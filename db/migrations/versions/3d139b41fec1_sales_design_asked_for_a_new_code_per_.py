"""sales design asked for a new code per line

Revision ID: 3d139b41fec1
Revises: 7c00901ada90
Create Date: 2026-11-16 07:16:22.242486+00:00

Sales ticket 06: a line no item fits ("chưa có mã") gets a request to Design
to create a PRV code, drafted by DW1 for a person to send; once the person
records it sent, the case waits on Design for that line until Sales confirms
the code Design named.

- **`sales.order_cases.design_requests`**: the open requests (`DesignRequest`:
  the line, who recorded the request sent and when), an array, empty while the
  case waits on nobody at Design. The domain keeps only lines still without a
  code, in review, so a confirmed code or a new revision ends the wait. NOT
  NULL with an empty array for every case before this one: none of them
  waited on Design.

The column belongs to a table that already holds its grants, RLS policy and
FORCE: nothing about who may read or write it changes. A CHECK holds it to an
array, so an object or a scalar written by mistake is refused.

Downgrade drops the column.
"""

from __future__ import annotations

from alembic import op

revision = "3d139b41fec1"
down_revision = "7c00901ada90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE sales.order_cases"
        " ADD COLUMN design_requests jsonb NOT NULL DEFAULT '[]'::jsonb,"
        " ADD CONSTRAINT ck_order_cases_design_requests"
        " CHECK (jsonb_typeof(design_requests) = 'array')"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE sales.order_cases DROP COLUMN design_requests")
