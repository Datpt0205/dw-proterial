"""sales PC's reply read by DW1

Revision ID: 79418de5ab48
Revises: d217eda10ac8
Create Date: 2026-11-26 21:06:44.328414+00:00

Sales ticket 77: while an order waits on PC, DW1 reads PC's mail and proposes
its dates line by line; the PIC confirms each line or corrects it, and nothing
of the case's values changes until they do.

- **`sales.order_cases.pc_reply`**: the proposal (`PcReply`: each date with
  the words it rests on and the mail it was read from, and every mail read
  for this wait so none is read twice), an object, NULL while DW1 read
  nothing. The domain clears it with the wait and drops a line's dates once
  the line changes. The column belongs to a table that already holds its
  grants, RLS policy and FORCE: nothing about who may read or write it
  changes. A CHECK holds it to an object.
- **The step CHECKs** (`ck_model_step_measurements_step`,
  `ck_step_outcomes_step`, `ck_labelled_cases_step`,
  `ck_step_thresholds_step`) admit `pc_reply` (`ModelStep.PC_REPLY`, the
  switch `model_assist.pc_reply`, off where a version does not say), as
  `d759676dee5e` admitted `case_chat`: each rebuilt from the values it holds
  when this runs, plus this revision's own. `test_sales_schema.py` holds
  each to `ModelStep`.

Downgrade deletes the rows the old checks cannot hold and drops the column.
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op

revision = "79418de5ab48"
down_revision = "d217eda10ac8"
branch_labels = None
depends_on = None

_NEW_STEPS = ("pc_reply",)
_STEP_CHECKS = (
    ("platform.model_step_measurements", "ck_model_step_measurements_step"),
    ("sales.step_outcomes", "ck_step_outcomes_step"),
    ("sales.labelled_cases", "ck_labelled_cases_step"),
    ("sales.step_thresholds", "ck_step_thresholds_step"),
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
    """The patterns a CHECK admits beside its list (``step ~ '...'``)."""
    return re.findall(r"~ '([^']+)'::text", definition)


def _set(table: str, check: str, values: list[str], patterns: list[str]) -> None:
    listed = ", ".join(f"'{value}'" for value in values)
    extra = "".join(f" OR step ~ '{pattern}'" for pattern in patterns)
    op.execute(
        f"ALTER TABLE {table} DROP CONSTRAINT {check},"
        f" ADD CONSTRAINT {check} CHECK (step IN ({listed}){extra})"
    )


def upgrade() -> None:
    op.execute("ALTER TABLE sales.order_cases ADD COLUMN pc_reply jsonb")
    op.execute(
        "ALTER TABLE sales.order_cases ADD CONSTRAINT ck_order_cases_pc_reply"
        " CHECK (pc_reply IS NULL OR jsonb_typeof(pc_reply) = 'object')"
    )
    for table, check in _STEP_CHECKS:
        definition = _definition(table, check)
        held = _held(definition)
        _set(
            table,
            check,
            [*held, *(v for v in _NEW_STEPS if v not in held)],
            _patterns(definition),
        )


def downgrade() -> None:
    listed = ", ".join(f"'{value}'" for value in _NEW_STEPS)
    for table, check in _STEP_CHECKS:
        op.execute(f"DELETE FROM {table} WHERE step IN ({listed})")
        definition = _definition(table, check)
        _set(
            table,
            check,
            [v for v in _held(definition) if v not in _NEW_STEPS],
            _patterns(definition),
        )
    op.execute("ALTER TABLE sales.order_cases DROP COLUMN pc_reply")
