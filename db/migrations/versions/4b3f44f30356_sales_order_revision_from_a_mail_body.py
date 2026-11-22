"""sales order revision from a mail body

Revision ID: 4b3f44f30356
Revises: d759676dee5e
Create Date: 2026-11-22

AI item 4 (a PO the customer wrote in the mail body, no file) builds a
`PoDocument` whose ``attachment_id`` is None: its anchors point into the
message's own text, kept on the document (``body``). The baseline's
`ck_order_revisions_attachment_id` required an attachment id, so such a case
could never be stored on PostgreSQL: intake's transaction was refused
(`ConflictError`) and the mail never became a case. Found 2026-11-22 by
ticket 43's integration test; every earlier test of the step ran on the
memory store, which holds no CHECK.

- **The CHECK** admits no attachment id exactly when the document carries
  the mail text it was read from: ``attachment_id`` matches the id pattern,
  or it is NULL and ``document -> 'body'`` is an object. A file PO without
  an id stays refused, and so does a body PO without its text.
  `test_sales_po_body_examples.py` stores and reads one back.

Downgrade deletes the order cases holding a revision the old check cannot
hold (their lines and events cascade).
"""

from __future__ import annotations

from alembic import op

revision = "4b3f44f30356"
down_revision = "d759676dee5e"
branch_labels = None
depends_on = None

_ID = "'^[A-Za-z0-9._-]{1,128}$'"


def upgrade() -> None:
    op.execute("ALTER TABLE sales.order_revisions DROP CONSTRAINT ck_order_revisions_attachment_id")
    op.execute(
        "ALTER TABLE sales.order_revisions ADD CONSTRAINT ck_order_revisions_attachment_id CHECK ("
        f" (attachment_id IS NOT NULL AND attachment_id ~ {_ID})"
        " OR (attachment_id IS NULL AND jsonb_typeof(document -> 'body') = 'object'))"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM sales.order_cases WHERE id IN"
        " (SELECT case_id FROM sales.order_revisions WHERE attachment_id IS NULL)"
    )
    op.execute("ALTER TABLE sales.order_revisions DROP CONSTRAINT ck_order_revisions_attachment_id")
    op.execute(
        "ALTER TABLE sales.order_revisions ADD CONSTRAINT ck_order_revisions_attachment_id CHECK ("
        f" attachment_id IS NOT NULL AND attachment_id ~ {_ID})"
    )
