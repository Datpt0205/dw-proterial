"""sales dw1 service account role

Revision ID: af154486381e
Revises: 33f444c15062
Create Date: 2026-10-12 10:41:22.442420+00:00

Sales ticket 16: DW1 processes new mail on its own, in the worker's
`sales_inbox` lane. Whose authority it carries was decided on 2026-10-12
(the ticket's Comments, shape (a)): a service account per tenant, the spec's
"DW1 (tài khoản dịch vụ)", which the platform resolves like any member, so
`effective_scopes` stays the one answer to who may act.

The account is a platform user with a membership; this revision adds the role
that membership holds:

- **`sales_dw1`**, "DW1 (tài khoản dịch vụ)": `sales.inbox.process` and
  nothing else. DW1 never prepares, cross-checks, prices or approves (spec,
  actor table), and it decides no approval, so it carries no
  `approvals.decide` either. `test_sales_roles.py` holds the role to exactly
  this.

The role is a catalogue row like the other Sales roles (`68305ebe4a83`); no
platform role gains a `sales.*` scope. It breaks no separation-of-duty rule
(`platform.members.write` is not on it), so no membership needs checking.
Who holds it is seed data (`dw_sales.testing.seed_personas`) on the demo
tenant; a production tenant's account is provisioned like any member.
"""

from __future__ import annotations

from alembic import op

revision = "af154486381e"
down_revision = "33f444c15062"
branch_labels = None
depends_on = None

_ROLE = "sales_dw1"
_NAME = "DW1 (tài khoản dịch vụ)"
_SCOPES = '["sales.inbox.process"]'


def upgrade() -> None:
    op.execute(
        "INSERT INTO platform.roles (key, name, scopes)"
        f" VALUES ('{_ROLE}', '{_NAME}', '{_SCOPES}'::jsonb)"
    )


def downgrade() -> None:
    # Runs as the migrator, which bypasses RLS: every tenant's memberships. A
    # key left behind would name a role the catalogue no longer has.
    op.execute(
        f"UPDATE platform.memberships SET role_keys = role_keys - '{_ROLE}'"
        f" WHERE role_keys ? '{_ROLE}'"
    )
    op.execute(f"DELETE FROM platform.roles WHERE key = '{_ROLE}'")
