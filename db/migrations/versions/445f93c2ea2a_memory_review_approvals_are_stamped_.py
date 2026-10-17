"""memory review approvals are stamped with memory.review

Revision ID: 445f93c2ea2a
Revises: 271bdb87af91
Create Date: 2026-10-17 17:08:56.181070+00:00

The platform decides an approval on `approvals.decide` AND its stamp
(`required_scope`, `docs/adr/0011`). An unstamped request is therefore decided
by anyone holding `approvals.decide` in the workspace, and since
`ac31ff0f2087` that includes the Sales roles `sales_pic`, `sales_head` and the
permission set `sales_quote_approver`. `memory.review`, which the memory
service opens for a held candidate, was the one unstamped type in production:
a Sales PIC could vouch for a fact the platform will repeat as memory.

Decided 2026-10-18 (Đạt): the platform stamps its own approval types. This
revision is the data side of it:

- **A new platform scope, `memory.review`,** for the roles that decided memory
  reviews before and are the platform's deciders: `approver`, `manager`,
  `director`, and the permission set `approver_boost` (authority to approve
  without being a manager). No context role gains it; the Sales roles keep
  `approvals.decide` for their own stamped types and lose memory reviews.
  `platform_admin` holds no stamp by rule (`holds_stamped_scope`), so it does
  not decide one either, as with every stamped type.
- **Rows already written are stamped**, whatever their status: a decided
  request's stamp also decides who may read it (ADR 0011 amendment
  2026-10-07). As the migrator, which bypasses RLS and holds the UPDATE
  `dw_app` does not (the stamp is written once).
- **The database refuses the type unstamped or stamped otherwise**
  (`ck_approval_requests_memory_review_stamped`), as
  `ck_approval_requests_sales_stamped` does for `sales.`; `coalesce` because a
  CHECK that evaluates to NULL passes (`d9e73228e7d7`). Added validated, after
  the backfill, so a row the backfill missed stops the upgrade.
- **Separation of duties:** widening a role or permission set fires
  `ck_roles_sod_memberships` (`f381f1694395`), which refuses the upgrade while
  any membership holding it would break a rule its tenant has not waived. No
  rule names the new scope today.

Downgrade drops the constraint, unstamps the rows and takes the scope back:
the code before this revision reads a decided review with no scopes and would
not find a stamped one.
"""

from __future__ import annotations

from alembic import op

revision = "445f93c2ea2a"
down_revision = "271bdb87af91"
branch_labels = None
depends_on = None

_TABLE = "platform.approval_requests"
_NAME = "ck_approval_requests_memory_review_stamped"
_TYPE = "memory.review"
_SCOPE = "memory.review"
_ROLES = ("approver", "manager", "director")
_PERMISSION_SETS = ("approver_boost",)


def _keys(keys: tuple[str, ...]) -> str:
    return ", ".join(f"'{key}'" for key in keys)


def upgrade() -> None:
    op.execute(
        f"UPDATE platform.roles SET scopes = scopes || '[\"{_SCOPE}\"]'::jsonb"
        f" WHERE key IN ({_keys(_ROLES)}) AND NOT scopes ? '{_SCOPE}'"
    )
    op.execute(
        f"UPDATE platform.permission_sets SET scopes = scopes || '[\"{_SCOPE}\"]'::jsonb"
        f" WHERE key IN ({_keys(_PERMISSION_SETS)}) AND NOT scopes ? '{_SCOPE}'"
    )
    op.execute(
        f"UPDATE {_TABLE} SET required_scope = '{_SCOPE}'"
        f" WHERE approval_type = '{_TYPE}' AND required_scope IS DISTINCT FROM '{_SCOPE}'"
    )
    op.execute(
        f"ALTER TABLE {_TABLE} ADD CONSTRAINT {_NAME} CHECK ("
        f"approval_type <> '{_TYPE}' OR coalesce(required_scope, '') = '{_SCOPE}')"
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE {_TABLE} DROP CONSTRAINT IF EXISTS {_NAME}")
    op.execute(
        f"UPDATE {_TABLE} SET required_scope = NULL"
        f" WHERE approval_type = '{_TYPE}' AND required_scope = '{_SCOPE}'"
    )
    op.execute(
        f"UPDATE platform.permission_sets SET scopes = scopes - '{_SCOPE}'"
        f" WHERE key IN ({_keys(_PERMISSION_SETS)})"
    )
    op.execute(
        f"UPDATE platform.roles SET scopes = scopes - '{_SCOPE}' WHERE key IN ({_keys(_ROLES)})"
    )
