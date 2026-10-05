"""sales roles permission sets and separation of duties

Revision ID: 68305ebe4a83
Revises: 621864952a54
Create Date: 2026-10-05

DW1's actors (spec "Actors, roles and scopes", dw_sales ADR 0003), as rows in
the platform's catalogue, which a context extends in its own migration:

- roles `sales_pic`, `sales_head` and `sales_viewer`;
- permission sets `sales_price_evidence`, `sales_quote_approver` and
  `sales_export_control`, each added to a `sales_pic` membership;
- a separation-of-duty rule keeping `platform.members.write` (tenant IT) and
  `sales.price.read` off one membership: IT is not Sales.

No `sales.*` scope goes on a platform role (member, approver, manager,
director, executive, org_admin). A purchasing manager must not approve a
quotation, and a member must not read every price; `test_sales_roles.py`
asserts it against the catalogue.

`sales.rules.approve` and `sales.case.assign` are not declared: they arrive
with the routes that read them (ticket 12).

The rule is not waivable. A tenant small enough that IT and Sales are one
person decides that with Proterial and a new rule, not a waiver.

Nothing can hold these keys yet, so no membership breaks the rule now. The
upgrade asserts that anyway, because the trigger judges a membership only
when it is written: one already in breach would sit unnoticed until its next
edit failed.
"""

from __future__ import annotations

import json

from alembic import op

revision = "68305ebe4a83"
down_revision = "621864952a54"
branch_labels = None
depends_on = None

_PIC = (
    "sales.overview.read",
    "sales.case.read",
    "sales.price.read",
    "sales.inbox.process",
    "sales.order.prepare",
    "sales.order.cross_check",
    "sales.quote.prepare",
    "sales.worker.pause",
)
_HEAD = (
    *_PIC,
    "sales.price.other_customers.read",
    "sales.quote.approve",
    "sales.worker.resume",
)

_ROLES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("sales_pic", "Sales phụ trách (PIC)", _PIC),
    ("sales_head", "Trưởng bộ phận Sales", _HEAD),
    # Counts and times, no amounts and no case list.
    ("sales_viewer", "Lãnh đạo (xem tổng hợp)", ("sales.overview.read",)),
)
_PERMISSION_SETS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "sales_price_evidence",
        "Xem giá đã báo cho khách khác",
        ("sales.price.other_customers.read",),
    ),
    ("sales_quote_approver", "Người duyệt báo giá thay", ("sales.quote.approve",)),
    ("sales_export_control", "PIC kiểm soát xuất khẩu", ("sales.compliance.ack",)),
)
_RULE_KEY = "sod_sales_price_vs_member_admin"
_RULE_DESCRIPTION = (
    "Quản trị thành viên (platform.members.write) và xem giá bán (sales.price.read)"
    " không cùng một người: IT không phải Sales (dw_sales ADR 0003)."
)


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _scopes(scopes: tuple[str, ...]) -> str:
    return _literal(json.dumps(list(scopes))) + "::jsonb"


def upgrade() -> None:
    for key, name, scopes in _ROLES:
        op.execute(
            "INSERT INTO platform.roles (key, name, scopes)"
            f" VALUES ({_literal(key)}, {_literal(name)}, {_scopes(scopes)})"
        )
    for key, name, scopes in _PERMISSION_SETS:
        op.execute(
            "INSERT INTO platform.permission_sets (key, name, scopes)"
            f" VALUES ({_literal(key)}, {_literal(name)}, {_scopes(scopes)})"
        )
    op.execute(
        "INSERT INTO platform.sod_rules (key, description, left_scopes, right_scopes, waivable)"
        f" VALUES ({_literal(_RULE_KEY)}, {_literal(_RULE_DESCRIPTION)},"
        f" {_scopes(('platform.members.write',))}, {_scopes(('sales.price.read',))}, false)"
    )
    # Runs as the migrator, which bypasses RLS: every tenant's memberships.
    op.execute(
        """
        DO $$
        DECLARE
            breaking integer;
        BEGIN
            -- This rule alone: `sod_violation` names only the first rule a
            -- membership breaks, which could be another one.
            SELECT count(*) INTO breaking
            FROM platform.memberships m
            WHERE platform.sod_rule_broken(
                'sod_sales_price_vs_member_admin', m.role_keys, m.permission_set_keys
            );
            IF breaking > 0 THEN
                RAISE EXCEPTION
                    '% membership(s) already hold platform.members.write and sales.price.read',
                    breaking;
            END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM platform.sod_rules WHERE key = {_literal(_RULE_KEY)}")
    keys = ", ".join(_literal(key) for key, _, _ in _PERMISSION_SETS)
    op.execute(f"DELETE FROM platform.permission_sets WHERE key IN ({keys})")
    keys = ", ".join(_literal(key) for key, _, _ in _ROLES)
    op.execute(f"DELETE FROM platform.roles WHERE key IN ({keys})")
