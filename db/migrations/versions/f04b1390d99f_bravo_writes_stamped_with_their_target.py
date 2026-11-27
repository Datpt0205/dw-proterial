"""bravo writes stamped with their target

Revision ID: f04b1390d99f
Revises: d533225350dd
Create Date: 2026-11-27 07:14:36.108874+00:00

Sales ticket 85: the gateway reaches two Bravos, UAT and production, and the
tenant's `sales_bravo_writes` version names the one in use. Each write is
stamped with the one it was read from:

- **`sales.bravo_line_writes.target`**: the Bravo the proposal read the line
  from, carried in the approval token; the gateway refuses the write when the
  tenant's target is another one now.
- **`bravo.write_ledger.target`**: the Bravo the gateway acted on, from the
  verified token.

Both `uat` or `production` (`ck_*_target`). Which Bravo a row stored
before ticket 85 used is not recorded: the gateway held one set, named by an
`environment` that defaulted to `production`. Those rows are backfilled
`uat` as a label, not a fact: nothing reads a ledger row's target, and a
proposal still open has no target in its approval, so its decision signs no
write token and it is proposed again. The old set itself now refuses to
start (ticket 85 review). The default goes once the backfill is done, so a
new row states its target or is refused.

No grant changes: both tables are granted whole to `dw_app` (af89f3f5d27d,
2c32bc10b019), and the ledger's REVOKE of DELETE stands.
"""

from __future__ import annotations

from alembic import op

revision = "f04b1390d99f"
down_revision = "d533225350dd"
branch_labels = None
depends_on = None

_TABLES = (
    ("sales.bravo_line_writes", "ck_bravo_line_writes_target"),
    ("bravo.write_ledger", "ck_write_ledger_target"),
)


def upgrade() -> None:
    for table, check in _TABLES:
        op.execute(f"ALTER TABLE {table} ADD COLUMN target text NOT NULL DEFAULT 'uat'")
        op.execute(f"ALTER TABLE {table} ALTER COLUMN target DROP DEFAULT")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {check} CHECK (target IN ('uat', 'production'))"
        )


def downgrade() -> None:
    for table, _ in _TABLES:
        op.execute(f"ALTER TABLE {table} DROP COLUMN target")
