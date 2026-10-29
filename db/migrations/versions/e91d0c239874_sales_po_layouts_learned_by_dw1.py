"""sales po layouts learned by DW1

Revision ID: e91d0c239874
Revises: 8607c7876b2e
Create Date: 2026-10-29 06:00:00.000000+00:00

dw_sales ADR 0006 (Đạt, 2026-10-29): when a model's mapping of a customer's PO
form passes every check, DW1 adopts it as the customer's layout itself, with
no person's approval. `sales.po_layouts` held only a person's mapping, every
row tied to the platform approval a second person decides it on.

- **`origin`**: `person` (ticket 30, every row before this revision) or
  `model` (learned by DW1). CHECKed.
- **`approval_id`** may be NULL, and is exactly when the layout was learned:
  `ck_po_layouts_origin` holds the two together, with a learned layout in
  force from the start (`approved`, later `superseded`) and decided by no one.
  The foreign key to the approval is unchanged; a NULL references nothing.
- **`ck_po_layouts_decided`** keeps "decided exactly when not proposed" for a
  person's layout; a learned one names no decider.
"""

from __future__ import annotations

from alembic import op

revision = "e91d0c239874"
down_revision = "8607c7876b2e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE sales.po_layouts
            ADD COLUMN origin text NOT NULL DEFAULT 'person',
            ALTER COLUMN approval_id DROP NOT NULL,
            ADD CONSTRAINT ck_po_layouts_origin_value CHECK (origin IN ('person', 'model')),
            ADD CONSTRAINT ck_po_layouts_origin CHECK (
                (origin = 'person') = (approval_id IS NOT NULL)
                AND (
                    origin = 'person'
                    OR (decided_by IS NULL AND status IN ('approved', 'superseded'))
                )
            ),
            DROP CONSTRAINT ck_po_layouts_decided,
            ADD CONSTRAINT ck_po_layouts_decided CHECK (
                origin = 'model' OR (status = 'proposed') = (decided_by IS NULL)
            )
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM sales.po_layouts WHERE origin = 'model'")
    op.execute(
        """
        ALTER TABLE sales.po_layouts
            DROP CONSTRAINT ck_po_layouts_decided,
            ADD CONSTRAINT ck_po_layouts_decided
                CHECK ((status = 'proposed') = (decided_by IS NULL)),
            DROP CONSTRAINT ck_po_layouts_origin,
            DROP CONSTRAINT ck_po_layouts_origin_value,
            ALTER COLUMN approval_id SET NOT NULL,
            DROP COLUMN origin
        """
    )
