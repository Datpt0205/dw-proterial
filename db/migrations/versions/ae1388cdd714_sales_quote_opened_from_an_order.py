"""sales quote opened from an order

Revision ID: ae1388cdd714
Revises: 10d5dfc1a3f1
Create Date: 2026-11-16 07:24:37.614974+00:00

Sales ticket 09: a PO for an item with no valid quotation opens a quote case
("Mở báo giá"), linked to the order; the order cannot be prepared while that
quote case is open, and its lines are checked against the approved quotation.

- **`sales.order_cases.quote_links`**: the quote cases opened from the order
  (`QuoteLink`: the quote case's id, the lines it was opened for, who opened
  it and when), an array, oldest first. Whether the order still waits is the
  quote case's own status, never a copy here. NOT NULL with an empty array for
  every case before this one: none of them opened a quote.
- The quote side needs no column: `sales.quote_cases.body` holds the case,
  `from_order` (the order's id and PO number) included.

The column belongs to a table that already holds its grants, RLS policy and
FORCE: nothing about who may read or write it changes. A CHECK holds it to an
array, so an object or a scalar written by mistake is refused.

Downgrade drops the column.
"""

from __future__ import annotations

from alembic import op

revision = "ae1388cdd714"
down_revision = "10d5dfc1a3f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE sales.order_cases"
        " ADD COLUMN quote_links jsonb NOT NULL DEFAULT '[]'::jsonb,"
        " ADD CONSTRAINT ck_order_cases_quote_links"
        " CHECK (jsonb_typeof(quote_links) = 'array')"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE sales.order_cases DROP COLUMN quote_links")
