"""sales assistant turns take the case steps

Revision ID: e31ed3f062a1
Revises: 0b6574e8974d
Create Date: 2026-11-18 05:19:36.939806+00:00

Sales ticket 46: a person may ask a case's conversation for one of three
steps of the case, answered with the case page's own control.

- **`ck_assistant_turns_kind`** (`sales.assistant_turns`) admits
  `draft_reply`, `remind_customer` and `explain_thread`, the kinds
  `QuestionKind` gained; `test_sales_schema.py` holds the CHECK to it.

No column and no table: the control offered is read from the turn's kind
(`assistant.OFFERS`). Purchasing's table of the same constraint name is in
its own schema and untouched.

The CHECK is rebuilt from the values it holds when this runs, plus this
revision's own, as `0b6574e8974d` does. Downgrade deletes the turns of the
three kinds, which the old check cannot hold.
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op

revision = "e31ed3f062a1"
down_revision = "0b6574e8974d"
branch_labels = None
depends_on = None

_TABLE = "sales.assistant_turns"
_CHECK = "ck_assistant_turns_kind"
_NEW = ("draft_reply", "remind_customer", "explain_thread")


def _held() -> list[str]:
    definition = op.get_bind().scalar(
        sa.text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
            " WHERE conname = :check AND conrelid = CAST(:table AS regclass)"
        ),
        {"check": _CHECK, "table": _TABLE},
    )
    return re.findall(r"'([a-z_]+)'::text", str(definition))


def _set(values: list[str]) -> None:
    listed = ", ".join(f"'{value}'" for value in values)
    op.execute(
        f"ALTER TABLE {_TABLE} DROP CONSTRAINT {_CHECK},"
        f" ADD CONSTRAINT {_CHECK} CHECK (kind IN ({listed}))"
    )


def upgrade() -> None:
    held = _held()
    _set([*held, *(v for v in _NEW if v not in held)])


def downgrade() -> None:
    listed = ", ".join(f"'{value}'" for value in _NEW)
    op.execute(f"DELETE FROM {_TABLE} WHERE kind IN ({listed})")
    _set([v for v in _held() if v not in _NEW])
