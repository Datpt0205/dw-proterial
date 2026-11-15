"""sales model step checks admit the thread agent

Revision ID: 5461a43e48bf
Revises: 64d50dbc1d00
Create Date: 2026-11-15 01:22:51.367334+00:00

Sales tickets 30 and 31 (dw_sales ADR 0012) add `ModelStep.THREAD_AGENT`: a
thread message read with read-only tools before the one-call reading. The two
tables whose `step` is a `ModelStep` admit it, as `c7d0730fcccd` did for
`change_request`:

- `ck_model_step_measurements_step` (`platform.model_step_measurements`): a
  live measurement of the step can be attested for a tenant, which the switch
  `model_assist.thread_agent` needs before it does anything;
- `ck_step_outcomes_step` (`sales.step_outcomes`): the activity row of a
  thread message the agent read, or of its turn that fell back. The parent
  carries the constraint to every partition.

`test_sales_schema.py` and `test_sales_step_outcomes.py` hold each CHECK to
the domain's values. Downgrade deletes the rows the old checks cannot hold.
"""

from __future__ import annotations

from alembic import op

revision = "5461a43e48bf"
down_revision = "64d50dbc1d00"
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
)
_PURCHASING_STEPS = (
    "purchasing_pr_mail_reading",
    "purchasing_supplier_quote_reading",
    "purchasing_order_confirmation_reading",
)
_NEW_STEP = "thread_agent"


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
