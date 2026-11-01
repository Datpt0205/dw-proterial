"""purchasing rules proposed and decided

Revision ID: 633993a6d8b4
Revises: 5ef229da512b
Create Date: 2026-11-01 05:10:00.000000+00:00

DW2 registers its rules with the platform's rule-version engine (ADR 0013,
0014): a tenant's `purchasing_rules` is proposed, decided by a second person
and resolved per tenant, like a Sales rule.

- **`ck_rule_versions_key`** (on `platform.rule_versions`, moved by
  5ef229da512b) admits `purchasing_rules` beside Sales' keys.
- **Scopes**: `purchasing.rules.propose` and `purchasing.rules.approve` for
  `purchasing_head` (whose own version applies at once, as a Sales head's);
  a new role `purchasing_configurer` (Người cấu hình DW2) reads requests and
  proposes, and their version waits for the head.
"""

from __future__ import annotations

import json

from alembic import op

revision = "633993a6d8b4"
down_revision = "5ef229da512b"
branch_labels = None
depends_on = None

_SALES_KEYS = (
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
_PURCHASING_KEYS = ("purchasing_rules",)
_PROPOSE = "purchasing.rules.propose"
_APPROVE = "purchasing.rules.approve"
_CONFIGURER = ("purchasing.request.read", _PROPOSE)


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _scopes(scopes: tuple[str, ...]) -> str:
    return _literal(json.dumps(list(scopes))) + "::jsonb"


def _keys(keys: tuple[str, ...]) -> None:
    listed = ", ".join(_literal(key) for key in keys)
    op.execute(
        f"""
        ALTER TABLE platform.rule_versions
            DROP CONSTRAINT ck_rule_versions_key,
            ADD CONSTRAINT ck_rule_versions_key CHECK (key IN ({listed}))
        """
    )


def upgrade() -> None:
    _keys(_SALES_KEYS + _PURCHASING_KEYS)
    op.execute(
        f"UPDATE platform.roles SET scopes = scopes || {_scopes((_PROPOSE, _APPROVE))}"
        " WHERE key = 'purchasing_head'"
    )
    op.execute(
        "INSERT INTO platform.roles (key, name, scopes)"
        f" VALUES ('purchasing_configurer', 'Người cấu hình DW2', {_scopes(_CONFIGURER)})"
    )


def downgrade() -> None:
    op.execute("DELETE FROM platform.roles WHERE key = 'purchasing_configurer'")
    op.execute(
        f"UPDATE platform.roles SET scopes = scopes - {_literal(_PROPOSE)} - {_literal(_APPROVE)}"
        " WHERE key = 'purchasing_head'"
    )
    keys = ", ".join(_literal(key) for key in _PURCHASING_KEYS)
    op.execute(f"DELETE FROM platform.rule_versions WHERE key IN ({keys})")
    _keys(_SALES_KEYS)
