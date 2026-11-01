"""purchasing switches and their model step

Revision ID: 82cc61f87d6c
Revises: 315c7ae4844f
Create Date: 2026-11-01 07:00:00.000000+00:00

DW2's three-level switch per step (`dw_purchasing.domain.automation`) is a
rule a tenant holds its own version of, and its `ai_auto` waits on a live
measurement of the model reading it runs on:

- **`ck_rule_versions_key`** admits `purchasing_automation`.
- **`ck_model_step_measurements_step`** (on `platform.model_step_measurements`,
  moved by 315c7ae4844f) admits `purchasing_pr_mail_reading` beside Sales'
  steps.
"""

from __future__ import annotations

from alembic import op

revision = "82cc61f87d6c"
down_revision = "315c7ae4844f"
branch_labels = None
depends_on = None

_KEYS = (
    "sales_order_rules",
    "sales_kpi",
    "sales_quote_rules",
    "sales_pricing",
    "sales_emails",
    "sales_documents",
    "sales_bravo_upload",
    "sales_handoffs",
    "sales_followups",
    "purchasing_rules",
)
_SALES_STEPS = (
    "description_attributes",
    "message_intent",
    "rfq_extraction",
    "reply_intent",
    "request_handoff",
    "layout_proposal",
    "po_body_extraction",
)
_KEY = "purchasing_automation"
_STEP = "purchasing_pr_mail_reading"


def _listed(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _set(keys: tuple[str, ...], steps: tuple[str, ...]) -> None:
    op.execute(
        "ALTER TABLE platform.rule_versions DROP CONSTRAINT ck_rule_versions_key,"
        f" ADD CONSTRAINT ck_rule_versions_key CHECK (key IN ({_listed(keys)}))"
    )
    op.execute(
        "ALTER TABLE platform.model_step_measurements"
        " DROP CONSTRAINT ck_model_step_measurements_step,"
        f" ADD CONSTRAINT ck_model_step_measurements_step CHECK (step IN ({_listed(steps)}))"
    )


def upgrade() -> None:
    _set((*_KEYS, _KEY), (*_SALES_STEPS, _STEP))


def downgrade() -> None:
    op.execute(f"DELETE FROM platform.rule_versions WHERE key = '{_KEY}'")
    op.execute(f"DELETE FROM platform.model_step_measurements WHERE step = '{_STEP}'")
    _set(_KEYS, _SALES_STEPS)
