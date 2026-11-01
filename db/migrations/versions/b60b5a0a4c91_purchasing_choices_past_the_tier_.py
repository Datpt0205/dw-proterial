"""purchasing choices past the tier approved again

Revision ID: b60b5a0a4c91
Revises: 6971b41fcdf6
Create Date: 2026-11-01 11:00:00.000000+00:00

A choice of suppliers whose total passes what the approver's tier decides
goes back for approval at the tier its total names
(`dw_purchasing.application.reapprovals`):

- **`ck_cases_status`** admits `awaiting_reapproval`.
- **`ck_cases_sent`**, **`ck_cases_sourced`** are rewritten so the waiting
  state holds what a decided, sourced case holds (the decision, the RFQ
  round) and no selection yet (the choice waits in `reapproval`).
- **`ck_cases_reapproval`**: `awaiting_reapproval` holds its `reapproval`.
- **`reapproval_id`**, generated from the body, unique per tenant like
  `approval_id`, so the worker finds the case a decision is for.
"""

from __future__ import annotations

from alembic import op

revision = "b60b5a0a4c91"
down_revision = "6971b41fcdf6"
branch_labels = None
depends_on = None

_STATUSES = (
    "('received', 'awaiting_approval', 'approved', 'rejected', 'rfq_drafted',"
    " 'awaiting_reapproval', 'supplier_selected', 'po_drafted')"
)
_DECIDED = (
    "('approved', 'rejected', 'rfq_drafted', 'awaiting_reapproval', 'supplier_selected',"
    " 'po_drafted')"
)
_SOURCING = "('rfq_drafted', 'awaiting_reapproval', 'supplier_selected', 'po_drafted')"
_STATUSES_BEFORE = (
    "('received', 'awaiting_approval', 'approved', 'rejected', 'rfq_drafted',"
    " 'supplier_selected', 'po_drafted')"
)
_DECIDED_BEFORE = "('approved', 'rejected', 'rfq_drafted', 'supplier_selected', 'po_drafted')"
_SOURCING_BEFORE = "('rfq_drafted', 'supplier_selected', 'po_drafted')"
_CHOSEN = "('supplier_selected', 'po_drafted')"


def _object(key: str) -> str:
    return f"(coalesce(jsonb_typeof(body -> '{key}'), 'absent') = 'object')"


def _replace(statuses: str, decided: str, sourcing: str) -> None:
    for name in ("ck_cases_status", "ck_cases_sent", "ck_cases_sourced"):
        op.execute(f"ALTER TABLE purchasing.cases DROP CONSTRAINT {name}")
    op.execute(
        f"ALTER TABLE purchasing.cases ADD CONSTRAINT ck_cases_status CHECK (status IN {statuses})"
    )
    op.execute(
        "ALTER TABLE purchasing.cases ADD CONSTRAINT ck_cases_sent CHECK ("
        " (status = 'received') = (approval_id IS NULL)"
        f" AND (status IN {decided}) = {_object('decision')})"
    )
    op.execute(
        "ALTER TABLE purchasing.cases ADD CONSTRAINT ck_cases_sourced CHECK ("
        f" (status IN {sourcing}) = {_object('rfq')}"
        f" AND (status IN {_CHOSEN}) = {_object('selection')})"
    )


def upgrade() -> None:
    _replace(_STATUSES, _DECIDED, _SOURCING)
    op.execute(
        "ALTER TABLE purchasing.cases ADD CONSTRAINT ck_cases_reapproval CHECK ("
        f" status <> 'awaiting_reapproval' OR {_object('reapproval')})"
    )
    op.execute(
        "ALTER TABLE purchasing.cases ADD COLUMN reapproval_id uuid"
        " GENERATED ALWAYS AS ((body #>> '{reapproval,approval,approval_id}')::uuid) STORED"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_cases_tenant_id_reapproval_id"
        " ON purchasing.cases (tenant_id, reapproval_id) WHERE reapproval_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE purchasing.cases SET status = 'rfq_drafted', body = body - 'reapproval'"
        " WHERE status = 'awaiting_reapproval'"
    )
    op.execute("DROP INDEX purchasing.uq_cases_tenant_id_reapproval_id")
    op.execute("ALTER TABLE purchasing.cases DROP COLUMN reapproval_id")
    op.execute("ALTER TABLE purchasing.cases DROP CONSTRAINT ck_cases_reapproval")
    _replace(_STATUSES_BEFORE, _DECIDED_BEFORE, _SOURCING_BEFORE)
