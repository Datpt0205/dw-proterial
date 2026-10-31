"""purchasing schema cases and mail outcomes

Revision ID: 2d0c58dc3806
Revises: 55aea24d5845
Create Date: 2026-11-01 09:00:00.000000+00:00

DW2 (Mua hàng), DW02 function 1: a purchase request received from a form or
read from a mail (ADR 0013 decision 5).

- **`purchasing` schema**, its own, as `sales` is: `dw_app` gets USAGE and,
  by default and explicitly, the verbs each table needs.
- **`purchasing.cases`**: one row per purchase case. The aggregate is the
  `body` (validated by `dw_purchasing.domain.requests.PurchaseCase` before it
  is written); its identity, version and status are columns, never a second
  copy inside the body. The PR number and the mail it came from are generated
  from the body for lookups. `rules_ref` is the tenant rules the case was
  received under, stamped once.
- **`purchasing.mail_outcomes`**: what DW2 did with one mail, at most once
  per (tenant, workspace, message): a case opened, or a person reads it with a
  reason code. Appended, never changed: `dw_app` holds SELECT and INSERT, and
  UPDATE and DELETE are REVOKEd (failure-modes #7).
- **Tenant AND workspace** on both sides of every policy, in the shape
  `test_rls_coverage.py` holds (the offboarding lane's workspace scope).
  Foreign keys to the tenant and the workspace `ON DELETE CASCADE`, each
  indexed on its own side; the case list's keyset order has an index that
  leads with what RLS supplies.
- **Roles** in the platform's catalogue, which a context extends in its own
  migration (as `68305ebe4a83` did for Sales): `purchasing_buyer` receives
  and reads requests, `purchasing_viewer` reads them. No `purchasing.*`
  scope goes on a platform role.
"""

from __future__ import annotations

import json

from alembic import op

revision = "2d0c58dc3806"
down_revision = "55aea24d5845"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"
_SCOPE = f"({_TENANT} AND ({_WORKSPACE} OR {_WORKSPACE_SCOPE}))"

# `dw_purchasing.domain.requests.CaseStatus` / `PrSource` and
# `dw_purchasing.application.ports.Disposition`, each held to its enum by
# `test_purchasing_schema.py`.
_STATUSES = "('received')"
_SOURCES = "('form', 'mail')"
_DISPOSITIONS = "('opened', 'to_person')"

_CASES = f"""
    CREATE TABLE purchasing.cases (
        id uuid NOT NULL,
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        case_version integer NOT NULL,
        status text NOT NULL,
        source text NOT NULL,
        body jsonb NOT NULL,
        pr_no text GENERATED ALWAYS AS (body #>> '{{request,pr_no}}') STORED,
        source_ref text GENERATED ALWAYS AS (body #>> '{{source_ref}}') STORED,
        rules_ref text NOT NULL,
        received_by uuid NOT NULL,
        received_at timestamptz NOT NULL,
        created_at timestamptz DEFAULT now() NOT NULL,
        updated_at timestamptz DEFAULT now() NOT NULL,
        CONSTRAINT pk_cases PRIMARY KEY (id),
        CONSTRAINT fk_cases_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_cases_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT ck_cases_case_version CHECK (case_version >= 1),
        CONSTRAINT ck_cases_status CHECK (status IN {_STATUSES}),
        CONSTRAINT ck_cases_source CHECK (source IN {_SOURCES}),
        CONSTRAINT ck_cases_body CHECK (
            jsonb_typeof(body) = 'object'
            AND jsonb_typeof(body #> '{{request,lines}}') = 'array'
            AND jsonb_array_length(body #> '{{request,lines}}') > 0
            AND NOT body ?| ARRAY['case_id', 'case_version', 'status']
        ),
        CONSTRAINT ck_cases_pr_no CHECK (pr_no ~ '^[A-Za-z0-9][A-Za-z0-9._/-]{{0,47}}$'),
        CONSTRAINT ck_cases_source_ref CHECK (
            (source = 'mail') = (source_ref IS NOT NULL)
            AND (source_ref IS NULL OR char_length(source_ref) <= 512)
        ),
        CONSTRAINT ck_cases_rules_ref CHECK (
            rules_ref ~ '^purchasing_rules@[0-9]+\\.[0-9]+\\.[0-9]+(-[a-z0-9.]+)?$'
            AND char_length(rules_ref) <= 80
        )
    )
"""

