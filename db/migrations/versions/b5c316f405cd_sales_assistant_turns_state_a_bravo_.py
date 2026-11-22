"""sales assistant turns state a bravo write

Revision ID: b5c316f405cd
Revises: ffd0c95da906
Create Date: 2026-11-22 02:40:51.235029+00:00

Sales ticket 56 over ticket 53: in an order's conversation the PIC asks for
one SO line's confirmed date or quantity to be written into Bravo; DW1 says
it back word for word and proposes it for approval only when the PIC
confirms that statement.

- **`ck_assistant_turns_kind`** (`sales.assistant_turns`) admits
  `propose_bravo_write`, the kind `QuestionKind` gained; `test_sales_schema.py`
  holds the CHECK to it.
- **`ck_assistant_turns_proposal`** admits a proposal on a
  `propose_bravo_write` turn too (a `ProposedBravoWrite`, which names its
  `action`), still an object and still on those two kinds only.

No grant or column changes. Each CHECK is rebuilt from what it holds, as
`3187714cd75c` does. Downgrade deletes the `propose_bravo_write` turns, which
the old checks cannot hold.
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op

revision = "b5c316f405cd"
down_revision = "ffd0c95da906"
branch_labels = None
depends_on = None

_TABLE = "sales.assistant_turns"
_KIND = "ck_assistant_turns_kind"
_PROPOSAL = "ck_assistant_turns_proposal"
_NEW = ("propose_bravo_write",)


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
    _set_proposal(("decide_finding", *_NEW))


def downgrade() -> None:
    listed = ", ".join(f"'{value}'" for value in _NEW)
    op.execute(f"DELETE FROM {_TABLE} WHERE kind IN ({listed})")
    _set_proposal(("decide_finding",))
    _set_kinds([v for v in _held() if v not in _NEW])
