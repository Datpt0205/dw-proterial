"""sales internal change step admitted

Revision ID: 1f037954f3d9
Revises: ae1388cdd714
Create Date: 2026-11-16 08:15:14.843186+00:00

Sales ticket 10: a local model reads PC's mail Sales pastes into "Thay đổi
nội bộ" (Proterial's own change of a confirmed order), a model step like
every other (`ModelStep.INTERNAL_CHANGE`, the switch
`model_assist.internal_change`, off where a version does not say).

- **The step CHECKs** (`ck_model_step_measurements_step`,
  `ck_step_outcomes_step`, `ck_labelled_cases_step`,
  `ck_step_thresholds_step`) admit `internal_change`, so its live eval can be
  recorded as every step's is, and the gate can find it.

Nothing else changes: the change itself rides on `sales.order_cases.update_loop`
(a new key, `reason`, inside the JSON the loop's CHECK already admits; its
values are held by the model that reads it). Each CHECK is rebuilt from the
values it holds when this runs, plus this revision's own, as `7c00901ada90`
does, so a revision made beside this one keeps its values whichever runs
first. `test_sales_schema.py` holds each step CHECK to `ModelStep`.

Downgrade deletes the rows the old checks cannot hold: a measurement, a step
outcome, a labelled case or a threshold of the step is a fact about a past
reading.
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op

revision = "1f037954f3d9"
down_revision = "ae1388cdd714"
branch_labels = None
depends_on = None

_NEW_STEPS = ("internal_change",)
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
