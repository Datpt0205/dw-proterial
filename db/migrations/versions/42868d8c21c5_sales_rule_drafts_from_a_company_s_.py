"""sales rule drafts from a company's template

Revision ID: 42868d8c21c5
Revises: 89bcd0d49ea6
Create Date: 2026-10-21 02:37:53.619402+00:00

"Tạo từ tệp mẫu", phase 1 (Đạt, 2026-10-20: the configurator uploads the
company's Bravo import template and DW1 proposes the upload layout from it;
the diff and the approval stay as they are). A draft is a starting point for
a proposal, never a rule version: the person sends it through the rules
editor (`dw_sales.application.rule_drafts`).

- **`sales.rule_drafts`**: one row per uploaded template. Who asked and
  when, the file's name, sha256 and size, its status
  (`ck_rule_drafts_status`: queued, ready, refused, unavailable, failed),
  the key (`ck_rule_drafts_rule_key`: `sales_bravo_upload` only until phase
  2), the header row code read (`template`), the drafted document, the
  document paths the machine filled (`machine_read`) and the cell each came
  from (`evidence`), the problems, the reason a draft failed
  (`ck_rule_drafts_error`: exactly when failed), and the prompt and model
  profile a mapping was asked under. `ix_rule_drafts_requested` carries the
  prune by age, led by what RLS supplies.
- **`sales.rule_draft_files`**: an uploaded template's bytes until the worker
  reads them (deleted then, or with their draft), at most 2 MiB. Never
  updated.
- **Row security**: both narrowed by tenant AND workspace with the
  offboarding scope, ENABLEd and FORCEd: a draft is its workspace's, as the
  file it was read from.

Grants: `dw_app` every verb on the drafts (the worker settles them, a request
prunes old ones, offboarding purges as the app role); SELECT, INSERT and
DELETE on the files, and UPDATE revoked, which the sales schema's default
privileges would otherwise give (`89bcd0d49ea6`). Downgrade drops both.
"""

from __future__ import annotations

from alembic import op

revision = "42868d8c21c5"
down_revision = "89bcd0d49ea6"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_WORKSPACE_SCOPE = "(current_setting('app.workspace_scope'::text, true) = 'tenant'::text)"
_SCOPE = f"({_TENANT} AND ({_WORKSPACE} OR {_WORKSPACE_SCOPE}))"

# `dw_sales.application.rule_drafts.DraftStatus` and `DRAFTABLE`;
# `test_sales_schema.py` holds the two together.
_STATUSES = "('queued', 'ready', 'refused', 'unavailable', 'failed')"
_KEYS = "('sales_bravo_upload')"
_DRAFTED = "('ready', 'refused', 'unavailable')"
_MAX_BYTES = 2 * 1024 * 1024

_DRAFTS = f"""
    CREATE TABLE sales.rule_drafts (
        id uuid NOT NULL,
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        rule_key text NOT NULL,
        status text NOT NULL,
        requested_by uuid NOT NULL,
        requested_at timestamptz NOT NULL,
        file_name text NOT NULL,
        file_sha256 text NOT NULL,
        file_size integer NOT NULL,
        template jsonb,
        document jsonb,
        machine_read jsonb DEFAULT '[]'::jsonb NOT NULL,
        evidence jsonb DEFAULT '{{}}'::jsonb NOT NULL,
        problems jsonb DEFAULT '[]'::jsonb NOT NULL,
        error text,
        prompt_ref text,
        model_profile text,
        created_at timestamptz DEFAULT now() NOT NULL,
        updated_at timestamptz DEFAULT now() NOT NULL,
        CONSTRAINT pk_rule_drafts PRIMARY KEY (id),
        CONSTRAINT fk_rule_drafts_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_rule_drafts_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT uq_rule_drafts_tenant_id_workspace_id_id UNIQUE (tenant_id, workspace_id, id),
        CONSTRAINT ck_rule_drafts_rule_key CHECK (rule_key IN {_KEYS}),
        CONSTRAINT ck_rule_drafts_status CHECK (status IN {_STATUSES}),
        CONSTRAINT ck_rule_drafts_file_name CHECK (char_length(file_name) BETWEEN 1 AND 200),
        CONSTRAINT ck_rule_drafts_file_sha256 CHECK (file_sha256 ~ '^[0-9a-f]{{64}}$'),
        CONSTRAINT ck_rule_drafts_file_size CHECK (file_size BETWEEN 1 AND {_MAX_BYTES}),
        CONSTRAINT ck_rule_drafts_document CHECK (
            (status IN {_DRAFTED}) = (document IS NOT NULL AND template IS NOT NULL)
            AND (document IS NULL OR jsonb_typeof(document) = 'object')
        ),
        CONSTRAINT ck_rule_drafts_shapes CHECK (
            jsonb_typeof(machine_read) = 'array'
            AND jsonb_typeof(evidence) = 'object'
            AND jsonb_typeof(problems) = 'array'
        ),
        CONSTRAINT ck_rule_drafts_error CHECK (
            (status = 'failed') = (error IS NOT NULL) AND char_length(error) <= 500
        )
    )
"""

