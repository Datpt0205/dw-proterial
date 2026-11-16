"""sales salesorder worked pairs and customer skills

Revision ID: 711e8b760139
Revises: beba87138cda
Create Date: 2026-11-16 03:10:00.000000+00:00

Sales ticket 41 (dw_sales ADR 0013 as amended 2026-11-16 under ADR 0014): a
customer's SalesOrder is filled by a model with the customer's skill and
read-only tools, every cell traced by code.

- **`sales.salesorder_pairs`**: a customer's worked pairs, one row per pair:
  the PO as the normal reading read it (`document`, the `PoDocument`), the day
  it came in, and the rows of the SalesOrder file the PIC made from it
  (`expected`, cells by column letter), written by the worker when it reads an
  uploaded example (`salesorder_learning.SalesOrderLearning`). Price-bearing,
  as the files are. Narrowed by tenant AND workspace, in CLAUDE.md's one
  policy shape (the offboarding lane reads `app.workspace_scope`); ENABLEd
  and FORCEd. **Append-only**: `dw_app` holds SELECT and INSERT; UPDATE and
  DELETE are REVOKEd (failure-modes #7). `example_id` names the example the
  pair came from, `ON DELETE SET NULL`: an example never sent is pruned after
  30 days, and its pair stays. Every JSON value is bounded and typed by a
  CHECK; no value has a default but the row's own `created_at`.
- **`ck_rule_versions_key`** (`platform.rule_versions`) admits, beside every
  key it holds now, a customer's SalesOrder skill:
  `sales_skill_salesorder_<customer code in lower case>`
  (`dw_sales.application.skills.salesorder_key`), one per customer, so the
  CHECK holds a pattern for that family rather than one key per customer.
- **`ck_skill_replays_source`** admits `customer_pairs`: a customer's
  SalesOrder skill replayed on its worked pairs.
- **The step CHECKs** (`ck_model_step_measurements_step`,
  `ck_step_outcomes_step`, `ck_labelled_cases_step`,
  `ck_step_thresholds_step`) admit `salesorder_skill`, the step that fills a
  SalesOrder with the skill.

The CHECKs are rebuilt from the values each holds when this runs, plus this
revision's own, so a revision made beside this one (ticket 42 widened the
same CHECKs at the same time) keeps its values whichever runs first.
`test_sales_schema.py` holds each CHECK to the domain's values.

Downgrade deletes the rows the old checks cannot hold, and drops the table.
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op

revision = "711e8b760139"
down_revision = "beba87138cda"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"
_SCOPE = f"({_TENANT} AND ({_WORKSPACE} OR {_WORKSPACE_SCOPE}))"

# `dw_sales.application.skills.is_salesorder_key`: the prefix, then a
# customer code (`[A-Z][A-Z0-9]{1,15}`) in lower case.
_CUSTOMER_SKILL = "^sales_skill_salesorder_[a-z][a-z0-9]{1,15}$"
_NEW_STEP = "salesorder_skill"
_NEW_SOURCE = "customer_pairs"
# Every table whose step CHECK lists Sales' steps.
_STEP_CHECKS = (
    ("platform.model_step_measurements", "ck_model_step_measurements_step"),
    ("sales.step_outcomes", "ck_step_outcomes_step"),
    ("sales.labelled_cases", "ck_labelled_cases_step"),
    ("sales.step_thresholds", "ck_step_thresholds_step"),
)

_TABLE = """
    CREATE TABLE sales.salesorder_pairs (
        id uuid NOT NULL,
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        example_id uuid,
        customer_code text NOT NULL,
        received_on date NOT NULL,
        layout_ref text NOT NULL,
        document jsonb NOT NULL,
        expected jsonb NOT NULL,
        added_by uuid NOT NULL,
        added_at timestamp with time zone NOT NULL,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        CONSTRAINT pk_salesorder_pairs PRIMARY KEY (id),
        CONSTRAINT fk_salesorder_pairs_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_salesorder_pairs_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT fk_salesorder_pairs_example_id_salesorder_examples FOREIGN KEY (example_id)
            REFERENCES sales.salesorder_examples (id) ON DELETE SET NULL,
        CONSTRAINT ck_salesorder_pairs_customer_code CHECK (
            char_length(customer_code) BETWEEN 2 AND 16
        ),
        CONSTRAINT ck_salesorder_pairs_layout_ref CHECK (
            char_length(layout_ref) BETWEEN 1 AND 200
        ),
        CONSTRAINT ck_salesorder_pairs_document CHECK (
            jsonb_typeof(document) = 'object'
            AND octet_length(document::text) <= 4194304
        ),
        CONSTRAINT ck_salesorder_pairs_expected CHECK (
            jsonb_typeof(expected) = 'array'
            AND jsonb_array_length(expected) BETWEEN 1 AND 2000
            AND octet_length(expected::text) <= 4194304
        )
    )
