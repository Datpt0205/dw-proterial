"""purchasing requesters write their own requests

Revision ID: e823f9c57e5a
Revises: 82cc61f87d6c
Create Date: 2026-11-01 08:00:00.000000+00:00

DW2's requester (Người yêu cầu) writes a request in DW2 ("Tôi cần mua…")
and sees only the requests they wrote, narrowed in the query:

- **`ck_cases_source`** admits `requester`.
- **`requested_by`**: generated from the case's body, the signed-in person
  who asked; `ck_cases_requester` holds a requester's case to naming them.
- **`ix_cases_tenant_id_requested_by_received_at`** carries a requester's
  list as it pages (`received_at DESC, id DESC`), led by the column RLS
  supplies.
- **Role `purchasing_requester`** (Người yêu cầu mua hàng):
  `purchasing.request.create`, `purchasing.request.read_own`.
"""

from __future__ import annotations

import json

from alembic import op

revision = "e823f9c57e5a"
down_revision = "82cc61f87d6c"
branch_labels = None
depends_on = None

_SCOPES = ("purchasing.request.create", "purchasing.request.read_own")


def upgrade() -> None:
    op.execute(
        "ALTER TABLE purchasing.cases DROP CONSTRAINT ck_cases_source,"
        " ADD CONSTRAINT ck_cases_source CHECK (source IN ('form', 'mail', 'requester'))"
    )
    op.execute(
        "ALTER TABLE purchasing.cases ADD COLUMN requested_by uuid"
        " GENERATED ALWAYS AS ((body #>> '{requested_by}')::uuid) STORED"
    )
    op.execute(
        "ALTER TABLE purchasing.cases ADD CONSTRAINT ck_cases_requester"
        " CHECK (source <> 'requester' OR requested_by IS NOT NULL)"
    )
    op.execute(
        "CREATE INDEX ix_cases_tenant_id_requested_by_received_at ON purchasing.cases"
        " (tenant_id, requested_by, received_at DESC, id DESC) WHERE requested_by IS NOT NULL"
    )
    scopes = json.dumps(list(_SCOPES)).replace("'", "''")
    op.execute(
        "INSERT INTO platform.roles (key, name, scopes)"
        f" VALUES ('purchasing_requester', 'Người yêu cầu mua hàng', '{scopes}'::jsonb)"
    )


def downgrade() -> None:
    op.execute("DELETE FROM platform.roles WHERE key = 'purchasing_requester'")
    op.execute("DELETE FROM purchasing.cases WHERE source = 'requester'")
    op.execute("DROP INDEX purchasing.ix_cases_tenant_id_requested_by_received_at")
    op.execute("ALTER TABLE purchasing.cases DROP CONSTRAINT ck_cases_requester")
    op.execute("ALTER TABLE purchasing.cases DROP COLUMN requested_by")
    op.execute(
        "ALTER TABLE purchasing.cases DROP CONSTRAINT ck_cases_source,"
        " ADD CONSTRAINT ck_cases_source CHECK (source IN ('form', 'mail'))"
    )
