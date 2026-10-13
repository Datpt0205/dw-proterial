"""sales head grants support access

Revision ID: 7c8ba908575f
Revises: af154486381e
Create Date: 2026-10-12 12:37:15.929038+00:00

Sales ticket 22 (G20). The platform's customer-granted support access
(ADR 0024, `af8ee878b4ab`) gives `support.grant` to no platform role: "a
context gives it to the role that owns the data". In Sales that is the head
(dw_sales ADR 0003 §5): `sales_head` gains `support.grant`, and no other
role or permission set does.

What the head may grant is the one set Sales registers at the composition
root, `sales.case_support` = `{sales.overview.read, sales.case.read}`: never
a price, never a write. The platform checks that a granter holds every scope
of the set; the head does, and a grant stays in force only while the head
still holds `support.grant` and both scopes (`grant_effective_state`).

`support.grant` also lets the head see, approve, reject and revoke the
workspace's support requests (an `org_admin` files them with
`support.request`). It is not a `sales.*` scope, so the separation-of-duty
rule on `sales.price.read` and `platform.members.write` is untouched, and no
membership needs checking.
"""

from __future__ import annotations

from alembic import op

revision = "7c8ba908575f"
down_revision = "af154486381e"
branch_labels = None
depends_on = None

_SCOPE = "support.grant"
_ROLE = "sales_head"


def upgrade() -> None:
    op.execute(
        f"UPDATE platform.roles SET scopes = scopes || '[\"{_SCOPE}\"]'::jsonb"
        f" WHERE key = '{_ROLE}' AND NOT scopes ? '{_SCOPE}'"
    )


def downgrade() -> None:
    op.execute(f"UPDATE platform.roles SET scopes = scopes - '{_SCOPE}' WHERE key = '{_ROLE}'")