_FILES = f"""
    CREATE TABLE sales.rule_draft_files (
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        draft_id uuid NOT NULL,
        content bytea NOT NULL,
        created_at timestamptz DEFAULT now() NOT NULL,
        CONSTRAINT pk_rule_draft_files PRIMARY KEY (tenant_id, workspace_id, draft_id),
        CONSTRAINT fk_rule_draft_files_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT fk_rule_draft_files_workspace_id_workspaces FOREIGN KEY (workspace_id)
            REFERENCES platform.workspaces (id) ON DELETE CASCADE,
        CONSTRAINT fk_rule_draft_files_rule_drafts
            FOREIGN KEY (tenant_id, workspace_id, draft_id)
            REFERENCES sales.rule_drafts (tenant_id, workspace_id, id) ON DELETE CASCADE,
        CONSTRAINT ck_rule_draft_files_content
            CHECK (octet_length(content) BETWEEN 1 AND {_MAX_BYTES})
    )
"""

_INDEXES = (
    # The prune by age, led by what RLS supplies.
    "CREATE INDEX ix_rule_drafts_requested ON sales.rule_drafts"
    " (tenant_id, workspace_id, requested_at)",
    "CREATE INDEX ix_rule_drafts_workspace_id ON sales.rule_drafts (workspace_id)",
    "CREATE INDEX ix_rule_draft_files_workspace_id ON sales.rule_draft_files (workspace_id)",
)

_GRANTS = (
    "GRANT SELECT, INSERT, UPDATE, DELETE ON sales.rule_drafts TO dw_app",
    "GRANT SELECT, INSERT, DELETE ON sales.rule_draft_files TO dw_app",
    # A GRANT never takes away what the schema's default privileges gave.
    "REVOKE UPDATE ON sales.rule_draft_files FROM dw_app",
)

# Spelled out per table, not looped: `verify_invariants.py` reads this text.
_ROW_SECURITY = (
    "ALTER TABLE sales.rule_drafts ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.rule_drafts FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_rule_drafts ON sales.rule_drafts"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
    "ALTER TABLE sales.rule_draft_files ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.rule_draft_files FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_rule_draft_files ON sales.rule_draft_files"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
)


def upgrade() -> None:
    for ddl in (_DRAFTS, _FILES, *_INDEXES, *_ROW_SECURITY):
        op.execute(ddl)
    op.execute(
        "CREATE TRIGGER touch_updated_at BEFORE UPDATE ON sales.rule_drafts"
        " FOR EACH ROW EXECUTE FUNCTION platform.touch_updated_at()"
    )
    for grant in _GRANTS:
        op.execute(grant)


def downgrade() -> None:
    op.execute("DROP TABLE sales.rule_draft_files")
    op.execute("DROP TABLE sales.rule_drafts")
