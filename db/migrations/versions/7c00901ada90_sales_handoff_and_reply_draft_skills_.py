"""sales handoff and reply draft skills and their steps admitted

Revision ID: 7c00901ada90
Revises: 42b7626a1bb7
Create Date: 2026-11-16 05:04:40.046277+00:00

Sales ticket 42 family 5 (dw_sales ADR 0014): the kinds of hand-off to PC or
QA and the kinds of mail to a customer a tenant writes become its
``handoffs`` and ``reply-drafts`` skills, each kind mapped onto the
platform's closed sets (the fields a hand-off asks for and the team it goes
to; the draft a mail is worded as); code keeps every check.

- **`ck_rule_versions_key`** (`platform.rule_versions`) admits
  `sales_skill_handoffs` and `sales_skill_reply_drafts`, the skills' keys
  (`dw_sales.application.skills.skill_key`). A tenant's version of either
  is a rule version like the mail kinds' (`beba87138cda`): one row per
  tenant, key and version, under the table's RLS (tenant, ENABLEd and
  FORCEd), grants and checks, which the platform's tests already assert. The
  CHECK keeps the customer SalesOrder skills' pattern `711e8b760139` added
  beside its list.
- **The step CHECKs** (`ck_model_step_measurements_step`,
  `ck_step_outcomes_step`, `ck_labelled_cases_step`,
  `ck_step_thresholds_step`) admit `skill_handoffs` and
  `skill_reply_drafts`, the steps that read by those kinds.

Each CHECK is rebuilt from the values it holds when this runs, plus this
revision's own, as `42b7626a1bb7` does, so a revision made beside this one
keeps its values whichever runs first. `test_sales_schema.py` holds each
step CHECK to `ModelStep`.

Downgrade deletes the rows the old checks cannot hold: a measurement, a step
outcome or a labelled case of a step is a fact about a past reading, and a
tenant's version of a skill is a skill the platform no longer serves.
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op

revision = "7c00901ada90"
down_revision = "42b7626a1bb7"
branch_labels = None
depends_on = None

_NEW_KEYS = ("sales_skill_handoffs", "sales_skill_reply_drafts")
_NEW_STEPS = ("skill_handoffs", "skill_reply_drafts")
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


def _admit(table: str, check: str, column: str, new: tuple[str, ...]) -> None:
    definition = _definition(table, check)
    held = _held(definition)
    _set(table, check, column, [*held, *(v for v in new if v not in held)], _patterns(definition))


def _withdraw(table: str, check: str, column: str, new: tuple[str, ...]) -> None:
    listed = ", ".join(f"'{value}'" for value in new)
    op.execute(f"DELETE FROM {table} WHERE {column} IN ({listed})")
    definition = _definition(table, check)
    _set(
        table, check, column, [v for v in _held(definition) if v not in new], _patterns(definition)
    )


def upgrade() -> None:
    _admit(*_KEY_CHECK, "key", _NEW_KEYS)
    for table, check in _STEP_CHECKS:
        _admit(table, check, "step", _NEW_STEPS)


def downgrade() -> None:
    for table, check in _STEP_CHECKS:
        _withdraw(table, check, "step", _NEW_STEPS)
    _withdraw(*_KEY_CHECK, "key", _NEW_KEYS)
