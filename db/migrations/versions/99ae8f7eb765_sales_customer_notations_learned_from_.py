"""sales customer notations learned from confirmations

Revision ID: 99ae8f7eb765
Revises: 2c91d318f833
Create Date: 2026-11-16 02:37:56.496731+00:00

Sales ticket 37. A document that does not settle its own notation ("1.200 m",
"05/11/2026", a bare "$") has those values read by nobody: a person types
them. A customer writes one way, and Sales knows it the first time they
confirm such a value; DW now keeps what that confirmation settles
(`dw_sales.domain.customer_notation`), and a later document of the customer
that says nothing is read by it (`dw_platform.domain.notation.settle`).

- **`sales.customer_notations`**: one row per (customer, kind). The kind
  (`ck_customer_notations_kind`: decimal_mark, date_order, dollar_sign,
  yen_sign) and the values each holds (`ck_customer_notations_value`), held
  to `dw_platform.domain.notation.KIND_VALUES` by `test_sales_schema.py`.
  Its source (`ck_customer_notations_source`): `confirmed`, learned from a
  value Sales kept, naming the case (order or quote), the field, the words as
  written and the value confirmed; or `set` by a person on the customer's
  master data, naming none of them (`ck_customer_notations_evidence`). Who
  decided and when, either way. The case is named, not referenced: the row
  outlives nothing it needs, and an order or a quote are two tables.
- **Mutable**: a later confirmation or a person replaces the value, a person
  forgets one, so `dw_app` holds every verb; `updated_at` by the trigger,
  which yields to a value the statement states.
- **Not partitioned, not pruned**: bounded by the customers, four kinds each.
- **Tenant AND workspace** on both sides of the policy, with the offboarding
  scope; foreign keys to the tenant and the workspace `ON DELETE CASCADE`, the
  workspace's indexed on its own side (the tenant leads the primary key).
"""

from __future__ import annotations

from alembic import op

revision = "99ae8f7eb765"
down_revision = "2c91d318f833"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"
_SCOPE = f"({_TENANT} AND ({_WORKSPACE} OR {_WORKSPACE_SCOPE}))"

_TABLE = """
    CREATE TABLE sales.customer_notations (
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        customer_code text NOT NULL,
        kind text NOT NULL,
        value text NOT NULL,
        source text NOT NULL,
        case_kind text,
        case_id uuid,
        field text,
        written text,
        confirmed text,
        decided_by uuid NOT NULL,
        decided_at timestamptz NOT NULL,
        created_at timestamptz DEFAULT now() NOT NULL,
        updated_at timestamptz DEFAULT now() NOT NULL,
        CONSTRAINT pk_customer_notations
            PRIMARY KEY (tenant_id, workspace_id, customer_code, kind),
        CONSTRAINT fk_customer_notations_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_customer_notations_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT ck_customer_notations_customer_code
            CHECK (customer_code ~ '^[A-Z][A-Z0-9]{1,15}$'),
        CONSTRAINT ck_customer_notations_kind
            CHECK (kind IN ('decimal_mark', 'date_order', 'dollar_sign', 'yen_sign')),
        CONSTRAINT ck_customer_notations_value CHECK (
            (kind = 'decimal_mark' AND value IN ('.', ','))
            OR (kind = 'date_order' AND value IN ('day_first', 'month_first'))
            OR (kind = 'dollar_sign' AND value IN ('AUD', 'CAD', 'HKD', 'SGD', 'TWD', 'USD'))
            OR (kind = 'yen_sign' AND value IN ('CNY', 'JPY'))
        ),
        CONSTRAINT ck_customer_notations_source CHECK (source IN ('confirmed', 'set')),
        CONSTRAINT ck_customer_notations_case_kind
            CHECK (case_kind IS NULL OR case_kind IN ('order', 'quote')),
        CONSTRAINT ck_customer_notations_evidence CHECK (
            (
                source = 'confirmed'
                AND case_kind IS NOT NULL
                AND case_id IS NOT NULL
                -- Each IS NOT NULL spelled out: a NULL compared is no FALSE,
                -- and a CHECK passes on NULL (failure-modes #7).
                AND field IS NOT NULL
                AND field ~ '^[a-z_]{1,32}$'
                AND written IS NOT NULL
                AND char_length(written) BETWEEN 1 AND 300
                AND confirmed IS NOT NULL
                AND char_length(confirmed) BETWEEN 1 AND 64
            )
            OR (
                source = 'set'
                AND case_kind IS NULL
                AND case_id IS NULL
                AND field IS NULL
                AND written IS NULL
                AND confirmed IS NULL
            )
        )
    )
"""

_INDEXES = (
    "CREATE INDEX ix_customer_notations_workspace_id ON sales.customer_notations (workspace_id)",
)

_TRIGGER = (
    "CREATE TRIGGER touch_updated_at BEFORE UPDATE ON sales.customer_notations"
    " FOR EACH ROW EXECUTE FUNCTION platform.touch_updated_at()"
)

_GRANTS = ("GRANT SELECT, INSERT, UPDATE, DELETE ON sales.customer_notations TO dw_app",)

# Spelled out, not looped: `verify_invariants.py` reads this text.
_ROW_SECURITY = (
    "ALTER TABLE sales.customer_notations ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.customer_notations FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_customer_notations ON sales.customer_notations"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
)


def upgrade() -> None:
    for ddl in (_TABLE, *_INDEXES, *_ROW_SECURITY, _TRIGGER, *_GRANTS):
        op.execute(ddl)


def downgrade() -> None:
    op.execute("DROP TABLE sales.customer_notations")
