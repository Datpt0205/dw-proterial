"""sales model step checks admit the reply draft

Revision ID: 3aca293b2c92
Revises: 5461a43e48bf
Create Date: 2026-11-15 03:15:12.441624+00:00

Sales ticket 32 (dw_sales ADR 0012 decision 2) adds `ModelStep.REPLY_DRAFT`:
a mail to a customer about an order worded by the model beside the
template's draft, every figure checked by code. The two tables whose `step`
is a `ModelStep` admit it, as `5461a43e48bf` did for `thread_agent`:

- `ck_model_step_measurements_step` (`platform.model_step_measurements`): a
  live measurement of the step can be attested for a tenant, which the switch
  `model_assist.reply_draft` needs before it does anything;
- `ck_step_outcomes_step` (`sales.step_outcomes`): held to the domain's
  values like every other step, though the draft writes no activity row
  today (nothing of it is stored). The parent carries the constraint to
  every partition.

`test_sales_schema.py` and `test_sales_step_outcomes.py` hold each CHECK to
the domain's values. Downgrade deletes the rows the old checks cannot hold.
"""

from __future__ import annotations

from alembic import op

revision = "3aca293b2c92"
down_revision = "5461a43e48bf"
branch_labels = None
depends_on = None

# `dw_sales.domain.order_checks.ModelStep`; the platform's table also holds
# Purchasing's steps, which this leaves as they are.
_SALES_STEPS = (
    "description_attributes",
    "message_intent",
    "rfq_extraction",
    "reply_intent",
    "request_handoff",
    "layout_proposal",
    "po_body_extraction",
    "change_request",
    "thread_agent",
)
_PURCHASING_STEPS = (
    "purchasing_pr_mail_reading",
    "purchasing_supplier_quote_reading",
    "purchasing_order_confirmation_reading",
)
_NEW_STEP = "reply_draft"


def _listed(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _steps(sales: tuple[str, ...]) -> None:
    op.execute(
        "ALTER TABLE platform.model_step_measurements"
        " DROP CONSTRAINT ck_model_step_measurements_step,"
        " ADD CONSTRAINT ck_model_step_measurements_step"
        f" CHECK (step IN ({_listed((*sales, *_PURCHASING_STEPS))}))"
    )
    op.execute(
        "ALTER TABLE sales.step_outcomes"
        " DROP CONSTRAINT ck_step_outcomes_step,"
        f" ADD CONSTRAINT ck_step_outcomes_step CHECK (step IN ({_listed(sales)}))"
    )


def upgrade() -> None:
    _steps((*_SALES_STEPS, _NEW_STEP))


def downgrade() -> None:
    op.execute(f"DELETE FROM platform.model_step_measurements WHERE step = '{_NEW_STEP}'")
    op.execute(f"DELETE FROM sales.step_outcomes WHERE step = '{_NEW_STEP}'")
    _steps(_SALES_STEPS)
