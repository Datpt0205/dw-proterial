"""sales bravo line writes cancel a line

Revision ID: a56aac13a035
Revises: 1bf300e276b7
Create Date: 2026-11-26

Sales ticket 71: an SO line cancelled in Bravo is proposed like a date or a
quantity (the gateway runs `so.line.cancel@1`, traced on UAT 11-25).

- **`ck_bravo_line_writes_field`** admits `cancel`; its `after_value` reads
  "Hủy: <reason>", its `before_value` the quantity it ends.
- **`ck_bravo_line_writes_kind`** admits `so.line.cancel@1`.

No grant or column changes. Downgrade deletes the cancel proposals, which the
old checks cannot hold.
"""

from __future__ import annotations

from alembic import op

revision = "a56aac13a035"
down_revision = "1bf300e276b7"
branch_labels = None
depends_on = None

_TABLE = "sales.bravo_line_writes"
_FIELDS_OLD = "('confirmed_date', 'quantity')"
_FIELDS_NEW = "('confirmed_date', 'quantity', 'cancel')"
_KINDS_OLD = "('so.line.set_confirmed_date@1', 'so.line.set_quantity@1')"
_KINDS_NEW = "('so.line.set_confirmed_date@1', 'so.line.set_quantity@1', 'so.line.cancel@1')"


def _checks(fields: str, kinds: str) -> None:
    op.execute(
        f"ALTER TABLE {_TABLE}"
        " DROP CONSTRAINT ck_bravo_line_writes_field,"
        f" ADD CONSTRAINT ck_bravo_line_writes_field CHECK (field IN {fields}),"
        " DROP CONSTRAINT ck_bravo_line_writes_kind,"
        f" ADD CONSTRAINT ck_bravo_line_writes_kind CHECK (kind IN {kinds})"
    )


def upgrade() -> None:
    _checks(_FIELDS_NEW, _KINDS_NEW)


def downgrade() -> None:
    op.execute(f"DELETE FROM {_TABLE} WHERE field = 'cancel'")
    _checks(_FIELDS_OLD, _KINDS_OLD)
