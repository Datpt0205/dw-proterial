"""Autonomy becomes a decision the database records and constrains.

Revision ID: 5eda1d6108cc
Revises: bb430ecd4f84
Create Date: 2026-09-17

`WorkerDefinition.autonomy_level` was declared and read by nothing: approval was a
function of the tool alone, so a worker at A4 paused exactly as often as one at
A0. Making the level decide means it has to live somewhere a run can be traced
back to, in two places:

- `platform.tenants.max_autonomy_level` — the ceiling a tenant holds its workers
  under. It can only lower a worker, never lift it (the runtime takes the more
  restrictive of the two). The default `A4` is not a permission: it is the
  absence of an extra restriction, and every run is still capped by the level its
  worker was built for.

- `platform.worker_runs.autonomy_level` and `approval_policy_version` — the level
  a run actually ran at, and the policy that turned that level into decisions.
  Stamped at start and replayed on resume, never re-derived: a tenant who lowers
  its ceiling on Tuesday does not rewrite what Monday's run was allowed to do, and
  a later change to the policy is read against the version that made the call.
  Nullable because a run started before this has no such record, and inventing
  one would be worse than saying so.

CHECK constraints on both, which the tenant setting it is modelled on
(`record_visibility`) does not have — that one is validated only by the service
that writes it, so a direct UPDATE or a bug in a second writer puts a value in the
table that no code knows how to read. A level the runtime does not recognise is a
level nobody can say what it permits, so the database refuses it.
"""

from __future__ import annotations

from alembic import op

revision = "5eda1d6108cc"
down_revision = "bb430ecd4f84"
branch_labels = None
depends_on = None

# Mirrors `dw_kernel.autonomy.AUTONOMY_LEVELS`. Written out rather than imported:
# a migration is a record of what the schema WAS, and one that read today's list
# would silently change meaning if the list ever did.
_LEVELS = "('A0', 'A1', 'A2', 'A3', 'A4')"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE platform.tenants"
        " ADD COLUMN max_autonomy_level text NOT NULL DEFAULT 'A4'"
    )
    op.execute(
        "ALTER TABLE platform.tenants ADD CONSTRAINT ck_tenants_max_autonomy_level"
        f" CHECK (max_autonomy_level IN {_LEVELS})"
    )

    op.execute("ALTER TABLE platform.worker_runs ADD COLUMN autonomy_level text")
    op.execute(
        "ALTER TABLE platform.worker_runs ADD CONSTRAINT ck_worker_runs_autonomy_level"
        f" CHECK (autonomy_level IS NULL OR autonomy_level IN {_LEVELS})"
    )
    op.execute("ALTER TABLE platform.worker_runs ADD COLUMN approval_policy_version varchar(16)")


def downgrade() -> None:
    op.execute("ALTER TABLE platform.worker_runs DROP COLUMN approval_policy_version")
    op.execute(
        "ALTER TABLE platform.worker_runs DROP CONSTRAINT ck_worker_runs_autonomy_level"
    )
    op.execute("ALTER TABLE platform.worker_runs DROP COLUMN autonomy_level")
    op.execute("ALTER TABLE platform.tenants DROP CONSTRAINT ck_tenants_max_autonomy_level")
    op.execute("ALTER TABLE platform.tenants DROP COLUMN max_autonomy_level")
