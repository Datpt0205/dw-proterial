"""sales assistant copy key

Revision ID: 0b6574e8974d
Revises: 985e4fa0cd4f
Create Date: 2026-11-18 05:00:00.000000+00:00

Sales ticket 42 family 6: the assistant's own sentences are a copy key.

- **`ck_rule_versions_key`** (`platform.rule_versions`) and
  **`ck_rule_drafts_rule_key`** (`sales.rule_drafts`) admit
  `sales_assistant`, the words DW1's assistant says where code answers
  (`AssistantCopy`): a tenant's version of them is a rule version like the
  reminder copy's, under the tables' RLS, grants and checks, which the
  platform's and Sales' tests already assert.

No column and no table. Each CHECK is rebuilt from the values it holds when
this runs, plus this revision's own (as `57bbf61ae6b8` does), so a revision
made beside this one keeps its values whichever runs first, and a pattern
beside a list is kept.

Downgrade deletes a tenant's version or draft of the key, which the old
checks cannot hold.
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op

revision = "0b6574e8974d"
down_revision = "985e4fa0cd4f"
branch_labels = None
depends_on = None

_NEW_KEYS = ("sales_assistant",)
# (table, check, column, the values this revision admits)
_CHECKS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
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
