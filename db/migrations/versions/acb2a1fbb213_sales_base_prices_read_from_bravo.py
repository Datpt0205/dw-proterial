"""sales base prices read from Bravo

Revision ID: acb2a1fbb213
Revises: 57bbf61ae6b8
Create Date: 2026-11-16 12:53:39.093934+00:00

dw_sales ticket 11. Design's base price for a BP code is Bravo's "Danh mục
Base price" (Box B21: BP code, date, units, specification, category, copper
weight, the base price, LME and %MR of BP, the cost split). DW1 reads it as
one more master list, through the same Bravo port, snapshot and
second-person approval as the others (ticket 14), so `sales.catalog_snapshots`
admits the list ``base_prices``. dw_sales ticket 12 reads Bravo's "Master
list báo giá" (Box B07) the same way, as ``bravo_quotations``.

Only `ck_catalog_snapshots_list` changes: the records ride the snapshot's
existing rows, and their privileges and row security are the table's.
Downgrade refuses while a base-price snapshot exists rather than dropping
one: an approved list is evidence a check stamped.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "acb2a1fbb213"
down_revision = "57bbf61ae6b8"
branch_labels = None
depends_on = None

# `dw_sales.domain.master_data.CatalogList`; `test_sales_schema.py` holds the
# two together.
_BEFORE = "('customers', 'items', 'convert_list', 'quotations', 'lme')"
_AFTER = (
    "('customers', 'items', 'convert_list', 'quotations', 'lme', 'base_prices', 'bravo_quotations')"
)


def upgrade() -> None:
    op.execute("ALTER TABLE sales.catalog_snapshots DROP CONSTRAINT ck_catalog_snapshots_list")
    op.execute(
        "ALTER TABLE sales.catalog_snapshots ADD CONSTRAINT ck_catalog_snapshots_list"
        f" CHECK (list IN {_AFTER})"
    )


def downgrade() -> None:
    held = op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM sales.catalog_snapshots"
            " WHERE list IN ('base_prices', 'bravo_quotations')"
        )
    )
    if held:
        raise RuntimeError(f"{held} snapshot(s) of the lists exist: refusing to drop them")
    op.execute("ALTER TABLE sales.catalog_snapshots DROP CONSTRAINT ck_catalog_snapshots_list")
    op.execute(
        "ALTER TABLE sales.catalog_snapshots ADD CONSTRAINT ck_catalog_snapshots_list"
        f" CHECK (list IN {_BEFORE})"
    )
