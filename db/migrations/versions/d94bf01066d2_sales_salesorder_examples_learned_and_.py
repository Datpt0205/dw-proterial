"""sales salesorder examples learned and replayed

Revision ID: d94bf01066d2
Revises: bc50e4985878
Create Date: 2026-11-14 10:00:00.000000+00:00

Sales ticket 38 (dw_sales ADR 0013): a customer's SalesOrder rules learned
from one worked example, the customer's PO and the PIC's SalesOrder file,
and proven by replaying them on it (`dw_sales.application.salesorder_learning`).

- **`ck_rule_versions_key`** and **`ck_rule_drafts_rule_key`** admit
  `sales_salesorder_rules`, the customers' rules, a tenant version proposed
  only from an example whose replay matched (`test_sales_schema.py` holds
  both to `RuleKey`).
- **`sales.salesorder_examples`**: one row per uploaded pair. The customer,
  who asked and when, the day the PO came in, each file's name, sha256 and
  size, its status (`ck_salesorder_examples_status`: queued, replayed,
  refused, unavailable, failed, submitted), the rules proposed and their
  replay (`ck_salesorder_examples_rules`: rules only once replayed or sent;
  a sent one has both and names the version it was sent as,
  `ck_salesorder_examples_submitted`), the problems, the reason a learning
  failed (`ck_salesorder_examples_error`: exactly when failed), and the
  prompt and model profile it was asked under. The replay names cells and
  their values: price-bearing, read only through the service, which asks
  for `sales.price.read`. `ix_salesorder_examples_customer` carries the
  customer's list, newest first, and the prune by age, led by what RLS
  supplies; `ix_salesorder_examples_version` the approval's look-up.
- **`sales.salesorder_example_files`**: the pair's bytes until the worker
  reads them (deleted then, or with their example), one row per file
  (`ck_salesorder_example_files_kind`: po, salesorder), at most 5 MiB each.
  Never updated.
- **Row security**: both narrowed by tenant AND workspace with the
  offboarding scope, ENABLEd and FORCEd.

Grants: `dw_app` every verb on the examples (the worker settles them, a send
marks one, a request prunes old ones never sent); SELECT, INSERT and DELETE
on the files, UPDATE revoked, which the sales schema's default privileges
would otherwise give (`89bcd0d49ea6`). Downgrade drops both tables and the
key's versions and drafts, then narrows the checks.
"""

from __future__ import annotations

from alembic import op

revision = "d94bf01066d2"
down_revision = "bc50e4985878"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"
_SCOPE = f"({_TENANT} AND ({_WORKSPACE} OR {_WORKSPACE_SCOPE}))"

_RULE_KEYS = (
    "sales_order_rules",
    "sales_kpi",
    "sales_quote_rules",
    "sales_pricing",
    "sales_emails",
    "sales_documents",
    "sales_bravo_upload",
    "sales_handoffs",
    "sales_followups",
    "purchasing_rules",
    "purchasing_automation",
    "purchasing_master_data",
)
_DRAFT_KEYS = tuple(key for key in _RULE_KEYS if key.startswith("sales_"))
_KEY = "sales_salesorder_rules"
# `dw_sales.application.salesorder_learning.ExampleStatus`;
# `test_sales_schema.py` holds the two together.
_STATUSES = "('queued', 'replayed', 'refused', 'unavailable', 'failed', 'submitted')"
_MAX_BYTES = 5 * 1024 * 1024

_EXAMPLES = f"""
    CREATE TABLE sales.salesorder_examples (
        id uuid NOT NULL,
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        customer_code text NOT NULL,
        status text NOT NULL,
        requested_by uuid NOT NULL,
        requested_at timestamptz NOT NULL,
        received_on date NOT NULL,
        po_file_name text NOT NULL,
        po_sha256 text NOT NULL,
        po_size integer NOT NULL,
        salesorder_file_name text NOT NULL,
        salesorder_sha256 text NOT NULL,
        salesorder_size integer NOT NULL,
        rules jsonb,
        replay jsonb,
        problems jsonb DEFAULT '[]'::jsonb NOT NULL,
        error text,
        prompt_ref text,
        model_profile text,
        version_id uuid,
        created_at timestamptz DEFAULT now() NOT NULL,
        updated_at timestamptz DEFAULT now() NOT NULL,
        CONSTRAINT pk_salesorder_examples PRIMARY KEY (id),
        CONSTRAINT fk_salesorder_examples_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_salesorder_examples_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT uq_salesorder_examples_tenant_id_workspace_id_id
            UNIQUE (tenant_id, workspace_id, id),
        CONSTRAINT ck_salesorder_examples_customer_code
            CHECK (customer_code ~ '^[A-Z][A-Z0-9]*$' AND char_length(customer_code) <= 16),
        CONSTRAINT ck_salesorder_examples_status CHECK (status IN {_STATUSES}),
        CONSTRAINT ck_salesorder_examples_files CHECK (
            char_length(po_file_name) BETWEEN 1 AND 200
            AND char_length(salesorder_file_name) BETWEEN 1 AND 200
            AND po_sha256 ~ '^[0-9a-f]{{64}}$'
            AND salesorder_sha256 ~ '^[0-9a-f]{{64}}$'
            AND po_size BETWEEN 1 AND {_MAX_BYTES}
            AND salesorder_size BETWEEN 1 AND {_MAX_BYTES}
        ),
        CONSTRAINT ck_salesorder_examples_rules CHECK (
            (rules IS NULL OR status IN ('replayed', 'submitted'))
            AND (rules IS NULL OR jsonb_typeof(rules) = 'object')
            AND (replay IS NULL OR jsonb_typeof(replay) = 'object')
        ),
        CONSTRAINT ck_salesorder_examples_submitted CHECK (
            (status = 'submitted') = (version_id IS NOT NULL)
            AND (status <> 'submitted' OR (rules IS NOT NULL AND replay IS NOT NULL))
        ),
        CONSTRAINT ck_salesorder_examples_problems CHECK (jsonb_typeof(problems) = 'array'),
        CONSTRAINT ck_salesorder_examples_error CHECK (
            (status = 'failed') = (error IS NOT NULL) AND char_length(error) <= 500
        )
    )
"""