_OUTCOMES = f"""
    CREATE TABLE purchasing.mail_outcomes (
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        message_id text NOT NULL,
        disposition text NOT NULL,
        reason text,
        case_id uuid,
        settled_by uuid NOT NULL,
        settled_at timestamptz NOT NULL,
        CONSTRAINT pk_mail_outcomes PRIMARY KEY (tenant_id, workspace_id, message_id),
        CONSTRAINT fk_mail_outcomes_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_mail_outcomes_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT fk_mail_outcomes_case_id_cases FOREIGN KEY (case_id)
            REFERENCES purchasing.cases (id) ON DELETE CASCADE,
        CONSTRAINT ck_mail_outcomes_message_id CHECK (
            message_id ~ '^[!-~]+$' AND char_length(message_id) <= 512
        ),
        CONSTRAINT ck_mail_outcomes_disposition CHECK (disposition IN {_DISPOSITIONS}),
        -- A case opened names it and gives no reason; a mail for a person
        -- names no case and says why, as a code.
        CONSTRAINT ck_mail_outcomes_shape CHECK (
            (disposition = 'opened' AND case_id IS NOT NULL AND reason IS NULL)
            OR (disposition = 'to_person' AND case_id IS NULL AND reason IS NOT NULL)
        ),
        CONSTRAINT ck_mail_outcomes_reason CHECK (
            reason IS NULL OR (reason ~ '^[a-z_:]+$' AND char_length(reason) <= 64)
        )
    )
"""

_INDEXES = (
    "CREATE INDEX ix_cases_workspace_id ON purchasing.cases (workspace_id)",
    # The case list's keyset order, leading with what RLS supplies.
    "CREATE INDEX ix_cases_tenant_id_workspace_id_received_at_id"
    " ON purchasing.cases (tenant_id, workspace_id, received_at DESC, id DESC)",
    "CREATE INDEX ix_cases_tenant_id_workspace_id_pr_no"
    " ON purchasing.cases (tenant_id, workspace_id, pr_no)",
    "CREATE INDEX ix_mail_outcomes_workspace_id ON purchasing.mail_outcomes (workspace_id)",
    "CREATE INDEX ix_mail_outcomes_case_id ON purchasing.mail_outcomes (case_id)",
)

# Spelled out, not looped: `verify_invariants.py` reads this text.
_ROW_SECURITY = (
    "ALTER TABLE purchasing.cases ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE purchasing.cases FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_cases ON purchasing.cases"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
    "ALTER TABLE purchasing.mail_outcomes ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE purchasing.mail_outcomes FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_mail_outcomes ON purchasing.mail_outcomes"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
)

_GRANTS = (
    "GRANT SELECT, INSERT, UPDATE, DELETE ON purchasing.cases TO dw_app",
    "GRANT SELECT, INSERT ON purchasing.mail_outcomes TO dw_app",
    # A GRANT never takes away what the schema's default privileges gave.
    "REVOKE UPDATE, DELETE ON purchasing.mail_outcomes FROM dw_app",
)

_READ = ("purchasing.request.read",)
_BUYER = (*_READ, "purchasing.request.intake")
_ROLES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("purchasing_buyer", "Nhân viên mua hàng", _BUYER),
    ("purchasing_viewer", "Xem yêu cầu mua hàng", _READ),
)


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def upgrade() -> None:
    op.execute("CREATE SCHEMA purchasing")
    # Before any table, so every table is born readable by the application.
    op.execute("GRANT USAGE ON SCHEMA purchasing TO dw_app")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA purchasing"
        " GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO dw_app"
    )
    for ddl in (_CASES, _OUTCOMES, *_INDEXES, *_ROW_SECURITY, *_GRANTS):
        op.execute(ddl)
    op.execute(
        "CREATE TRIGGER touch_updated_at BEFORE UPDATE ON purchasing.cases"
        " FOR EACH ROW EXECUTE FUNCTION platform.touch_updated_at()"
    )
    for key, name, scopes in _ROLES:
        op.execute(
            "INSERT INTO platform.roles (key, name, scopes)"
            f" VALUES ({_literal(key)}, {_literal(name)},"
            f" {_literal(json.dumps(list(scopes)))}::jsonb)"
        )


def downgrade() -> None:
    keys = ", ".join(_literal(key) for key, _, _ in _ROLES)
    op.execute(f"DELETE FROM platform.roles WHERE key IN ({keys})")
    op.execute("DROP TABLE purchasing.mail_outcomes")
    op.execute("DROP TABLE purchasing.cases")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA purchasing"
        " REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM dw_app"
    )
    op.execute("REVOKE USAGE ON SCHEMA purchasing FROM dw_app")
    op.execute("DROP SCHEMA purchasing")
