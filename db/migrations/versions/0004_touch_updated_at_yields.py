"""`updated_at` stops overwriting a value a writer set on purpose.

Revision ID: e597bd453625
Revises: 397e15693ea0
Create Date: 2026-09-17

The baseline added `platform.touch_updated_at()` so that `updated_at` could not
be left stale by a writer who forgot it. It was written as an unconditional
`NEW.updated_at := now()`, which also silently discards a value a writer chose
deliberately — and the two cases are not the same thing at all.

What that costs is not hypothetical. `_reap_stale_thread` decides a run's
process is gone by how old `updated_at` is, and the only way to exercise it is
to put a row's timestamp in the past. Under the unconditional trigger no
statement can do that, from any role: the reaper became untestable, and
`test_a_thread_stranded_by_a_hard_kill_is_freed_by_the_next_turn` — which
covers a bug that once locked a conversation permanently — went red. The same
limit applies to a data repair and to a backfill that has to preserve the
original times.

So the rule becomes what it was always meant to be: an UPDATE that does not
mention `updated_at` gets `now()`; an UPDATE that states a value keeps it. The
guarantee against forgetting is untouched, because forgetting is exactly the
case where old and new are not distinct.

`IS NOT DISTINCT FROM` rather than `<>`: the column is NOT NULL on all three
tables today, but a plain comparison against a NULL would be NULL, the branch
would not fire, and the row would keep a NULL nobody intended — a trap left for
whoever adds the fourth table.
"""

from __future__ import annotations

from alembic import op

revision = "e597bd453625"
down_revision = "397e15693ea0"
branch_labels = None
depends_on = None

# The triggers themselves are unchanged; only the function they call is
# replaced, so all three tables pick this up with no DDL on the tables.
_YIELDING = """
CREATE OR REPLACE FUNCTION platform.touch_updated_at() RETURNS trigger
    LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.updated_at IS NOT DISTINCT FROM OLD.updated_at THEN
        NEW.updated_at := now();
    END IF;
    RETURN NEW;
END;
$$
"""

_UNCONDITIONAL = """
CREATE OR REPLACE FUNCTION platform.touch_updated_at() RETURNS trigger
    LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$
"""


def upgrade() -> None:
    op.execute(_YIELDING)


def downgrade() -> None:
    op.execute(_UNCONDITIONAL)
