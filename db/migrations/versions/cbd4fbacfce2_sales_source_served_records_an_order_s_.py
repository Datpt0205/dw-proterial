"""sales source served records an order's message text

Revision ID: cbd4fbacfce2
Revises: 129852d287dc
Create Date: 2026-10-30 09:00:00.000000+00:00

The AI list, item 4. A PO the customer wrote in the mail itself is read by a
model from the message's newest part, and its values are anchored in that
text as a quotation's request read from the mail is (ticket 29,
`546a6a81e58c`). `prepare` and `cross-check` refuse until the person was
served the text (`require_served`), so the text is now recorded for an order
case as well:

- **`ck_source_served_region`**: `attachment_id` NULL (the message's text)
  holds neither page nor sheet, for a quotation or an order. Which case a
  row belongs to is `ck_source_served_one_case`, unchanged: exactly one of
  `order_case_id`, `quote_case_id`.

The downgrade deletes an order's text rows: the old check cannot hold them.
"""

from __future__ import annotations

from alembic import op

revision = "cbd4fbacfce2"
down_revision = "129852d287dc"
branch_labels = None
depends_on = None

_FILE_REGION = "num_nonnulls(page, sheet) = 1 AND page >= 1 AND char_length(sheet) BETWEEN 1 AND 31"


def upgrade() -> None:
    op.execute(
        f"""
        ALTER TABLE sales.source_served
            DROP CONSTRAINT ck_source_served_region,
            ADD CONSTRAINT ck_source_served_region CHECK (
                CASE WHEN attachment_id IS NULL
                     THEN page IS NULL AND sheet IS NULL
                     ELSE {_FILE_REGION}
                END
            )
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM sales.source_served WHERE attachment_id IS NULL AND quote_case_id IS NULL"
    )
    op.execute(
        f"""
        ALTER TABLE sales.source_served
            DROP CONSTRAINT ck_source_served_region,
            ADD CONSTRAINT ck_source_served_region CHECK (
                CASE WHEN attachment_id IS NULL
                     THEN page IS NULL AND sheet IS NULL AND quote_case_id IS NOT NULL
                     ELSE {_FILE_REGION}
                END
            )
        """
    )
