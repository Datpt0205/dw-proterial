"""sales export control hold told to the export control pic

Revision ID: fa17832cd08d
Revises: 0662b6f0a31c
Create Date: 2026-11-26 17:39:42.495289+00:00

Sales ticket 78's follow-up. **`ck_followup_deliveries_followup`**
(`sales.followup_deliveries`) and **`ck_reminder_marks_followup`**
(`sales.reminder_marks`) admit `export_control_hold`: an order held on an
open `missing_noc_esf` waits for the export-control PIC. `test_today.py`
holds the second to the feed's reminders. Not a customer's term: it may be
dismissed or snoozed like `waiting_pcs_price`.

No column and no table: the hold is read from the current revision's
findings when the lane reads.

Each CHECK is rebuilt from the values it holds when this runs, plus this
revision's own (as `b01dba5d0433` does), so a revision made beside this one
keeps its values whichever runs first. Downgrade deletes the rows the old
checks cannot hold: a delivery record or a mark of this follow-up.
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op

revision = "fa17832cd08d"
down_revision = "0662b6f0a31c"
branch_labels = None
depends_on = None

_NEW_REMINDERS = ("export_control_hold",)
# (table, check, column, the values this revision admits)
_CHECKS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("sales.followup_deliveries", "ck_followup_deliveries_followup", "followup", _NEW_REMINDERS),
    ("sales.reminder_marks", "ck_reminder_marks_followup", "followup", _NEW_REMINDERS),
)


def _definition(table: str, check: str) -> str:
    return str(
        op.get_bind().scalar(
            sa.text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
                " WHERE conname = :check AND conrelid = CAST(:table AS regclass)"
            ),
            {"check": check, "table": table},
        )
    )


def _held(definition: str) -> list[str]:
    """The values a CHECK's list admits, in its order."""
    return re.findall(r"'([a-z_]+)'::text", definition)


def _patterns(definition: str) -> list[str]:
    """The patterns a CHECK admits beside its list (``key ~ '...'``)."""
    return re.findall(r"~ '([^']+)'::text", definition)


def _set(table: str, check: str, column: str, values: list[str], patterns: list[str]) -> None:
    listed = ", ".join(f"'{value}'" for value in values)
    extra = "".join(f" OR {column} ~ '{pattern}'" for pattern in patterns)
    op.execute(
        f"ALTER TABLE {table} DROP CONSTRAINT {check},"
        f" ADD CONSTRAINT {check} CHECK ({column} IN ({listed}){extra})"
    )


def upgrade() -> None:
    for table, check, column, new in _CHECKS:
        definition = _definition(table, check)
        held = _held(definition)
        values = [*held, *(v for v in new if v not in held)]
        _set(table, check, column, values, _patterns(definition))


def downgrade() -> None:
    for table, check, column, new in reversed(_CHECKS):
        listed = ", ".join(f"'{value}'" for value in new)
        op.execute(f"DELETE FROM {table} WHERE {column} IN ({listed})")
        definition = _definition(table, check)
        values = [v for v in _held(definition) if v not in new]
        _set(table, check, column, values, _patterns(definition))
