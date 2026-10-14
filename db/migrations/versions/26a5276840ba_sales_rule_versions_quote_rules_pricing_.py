"""sales rule versions quote rules pricing and copy

Revision ID: 26a5276840ba
Revises: b2afb906fbf2
Create Date: 2026-10-14 03:40:00.000000+00:00

Sales ticket 36. Ticket 19 let a tenant hold its own, approved version of the
order rules and the KPI policy. The quote rules, the pricing policy, the
e-mail and document copy, the Bravo upload template and the hand-off copy now
resolve per tenant too (`dw_sales.application.rules.RuleKey`), so
`sales.rule_versions` takes their keys, in the same change as their readers.

- **`ck_rule_versions_key`** names the eight keys `RuleKey` has
  (`test_sales_schema.py` holds the two lists equal).
- **`ck_rule_versions_document`**: a policy names itself with `policy_id`
  and `policy_version`; a copy file with `copy_id` and `version`. The
  document names its key and the row's version either way, as before, and a
  document naming neither is refused: the comparison is wrapped in
  `COALESCE(..., false)`, since a missing key makes it NULL and a CHECK that
  evaluates to NULL passes (the earlier constraint had that gap).

Same names, same table, dropped and re-added in one statement and checked
against the rows already there, as `13c687788955` did. Downgrade restores
`57a241ea182b`'s two keys; it fails, with Postgres's own "violated by some
row", while a version of one of the six is stored: deleting a version two
people approved to make a downgrade pass would lose it.
"""

from __future__ import annotations

from alembic import op

revision = "26a5276840ba"
down_revision = "b2afb906fbf2"
branch_labels = None
depends_on = None

_BEFORE = ("sales_order_rules", "sales_kpi")
_KEYS = (
    *_BEFORE,
    "sales_quote_rules",
    "sales_pricing",
    "sales_emails",
    "sales_documents",
    "sales_bravo_upload",
    "sales_handoffs",
)
_POLICY_DOCUMENT = (
    "document ->> 'policy_id' = key AND document ->> 'policy_version' = version"
)
_COPY_DOCUMENT = "document ->> 'copy_id' = key AND document ->> 'version' = version"


def _in(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{value}'" for value in values) + ")"


def _checks(keys: tuple[str, ...], document: str) -> None:
    op.execute(
        f"""
        ALTER TABLE sales.rule_versions
            DROP CONSTRAINT ck_rule_versions_key,
            DROP CONSTRAINT ck_rule_versions_document,
            ADD CONSTRAINT ck_rule_versions_key CHECK (key IN {_in(keys)}),
            ADD CONSTRAINT ck_rule_versions_document CHECK (
                jsonb_typeof(document) = 'object' AND COALESCE({document}, false)
            )
        """
    )


def upgrade() -> None:
    _checks(_KEYS, f"({_POLICY_DOCUMENT}) OR ({_COPY_DOCUMENT})")


def downgrade() -> None:
    _checks(_BEFORE, _POLICY_DOCUMENT)
