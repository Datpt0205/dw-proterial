"""sales assistant turns state a flag decision

Revision ID: 3187714cd75c
Revises: e31ed3f062a1
Create Date: 2026-11-21 04:17:59.791256+00:00

Sales ticket 56: in a case's conversation the PIC states a decision on one of
the case's open flags; DW1 says it back word for word and records it only
when the PIC confirms that statement.

- **`ck_assistant_turns_kind`** (`sales.assistant_turns`) admits
  `decide_finding`, the kind `QuestionKind` gained; `test_sales_schema.py`
  holds the CHECK to it.
- **`proposal`** (jsonb, NULL): the `ProposedDecision` the turn stated, which
  `POST .../turns/{seq}/confirm` records when its hash matches.
  **`ck_assistant_turns_proposal`** holds it to an object, on a
  `decide_finding` turn only.

No grant changes: the column is on a table `dw_app` already inserts into and
reads. The CHECK is rebuilt from the values it holds, plus this revision's, as
`e31ed3f062a1` does. Downgrade deletes the `decide_finding` turns, which the
old check cannot hold.
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op

revision = "3187714cd75c"
down_revision = "e31ed3f062a1"
branch_labels = None
depends_on = None

_TABLE = "sales.assistant_turns"
_KIND = "ck_assistant_turns_kind"
_PROPOSAL = "ck_assistant_turns_proposal"
_NEW = ("decide_finding",)


def _held() -> list[str]:
    definition = op.get_bind().scalar(
        sa.text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
            " WHERE conname = :check AND conrelid = CAST(:table AS regclass)"
        ),
        {"check": _KIND, "table": _TABLE},
    )
    return re.findall(r"'([a-z_]+)'::text", str(definition))


def _set(values: list[str]) -> None:
    listed = ", ".join(f"'{value}'" for value in values)
    op.execute(
        f"ALTER TABLE {_TABLE} DROP CONSTRAINT {_KIND},"
        f" ADD CONSTRAINT {_KIND} CHECK (kind IN ({listed}))"
    )


def upgrade() -> None:
    held = _held()
    _set([*held, *(v for v in _NEW if v not in held)])
    op.execute(f"ALTER TABLE {_TABLE} ADD COLUMN proposal jsonb")
    op.execute(
        f"ALTER TABLE {_TABLE} ADD CONSTRAINT {_PROPOSAL} CHECK ("
        " proposal IS NULL"
        " OR (kind = 'decide_finding' AND jsonb_typeof(proposal) = 'object'))"
    )


def downgrade() -> None:
    listed = ", ".join(f"'{value}'" for value in _NEW)
    op.execute(f"DELETE FROM {_TABLE} WHERE kind IN ({listed})")
    op.execute(f"ALTER TABLE {_TABLE} DROP CONSTRAINT {_PROPOSAL}")
    op.execute(f"ALTER TABLE {_TABLE} DROP COLUMN proposal")
    _set([v for v in _held() if v not in _NEW])
