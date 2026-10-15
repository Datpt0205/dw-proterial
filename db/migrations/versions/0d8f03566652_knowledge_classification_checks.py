"""knowledge classification checks

Revision ID: 0d8f03566652
Revises: d82a60870baf
Create Date: 2026-10-15 03:55:00.000000+00:00

`classification` on `knowledge.documents`, `knowledge.ingest_jobs` (both
0001) and `knowledge.evidence` (0007) accepted any text. It is what retrieval's
clearance filter matches and what memory ranks to label a fact built on a
document, so a `public` document is one no clearance retrieves, and a memory
built on it could only be labelled by a guess (`classification_rank` refuses
it; memory-write-trust/01 measured that such a label could be written).
a4104b95722b gave the memory columns this CHECK and left these out of scope.

The set is the clearance ladder, `dw_knowledge.contracts.CLASSIFICATIONS`
(read off `_CLEARANCE_ALLOWS`), written out here because a migration is
history and must not change when the code does. What keeps the copy honest is
`test_the_classification_checks_hold_the_clearance_ladder`, which reads these
constraints back from `pg_constraint` and compares them with the ladder.

Added validated, not `NOT VALID`, like a4104b95722b: a row already off the
ladder should stop the migration and be looked at, not be grandfathered in.
"""

from __future__ import annotations

from alembic import op

revision = "0d8f03566652"
down_revision = "d82a60870baf"
branch_labels = None
depends_on = None

_CLASSIFICATIONS = ("internal", "confidential", "restricted")

# Names follow NAMING_CONVENTION: ck_<table>_<column>.
_TABLES = ("documents", "ingest_jobs", "evidence")


def upgrade() -> None:
    values = ", ".join(f"'{value}'" for value in _CLASSIFICATIONS)
    for table in _TABLES:
        op.execute(
            f"ALTER TABLE knowledge.{table} ADD CONSTRAINT ck_{table}_classification"
            f" CHECK (classification IN ({values}))"
        )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.execute(f"ALTER TABLE knowledge.{table} DROP CONSTRAINT ck_{table}_classification")
