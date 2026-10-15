"""platform worker runs record their model profile

Revision ID: 271bdb87af91
Revises: 0d8f03566652
Create Date: 2026-10-15 04:05:00.000000+00:00

A run recorded every artifact version its worker pins (0005) except one: the
model profile its agent loop runs on, `WorkerDefinition.default_model_profile`.
The runner already prices the loop with it and puts it on the span
(`dw.model_profile`), but a span is sampled and expires, so "which profile did
this run use" had no answer in the system of record
(platform-runtime Open: "no run records which profile it used").

0005 left the profile out because a profile is chosen per call and each call
already lands on `model_usage_ledger` with its own. That stays true of the
calls a graph makes through the structured gateway; this column is the
profile the WORKER pins for the run, fixed by its definition like the four
versions beside it, and is what a run with no model call at all still has.

Nullable, as in 0005: a run started before this has no record of it, and
inventing one would be worse than admitting it. A CHECK refuses a blank one,
since `WorkerDefinition` refuses a blank profile and a blank on the row would
read as recorded when it is not.
"""

from __future__ import annotations

from alembic import op

revision = "271bdb87af91"
down_revision = "0d8f03566652"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE platform.worker_runs ADD COLUMN model_profile text"
        " CONSTRAINT ck_worker_runs_model_profile CHECK (btrim(model_profile) <> '')"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE platform.worker_runs DROP COLUMN model_profile")
