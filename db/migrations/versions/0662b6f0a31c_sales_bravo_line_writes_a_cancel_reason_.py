"""sales bravo line writes a cancel reason as long as Bravo holds

Revision ID: 0662b6f0a31c
Revises: a56aac13a035
Create Date: 2026-11-26

Sales ticket 71: a cancel's `after_value` reads "Hủy: <reason>", and the
reason is as long as Bravo's `CancelRemark` holds, nvarchar(192) (the 11-19
survey's `sys.columns.max_length`, 384 bytes), not the 58 characters the
first cancel took from this column's 64. So `ck_bravo_line_writes_values`
admits an `after_value` of 5 + 192 = 197 characters; `before_value` stays at
64 (a date or a quantity).

No grant or column changes. Downgrade deletes the proposals the old check
cannot hold.
"""

from __future__ import annotations

from alembic import op

revision = "0662b6f0a31c"
down_revision = "a56aac13a035"
branch_labels = None
depends_on = None

_TABLE = "sales.bravo_line_writes"


def _values(after_chars: int) -> None:
    op.execute(
        f"ALTER TABLE {_TABLE}"
        " DROP CONSTRAINT ck_bravo_line_writes_values,"
        " ADD CONSTRAINT ck_bravo_line_writes_values CHECK ("
        f" char_length(after_value) BETWEEN 1 AND {after_chars}"
        " AND (before_value IS NULL OR char_length(before_value) <= 64))"
    )


def upgrade() -> None:
    _values(197)


def downgrade() -> None:
    op.execute(f"DELETE FROM {_TABLE} WHERE char_length(after_value) > 64")
    _values(64)
