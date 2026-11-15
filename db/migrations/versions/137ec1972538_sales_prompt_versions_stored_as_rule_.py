"""sales prompt versions stored as rule versions

Revision ID: 137ec1972538
Revises: bfe2d1aeadcd
Create Date: 2026-11-15 18:49:02.077179+00:00

Sales ticket 43 part 3 (dw_sales ADR 0015 decision 5): the worker's optimiser
proposes a tenant's version of the description reading's prompt, the
demonstrations every reading is shown, and the head approves it.

- **`ck_rule_versions_key`** (`platform.rule_versions`) admits
  `sales_prompt_description_attributes`. A tenant's version is a rule version
  like any other: one row per tenant, key and version, its demonstrations and
  replay figures the document
  (`dw_sales.application.prompt_versions.PromptDemonstrations`), proposed by
  the `sales_prompt_optimiser` lane and decided by the head on a
  `sales.prompts` approval. The table's RLS (tenant only, ENABLEd and FORCEd),
  its grants, `uq_rule_versions_one_proposed`,
  `ck_rule_versions_checker_not_maker` and `ck_rule_versions_document` hold
  for it unchanged; `test_rls_coverage.py` and `test_privileges.py` already
  assert them.

Nothing else: the decided lines it learns from are `sales.labelled_cases`
(`eac4fabdb31a`), read with the order lines they name. Downgrade deletes the
rows the old check cannot hold.
"""

from __future__ import annotations

from alembic import op

revision = "137ec1972538"
down_revision = "bfe2d1aeadcd"
branch_labels = None
depends_on = None

# `80584b911796`'s keys, unchanged since.
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
    "purchasing_automation",
    "purchasing_master_data",
    "sales_salesorder_rules",
    "sales_skill_thread_intents",
)
# `dw_sales.application.prompt_versions.PROMPT_KEY`.
_NEW_KEY = "sales_prompt_description_attributes"


def _keys(keys: tuple[str, ...]) -> None:
    listed = ", ".join(f"'{key}'" for key in keys)
    op.execute(
        "ALTER TABLE platform.rule_versions DROP CONSTRAINT ck_rule_versions_key,"
        f" ADD CONSTRAINT ck_rule_versions_key CHECK (key IN ({listed}))"
    )


def upgrade() -> None:
    _keys((*_KEYS, _NEW_KEY))


def downgrade() -> None:
    op.execute(f"DELETE FROM platform.rule_versions WHERE key = '{_NEW_KEY}'")
    _keys(_KEYS)
