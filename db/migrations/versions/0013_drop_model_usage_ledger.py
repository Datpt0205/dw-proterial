"""Remove `platform.model_usage_ledger` and everything that read it.

Đạt asked for the whole feature gone, having been told what it costs. What it
cost: the per-tenant daily spend cap (`RunAllowancePort.spend_usd_per_day` and
`RunStore.spend_since`) and the admin cost dashboard. Nothing now bounds what a
tenant's runs cost in a day — `runs_per_day` still bounds how MANY, and the
per-run ceiling from Mốc 1a still bounds one loop, but a day of expensive runs
has no ceiling. That is the deliberate trade, recorded here because a migration
is the one place a future reader will look for why a table went.

The table was misdescribed in the retention policy as "evidence for invoices".
It was not: nothing in this repo invoices anybody, `platform.plans` carries
quotas and no prices, and `cost_usd` came from `route_cost(...)` — what FDX pays
the provider, attributed per tenant. Its only readers were the two above.

Cost still reaches telemetry, which is where one call is inspected.

DROP TABLE takes the partitions with it, the DEFAULT one included. It also takes
the rows: this is not a soft delete and there is no grace period, because the
decision is to stop holding the data at all rather than to hold it for a term.

`downgrade` recreates the table, its partitioning, RLS and grants — but not the
rows, which are gone. It exists so a deployment can roll back the schema without
the application failing on a missing relation; the reporting it fed would come
back empty and fill again from that point.
"""

from __future__ import annotations

import re
from pathlib import Path

from alembic import op

revision = "aefe7c1f5d9b"
down_revision = "06d9e1a67d40"
branch_labels = None
depends_on = None

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


_SQL_DIR = Path(__file__).resolve().parents[1] / "sql"

_PREDICATE = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"

_DOWNGRADE = (
    """
    CREATE TABLE platform.model_usage_ledger (
        id uuid NOT NULL,
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        run_id uuid,
        worker_id character varying(128),
        task character varying(128),
        prompt_id character varying(128),
        prompt_version character varying(32),
        provider character varying(64),
        model character varying(128),
        input_tokens bigint,
        output_tokens bigint,
        cost_usd numeric(12, 6),
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        CONSTRAINT pk_model_usage_ledger PRIMARY KEY (id, created_at),
        CONSTRAINT ck_model_usage_ledger_cost
            CHECK ((cost_usd IS NULL) OR (cost_usd >= (0)::numeric)),
        CONSTRAINT ck_model_usage_ledger_tokens
            CHECK ((input_tokens IS NULL) OR (input_tokens >= 0)),
        CONSTRAINT ck_model_usage_ledger_output_tokens
            CHECK ((output_tokens IS NULL) OR (output_tokens >= 0))
    ) PARTITION BY RANGE (created_at)
    """,
    "CREATE TABLE platform.model_usage_ledger_default"
    " PARTITION OF platform.model_usage_ledger DEFAULT",
    "CREATE INDEX ix_model_usage_ledger_created_brin"
    " ON ONLY platform.model_usage_ledger USING brin (created_at)",
    "ALTER TABLE platform.model_usage_ledger ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE platform.model_usage_ledger FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_model_usage_ledger ON platform.model_usage_ledger"
    f" USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})",
    # The partition needs its own, exactly as migration 0009 established: a
    # partition addressed by name uses its own settings.
    "ALTER TABLE platform.model_usage_ledger_default ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE platform.model_usage_ledger_default FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_model_usage_ledger_default"
    f" ON platform.model_usage_ledger_default"
    f" USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})",
)


def upgrade() -> None:
    # CASCADE is not needed and not used: nothing references this table, and a
    # CASCADE here would silently take anything that did.
    op.execute("DROP TABLE IF EXISTS platform.model_usage_ledger")
    # `platform.usage.read` opened the dashboard that is gone. A scope that
    # grants access to nothing is worse than no scope: it reads, in a review of
    # who can see what, as a capability somebody has.
    op.execute(
        "UPDATE platform.roles SET scopes = scopes - 'platform.usage.read'"
        " WHERE key = 'org_admin'"
    )
    # The maintenance functions name their parents in an array. Left alone,
    # `ensure_time_partitions` would try to create a partition OF the table just
    # dropped, hourly, for ever.
    for statement in _statements((_SQL_DIR / "0013_partition_maintenance.sql").read_text("utf-8")):
        op.execute(statement)


def downgrade() -> None:
    op.execute(
        "UPDATE platform.roles"
        " SET scopes = scopes || '[\"platform.usage.read\"]'::jsonb"
        " WHERE key = 'org_admin' AND NOT scopes ? 'platform.usage.read'"
    )
    for statement in _DOWNGRADE:
        op.execute(statement)
    # Back to the two-table form, including the two-argument signature. The
    # one-argument version has to go explicitly or Postgres keeps both as
    # overloads and the caller picks by arity.
    op.execute("DROP FUNCTION IF EXISTS platform.drop_expired_partitions(timestamptz)")
    for statement in _statements((_SQL_DIR / "0012_partition_maintenance.sql").read_text("utf-8")):
        op.execute(statement)
