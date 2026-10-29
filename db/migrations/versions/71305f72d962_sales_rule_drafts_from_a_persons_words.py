"""sales rule drafts from a person's words

Revision ID: 71305f72d962
Revises: fc723c5a7d81
Create Date: 2026-10-29 08:00:00.000000+00:00

dw_sales ADR 0006, decision 3 (Đạt, 2026-10-29: "nó quá rườm rà để 1 người
non tech có thể config"). A draft was made only from the company's Bravo
template file. It can now be made from what a person typed, for any key they
may propose a version of: the model proposes changes, code checks them, and
the draft opens in the rules editor as a start option, as a file's does.

- **`request`**: the person's words, kept with the draft so its reader sees
  what was asked; NULL for a draft from a file. Bounded by `char_length`.
- **`focus`**: the part of the document the words are about (a mail's kind,
  ``emails.confirmation_draft``), or NULL for the whole of it.
- **`ck_rule_drafts_document`**: a drafted file still has its header row; a
  drafted request has none.
- **`ck_rule_drafts_rule_key`** takes every key a version may be proposed for
  (`dw_sales.application.rules.RuleKey`, `test_sales_schema.py` holds them
  equal), not only the Bravo template.
"""

from __future__ import annotations

from alembic import op

revision = "71305f72d962"
down_revision = "fc723c5a7d81"
branch_labels = None
depends_on = None

_DRAFTED = "('ready', 'refused', 'unavailable')"
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
)


def _in(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
    op.execute(
        f"""
        ALTER TABLE sales.rule_drafts
            ADD COLUMN request text,
            ADD COLUMN focus text,
            ADD CONSTRAINT ck_rule_drafts_request CHECK (
                request IS NULL OR char_length(request) BETWEEN 1 AND 2000
            ),
            ADD CONSTRAINT ck_rule_drafts_focus CHECK (
                focus IS NULL
                OR (request IS NOT NULL AND focus ~ '^[A-Za-z_][A-Za-z0-9_.]*$'
                    AND char_length(focus) <= 200)
            ),
            DROP CONSTRAINT ck_rule_drafts_document,
            ADD CONSTRAINT ck_rule_drafts_document CHECK (
                (status IN {_DRAFTED}) = (document IS NOT NULL)
                AND (status NOT IN {_DRAFTED} OR request IS NOT NULL OR template IS NOT NULL)
                AND (document IS NULL OR jsonb_typeof(document) = 'object')
            ),
            DROP CONSTRAINT ck_rule_drafts_rule_key,
            ADD CONSTRAINT ck_rule_drafts_rule_key CHECK (rule_key IN {_in(_KEYS)})
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM sales.rule_drafts WHERE request IS NOT NULL")
    op.execute(
        f"""
        ALTER TABLE sales.rule_drafts
            DROP CONSTRAINT ck_rule_drafts_rule_key,
            ADD CONSTRAINT ck_rule_drafts_rule_key CHECK (rule_key IN ('sales_bravo_upload')),
            DROP CONSTRAINT ck_rule_drafts_document,
            ADD CONSTRAINT ck_rule_drafts_document CHECK (
                (status IN {_DRAFTED}) = (document IS NOT NULL AND template IS NOT NULL)
                AND (document IS NULL OR jsonb_typeof(document) = 'object')
            ),
            DROP CONSTRAINT ck_rule_drafts_focus,
            DROP CONSTRAINT ck_rule_drafts_request,
            DROP COLUMN focus,
            DROP COLUMN request
        """
    )
