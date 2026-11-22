"""sales case chat step admitted

Revision ID: d759676dee5e
Revises: b5c316f405cd
Create Date: 2026-11-22

Sales ticket 57: the case chat's reading of what a PIC states there
(`question_intent`, tickets 46 and 56) is a model step like every other
(`ModelStep.CASE_CHAT`, the switch `model_assist.case_chat`, ON where a
version does not say, Đạt 2026-11-22), so its live eval is recorded and its
statements the PIC confirms become labelled cases.

- **The step CHECKs** (`ck_model_step_measurements_step`,
  `ck_step_outcomes_step`, `ck_labelled_cases_step`,
  `ck_step_thresholds_step`) admit `case_chat`, as `1f037954f3d9` admitted
  `internal_change`: each rebuilt from the values it holds when this runs,
  plus this revision's own. `test_sales_schema.py` holds each to `ModelStep`.

Downgrade deletes the rows the old checks cannot hold.
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op

revision = "d759676dee5e"
down_revision = "b5c316f405cd"
branch_labels = None
depends_on = None

_NEW_STEPS = ("case_chat",)
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
