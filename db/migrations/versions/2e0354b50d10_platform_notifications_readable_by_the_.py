"""platform notifications readable by the offboarding lane

Revision ID: 2e0354b50d10
Revises: 546a6a81e58c
Create Date: 2026-10-15 03:28:08.029814+00:00

`platform.notifications` is read only by its recipient (855ae928c3fa): the
SELECT policy is `tenant AND recipient`, recipient being `app.user_id`. The
offboarding lane binds no user, so its export listed the table with 0 rows,
its purge deleted none (`dw_app` holds no DELETE there), and the purge of
`platform.workspaces` then CASCADEd every notification away unexported.
Measured on the test database 2026-10-03 (`workspace-scope-offboarding/01`
step 4): one notification, `[0]` rows exported, none left after the purge.

The lane already sets `app.workspace_scope = 'tenant'` per transaction to read
every workspace of the one tenant it works on. The SELECT policy reads that
scope in the shape `CLAUDE.md` gives it, beside a pure tenant clause:

    tenant AND (recipient OR current_setting('app.workspace_scope') = 'tenant')

so the lane reads every person's notifications of that tenant and of no other.
Only SELECT widens. The UPDATE policy stays `tenant AND recipient` on both
sides, and `dw_app`'s grants are unchanged (UPDATE of `read_at`, no DELETE):
with the scope set, the lane still cannot mark anyone's notification read.
"""

from __future__ import annotations

from alembic import op

revision = "2e0354b50d10"
down_revision = "546a6a81e58c"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_RECIPIENT = (
    "(recipient_user_id = (NULLIF(current_setting('app.user_id'::text, true), ''::text))::uuid)"
)
_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"

_POLICY = "tenant_isolation_notifications_select ON platform.notifications"


def upgrade() -> None:
    op.execute(f"ALTER POLICY {_POLICY} USING ({_TENANT} AND ({_RECIPIENT} OR {_SCOPE}))")


def downgrade() -> None:
    op.execute(f"ALTER POLICY {_POLICY} USING ({_TENANT} AND {_RECIPIENT})")
