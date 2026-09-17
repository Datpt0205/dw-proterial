"""A run records every artifact version it ran under — in the database.

Revision ID: bb430ecd4f84
Revises: e597bd453625
Create Date: 2026-09-17

`configs/workers/README.md` claims "a run records every one of those versions,
so a result can be traced back to the exact artifacts that produced it". That
was true of the OpenTelemetry span and false of `platform.worker_runs`, which
carried `worker_version` and `graph_version` and none of the other four.

A trace is not a record. It is sampled, it expires on the vendor's retention
schedule, and it is not queryable next to the row whose provenance is in
question — so "which prompt bundle scored this lead differently last week"
could not be answered from the system of record at all. The versions are the
answer to that question and they belong on the row.

`release_manifest_ref` does not close this. It is a text reference to a
manifest with no table behind it and no foreign key, so resolving it means
finding the artefact for a release that may no longer be deployed.

Nullable, because a run started before this migration genuinely has no record
of these, and inventing one would be worse than admitting it — the same
reasoning `actor_visible_owners` carries. Every run started after this carries
all four.
"""

from __future__ import annotations

from alembic import op

revision = "bb430ecd4f84"
down_revision = "e597bd453625"
branch_labels = None
depends_on = None

# Deliberately the artifact versions a worker PINS, not everything a run
# touched. A model profile is chosen per call and already lands on each row of
# `model_usage_ledger`; these four are fixed for the whole run by the worker
# definition, which is exactly what makes them a property of the run.
_COLUMNS = (
    "prompt_bundle_version",
    "toolset_version",
    "policy_version",
    "memory_policy_version",
)


def upgrade() -> None:
    for column in _COLUMNS:
        op.execute(f"ALTER TABLE platform.worker_runs ADD COLUMN {column} varchar(16)")


def downgrade() -> None:
    for column in _COLUMNS:
        op.execute(f"ALTER TABLE platform.worker_runs DROP COLUMN {column}")
