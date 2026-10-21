"""sales rules editor for tenant IT and approval kept from member admins

Revision ID: 59cf23d3a859
Revises: e8a1c3e8ed78
Create Date: 2026-10-21 02:30:13.977368+00:00

Đạt's decision of 2026-10-21 (dw_sales ADR 0003, addendum): the customer's IT
may propose a version of a Sales rule, and approving one stays with the Sales
head.

- **Permission set `sales_rules_editor`** = `{sales.rules.propose}`, for an IT
  membership (`org_admin`). No platform role gains a `sales.*` scope, so
  ADR 0003 §1 and `test_sales_roles.py` hold as they were. The set carries no
  price: a key whose documents hold prices or price policy also asks for
  `sales.price.read` (`dw_sales.application.rules.PRICE_BEARING`), which the
  rule of 68305ebe4a83 already keeps off any membership administering members.
- **Separation-of-duty rule `sod_sales_rules_approve_vs_member_admin`**:
  `platform.members.write` and `sales.rules.approve` never on one membership,
  so whoever administers members cannot grant themselves the checker's side
  of a rule they could propose. Not waivable, like the price rule. Checked
  against every existing membership when the row is inserted by
  `trg_sod_rules_memberships_insert` (d82a60870baf): the upgrade fails,
  naming them, if any membership already holds both.

Downgrade removes the rule and the set, in that order.
"""

from __future__ import annotations

import json

from alembic import op

revision = "59cf23d3a859"
down_revision = "e8a1c3e8ed78"
branch_labels = None
depends_on = None

_SET = ("sales_rules_editor", "Người đề xuất quy tắc", ("sales.rules.propose",))
_RULE_KEY = "sod_sales_rules_approve_vs_member_admin"
_RULE_DESCRIPTION = (
    "Quản trị thành viên (platform.members.write) và duyệt quy tắc Sales"
    " (sales.rules.approve) không cùng một người: IT đề xuất, Trưởng bộ phận"
    " Sales duyệt (dw_sales ADR 0003)."
)


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
        "INSERT INTO platform.sod_rules (key, description, left_scopes, right_scopes, waivable)"
        f" VALUES ({_literal(_RULE_KEY)}, {_literal(_RULE_DESCRIPTION)},"
        f" {_scopes(('platform.members.write',))}, {_scopes(('sales.rules.approve',))}, false)"
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM platform.sod_rules WHERE key = {_literal(_RULE_KEY)}")
    op.execute(f"DELETE FROM platform.permission_sets WHERE key = {_literal(_SET[0])}")
