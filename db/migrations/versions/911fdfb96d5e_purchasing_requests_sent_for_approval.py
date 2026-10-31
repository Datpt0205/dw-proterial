"""purchasing requests sent for approval

Revision ID: 911fdfb96d5e
Revises: 2d0c58dc3806
Create Date: 2026-11-01 14:00:00.000000+00:00

DW2, DW02 function 2: a request checked against master data and sent to the
approver its amount and findings name (`dw_purchasing.application.approvals`).

- **`purchasing.cases.status`** admits `awaiting_approval`, `approved` and
  `rejected`; the check, the approval asked and the decision live in the
  `body`, stamped once.
- **`approval_id`**, generated from the body, names the platform approval a
  case waits on; unique, so one approval decides one case, and indexed for the
  worker that carries a decision out by it. Not a foreign key: the approval
  is the platform's row, and a case keeps its stamp whatever becomes of it.
- **Scopes and who holds them**: `purchasing_buyer` also sends a request for
  approval (`purchasing.request.submit`); a new role `purchasing_head`
  (Trưởng phòng Mua hàng) reads and decides the first two tiers; a permission
  set `purchasing_director_approver` decides the third. Which band of amounts
  each tier decides is the tenant's rule (`purchasing_rules`), not this
  migration's. No `purchasing.*` scope goes on a platform role.
"""

from __future__ import annotations

import json

from alembic import op

revision = "911fdfb96d5e"
down_revision = "2d0c58dc3806"
branch_labels = None
depends_on = None

# `dw_purchasing.domain.cases.CaseStatus`, held to it by test.
_STATUSES = "('received', 'awaiting_approval', 'approved', 'rejected')"
_STATUSES_BEFORE = "('received')"

_SUBMIT = "purchasing.request.submit"
_HEAD = (
    "purchasing.request.read",
    "purchasing.approve.tier1",
    "purchasing.approve.tier2",
)
_DIRECTOR = ("purchasing.approve.tier3",)


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _scopes(scopes: tuple[str, ...]) -> str:
    return _literal(json.dumps(list(scopes))) + "::jsonb"


def upgrade() -> None:
    op.execute("ALTER TABLE purchasing.cases DROP CONSTRAINT ck_cases_status")
    op.execute(
        f"ALTER TABLE purchasing.cases ADD CONSTRAINT ck_cases_status CHECK (status IN {_STATUSES})"
    )
    op.execute(
        "ALTER TABLE purchasing.cases ADD COLUMN approval_id uuid"
        " GENERATED ALWAYS AS ((body #>> '{approval,approval_id}')::uuid) STORED"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_cases_tenant_id_approval_id"
        " ON purchasing.cases (tenant_id, approval_id) WHERE approval_id IS NOT NULL"
    )
    # A case sent for approval holds what it was sent with.
    op.execute(
        "ALTER TABLE purchasing.cases ADD CONSTRAINT ck_cases_sent CHECK ("
        " (status = 'received') = (approval_id IS NULL)"
        " AND (status IN ('approved', 'rejected')) = (body ? 'decision'"
        " AND jsonb_typeof(body -> 'decision') = 'object'))"
    )
    op.execute(
        "UPDATE platform.roles SET scopes = scopes || "
        f"{_scopes((_SUBMIT,))} WHERE key = 'purchasing_buyer'"
    )
    op.execute(
        "INSERT INTO platform.roles (key, name, scopes)"
        f" VALUES ('purchasing_head', 'Trưởng phòng Mua hàng', {_scopes(_HEAD)})"
    )
    op.execute(
        "INSERT INTO platform.permission_sets (key, name, scopes)"
        " VALUES ('purchasing_director_approver', 'Duyệt yêu cầu mua hàng bậc 3',"
        f" {_scopes(_DIRECTOR)})"
    )


def downgrade() -> None:
    op.execute("DELETE FROM platform.permission_sets WHERE key = 'purchasing_director_approver'")
    op.execute("DELETE FROM platform.roles WHERE key = 'purchasing_head'")
    op.execute(
        f"UPDATE platform.roles SET scopes = scopes - {_literal(_SUBMIT)}"
        " WHERE key = 'purchasing_buyer'"
    )
    op.execute("ALTER TABLE purchasing.cases DROP CONSTRAINT ck_cases_sent")
    op.execute("DROP INDEX purchasing.uq_cases_tenant_id_approval_id")
    op.execute("ALTER TABLE purchasing.cases DROP COLUMN approval_id")
    op.execute("ALTER TABLE purchasing.cases DROP CONSTRAINT ck_cases_status")
    op.execute(
        "ALTER TABLE purchasing.cases ADD CONSTRAINT ck_cases_status"
        f" CHECK (status IN {_STATUSES_BEFORE})"
    )
