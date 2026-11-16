"""sales waits on design and linked quote reminded, reminder copy key

Revision ID: 57bbf61ae6b8
Revises: 1f037954f3d9
Create Date: 2026-11-16 09:43:21.351691+00:00

Sales tickets 06 and 09's follow-ups, and ticket 42 family 6's words.

- **`ck_followup_deliveries_followup`** (`sales.followup_deliveries`) and
  **`ck_reminder_marks_followup`** (`sales.reminder_marks`, ticket 47's
  "Đã xử lý / Nhắc lại sau / Không cần") admit `waiting_design_code` (an
  order line waits on Design's new PRV code) and `waiting_quote` (an order
  waits on a quote case opened from it). `test_sales_schema.py` holds the
  first to `Followup`, `test_today.py` the second to the feed's reminders.
  Neither is a customer's term: `ck_reminder_marks_customer_term` is
  unchanged, so both may be dismissed or snoozed.
- **`ck_rule_versions_key`** (`platform.rule_versions`) and
  **`ck_rule_drafts_rule_key`** (`sales.rule_drafts`) admit
  `sales_reminders`, the words of the follow-ups (`ReminderCopy`): a tenant's
  version of them is a rule version like the hand-off copy's, under the
  tables' RLS, grants and checks, which the platform's and Sales' tests
  already assert.

No column and no table: the waits are read from the order's own
`design_requests` and `quote_links` and the linked quote's status, and the
quote's Design result from its body (ticket 16), when the lane reads.

Each CHECK is rebuilt from the values it holds when this runs, plus this
revision's own (as `7c00901ada90` does), so a revision made beside this one
keeps its values whichever runs first, and a pattern beside a list is kept.

Downgrade deletes the rows the old checks cannot hold: a delivery record or
a mark of a follow-up the platform no longer has, and a tenant's version or
draft of a key it no longer serves.
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op

revision = "57bbf61ae6b8"
down_revision = "1f037954f3d9"
branch_labels = None
depends_on = None

_NEW_REMINDERS = ("waiting_design_code", "waiting_quote")
_NEW_KEYS = ("sales_reminders",)
# (table, check, column, the values this revision admits)
_CHECKS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("sales.followup_deliveries", "ck_followup_deliveries_followup", "followup", _NEW_REMINDERS),
    ("sales.reminder_marks", "ck_reminder_marks_followup", "followup", _NEW_REMINDERS),
    ("platform.rule_versions", "ck_rule_versions_key", "key", _NEW_KEYS),
    ("sales.rule_drafts", "ck_rule_drafts_rule_key", "rule_key", _NEW_KEYS),
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
