"""sales assistant turns give a case

Revision ID: 1bf300e276b7
Revises: 19a366484422
Create Date: 2026-11-26

Sales ticket 79: in a case's conversation the head names a colleague; DW1
finds exactly one of the people the case may be given to, says it back, and
gives the case ("Giao lại") only when the head confirms that statement.

- **`ck_assistant_turns_kind`** (`sales.assistant_turns`) admits
  `assign_case`, the kind `QuestionKind` gained; `test_assistant.py` holds the
  CHECK to it.
- **`ck_assistant_turns_proposal`** admits a proposal on an `assign_case`
  turn too (a `ProposedAssignment`, which names its `action`), still an
  object and still on the stating kinds only.

No grant or column changes. Each CHECK is rebuilt from what it holds, as
`b5c316f405cd` does. Downgrade deletes the `assign_case` turns, which the old
checks cannot hold.
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op

revision = "1bf300e276b7"
down_revision = "19a366484422"
branch_labels = None
depends_on = None

_TABLE = "sales.assistant_turns"
_KIND = "ck_assistant_turns_kind"
_PROPOSAL = "ck_assistant_turns_proposal"
_NEW = ("assign_case",)
_STATING = ("decide_finding", "propose_bravo_write")


def _held() -> list[str]:
    definition = op.get_bind().scalar(
        sa.text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
            " WHERE conname = :check AND conrelid = CAST(:table AS regclass)"
        ),
        {"check": _KIND, "table": _TABLE},
    )
    return re.findall(r"'([a-z_]+)'::text", str(definition))


def _set_kinds(values: list[str]) -> None:
    listed = ", ".join(f"'{value}'" for value in values)
    op.execute(
        f"ALTER TABLE {_TABLE} DROP CONSTRAINT {_KIND},"
        f" ADD CONSTRAINT {_KIND} CHECK (kind IN ({listed}))"
    )


def _set_proposal(kinds: tuple[str, ...]) -> None:
    listed = ", ".join(f"'{kind}'" for kind in kinds)
    op.execute(
        f"ALTER TABLE {_TABLE} DROP CONSTRAINT {_PROPOSAL},"
        f" ADD CONSTRAINT {_PROPOSAL} CHECK ("
        " proposal IS NULL"
        f" OR (kind IN ({listed}) AND jsonb_typeof(proposal) = 'object'))"
    )


def upgrade() -> None:
    held = _held()
    _set_kinds([*held, *(v for v in _NEW if v not in held)])
    _set_proposal((*_STATING, *_NEW))


def downgrade() -> None:
    listed = ", ".join(f"'{value}'" for value in _NEW)
    op.execute(f"DELETE FROM {_TABLE} WHERE kind IN ({listed})")
    _set_proposal(_STATING)
    _set_kinds([v for v in _held() if v not in _NEW])
