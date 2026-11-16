"""sales triage card on a routed message and the mail a skill version was taught from

Revision ID: 2c91d318f833
Revises: 456986ea413a
Create Date: 2026-11-16 02:34:13.513811+00:00

Sales tickets 33 and 34, rebuilt under dw_sales ADR 0014.

- **`sales.messages.triage`**: the card a message routed ``other`` carries
  where the tenant turns the step on (`dw_sales.domain.triage.TriageCard`):
  what a model read it as by the tenant's mail kinds, the case code resolved
  from the sender's customer's records, one suggested step, and the person's
  decision once made. A JSON object, bounded, and only on a message routed
  to Sales or attached to a case by that decision
  (`ck_messages_triage`); NULL on every other message. It takes the table's
  RLS, policy and grants as every column of it does.
- **`sales.skill_replays.trigger`**: the mail a mail-kinds version was
  proposed from (a triage card, ticket 34), read with the version and
  without it by its replay (`dw_sales.application.skills.TriggerReplay`). A
  JSON object, bounded (`ck_skill_replays_trigger`); NULL for a version no
  card proposed. The table stays append-only.
- **The step CHECKs** (`ck_model_step_measurements_step`,
  `ck_step_outcomes_step`, `ck_labelled_cases_step`,
  `ck_step_thresholds_step`) admit `triage_card`. Each is rebuilt from the
  values it holds when this runs, plus this revision's own, as `711e8b760139`
  does, so a revision made beside this one keeps its values whichever runs
  first. `test_sales_schema.py` holds each CHECK to `ModelStep`.

Downgrade deletes the rows the old step checks cannot hold and drops both
columns: a card and a taught mail's reading are facts about this step.
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op

revision = "2c91d318f833"
down_revision = "456986ea413a"
branch_labels = None
depends_on = None

_NEW_STEP = "triage_card"
_STEP_CHECKS = (
    ("platform.model_step_measurements", "ck_model_step_measurements_step"),
    ("sales.step_outcomes", "ck_step_outcomes_step"),
    ("sales.labelled_cases", "ck_labelled_cases_step"),
    ("sales.step_thresholds", "ck_step_thresholds_step"),
)

_STATEMENTS: tuple[str, ...] = (
    "ALTER TABLE sales.messages ADD COLUMN triage jsonb",
    "ALTER TABLE sales.messages ADD CONSTRAINT ck_messages_triage CHECK ("
    " triage IS NULL OR ("
    " jsonb_typeof(triage) = 'object'"
    " AND octet_length(triage::text) <= 8192"
    " AND disposition IN ('routed_to_sales', 'attached_to_case')))",
    "ALTER TABLE sales.skill_replays ADD COLUMN trigger jsonb",
    "ALTER TABLE sales.skill_replays ADD CONSTRAINT ck_skill_replays_trigger CHECK ("
    " trigger IS NULL OR ("
    " jsonb_typeof(trigger) = 'object' AND octet_length(trigger::text) <= 4096))",
)


def _listed(values: list[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _held(table: str, check: str) -> list[str]:
    """The values ``check`` on ``table`` admits now, in its order."""
    definition = op.get_bind().scalar(
        sa.text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
            " WHERE conname = :check AND conrelid = CAST(:table AS regclass)"
        ),
        {"check": check, "table": table},
    )
    return re.findall(r"'([a-z_]+)'::text", str(definition))


def _set(table: str, check: str, values: list[str]) -> None:
    op.execute(
        f"ALTER TABLE {table} DROP CONSTRAINT {check},"
        f" ADD CONSTRAINT {check} CHECK (step IN ({_listed(values)}))"
    )


def upgrade() -> None:
    for statement in _STATEMENTS:
        op.execute(statement)
    for table, check in _STEP_CHECKS:
        held = _held(table, check)
        _set(table, check, held if _NEW_STEP in held else [*held, _NEW_STEP])


def downgrade() -> None:
    for table, check in _STEP_CHECKS:
        op.execute(f"DELETE FROM {table} WHERE step = '{_NEW_STEP}'")
        _set(table, check, [v for v in _held(table, check) if v != _NEW_STEP])
    op.execute("ALTER TABLE sales.skill_replays DROP COLUMN trigger")
    op.execute("ALTER TABLE sales.messages DROP COLUMN triage")
