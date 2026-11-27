"""sales followup heads stand in for the export control pic

Revision ID: d217eda10ac8
Revises: fa17832cd08d
Create Date: 2026-11-26 19:03:52.114649+00:00

Sales ticket 78's review. While nobody holds both scopes that acknowledge an
NOC/ESF hold, the follow-ups lane tells the heads that nobody may. That
notice was recorded under the hold's own key, so once someone was granted
both, the revision read as told and the new export-control PIC never heard
of it. It is now recorded under its own stage:
**`ck_followup_deliveries_stage`** (`sales.followup_deliveries`) admits
`stand_in` (`followups.STAND_IN_STAGE`; `test_sales_schema.py` holds the
list equal to `Stage` plus the brief's and this one).

The CHECK is rebuilt from the values it holds when this runs, plus this
revision's own (as `fa17832cd08d` does), so a revision made beside this one
keeps its values whichever runs first. Downgrade deletes the records the old
check cannot hold: the heads' stand-in notices, which the lane then owes
again as the hold's own (the inbox keeps the heads' copy once per recipient).
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op

revision = "d217eda10ac8"
down_revision = "fa17832cd08d"
branch_labels = None
depends_on = None

_TABLE = "sales.followup_deliveries"
_CHECK = "ck_followup_deliveries_stage"
_NEW = ("stand_in",)


def _held() -> list[str]:
    """The values the CHECK's list admits, in its order."""
    definition = str(
        op.get_bind().scalar(
            sa.text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
                " WHERE conname = :check AND conrelid = CAST(:table AS regclass)"
            ),
            {"check": _CHECK, "table": _TABLE},
        )
    )
    return re.findall(r"'([a-z_]+)'::text", definition)


def _set(values: list[str]) -> None:
    listed = ", ".join(f"'{value}'" for value in values)
    op.execute(
        f"ALTER TABLE {_TABLE} DROP CONSTRAINT {_CHECK},"
        f" ADD CONSTRAINT {_CHECK} CHECK (stage IN ({listed}))"
    )


def upgrade() -> None:
    held = _held()
    _set([*held, *(v for v in _NEW if v not in held)])


def downgrade() -> None:
    listed = ", ".join(f"'{value}'" for value in _NEW)
    op.execute(f"DELETE FROM {_TABLE} WHERE stage IN ({listed})")
    _set([v for v in _held() if v not in _NEW])
