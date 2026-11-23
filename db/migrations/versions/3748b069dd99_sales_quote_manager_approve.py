"""sales quote manager approve

Revision ID: 3748b069dd99
Revises: 4b3f44f30356
Create Date: 2026-11-23

Sales ticket 39 (Đạt, 2026-11-23: follow WIV-03-023 section 4): a quotation that
comes with an order is checked at ASV level and then approved by a Manager,
three different people.

- **Scope `sales.quote.manager_approve`** decides the run-less
  `sales.quote.manager` approval the check opens. It joins `sales_head`
  (the head approves at either level, never both on one quotation: the
  approval names the checker among its makers).
- **Permission set `sales_quote_manager`** = `{sales.quote.manager_approve,
  approvals.decide}`, for a Manager who is not the Sales head, as
  `sales_quote_approver` is for an ASV deputy. No new role (Đạt, 10-27).

Downgrade removes the set and the scope, in that order.
"""

from __future__ import annotations

import json

from alembic import op

revision = "3748b069dd99"
down_revision = "4b3f44f30356"
branch_labels = None
depends_on = None

_SCOPE = "sales.quote.manager_approve"
_SET = ("sales_quote_manager", "Manager duyệt báo giá kèm đơn", (_SCOPE, "approvals.decide"))
_ROLE = "sales_head"


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _scopes(scopes: tuple[str, ...]) -> str:
    return _literal(json.dumps(list(scopes))) + "::jsonb"


def upgrade() -> None:
    key, name, scopes = _SET
    op.execute(
        "INSERT INTO platform.permission_sets (key, name, scopes)"
        f" VALUES ({_literal(key)}, {_literal(name)}, {_scopes(scopes)})"
    )
    op.execute(
        f"UPDATE platform.roles SET scopes = scopes || '[\"{_SCOPE}\"]'::jsonb"
        f" WHERE key = '{_ROLE}' AND NOT scopes ? '{_SCOPE}'"
    )


def downgrade() -> None:
    op.execute(f"UPDATE platform.roles SET scopes = scopes - '{_SCOPE}' WHERE key = '{_ROLE}'")
    op.execute(f"DELETE FROM platform.permission_sets WHERE key = {_literal(_SET[0])}")
