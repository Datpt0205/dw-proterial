"""sales salesorder pairs withdrawn and kept for a term

Revision ID: 985e4fa0cd4f
Revises: b01dba5d0433
Create Date: 2026-11-17 02:41:32.365287+00:00

Sales ticket 41's leftovers. A customer's worked pair
(`sales.salesorder_pairs`, migration 711e8b760139) leaves the table two
ways, and both are a DELETE:

- **withdrawn** by a person who proposes rules and reads prices: a wrong
  pair (the PIC's file was itself wrong) would otherwise fail every replay of
  the customer's SalesOrder skill for good. The audit row keeps who withdrew
  which pair, of which customer, and when; never a cell.
- **dropped past the tenant's term** (`OrderRules.learning.
  salesorder_pairs_kept_days`, a year by default) by the worker's
  `sales_salesorder_pairs_retention` lane, in each workspace's own scope.

So `dw_app` is granted DELETE. A row is still never changed: UPDATE stays
REVOKEd (failure-modes #7), and `test_privileges.py` holds the table to
SELECT, INSERT and DELETE. The policy is unchanged: a DELETE reaches only the
rows of the transaction's tenant and workspace.

No index: the term's DELETE reads one workspace's pairs, which the
replay's index (`tenant_id, workspace_id, customer_code, added_at`) already
narrows to a few hundred rows at most.

Downgrade takes DELETE back.
"""

from __future__ import annotations

from alembic import op

revision = "985e4fa0cd4f"
down_revision = "b01dba5d0433"
branch_labels = None
depends_on = None


def _grant(statement: str) -> str:
    return f"""
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
            {statement};
        END IF;
    END
    $$
"""


def upgrade() -> None:
    op.execute(_grant("GRANT DELETE ON sales.salesorder_pairs TO dw_app"))


def downgrade() -> None:
    op.execute(_grant("REVOKE DELETE ON sales.salesorder_pairs FROM dw_app"))