"""

_STATEMENTS: tuple[str, ...] = (
    _TABLE,
    # The replay's read: a customer's pairs, newest first, led by what RLS
    # supplies.
    "CREATE INDEX ix_salesorder_pairs_tenant_id_workspace_id_customer_code_added_at"
    " ON sales.salesorder_pairs (tenant_id, workspace_id, customer_code, added_at DESC)",
    "CREATE INDEX ix_salesorder_pairs_workspace_id ON sales.salesorder_pairs (workspace_id)",
    "CREATE INDEX ix_salesorder_pairs_example_id ON sales.salesorder_pairs (example_id)",
    "ALTER TABLE sales.salesorder_pairs ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.salesorder_pairs FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_salesorder_pairs ON sales.salesorder_pairs"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
)

_GRANTS = """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
            GRANT SELECT, INSERT ON sales.salesorder_pairs TO dw_app;
            REVOKE UPDATE, DELETE ON sales.salesorder_pairs FROM dw_app;
        END IF;
    END
    $$
"""


def _listed(values: list[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _held(table: str, check: str) -> list[str]:
    """The values ``check`` on ``table`` admits now, in its order."""
    definition = op.get_bind().scalar(
        sa.text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
            " WHERE conname = :check AND conrelid = CAST(:table AS regclass)"
        ),
        {"check": check, "table": table},
    )
    return re.findall(r"'([a-z_]+)'::text", str(definition))


def _set(table: str, check: str, column: str, values: list[str], extra: str = "") -> None:
    op.execute(
        f"ALTER TABLE {table} DROP CONSTRAINT {check},"
        f" ADD CONSTRAINT {check} CHECK ({column} IN ({_listed(values)}){extra})"
    )


def _with(values: list[str], new: str) -> list[str]:
    return values if new in values else [*values, new]


def upgrade() -> None:
    for statement in _STATEMENTS:
        op.execute(statement)
    op.execute(_GRANTS)
    keys = _held("platform.rule_versions", "ck_rule_versions_key")
    _set(
        "platform.rule_versions",
        "ck_rule_versions_key",
        "key",
        keys,
        f" OR key ~ '{_CUSTOMER_SKILL}'",
    )
    sources = _held("sales.skill_replays", "ck_skill_replays_source")
    _set("sales.skill_replays", "ck_skill_replays_source", "source", _with(sources, _NEW_SOURCE))
    for table, check in _STEP_CHECKS:
        _set(table, check, "step", _with(_held(table, check), _NEW_STEP))


def downgrade() -> None:
    for table, check in _STEP_CHECKS:
        op.execute(f"DELETE FROM {table} WHERE step = '{_NEW_STEP}'")
        _set(table, check, "step", [v for v in _held(table, check) if v != _NEW_STEP])
    op.execute(f"DELETE FROM sales.skill_replays WHERE source = '{_NEW_SOURCE}'")
    sources = [
        v for v in _held("sales.skill_replays", "ck_skill_replays_source") if v != _NEW_SOURCE
    ]
    _set("sales.skill_replays", "ck_skill_replays_source", "source", sources)
    op.execute(f"DELETE FROM platform.rule_versions WHERE key ~ '{_CUSTOMER_SKILL}'")
    _set(
        "platform.rule_versions",
        "ck_rule_versions_key",
        "key",
        _held("platform.rule_versions", "ck_rule_versions_key"),
    )
    op.execute("DROP TABLE sales.salesorder_pairs")
