"""bravo person links and the link queue

Revision ID: adad4d524377
Revises: 6b0f375184fb
Create Date: 2026-11-21 13:30:00.000000+00:00

One person, many accounts (ADR 0027 decision 5, sales ticket 64): a write
is the PIC's own, so DW anchors a person on their employee code, and every
account only points at the person.

- **`bravo.person_links`**: a DW principal (the Keycloak subject, which
  stays the same when the AD login is renamed: measured on Keycloak 26.7.2
  with LDAP, ticket 64) linked to an employee code, how (`employee_id` from
  the AD, `email` matched once against Bravo's employee record, or `admin`),
  by whom (null when DW linked it itself), and when. A link is retired, never
  deleted. At most one live link per subject and one per employee code
  (partial unique indexes): two live accounts for one code cannot both act.
- **`bravo.link_queue`**: what the automatic link would not decide, with
  why, for an admin: two live accounts for one code, two active Bravo users
  for one code, no match, an e-mail that matches several employees, a
  re-link while the old account is still live. One open item per subject.
- **Tenant only**, RLS enabled and forced; `dw_app` SELECT, INSERT, UPDATE,
  DELETE revoked. Scope `sales.identity.link` (who may link by hand) joins
  no role: an admin grants it through a permission set.
"""

from __future__ import annotations

from alembic import op

revision = "adad4d524377"
down_revision = "6b0f375184fb"
branch_labels = None
depends_on = None

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_CODE = "char_length(employee_code) BETWEEN 1 AND 24 AND employee_code !~ '[[:cntrl:]]'"

_LINKS = f"""
    CREATE TABLE bravo.person_links (
        tenant_id uuid NOT NULL,
        id uuid NOT NULL,
        subject uuid NOT NULL,
        employee_code text NOT NULL,
        linked_how text NOT NULL,
        linked_by uuid,
        linked_at timestamptz NOT NULL,
        retired_at timestamptz,
        retired_reason text,
        CONSTRAINT pk_person_links PRIMARY KEY (tenant_id, id),
        CONSTRAINT fk_person_links_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT ck_person_links_employee_code CHECK ({_CODE}),
        CONSTRAINT ck_person_links_linked_how CHECK (linked_how IN ('employee_id', 'email', 'admin')),
        CONSTRAINT ck_person_links_by_admin CHECK ((linked_how = 'admin') = (linked_by IS NOT NULL)),
        CONSTRAINT ck_person_links_retired CHECK (
            (retired_at IS NULL) = (retired_reason IS NULL)
            AND (retired_reason IS NULL OR char_length(retired_reason) BETWEEN 1 AND 200)
        )
    )
"""
_QUEUE = f"""
    CREATE TABLE bravo.link_queue (
        tenant_id uuid NOT NULL,
        id uuid NOT NULL,
        subject uuid NOT NULL,
        employee_code text,
        reason text NOT NULL,
        opened_at timestamptz NOT NULL,
        resolved_at timestamptz,
        resolved_by uuid,
        CONSTRAINT pk_link_queue PRIMARY KEY (tenant_id, id),
        CONSTRAINT fk_link_queue_tenant_id_tenants FOREIGN KEY (tenant_id)
            REFERENCES platform.tenants (id) ON DELETE CASCADE,
        CONSTRAINT ck_link_queue_employee_code CHECK (employee_code IS NULL OR ({_CODE})),
        CONSTRAINT ck_link_queue_reason CHECK (reason IN (
            'two_live_accounts', 'two_bravo_users', 'no_match', 'several_matches',
            'relink_while_old_live'
        )),
        CONSTRAINT ck_link_queue_resolved CHECK ((resolved_at IS NULL) = (resolved_by IS NULL))
    )
"""
_INDEXES = (
    "CREATE UNIQUE INDEX uq_person_links_live_subject ON bravo.person_links (tenant_id, subject)"
    " WHERE retired_at IS NULL",
    "CREATE UNIQUE INDEX uq_person_links_live_code ON bravo.person_links (tenant_id, employee_code)"
    " WHERE retired_at IS NULL",
    "CREATE UNIQUE INDEX uq_link_queue_open_subject ON bravo.link_queue (tenant_id, subject)"
    " WHERE resolved_at IS NULL",
    "CREATE INDEX ix_link_queue_opened_at ON bravo.link_queue (tenant_id, opened_at)",
)
# Spelled out, not looped: `verify_invariants.py` reads this text.
_ROW_SECURITY = (
    "ALTER TABLE bravo.person_links ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE bravo.person_links FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_person_links ON bravo.person_links"
    f" USING {_TENANT} WITH CHECK {_TENANT}",
    "ALTER TABLE bravo.link_queue ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE bravo.link_queue FORCE ROW LEVEL SECURITY",
    "CREATE POLICY tenant_isolation_link_queue ON bravo.link_queue"
    f" USING {_TENANT} WITH CHECK {_TENANT}",
)
_GRANTS = """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
            GRANT SELECT, INSERT, UPDATE ON bravo.person_links TO dw_app;
            REVOKE DELETE, TRUNCATE ON bravo.person_links FROM dw_app;
            GRANT SELECT, INSERT, UPDATE ON bravo.link_queue TO dw_app;
            REVOKE DELETE, TRUNCATE ON bravo.link_queue FROM dw_app;
        END IF;
    END
    $$
"""


def upgrade() -> None:
    for ddl in (_LINKS, _QUEUE, *_INDEXES, *_ROW_SECURITY, _GRANTS):
        op.execute(ddl)


def downgrade() -> None:
    op.execute("DROP TABLE bravo.link_queue")
    op.execute("DROP TABLE bravo.person_links")
