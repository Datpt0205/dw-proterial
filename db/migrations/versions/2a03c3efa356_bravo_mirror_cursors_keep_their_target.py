"""bravo mirror cursors keep their target

Revision ID: 2a03c3efa356
Revises: f04b1390d99f
Create Date: 2026-11-27 08:23:24.786058+00:00

Sales ticket 85 review: the `bravo_sync` lane reads the tenant's Bravo now,
UAT or production, and a rowversion is one database's counter. A cursor
read from one Bravo, asked of the other, skips every change below it, and
the copy keeps the first Bravo's rows as current.

**`bravo.mirror_cursors.target`**: the Bravo the cursor was read from
(`uat` or `production`, `ck_mirror_cursors_target`). NULL on every cursor
stored before: the lane reads a NULL as another Bravo's, so its first tick
marks that table's copy gone and reads it whole (`dw_bravo.sync.BravoSync`).

No grant changes: `dw_app` holds SELECT, INSERT and UPDATE on the table
(ffd0c95da906).
"""

from __future__ import annotations

from alembic import op

revision = "2a03c3efa356"
down_revision = "f04b1390d99f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE bravo.mirror_cursors ADD COLUMN target text,"
        " ADD CONSTRAINT ck_mirror_cursors_target"
        " CHECK (target IS NULL OR target IN ('uat', 'production'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE bravo.mirror_cursors DROP COLUMN target")
