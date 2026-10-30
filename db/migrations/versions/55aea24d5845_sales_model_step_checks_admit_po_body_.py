"""sales model step checks admit po body extraction

Revision ID: 55aea24d5845
Revises: e0940c90ce04
Create Date: 2026-10-30 09:20:00.000000+00:00

The AI list's item 4 added `ModelStep.PO_BODY_EXTRACTION` (a PO written in
the mail body, `9851a74`) and no migration followed it, so the two tables
whose `step` is a `ModelStep` still refused it:

- `ck_model_step_measurements_step` (`2d97d03c937a`): attesting the step for
  a tenant would fail its insert, so the switch that needs a passed
  measurement could never be turned on;
- `ck_step_outcomes_step` (`4bca401bcb3a`): the activity row of every PO read
  from a mail body would fail with the message's disposition.

Found by `test_sales_schema.py` and `test_sales_step_outcomes.py`, which hold
each CHECK to the domain's values. Both now admit the seven steps. The parent
of `step_outcomes` carries the constraint to every partition.

The downgrade deletes the rows the old checks cannot hold.
"""

from __future__ import annotations

from alembic import op

revision = "55aea24d5845"
down_revision = "e0940c90ce04"
branch_labels = None
depends_on = None

# `dw_sales.domain.order_checks.ModelStep`, held to it by the two tests above.
_STEPS = (
    "('description_attributes', 'message_intent', 'rfq_extraction', 'reply_intent',"
    " 'request_handoff', 'layout_proposal', 'po_body_extraction')"
)
_STEPS_BEFORE = (
    "('description_attributes', 'message_intent', 'rfq_extraction', 'reply_intent',"
    " 'request_handoff', 'layout_proposal')"
)


def _checks(steps: str) -> None:
    op.execute(
        "ALTER TABLE sales.model_step_measurements"
        " DROP CONSTRAINT ck_model_step_measurements_step,"
        f" ADD CONSTRAINT ck_model_step_measurements_step CHECK (step IN {steps})"
    )
    op.execute(
        "ALTER TABLE sales.step_outcomes"
        " DROP CONSTRAINT ck_step_outcomes_step,"
        f" ADD CONSTRAINT ck_step_outcomes_step CHECK (step IN {steps})"
    )


def upgrade() -> None:
    _checks(_STEPS)


def downgrade() -> None:
    op.execute("DELETE FROM sales.model_step_measurements WHERE step = 'po_body_extraction'")
    op.execute("DELETE FROM sales.step_outcomes WHERE step = 'po_body_extraction'")
    _checks(_STEPS_BEFORE)
