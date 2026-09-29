"""roles and permission sets read-only to application roles

Revision ID: 648e2f7c3edb
Revises: b9862fa13a80
Create Date: 2026-09-28

`platform.roles` and `platform.permission_sets` decide which scopes a
membership carries. `ALTER DEFAULT PRIVILEGES` (0001_platform_grants.sql)
handed `dw_app` INSERT, UPDATE and DELETE on both. No application code writes
either table: the catalogue changes only in migrations, as `dw_migrator`.
Application credentials could therefore widen a role past a separation-of-duty
rule, or put one scope in every role, and no application path could have
been the reason.

- `dw_app` keeps SELECT and loses INSERT, UPDATE, DELETE and TRUNCATE on both.
- `dw_provisioner` loses the same on `platform.roles`, and holds nothing on
  `platform.permission_sets`. The baseline granted it write on `roles`, while
  `scripts/create_provisioner_role.py` and the provisioning test fixture grant
  SELECT only. No provisioning code writes roles, so the narrower list is the
  intended one.

Each statement is guarded on the role existing, as in b9862fa13a80.
Downgrade gives back what the baseline granted: write on both tables to
`dw_app`, and write on `platform.roles` to `dw_provisioner`.
"""

from __future__ import annotations

from alembic import op

revision = "648e2f7c3edb"
down_revision = "b9862fa13a80"
branch_labels = None
depends_on = None

_CATALOGUE = ("platform.roles", "platform.permission_sets")


def _for_role(role: str, statement: str) -> str:
    return f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                {statement}
            END IF;
        END
        $$
        """


def upgrade() -> None:
    for table in _CATALOGUE:
        for role in ("dw_app", "dw_provisioner"):
            op.execute(
                _for_role(role, f"REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON {table} FROM {role};")
            )
        op.execute(_for_role("dw_app", f"GRANT SELECT ON {table} TO dw_app;"))


def downgrade() -> None:
    for table in _CATALOGUE:
        op.execute(_for_role("dw_app", f"GRANT INSERT, UPDATE, DELETE ON {table} TO dw_app;"))
    op.execute(
        _for_role(
            "dw_provisioner", "GRANT INSERT, UPDATE, DELETE ON platform.roles TO dw_provisioner;"
        )
    )
