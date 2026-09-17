"""HTTP idempotency keys: replay cache for mutating requests.

Revision ID: 894989786cc8
Revises: 5465c38d8b45
Create Date: 2026-09-17

``Idempotency-Key`` was advertised — it is in the API's CORS allow-list — and
enforced nowhere, so a client that retried a timed-out POST created a second
record and had no way to avoid it. This adds the storage behind the header:
``platform.idempotency_keys``, one row per (tenant, key), holding the
fingerprint of the request the key was spent on and the response it produced.

The DDL lives beside this file as ``sql/0002_http_idempotency.sql``, for the
same reason the baseline's does: it is reviewed, diffed and syntax-checked as
SQL, which is what it is.
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "894989786cc8"
down_revision = "5465c38d8b45"
branch_labels = None
depends_on = None

_SQL_FILE = Path(__file__).resolve().parents[1] / "sql" / "0002_http_idempotency.sql"


def _has_command(chunk: str) -> bool:
    """Whether the chunk contains SQL, rather than only comments and blanks."""
    return any(
        line.strip() and not line.lstrip().startswith("--") for line in chunk.split("\n")
    )


def _statements(text: str) -> list[str]:
    """Split the file into single statements.

    asyncpg prepares every statement it is given and a prepared statement may
    contain exactly one command, so the file cannot be handed over whole. The
    split ends a statement at a *line* that ends in a semicolon, like the
    baseline's — a semicolon in the middle of a line of prose does not end
    anything, and this file's comments carry plenty of prose. Unlike the
    baseline this file declares no function bodies, so there is no ``$$`` to
    track.

    The trailing chunk — the comment explaining why no GRANT is written here —
    is dropped: zero commands is as unpreparable as two.
    """
    statements: list[str] = []
    buffer: list[str] = []
    for line in text.split("\n"):
        buffer.append(line)
        if line.rstrip().endswith(";"):
            statements.append("\n".join(buffer).strip())
            buffer = []
    statements.append("\n".join(buffer).strip())
    return [statement for statement in statements if _has_command(statement)]


def upgrade() -> None:
    bind = op.get_bind()
    for statement in _statements(_SQL_FILE.read_text(encoding="utf-8")):
        bind.exec_driver_sql(statement)


def downgrade() -> None:
    # The policy and the index belong to the table and are dropped with it.
    op.execute("DROP TABLE IF EXISTS platform.idempotency_keys")
