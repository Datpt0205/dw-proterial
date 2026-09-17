"""Platform baseline: schemas, tables, constraints, indexes, RLS, partitions.

Revision ID: 5465c38d8b45
Revises:
Create Date: 2026-09-17

One migration rather than a chain, because a baseline is not history: it is the
starting shape of the database, and a new project has no interest in the order
somebody else's product arrived at it. Every later change is an ordinary
incremental revision on top of this one.

The DDL lives beside this file as ``sql/0001_platform_baseline.sql`` instead of
inside a thousand-line Python string. It is reviewed, diffed and syntax-checked
as SQL, which is what it is. Like every applied migration it is immutable: a
correction is a new revision, never an edit here.

What the baseline creates
-------------------------
Three schemas. ``platform`` holds tenancy, identity, authorization, approvals,
the agent runtime's run/checkpoint/tool tables, the transactional outbox and the
audit log; ``knowledge`` holds documents, chunks and ingest jobs; ``memory``
holds memory items and write candidates.

Row-level security is enabled and FORCEd on every tenant-scoped table, with the
tenant read from ``app.tenant_id``, set per transaction from a verified access
context. The application role must not hold BYPASSRLS — only the migrator does.

Two tables are range-partitioned: ``platform.audit_events`` by ``occurred_at``
and ``platform.model_usage_ledger`` by ``created_at``. Both are append-only and
grow without bound, and retention on a partitioned table is DROP PARTITION —
instant, and it leaves nothing to vacuum. Each has a DEFAULT partition so a row
outside every declared range is stored rather than rejected; a deployment rolls
real monthly partitions ahead of time.
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "5465c38d8b45"
down_revision = None
branch_labels = None
depends_on = None

_SQL_DIR = Path(__file__).resolve().parents[1] / "sql"
# Order matters: privileges are granted on objects that must already exist.
_SQL_FILES = ("0001_platform_baseline.sql", "0001_platform_grants.sql")

# Dropping the schemas drops everything in them, including the two functions and
# every policy. Listed explicitly rather than looped so a schema added later has
# to be added here too, deliberately.
_SCHEMAS = ("memory", "knowledge", "platform")


def _statements(text: str) -> list[str]:
    """Split the file into single statements.

    asyncpg prepares every statement it is given, and a prepared statement may
    contain exactly one command — so the file cannot be handed over whole. The
    split tracks ``$$`` so the semicolons inside a function body do not end a
    statement.
    """
    out: list[str] = []
    buf: list[str] = []
    in_body = False
    for line in text.split("\n"):
        if line.count("$$") % 2 == 1:
            in_body = not in_body
        buf.append(line)
        if not in_body and line.rstrip().endswith(";"):
            statement = "\n".join(buf).strip()
            if statement:
                out.append(statement)
            buf = []
    tail = "\n".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def upgrade() -> None:
    bind = op.get_bind()
    for name in _SQL_FILES:
        for statement in _statements((_SQL_DIR / name).read_text(encoding="utf-8")):
            bind.exec_driver_sql(statement)


def downgrade() -> None:
    for schema in _SCHEMAS:
        op.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
