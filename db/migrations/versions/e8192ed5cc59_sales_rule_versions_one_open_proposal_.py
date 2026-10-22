"""sales rule versions one open proposal per key

Revision ID: e8192ed5cc59
Revises: 59cf23d3a859
Create Date: 2026-10-22 10:23:21.369787+00:00

Đạt's decision of 2026-10-22 (the DW1 process page, slice 1): a key holds at
most one proposal waiting on its `sales.rules` approval.

A version is the whole document, never a patch, and approving one supersedes
whatever is in force (`RuleSettlement.settle`). Two proposals started from the
same version (one changing the price tolerance, another export control, both
in `sales_order_rules`) would each look right to the head, and approving the
second would silently undo the first. So a second proposal on a key that
already has one waiting is refused until the head approves or rejects the
first; either decision moves it out of `proposed` and frees the key.

- **`uq_rule_versions_one_proposed`** (partial, unique): `(tenant_id, key)
  WHERE status = 'proposed'`, the shape `uq_rule_versions_one_approved`
  already has. Narrowed by tenant alone, like the table (`57a241ea182b`): a
  version applies to the whole tenant whichever workspace proposed it, so two
  workspaces' proposals on one key collide the same way. Named like its
  sibling rather than by `NAMING_CONVENTION`'s `uq` form, which would give
  both partial indexes the one name `uq_rule_versions_tenant_id_key`.
- **The refusal** is translated by this name into a 409 naming the waiting
  version, who proposed it and when (`dw_sales.application.rules`,
  `ONE_OPEN_PROPOSAL`).

What it prevents is two proposals waiting side by side. It does not refuse a
proposal started from a version superseded since (a proposal records no base
version); the head reads every proposal's diff against the version in force.

Existing data, checked before the index is built, nothing decided on the
head's behalf:

- A proposal waiting on no approval (made before ticket 38, which added
  `ck_rule_versions_proposed_has_approval` NOT VALID) can be decided by nobody,
  and with this index would hold its key for good. The upgrade stops, naming
  each tenant and key; someone decides with that tenant what becomes of it.
  `218118b8f0e5` records that no deployment holds one.
- A tenant already holding two waiting proposals on one key fails the index,
  the database naming the tenant and the key. The head rejects one on
  `/approvals`, with the API and worker still on the previous revision, and
  the upgrade is run again.

Grants unchanged: an index takes none. Downgrade drops the index.
"""

from __future__ import annotations

from alembic import op

revision = "e8192ed5cc59"
down_revision = "59cf23d3a859"
branch_labels = None
depends_on = None

_INDEX = "uq_rule_versions_one_proposed"


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE
            stranded text;
        BEGIN
            SELECT string_agg(DISTINCT tenant_id::text || ' ' || key, ', ')
              INTO stranded
              FROM sales.rule_versions
             WHERE status = 'proposed' AND approval_id IS NULL;
            IF stranded IS NOT NULL THEN
                RAISE EXCEPTION 'proposals on no approval would hold their key: %',
                    stranded;
            END IF;
        END $$
        """
    )
    op.execute(
        f"CREATE UNIQUE INDEX {_INDEX} ON sales.rule_versions"
        " (tenant_id, key) WHERE status = 'proposed'"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX sales.{_INDEX}")