_FILES = f"""
    CREATE TABLE sales.salesorder_example_files (
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        example_id uuid NOT NULL,
        kind text NOT NULL,
        content bytea NOT NULL,
        created_at timestamptz DEFAULT now() NOT NULL,
        CONSTRAINT pk_salesorder_example_files
            PRIMARY KEY (tenant_id, workspace_id, example_id, kind),
        CONSTRAINT fk_salesorder_example_files_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_salesorder_example_files_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT fk_salesorder_example_files_salesorder_examples
            FOREIGN KEY (tenant_id, workspace_id, example_id)
            REFERENCES sales.salesorder_examples (tenant_id, workspace_id, id) ON DELETE CASCADE,
        CONSTRAINT ck_salesorder_example_files_kind CHECK (kind IN ('po', 'salesorder')),
        CONSTRAINT ck_salesorder_example_files_content
            CHECK (octet_length(content) BETWEEN 1 AND {_MAX_BYTES})
    )
"""

_INDEXES = (
    # The customer's list, newest first, and the prune by age, led by what RLS
    # supplies.
    "CREATE INDEX ix_salesorder_examples_customer ON sales.salesorder_examples"
    " (tenant_id, workspace_id, customer_code, requested_at DESC)",
    "CREATE INDEX ix_salesorder_examples_requested ON sales.salesorder_examples"
    " (tenant_id, workspace_id, requested_at)",
    # What a version's approval shows: the example it was sent from.
    "CREATE INDEX ix_salesorder_examples_version ON sales.salesorder_examples"
    " (tenant_id, version_id) WHERE version_id IS NOT NULL",
    "CREATE INDEX ix_salesorder_examples_workspace_id ON sales.salesorder_examples (workspace_id)",
    "CREATE INDEX ix_salesorder_example_files_workspace_id ON sales.salesorder_example_files"
    " (workspace_id)",
)

_GRANTS = (
    "GRANT SELECT, INSERT, UPDATE, DELETE ON sales.salesorder_examples TO dw_app",
    "GRANT SELECT, INSERT, DELETE ON sales.salesorder_example_files TO dw_app",
    # A GRANT never takes away what the schema's default privileges gave.
    "REVOKE UPDATE ON sales.salesorder_example_files FROM dw_app",
)

# Spelled out per table, not looped: `verify_invariants.py` reads this text.
_ROW_SECURITY = (
    "ALTER TABLE sales.salesorder_examples ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.salesorder_examples FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_salesorder_examples ON sales.salesorder_examples"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
    "ALTER TABLE sales.salesorder_example_files ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.salesorder_example_files FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_salesorder_example_files ON sales.salesorder_example_files"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
)


def _listed(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _keys(rule_keys: tuple[str, ...], draft_keys: tuple[str, ...]) -> None:
    op.execute(
        "ALTER TABLE platform.rule_versions DROP CONSTRAINT ck_rule_versions_key,"
        f" ADD CONSTRAINT ck_rule_versions_key CHECK (key IN ({_listed(rule_keys)}))"
    )
    op.execute(
        "ALTER TABLE sales.rule_drafts DROP CONSTRAINT ck_rule_drafts_rule_key,"
        f" ADD CONSTRAINT ck_rule_drafts_rule_key CHECK (rule_key IN ({_listed(draft_keys)}))"
    )


def upgrade() -> None:
    _keys((*_RULE_KEYS, _KEY), (*_DRAFT_KEYS, _KEY))
    for ddl in (_EXAMPLES, _FILES, *_INDEXES, *_ROW_SECURITY):
        op.execute(ddl)
    op.execute(
        "CREATE TRIGGER touch_updated_at BEFORE UPDATE ON sales.salesorder_examples"
        " FOR EACH ROW EXECUTE FUNCTION platform.touch_updated_at()"
    )
    for grant in _GRANTS:
        op.execute(grant)


def downgrade() -> None:
    op.execute("DROP TABLE sales.salesorder_example_files")
    op.execute("DROP TABLE sales.salesorder_examples")
    op.execute(f"DELETE FROM sales.rule_drafts WHERE rule_key = '{_KEY}'")
    op.execute(f"DELETE FROM platform.rule_versions WHERE key = '{_KEY}'")
    _keys(_RULE_KEYS, _DRAFT_KEYS)
