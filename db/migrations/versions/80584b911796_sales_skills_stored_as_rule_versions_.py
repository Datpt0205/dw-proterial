"""sales skills stored as rule versions, the skill step admitted

Revision ID: 80584b911796
Revises: 3aca293b2c92
Create Date: 2026-11-15 10:44:18.895160+00:00

Sales ticket 40 (dw_sales ADR 0014): DW1 reads with skills a tenant edits.

- **`ck_rule_versions_key`** (`platform.rule_versions`) admits
  `sales_skill_thread_intents`, DW1's first skill. A tenant's version of a
  skill is a rule version like any other: one row per tenant, key and
  version, its description and instructions the document
  (`dw_sales.application.skills.SkillDocument`), proposed by one person and
  decided by the head on a `sales.skills` approval. The table's RLS (tenant
  only, ENABLEd and FORCEd), its grants, `uq_rule_versions_one_proposed`,
  `ck_rule_versions_checker_not_maker` and `ck_rule_versions_document` hold
  for it unchanged; `test_rls_coverage.py` and `test_privileges.py` already
  assert them. The scope is the tenant's, as a rule's and a prompt's: a
  skill reads every workspace's mail alike.
- **`ck_model_step_measurements_step`** and **`ck_step_outcomes_step`**
  admit `skill_intents`, the step DW1's agent reads a thread message's
  intents in with its skills, as `3aca293b2c92` did for `reply_draft`.

`test_sales_schema.py` holds each CHECK to the domain's values. Downgrade
deletes the rows the old checks cannot hold.
"""

from __future__ import annotations

from alembic import op

revision = "80584b911796"
down_revision = "3aca293b2c92"
branch_labels = None
depends_on = None

# `d94bf01066d2`'s keys and the learned SalesOrder rules it added.
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
)
# `dw_sales.application.skills.skill_key` of each platform skill.
_SKILL_KEYS = ("sales_skill_thread_intents",)

# `dw_sales.domain.order_checks.ModelStep`, as `3aca293b2c92` left it.
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
)
_PURCHASING_STEPS = (
    "purchasing_pr_mail_reading",
    "purchasing_supplier_quote_reading",
    "purchasing_order_confirmation_reading",
)
_NEW_STEP = "skill_intents"


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
    op.execute(
        "ALTER TABLE sales.step_outcomes"
        " DROP CONSTRAINT ck_step_outcomes_step,"
        f" ADD CONSTRAINT ck_step_outcomes_step CHECK (step IN ({_listed(sales)}))"
    )


def upgrade() -> None:
    _keys((*_RULE_KEYS, *_SKILL_KEYS))
    _steps((*_SALES_STEPS, _NEW_STEP))


def downgrade() -> None:
    op.execute(f"DELETE FROM platform.model_step_measurements WHERE step = '{_NEW_STEP}'")
    op.execute(f"DELETE FROM sales.step_outcomes WHERE step = '{_NEW_STEP}'")
    _steps(_SALES_STEPS)
    op.execute(f"DELETE FROM platform.rule_versions WHERE key IN ({_listed(_SKILL_KEYS)})")
    _keys(_RULE_KEYS)
