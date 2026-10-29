"""sales export control page withdrawn; the hold stays

Revision ID: fc723c5a7d81
Revises: e91d0c239874
Create Date: 2026-10-29 07:00:00.000000+00:00

Đạt, 2026-10-29: "kiểm soát xuất khẩu đâu có nằm trong 2 quy trình đơn hàng
và báo giá ... bỏ đi được không". WIV-03-032 is a procedure of its own, not a
step of either DW1 process, so the page that recorded each of its steps
(ticket 45, `1a21c3a78c93`) goes. What stays is the one place it touches the
order process: `missing_noc_esf` holds an order's confirmation while the
customer's master data shows no NOC, no ESF for the fiscal year or no recent
denial-list check (contract acceptance row 3), and the export-control PIC
acknowledges it as before.

- **`sales.export_control_screenings`** is dropped, with its policy and grants.
- **`ck_rule_versions_key`** loses `sales_export_control`; a tenant version of
  it is deleted first, since nothing reads it any more.

Downgrade restores the empty table and the key as `1a21c3a78c93` made them.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision = "fc723c5a7d81"
down_revision = "e91d0c239874"
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
)


def _keys(keys: tuple[str, ...]) -> None:
    listed = ", ".join(f"'{key}'" for key in keys)
    op.execute(
        f"""
        ALTER TABLE sales.rule_versions
            DROP CONSTRAINT ck_rule_versions_key,
            ADD CONSTRAINT ck_rule_versions_key CHECK (key IN ({listed}))
        """
    )


def upgrade() -> None:
    op.execute("DELETE FROM sales.rule_versions WHERE key = 'sales_export_control'")
    _keys(_KEYS)
    op.execute("DROP TABLE sales.export_control_screenings")


def downgrade() -> None:
    path = Path(__file__).with_name("1a21c3a78c93_sales_export_control_screenings_per_.py")
    spec = importlib.util.spec_from_file_location("_made_1a21c3a78c93", path)
    assert spec is not None and spec.loader is not None
    made = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(made)
    for ddl in (made._SCREENINGS, *made._INDEXES, *made._ROW_SECURITY, *made._GRANTS):
        op.execute(ddl)
    _keys((*_KEYS, "sales_export_control"))
