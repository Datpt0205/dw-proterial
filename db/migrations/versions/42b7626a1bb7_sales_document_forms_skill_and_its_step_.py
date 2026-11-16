"""sales document forms skill and its step admitted

Revision ID: 42b7626a1bb7
Revises: 99ae8f7eb765
Create Date: 2026-11-16 04:59:42.948463+00:00

Sales ticket 42 family 3 (dw_sales ADR 0014): which label or column of a
customer's own request form means which field becomes the tenant's
``document-forms`` skill, each form bound to one customer (or any) and one
route of a closed set; code keeps every check of every value at its cell.

- **`ck_rule_versions_key`** (`platform.rule_versions`) admits
  `sales_skill_document_forms`, the skill's key
  (`dw_sales.application.skills.skill_key("document-forms")`). A tenant's
  version of it is a rule version like the mail kinds' (`beba87138cda`): one
  row per tenant, key and version, under the table's RLS (tenant, ENABLEd
  and FORCEd), grants and checks, which the platform's tests already assert.
  The CHECK keeps the customer SalesOrder skills' pattern `711e8b760139`
  added beside its list.
- **The step CHECKs** (`ck_model_step_measurements_step`,
  `ck_step_outcomes_step`, `ck_labelled_cases_step`,
  `ck_step_thresholds_step`) admit `skill_document_forms`, the step that
  reads a customer's file by those forms.

Each CHECK is rebuilt from the values it holds when this runs, plus this
revision's own, as `711e8b760139` does, so a revision made beside this one
(ticket 42 family 5 widens the same CHECKs) keeps its values whichever runs
first. `test_sales_schema.py` holds each step CHECK to `ModelStep`.

Downgrade deletes the rows the old checks cannot hold: a measurement, a step
outcome or a labelled case of the step is a fact about a past reading, and a
tenant's version of the skill is a skill the platform no longer serves.
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op

revision = "42b7626a1bb7"
down_revision = "99ae8f7eb765"
branch_labels = None
depends_on = None

_NEW_KEY = "sales_skill_document_forms"
_NEW_STEP = "skill_document_forms"
_KEY_CHECK = ("platform.rule_versions", "ck_rule_versions_key")
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
    """The patterns a CHECK admits beside its list (``key ~ '...'``)."""
    return re.findall(r"~ '([^']+)'::text", definition)


def _set(table: str, check: str, column: str, values: list[str], patterns: list[str]) -> None:
    listed = ", ".join(f"'{value}'" for value in values)
    extra = "".join(f" OR {column} ~ '{pattern}'" for pattern in patterns)
    op.execute(
        f"ALTER TABLE {table} DROP CONSTRAINT {check},"
        f" ADD CONSTRAINT {check} CHECK ({column} IN ({listed}){extra})"
    )


def _admit(table: str, check: str, column: str, new: str) -> None:
    definition = _definition(table, check)
    held = _held(definition)
    _set(table, check, column, held if new in held else [*held, new], _patterns(definition))


def _withdraw(table: str, check: str, column: str, new: str) -> None:
    op.execute(f"DELETE FROM {table} WHERE {column} = '{new}'")
    definition = _definition(table, check)
    _set(table, check, column, [v for v in _held(definition) if v != new], _patterns(definition))


def upgrade() -> None:
    _admit(*_KEY_CHECK, "key", _NEW_KEY)
    for table, check in _STEP_CHECKS:
        _admit(table, check, "step", _NEW_STEP)


def downgrade() -> None:
    for table, check in _STEP_CHECKS:
        _withdraw(table, check, "step", _NEW_STEP)
    _withdraw(*_KEY_CHECK, "key", _NEW_KEY)
