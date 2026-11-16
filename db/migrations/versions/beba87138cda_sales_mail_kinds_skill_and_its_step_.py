"""sales mail kinds skill and its step admitted

Revision ID: beba87138cda
Revises: e1b1e0cadb66
Create Date: 2026-11-15 21:01:05.078365+00:00

Sales ticket 42 family 1 (dw_sales ADR 0014): the kinds of mail a tenant
tells apart become its ``mail-kinds`` skill, each kind mapped onto one of the
platform's legal routes; code keeps the routes.

- **`ck_rule_versions_key`** (`platform.rule_versions`) admits
  `sales_skill_mail_kinds`, the skill's key. A tenant's version of it is a
  rule version like the thread-intents skill's (`80584b911796`): one row per
  tenant, key and version, under the table's RLS (tenant, ENABLEd and
  FORCEd), grants and checks, which the platform's tests already assert.
- **`ck_model_step_measurements_step`**, **`ck_step_outcomes_step`**,
  **`ck_labelled_cases_step`** and **`ck_step_thresholds_step`** admit
  `skill_mail_kinds`, the step that classifies a message by those kinds, as
  `80584b911796` did for `skill_intents`. Each list is `ModelStep`'s;
  `test_sales_schema.py` and `test_sales_step_thresholds.py` hold them to it.

Downgrade deletes the rows the old checks cannot hold. A labelled case or a
step outcome of the step is a fact about a past reading; dropping the step is
dropping them, which is what a downgrade of the step means.
"""

from __future__ import annotations

from alembic import op

revision = "beba87138cda"
down_revision = "e1b1e0cadb66"
branch_labels = None
depends_on = None

# `137ec1972538`'s keys, unchanged since.
_RULE_KEYS = (
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
    "purchasing_automation",
    "purchasing_master_data",
    "sales_salesorder_rules",
    "sales_skill_thread_intents",
    "sales_prompt_description_attributes",
)
# `dw_sales.application.skills.skill_key("mail-kinds")`.
_NEW_KEY = "sales_skill_mail_kinds"

# `dw_sales.domain.order_checks.ModelStep`, as `efc46a50e75e` listed it.
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
    "reply_draft",
    "skill_intents",
)
# `80584b911796`'s, unchanged since.
_PURCHASING_STEPS = (
    "purchasing_pr_mail_reading",
    "purchasing_supplier_quote_reading",
    "purchasing_order_confirmation_reading",
)
_NEW_STEP = "skill_mail_kinds"
# Every table whose step is a Sales step, by its CHECK.
_SALES_ONLY = (
    ("sales.step_outcomes", "ck_step_outcomes_step"),
    ("sales.labelled_cases", "ck_labelled_cases_step"),
    ("sales.step_thresholds", "ck_step_thresholds_step"),
)


def _listed(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _keys(keys: tuple[str, ...]) -> None:
    op.execute(
        "ALTER TABLE platform.rule_versions DROP CONSTRAINT ck_rule_versions_key,"
        f" ADD CONSTRAINT ck_rule_versions_key CHECK (key IN ({_listed(keys)}))"
    )


def _steps(sales: tuple[str, ...]) -> None:
    op.execute(
        "ALTER TABLE platform.model_step_measurements"
        " DROP CONSTRAINT ck_model_step_measurements_step,"
        " ADD CONSTRAINT ck_model_step_measurements_step"
        f" CHECK (step IN ({_listed((*sales, *_PURCHASING_STEPS))}))"
    )
    for table, check in _SALES_ONLY:
        op.execute(
            f"ALTER TABLE {table} DROP CONSTRAINT {check},"
            f" ADD CONSTRAINT {check} CHECK (step IN ({_listed(sales)}))"
        )


def upgrade() -> None:
    _keys((*_RULE_KEYS, _NEW_KEY))
    _steps((*_SALES_STEPS, _NEW_STEP))


def downgrade() -> None:
    op.execute(f"DELETE FROM platform.model_step_measurements WHERE step = '{_NEW_STEP}'")
    for table, _ in _SALES_ONLY:
        op.execute(f"DELETE FROM {table} WHERE step = '{_NEW_STEP}'")
    _steps(_SALES_STEPS)
    op.execute(f"DELETE FROM platform.rule_versions WHERE key = '{_NEW_KEY}'")
    _keys(_RULE_KEYS)
