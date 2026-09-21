"""Real partition management for the two time-series tables.

The whole of the reasoning is in `db/migrations/sql/0012_partition_maintenance.sql`
— it is long because three separate things were wrong, and each of them is the
kind that reads as fine in a diff.

Reversible in the sense that matters: the functions and the grant repair come
off cleanly. The relocation does not, and should not — the rows are in the
correct partitions now, and moving them back into a default partition would be
restoring the state the whole migration exists to end. `downgrade` therefore
leaves the data where it is and says so, rather than silently pretending.
"""

from __future__ import annotations

import re
from pathlib import Path

from alembic import op

revision = "06d9e1a67d40"
down_revision = "15276c3c92fa"
branch_labels = None
depends_on = None

_SQL_FILE = Path(__file__).resolve().parents[1] / "sql" / "0012_partition_maintenance.sql"

# Matches any dollar-quote tag, not just `$$`. The splitters in 0001 and 0002
# track `$$` alone, which is right for the files they read and would cut this
# one in half — the function bodies here are tagged so a `$$` inside one could
# never end it by accident. Those two migrations have already run; a new
# splitter beside them is safer than editing applied history.
_TAG = re.compile(r"\$[A-Za-z_]*\$")


def _statements(text: str) -> list[str]:
    """One command per string: asyncpg prepares what it is given, and a prepared
    statement may hold exactly one command."""
    out: list[str] = []
    buf: list[str] = []
    tag: str | None = None
    for line in text.split("\n"):
        if tag is None:
            found = _TAG.search(line)
            # Opened and closed on the same line is not an open body.
            if found and line.count(found.group(0)) == 1:
                tag = found.group(0)
        elif tag in line:
            tag = None
        buf.append(line)
        if tag is None and line.rstrip().endswith(";"):
            statement = "\n".join(buf).strip()
            if statement:
                out.append(statement)
            buf = []
    leftover = "\n".join(buf).strip()
    if leftover:  # pragma: no cover - a file ending mid-statement is a typo
        raise ValueError(f"unterminated statement: {leftover[:120]}")
    return out


_DOWNGRADE = (
    "DROP FUNCTION IF EXISTS platform.drop_expired_partitions(timestamptz, timestamptz)",
    "DROP FUNCTION IF EXISTS platform.ensure_time_partitions(integer)",
    "DROP FUNCTION IF EXISTS platform._ensure_one_partition(text, date)",
    # Puts the audit partition back to what the blanket grant gave it. Restoring
    # a hole is what a downgrade of this half means, and naming it is better
    # than a downgrade that quietly does not match its upgrade.
    "DO $$ BEGIN"
    " IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN"
    " GRANT UPDATE, DELETE ON platform.audit_events_default TO dw_app;"
    " END IF; END $$",
)


def upgrade() -> None:
    for statement in _statements(_SQL_FILE.read_text(encoding="utf-8")):
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
