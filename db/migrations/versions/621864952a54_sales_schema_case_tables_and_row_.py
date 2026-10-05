"""sales schema case tables and row security

Revision ID: 621864952a54
Revises: 855ae928c3fa
Create Date: 2026-10-05

DW1's case state (spec decision 3, ticket 04): order cases with every PO
revision, its lines and findings; quote cases; what became of each inbound
message; the artifacts generated for a case; which sources a person was
served; the per-workspace pause flag; and the case event log.

- **Tenant AND workspace.** Every table carries both, and every policy,
  `tenant_isolation_<table>`, narrows by `app.tenant_id` AND
  `app.workspace_id` on read and on write. These are the first policies in
  the repository to narrow by workspace, so offboarding (which binds only the
  tenant) learns to bind each of the tenant's workspaces in turn for them.
- **Master data is not here** (spec decision 2). The one exception is a check
  basis (decision 11): `order_lines.check_basis` is evidence stamped when the
  check ran, NOT NULL for clean lines too, with a CHECK on its keys.
- **One copy of each fact.** A PO revision's document, a line's printed
  values and a quote case are stored as the domain serialises them (jsonb).
  The columns queries and constraints need (`po_revision`, `parser_version`,
  `line_no`, `priced_by`, `approved_by`, ...) are GENERATED from that jsonb,
  so they cannot disagree with it. A line's values live in `order_lines`
  only: the revision's document is stored without them, and a CHECK keeps it
  that way.
- **Maker and checker.** `ck_order_cases_checker_not_maker` refuses a
  cross-checker who prepared the order or recorded its Bravo entry, in this
  revision or any earlier one: `order_cases.makers` accumulates every
  preparer and Bravo recorder, and only the `accumulate_makers` trigger
  writes it (after a revision, `apply_change` replaces `bravo_recorded_by`,
  so the previous recorder would otherwise pass).
  `ck_quote_cases_approver_not_pricer` refuses an approver who priced the
  quote (spec decision 7). The third maker kind, whoever typed a value still
  on the case, is per line and stays the handler's.
- **PO identity.** The ticket asked for `(tenant, workspace, customer_code,
  po_no, revision)`. The domain makes that key impossible twice over: a
  duplicate PO opens a case of its own (closed as `duplicate`), and the same
  revision number with other lines joins the case as a further revision. What
  does hold is one case per customer PO number that is not a duplicate, so
  that is the unique key (`uq_order_cases_tenant_id_workspace_id_customer_code_po_no`,
  partial). A message is at most one revision (`uq_order_revisions_..._message_id`),
  and a case has exactly one current revision.
- **Events are append-only and outlive the case.** `case_events` has typed
  columns and no free-text one: ids, finding keys, field names, reason codes,
  statuses, `case_version` and the actor (`actor_kind` worker|user). There is
  nowhere to put an amount (decision 8). It is range-partitioned by month with
  a DEFAULT partition, and `platform.ensure_time_partitions` now maintains it
  beside `platform.audit_events`. `dw_app` may SELECT and INSERT only, so, like
  the audit log, offboarding exports it and does not purge it; its retention
  term is ticket 12's.
- **Edges inside the schema are CASCADE.** A case takes its revisions, lines,
  findings, message dispositions, artifacts and served records with it, so
  offboarding needs no ordering for this schema. Actor columns are not
  foreign keys: an order's actors are principal subjects in the domain, and a
  decision's stamp must survive the person's removal.
- **Generalised partition maintenance.** `_ensure_one_partition` takes
  `schema.table` (a bare name still means `platform`), copies the parent's own
  `tenant_isolation_<table>` policy to the new partition instead of a
  hard-coded tenant predicate, and gives `dw_app` no UPDATE or DELETE on a
  partition when it has none on the parent. Both were facts the old body
  restated by hand for the one table it knew.
"""

from __future__ import annotations

import re
from pathlib import Path

from alembic import op

revision = "621864952a54"
down_revision = "855ae928c3fa"
branch_labels = None
depends_on = None

_SQL_DIR = Path(__file__).resolve().parents[1] / "sql"

_TENANT = "(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)"
_WORKSPACE = (
    "(workspace_id = (NULLIF(current_setting('app.workspace_id'::text, true), ''::text))::uuid)"
)
_SCOPE = f"({_TENANT} AND {_WORKSPACE})"

# The value sets the domain owns (`dw_sales.domain`, labels in CONTEXT.md).
# A CHECK is a second copy by necessity; `test_sales_schema.py` compares each
# one with its enum, so the two disagree loudly rather than quietly.
_ORDER_STATUSES = (
    "received",
    "checked",
    "in_review",
    "correction_requested",
    "prepared",
    "uploaded_to_bravo",
    "cross_checked",
    "confirmed",
    "change_review",
    "closed",
)
_CLOSE_REASONS = ("duplicate", "not_an_order", "superseded", "cannot_supply")
_EXPORT_CONTROL_MODES = ("warn", "block_confirmation")
_MAPPING_STATUSES = ("exact", "candidate", "ambiguous", "unmapped", "candidate_confirmed")
_FINDING_CODES = (
    "code_unmapped",
    "code_ambiguous",
    "price_mismatch",
    "currency_mismatch",
    "uom_mismatch",
    "quotation_missing",
    "lme_band_mismatch",
    "moq_violation",
    "pack_multiple",
    "line_total_mismatch",
    "value_uncertain",
    "customer_unknown",
    "duplicate_po",
    "requested_date_short_lt",
    "missing_noc_esf",
    "revised_po",
    "revision_without_base",
    "customer_temporary",
    "sender_unverified",
)
_SEVERITIES = ("error", "warning")
_FINDING_DISPOSITIONS = ("open", "accepted", "corrected_by_sales", "ask_customer")
_MESSAGE_DISPOSITIONS = ("case_created", "attached_to_case", "routed_to_sales", "not_yet_processed")
_ROUTING_REASONS = (
    "delivery_change",
    "complaint",
    "design_reply_unmatched",
    "sample_request",
    "customer_unknown",
    "attachment_unreadable",
    "other",
)
_QUOTE_STATUSES = (
    "received",
    "ycbg_drafted",
    "ycbg_recorded",
    "sent_to_design",
    "design_replied",
    "spec_discussion",
    "priced",
    "pending_approval",
    "returned",
    "approved",
    "sent",
    "master_list_recorded",
    "declined",
)
# `LineBasis`'s fields: what a check compared against.
_CHECK_BASIS_KEYS = (
    "convert_prv_code",
    "candidates",
    "item",
    "quotation",
    "lme",
    "lead_time_days",
    "lead_time_source",
    "checks_run",
)

_ACTOR = r"'^[!-~]{1,254}$'"
_VERSION_REF = r"'^[a-z][a-z0-9_.-]*@\d+\.\d+\.\d+$'"
_SHA256 = "'^[0-9a-f]{64}$'"
_ATTACHMENT_ID = "'^[A-Za-z0-9._-]{1,128}$'"
# Postgres caps a regex repetition count at 255, so the length is its own test.
_MESSAGE_ID = "'^[!-~]+$'"
_CUSTOMER_CODE = "'^[A-Z][A-Z0-9]{1,15}$'"
_DOCUMENT_NO = "'^[A-Z0-9][A-Z0-9/-]{1,31}$'"


def _in(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{value}'" for value in values) + ")"


def _scoped(table: str) -> str:
    """The two columns every table has, as foreign keys to their owners."""
    return f"""
            CONSTRAINT fk_{table}_tenant_id_tenants FOREIGN KEY (tenant_id)
                REFERENCES platform.tenants (id) ON DELETE CASCADE,
            CONSTRAINT fk_{table}_workspace_id_workspaces FOREIGN KEY (workspace_id)
                REFERENCES platform.workspaces (id) ON DELETE CASCADE,"""


def _case_scoped(table: str) -> str:
    """A row of one tenant's workspace that belongs to one order or quote case."""
    return _scoped(table) + f"""
            CONSTRAINT fk_{table}_order_case_id_order_cases FOREIGN KEY (order_case_id)
                REFERENCES sales.order_cases (id) ON DELETE CASCADE,
            CONSTRAINT fk_{table}_quote_case_id_quote_cases FOREIGN KEY (quote_case_id)
                REFERENCES sales.quote_cases (id) ON DELETE CASCADE,"""


_TABLES: tuple[str, ...] = (
    f"""
        CREATE TABLE sales.order_cases (
            id uuid NOT NULL,
            tenant_id uuid NOT NULL,
            workspace_id uuid NOT NULL,
            customer_code text NOT NULL,
            po_no text NOT NULL,
            case_version integer NOT NULL,
            status text NOT NULL,
            rules_version text,
            catalog_as_of timestamp with time zone,
            cross_check_required boolean,
            export_control_mode text,
            changes jsonb DEFAULT '[]'::jsonb NOT NULL,
            duplicate_of_case uuid,
            duplicate_of_so text,
            base_so_no text,
            prepared_by text,
            prepared_at timestamp with time zone,
            bravo_so_no text,
            bravo_recorded_by text,
            bravo_recorded_at timestamp with time zone,
            bravo_entry_compared boolean DEFAULT false NOT NULL,
            cross_checked_by text,
            cross_checked_at timestamp with time zone,
            returned_reason text,
            returned_by text,
            returned_at timestamp with time zone,
            confirmed_by text,
            confirmed_at timestamp with time zone,
            close_reason text,
            closed_by text,
            closed_at timestamp with time zone,
            superseded_by_case uuid,
            assigned_to text,
            release_manifest_ref text,
            makers text[] DEFAULT '{{}}'::text[] NOT NULL,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            updated_at timestamp with time zone DEFAULT now() NOT NULL,
            CONSTRAINT pk_order_cases PRIMARY KEY (id),{_scoped("order_cases")}
            CONSTRAINT fk_order_cases_duplicate_of_case_order_cases FOREIGN KEY (duplicate_of_case)
                REFERENCES sales.order_cases (id) ON DELETE CASCADE,
            CONSTRAINT fk_order_cases_superseded_by_case_order_cases
                FOREIGN KEY (superseded_by_case)
                REFERENCES sales.order_cases (id) ON DELETE CASCADE,
            CONSTRAINT ck_order_cases_customer_code CHECK (customer_code ~ {_CUSTOMER_CODE}),
            CONSTRAINT ck_order_cases_po_no CHECK (
                btrim(po_no) <> '' AND char_length(po_no) <= 200
            ),
            CONSTRAINT ck_order_cases_case_version CHECK (case_version >= 1),
            CONSTRAINT ck_order_cases_status CHECK (status IN {_in(_ORDER_STATUSES)}),
            CONSTRAINT ck_order_cases_close_reason CHECK (close_reason IN {_in(_CLOSE_REASONS)}),
            CONSTRAINT ck_order_cases_export_control_mode CHECK (
                export_control_mode IN {_in(_EXPORT_CONTROL_MODES)}
            ),
            CONSTRAINT ck_order_cases_rules_version CHECK (rules_version ~ {_VERSION_REF}),
            CONSTRAINT ck_order_cases_release_manifest_ref CHECK (
                btrim(release_manifest_ref) <> '' AND char_length(release_manifest_ref) <= 200
            ),
            CONSTRAINT ck_order_cases_changes CHECK (jsonb_typeof(changes) = 'array'),
            CONSTRAINT ck_order_cases_so_numbers CHECK (
                duplicate_of_so ~ {_DOCUMENT_NO}
                AND base_so_no ~ {_DOCUMENT_NO}
                AND bravo_so_no ~ {_DOCUMENT_NO}
            ),
            CONSTRAINT ck_order_cases_actors CHECK (
                prepared_by ~ {_ACTOR} AND bravo_recorded_by ~ {_ACTOR}
                AND cross_checked_by ~ {_ACTOR} AND returned_by ~ {_ACTOR}
                AND confirmed_by ~ {_ACTOR} AND closed_by ~ {_ACTOR}
                AND assigned_to ~ {_ACTOR}
            ),
            CONSTRAINT ck_order_cases_checked CHECK (
                status = 'received'
                OR (rules_version IS NOT NULL AND catalog_as_of IS NOT NULL
                    AND cross_check_required IS NOT NULL AND export_control_mode IS NOT NULL)
            ),
            CONSTRAINT ck_order_cases_closed CHECK (
                (status = 'closed')
                = (close_reason IS NOT NULL AND closed_by IS NOT NULL AND closed_at IS NOT NULL)
            ),
            CONSTRAINT ck_order_cases_close_stamp CHECK (
                num_nonnulls(close_reason, closed_by, closed_at) IN (0, 3)
            ),
            CONSTRAINT ck_order_cases_superseded_by CHECK (
                (superseded_by_case IS NOT NULL)
                = (close_reason IS NOT DISTINCT FROM 'superseded')
                AND superseded_by_case IS DISTINCT FROM id
            ),
            CONSTRAINT ck_order_cases_duplicate_of CHECK (duplicate_of_case IS DISTINCT FROM id),
            CONSTRAINT ck_order_cases_prepared_stamp CHECK (
                (prepared_by IS NULL) = (prepared_at IS NULL)
            ),
            CONSTRAINT ck_order_cases_bravo_stamp CHECK (
                num_nonnulls(bravo_so_no, bravo_recorded_by, bravo_recorded_at) IN (0, 3)
                AND bravo_entry_compared = (bravo_so_no IS NOT NULL)
            ),
            CONSTRAINT ck_order_cases_cross_checked_stamp CHECK (
                (cross_checked_by IS NULL) = (cross_checked_at IS NULL)
            ),
            CONSTRAINT ck_order_cases_returned_stamp CHECK (
                num_nonnulls(returned_reason, returned_by, returned_at) IN (0, 3)
                AND char_length(returned_reason) <= 500
            ),
            CONSTRAINT ck_order_cases_confirmed_stamp CHECK (
                (confirmed_by IS NULL) = (confirmed_at IS NULL)
            ),
            CONSTRAINT ck_order_cases_checker_not_maker CHECK (
                cross_checked_by IS NULL
                OR (cross_checked_by IS DISTINCT FROM prepared_by
                    AND cross_checked_by IS DISTINCT FROM bravo_recorded_by
                    AND cross_checked_by <> ALL (makers))
            )
        )
        """,
    f"""
        CREATE TABLE sales.quote_cases (
            id uuid NOT NULL,
            tenant_id uuid NOT NULL,
            workspace_id uuid NOT NULL,
            case_version integer NOT NULL,
            status text NOT NULL,
            body jsonb NOT NULL,
            message_id text GENERATED ALWAYS AS (body #>> '{{request,message_id}}') STORED,
            customer_code text GENERATED ALWAYS AS (body #>> '{{request,customer_code}}') STORED,
            ycbg_no text GENERATED ALWAYS AS (body #>> '{{ycbg,ycbg_no}}') STORED,
            priced_by uuid GENERATED ALWAYS AS ((body #>> '{{pricing,decided_by}}')::uuid) STORED,
            approved_by uuid
                GENERATED ALWAYS AS ((body #>> '{{approval,approved_by}}')::uuid) STORED,
            approved_version integer
                GENERATED ALWAYS AS ((body #>> '{{approval,case_version}}')::integer) STORED,
            document_sha256 text
                GENERATED ALWAYS AS (body #>> '{{submission,document_sha256}}') STORED,
            assigned_to text,
            release_manifest_ref text,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            updated_at timestamp with time zone DEFAULT now() NOT NULL,
            CONSTRAINT pk_quote_cases PRIMARY KEY (id),{_scoped("quote_cases")}
            CONSTRAINT ck_quote_cases_case_version CHECK (case_version >= 1),
            CONSTRAINT ck_quote_cases_status CHECK (status IN {_in(_QUOTE_STATUSES)}),
            -- The case's identity and version are columns, never a second
            -- copy inside the body.
            CONSTRAINT ck_quote_cases_body CHECK (
                jsonb_typeof(body) = 'object'
                AND NOT body ?| ARRAY['case_id', 'case_version', 'status']
            ),
            CONSTRAINT ck_quote_cases_message_id CHECK (
                message_id IS NOT NULL AND message_id ~ {_MESSAGE_ID} AND char_length(message_id) <= 512
            ),
            CONSTRAINT ck_quote_cases_customer_code CHECK (
                customer_code IS NOT NULL AND customer_code ~ {_CUSTOMER_CODE}
            ),
            CONSTRAINT ck_quote_cases_ycbg_no CHECK (ycbg_no ~ {_DOCUMENT_NO}),
            CONSTRAINT ck_quote_cases_document_sha256 CHECK (document_sha256 ~ {_SHA256}),
            CONSTRAINT ck_quote_cases_assigned_to CHECK (assigned_to ~ {_ACTOR}),
            CONSTRAINT ck_quote_cases_release_manifest_ref CHECK (
                btrim(release_manifest_ref) <> '' AND char_length(release_manifest_ref) <= 200
            ),
            CONSTRAINT ck_quote_cases_approver_not_pricer CHECK (
                approved_by IS NULL OR (priced_by IS NOT NULL AND approved_by <> priced_by)
            ),
            CONSTRAINT ck_quote_cases_approved_version CHECK (
                (approved_by IS NULL) = (approved_version IS NULL)
                AND approved_version < case_version
            )
        )
        """,
    f"""
        CREATE TABLE sales.order_revisions (
            id uuid NOT NULL,
            tenant_id uuid NOT NULL,
            workspace_id uuid NOT NULL,
            case_id uuid NOT NULL,
            seq integer NOT NULL,
            message_id text NOT NULL,
            received_at timestamp with time zone NOT NULL,
            document jsonb NOT NULL,
            attachment_id text GENERATED ALWAYS AS (document ->> 'attachment_id') STORED,
            attachment_sha256 text GENERATED ALWAYS AS (document ->> 'attachment_sha256') STORED,
            parser_version text GENERATED ALWAYS AS (document ->> 'parser_version') STORED,
            po_revision integer
                GENERATED ALWAYS AS ((document #>> '{{header,revision}}')::integer) STORED,
            superseded_at timestamp with time zone,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            CONSTRAINT pk_order_revisions PRIMARY KEY (id),{_scoped("order_revisions")}
            CONSTRAINT fk_order_revisions_case_id_order_cases FOREIGN KEY (case_id)
                REFERENCES sales.order_cases (id) ON DELETE CASCADE,
            CONSTRAINT ck_order_revisions_seq CHECK (seq >= 1),
            CONSTRAINT ck_order_revisions_message_id CHECK (message_id ~ {_MESSAGE_ID} AND char_length(message_id) <= 512),
            -- A line's printed values live in order_lines, once.
            CONSTRAINT ck_order_revisions_document CHECK (
                jsonb_typeof(document) = 'object' AND NOT document ? 'lines'
            ),
            CONSTRAINT ck_order_revisions_attachment_id CHECK (
                attachment_id IS NOT NULL AND attachment_id ~ {_ATTACHMENT_ID}
            ),
            CONSTRAINT ck_order_revisions_attachment_sha256 CHECK (
                attachment_sha256 IS NOT NULL AND attachment_sha256 ~ {_SHA256}
            ),
            CONSTRAINT ck_order_revisions_parser_version CHECK (
                parser_version IS NOT NULL AND parser_version ~ {_VERSION_REF}
            ),
            CONSTRAINT ck_order_revisions_po_revision CHECK (
                po_revision IS NOT NULL AND po_revision BETWEEN 0 AND 999
            )
        )
        """,
    f"""
        CREATE TABLE sales.order_lines (
            id uuid NOT NULL,
            tenant_id uuid NOT NULL,
            workspace_id uuid NOT NULL,
            revision_id uuid NOT NULL,
            position integer NOT NULL,
            po_line jsonb NOT NULL,
            line_no integer GENERATED ALWAYS AS ((po_line ->> 'line_no')::integer) STORED,
            mapping_status text NOT NULL,
            prv_code text,
            candidates jsonb DEFAULT '[]'::jsonb NOT NULL,
            mapping_confirmed_by text,
            mapping_confirmed_at timestamp with time zone,
            check_basis jsonb NOT NULL,
            suggested_delivery_date date,
            confirmed_delivery_date date,
            pc_confirmed_by text,
            pc_confirmed_at timestamp with time zone,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            updated_at timestamp with time zone DEFAULT now() NOT NULL,
            CONSTRAINT pk_order_lines PRIMARY KEY (id),{_scoped("order_lines")}
            CONSTRAINT fk_order_lines_revision_id_order_revisions FOREIGN KEY (revision_id)
                REFERENCES sales.order_revisions (id) ON DELETE CASCADE,
            CONSTRAINT ck_order_lines_position CHECK (position >= 0),
            CONSTRAINT ck_order_lines_po_line CHECK (jsonb_typeof(po_line) = 'object'),
            CONSTRAINT ck_order_lines_line_no CHECK (line_no IS NOT NULL AND line_no >= 1),
            CONSTRAINT ck_order_lines_mapping_status CHECK (
                mapping_status IN {_in(_MAPPING_STATUSES)}
            ),
            CONSTRAINT ck_order_lines_mapping_code CHECK (
                (mapping_status IN ('exact', 'candidate_confirmed')) = (prv_code IS NOT NULL)
            ),
            CONSTRAINT ck_order_lines_mapping_confirmation CHECK (
                (mapping_status = 'candidate_confirmed')
                = (mapping_confirmed_by IS NOT NULL AND mapping_confirmed_at IS NOT NULL)
                AND (mapping_confirmed_by IS NULL) = (mapping_confirmed_at IS NULL)
                AND mapping_confirmed_by ~ {_ACTOR}
            ),
            CONSTRAINT ck_order_lines_candidates CHECK (jsonb_typeof(candidates) = 'array'),
            -- Evidence of what each check compared against (spec decision 11):
            -- the checks that ran, and nothing but `LineBasis`'s own keys.
            CONSTRAINT ck_order_lines_check_basis CHECK (
                jsonb_typeof(check_basis) = 'object'
                -- `?` first: a missing key makes jsonb_typeof NULL, and a
                -- CHECK that evaluates to NULL passes.
                AND check_basis ? 'checks_run'
                AND jsonb_typeof(check_basis -> 'checks_run') = 'array'
                AND jsonb_array_length(check_basis -> 'checks_run') >= 1
                AND (check_basis - ARRAY{list(_CHECK_BASIS_KEYS)}::text[]) = '{{}}'::jsonb
            ),
            CONSTRAINT ck_order_lines_pc_confirmation CHECK (
                (pc_confirmed_by IS NULL) = (pc_confirmed_at IS NULL)
                AND pc_confirmed_by ~ {_ACTOR}
            )
        )
        """,
    f"""
        CREATE TABLE sales.order_findings (
            id uuid NOT NULL,
            tenant_id uuid NOT NULL,
            workspace_id uuid NOT NULL,
            revision_id uuid NOT NULL,
            position integer NOT NULL,
            code text NOT NULL,
            severity text NOT NULL,
            line_no integer,
            expected text,
            actual text,
            rule_version text NOT NULL,
            disposition text DEFAULT 'open' NOT NULL,
            disposition_reason text,
            disposition_value text,
            disposition_source text,
            disposition_by text,
            disposition_at timestamp with time zone,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            CONSTRAINT pk_order_findings PRIMARY KEY (id),{_scoped("order_findings")}
            CONSTRAINT fk_order_findings_revision_id_order_revisions FOREIGN KEY (revision_id)
                REFERENCES sales.order_revisions (id) ON DELETE CASCADE,
            CONSTRAINT ck_order_findings_position CHECK (position >= 0),
            CONSTRAINT ck_order_findings_code CHECK (code IN {_in(_FINDING_CODES)}),
            CONSTRAINT ck_order_findings_severity CHECK (severity IN {_in(_SEVERITIES)}),
            CONSTRAINT ck_order_findings_line_no CHECK (line_no >= 1),
            CONSTRAINT ck_order_findings_compared CHECK (
                char_length(expected) <= 200 AND char_length(actual) <= 200
            ),
            CONSTRAINT ck_order_findings_rule_version CHECK (rule_version ~ {_VERSION_REF}),
            CONSTRAINT ck_order_findings_disposition CHECK (
                disposition IN {_in(_FINDING_DISPOSITIONS)}
            ),
            -- What each decision carries (spec decision 9), and nothing else.
            CONSTRAINT ck_order_findings_disposition_shape CHECK (
                CASE disposition
                    WHEN 'open' THEN num_nonnulls(
                        disposition_reason, disposition_value, disposition_source,
                        disposition_by, disposition_at
                    ) = 0
                    WHEN 'accepted' THEN num_nonnulls(
                        disposition_reason, disposition_by, disposition_at
                    ) = 3 AND num_nonnulls(disposition_value, disposition_source) = 0
                    WHEN 'corrected_by_sales' THEN num_nonnulls(
                        disposition_value, disposition_source, disposition_by, disposition_at
                    ) = 4 AND disposition_reason IS NULL
                    WHEN 'ask_customer' THEN num_nonnulls(disposition_by, disposition_at) = 2
                        AND num_nonnulls(
                            disposition_reason, disposition_value, disposition_source
                        ) = 0
                END
            ),
            CONSTRAINT ck_order_findings_disposition_text CHECK (
                char_length(disposition_reason) <= 500
                AND char_length(disposition_value) <= 200
                AND char_length(disposition_source) <= 500
                AND disposition_by ~ {_ACTOR}
            )
        )
        """,
    f"""
        CREATE TABLE sales.messages (
            id uuid NOT NULL,
            tenant_id uuid NOT NULL,
            workspace_id uuid NOT NULL,
            message_id text NOT NULL,
            disposition text NOT NULL,
            order_case_id uuid,
            quote_case_id uuid,
            routing_reason text,
            detail text,
            owner text,
            customer_code text,
            compliance jsonb,
            processed_at timestamp with time zone NOT NULL,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            updated_at timestamp with time zone DEFAULT now() NOT NULL,
            CONSTRAINT pk_messages PRIMARY KEY (id),{_case_scoped("messages")}
            CONSTRAINT ck_messages_message_id CHECK (message_id ~ {_MESSAGE_ID} AND char_length(message_id) <= 512),
            CONSTRAINT ck_messages_disposition CHECK (disposition IN {_in(_MESSAGE_DISPOSITIONS)}),
            CONSTRAINT ck_messages_routing_reason CHECK (routing_reason IN {_in(_ROUTING_REASONS)}),
            -- Spec decision 10: exactly one disposition, and what it names.
            CONSTRAINT ck_messages_on_case CHECK (
                num_nonnulls(order_case_id, quote_case_id) <= 1
                AND (disposition IN ('case_created', 'attached_to_case'))
                    = (num_nonnulls(order_case_id, quote_case_id) = 1)
            ),
            CONSTRAINT ck_messages_routed CHECK (
                (disposition = 'routed_to_sales')
                = (routing_reason IS NOT NULL AND owner IS NOT NULL)
            ),
            CONSTRAINT ck_messages_compliance CHECK (
                compliance IS NULL
                OR (routing_reason IS NOT DISTINCT FROM 'sample_request'
                    AND jsonb_typeof(compliance) = 'object')
            ),
            CONSTRAINT ck_messages_text CHECK (
                char_length(detail) <= 500 AND char_length(owner) <= 254
                AND customer_code ~ {_CUSTOMER_CODE}
            )
        )
        """,
    f"""
        CREATE TABLE sales.artifacts (
            id uuid NOT NULL,
            tenant_id uuid NOT NULL,
            workspace_id uuid NOT NULL,
            order_case_id uuid,
            quote_case_id uuid,
            case_version integer NOT NULL,
            kind text NOT NULL,
            template_ref text NOT NULL,
            object_key text NOT NULL,
            sha256 text NOT NULL,
            content_type text NOT NULL,
            size_bytes bigint NOT NULL,
            created_by text NOT NULL,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            CONSTRAINT pk_artifacts PRIMARY KEY (id),{_case_scoped("artifacts")}
            CONSTRAINT ck_artifacts_one_case CHECK (num_nonnulls(order_case_id, quote_case_id) = 1),
            CONSTRAINT ck_artifacts_case_version CHECK (case_version >= 1),
            -- The set of kinds is ticket 06's to own in code; until then, a name.
            CONSTRAINT ck_artifacts_kind CHECK (kind ~ '^[a-z][a-z0-9_]{{2,47}}$'),
            CONSTRAINT ck_artifacts_template_ref CHECK (template_ref ~ {_VERSION_REF}),
            CONSTRAINT ck_artifacts_sha256 CHECK (sha256 ~ {_SHA256}),
            CONSTRAINT ck_artifacts_content_type CHECK (
                content_type ~ '^[a-z]+/[A-Za-z0-9.+-]{{1,100}}$'
            ),
            CONSTRAINT ck_artifacts_size_bytes CHECK (size_bytes > 0),
            CONSTRAINT ck_artifacts_created_by CHECK (created_by ~ {_ACTOR}),
            -- Ticket 06's key, derived from the row and nothing a caller chose:
            -- an object path always carries its tenant and workspace.
            CONSTRAINT ck_artifacts_object_key CHECK (
                object_key = tenant_id::text || '/' || workspace_id::text || '/sales/'
                    || coalesce(order_case_id, quote_case_id)::text || '/' || id::text
            )
        )
        """,
    f"""
        CREATE TABLE sales.source_served (
            id uuid NOT NULL,
            tenant_id uuid NOT NULL,
            workspace_id uuid NOT NULL,
            principal_id text NOT NULL,
            order_case_id uuid,
            quote_case_id uuid,
            case_version integer NOT NULL,
            attachment_id text NOT NULL,
            attachment_sha256 text NOT NULL,
            page integer,
            sheet text,
            served_at timestamp with time zone NOT NULL,
            CONSTRAINT pk_source_served PRIMARY KEY (id),{_case_scoped("source_served")}
            CONSTRAINT ck_source_served_one_case CHECK (
                num_nonnulls(order_case_id, quote_case_id) = 1
            ),
            CONSTRAINT ck_source_served_principal_id CHECK (principal_id ~ {_ACTOR}),
            CONSTRAINT ck_source_served_case_version CHECK (case_version >= 1),
            CONSTRAINT ck_source_served_attachment CHECK (
                attachment_id ~ {_ATTACHMENT_ID} AND attachment_sha256 ~ {_SHA256}
            ),
            -- A page of a PDF or a sheet of a workbook: one region, never both.
            CONSTRAINT ck_source_served_region CHECK (
                num_nonnulls(page, sheet) = 1 AND page >= 1
                AND char_length(sheet) BETWEEN 1 AND 31
            ),
            -- Recording the same view twice keeps the first: bounded by cases,
            -- versions and people, not by page loads.
            CONSTRAINT uq_source_served_tenant_id_workspace_id_principal_id
                UNIQUE NULLS NOT DISTINCT (
                    tenant_id, workspace_id, principal_id, order_case_id, quote_case_id,
                    case_version, attachment_id, page, sheet
                )
        )
        """,
    f"""
        CREATE TABLE sales.worker_state (
            tenant_id uuid NOT NULL,
            workspace_id uuid NOT NULL,
            paused boolean NOT NULL,
            changed_by text NOT NULL,
            changed_at timestamp with time zone NOT NULL,
            reason text,
            created_at timestamp with time zone DEFAULT now() NOT NULL,
            updated_at timestamp with time zone DEFAULT now() NOT NULL,
            CONSTRAINT pk_worker_state PRIMARY KEY (tenant_id, workspace_id),{_scoped("worker_state")}
            CONSTRAINT ck_worker_state_changed_by CHECK (changed_by ~ {_ACTOR}),
            CONSTRAINT ck_worker_state_reason CHECK (
                btrim(reason) <> '' AND char_length(reason) <= 500
            )
        )
        """,
)

# Partitioned: not in _TABLES, whose rows get the ordinary tail. No foreign
# keys: like platform.audit_events, the log outlives the case and the
# workspace it describes.
_CASE_EVENTS = f"""
    CREATE TABLE sales.case_events (
        id uuid NOT NULL,
        tenant_id uuid NOT NULL,
        workspace_id uuid NOT NULL,
        case_kind text NOT NULL,
        case_id uuid NOT NULL,
        case_version integer NOT NULL,
        action text NOT NULL,
        from_status text,
        to_status text NOT NULL,
        actor_kind text NOT NULL,
        actor_id text NOT NULL,
        worker_id text,
        worker_version text,
        initiated_by text,
        finding_key text,
        field text,
        reason_code text,
        occurred_at timestamp with time zone NOT NULL,
        CONSTRAINT pk_case_events PRIMARY KEY (id, occurred_at),
        CONSTRAINT ck_case_events_case_kind CHECK (case_kind IN ('order', 'quote')),
        CONSTRAINT ck_case_events_case_version CHECK (case_version >= 1),
        CONSTRAINT ck_case_events_action CHECK (
            action ~ '^(order|quote)\\.[a-z][a-z_]{{1,47}}$'
            AND split_part(action, '.', 1) = case_kind
        ),
        CONSTRAINT ck_case_events_status CHECK (
            CASE case_kind
                WHEN 'order' THEN to_status IN {_in(_ORDER_STATUSES)}
                    AND (from_status IS NULL OR from_status IN {_in(_ORDER_STATUSES)})
                ELSE to_status IN {_in(_QUOTE_STATUSES)}
                    AND (from_status IS NULL OR from_status IN {_in(_QUOTE_STATUSES)})
            END
        ),
        CONSTRAINT ck_case_events_actor_kind CHECK (actor_kind IN ('worker', 'user')),
        -- DW1 is a worker with an id and a version; a person is neither.
        CONSTRAINT ck_case_events_actor CHECK (
            actor_id ~ {_ACTOR}
            AND CASE actor_kind
                WHEN 'worker' THEN worker_id IS NOT NULL AND worker_version IS NOT NULL
                ELSE worker_id IS NULL AND worker_version IS NULL
            END
        ),
        CONSTRAINT ck_case_events_worker CHECK (
            worker_id ~ '^[a-z][a-z0-9_.-]{{0,63}}$'
            AND worker_version ~ '^\\d+\\.\\d+\\.\\d+$'
        ),
        CONSTRAINT ck_case_events_initiated_by CHECK (initiated_by ~ {_ACTOR}),
        -- Ids, codes and names only: no column here can hold an amount.
        CONSTRAINT ck_case_events_finding_key CHECK (
            finding_key ~ '^[a-z_]{{1,40}}:([1-9][0-9]{{0,4}}|-)$'
        ),
        CONSTRAINT ck_case_events_field CHECK (field ~ '^[a-z_]{{1,32}}$'),
        CONSTRAINT ck_case_events_reason_code CHECK (reason_code ~ '^[a-z_]{{1,40}}$')
    )
    PARTITION BY RANGE (occurred_at)
"""

# What a list endpoint or a lookup orders and filters by. Each leads with the
# columns RLS supplies; each foreign key is indexed on its own side.
_INDEXES: tuple[str, ...] = (
    "CREATE UNIQUE INDEX uq_order_cases_tenant_id_workspace_id_customer_code_po_no"
    " ON sales.order_cases (tenant_id, workspace_id, customer_code, po_no)"
    " WHERE duplicate_of_case IS NULL AND duplicate_of_so IS NULL",
    "CREATE INDEX ix_order_cases_tenant_id_workspace_id_created_at_id"
    " ON sales.order_cases (tenant_id, workspace_id, created_at DESC, id DESC)",
    "CREATE INDEX ix_order_cases_tenant_id_workspace_id_assigned_to"
    " ON sales.order_cases (tenant_id, workspace_id, assigned_to)",
    "CREATE INDEX ix_order_cases_workspace_id ON sales.order_cases (workspace_id)",
    "CREATE INDEX ix_order_cases_duplicate_of_case ON sales.order_cases (duplicate_of_case)",
    "CREATE INDEX ix_order_cases_superseded_by_case ON sales.order_cases (superseded_by_case)",
    "CREATE UNIQUE INDEX uq_quote_cases_tenant_id_workspace_id_message_id"
    " ON sales.quote_cases (tenant_id, workspace_id, message_id)",
    "CREATE INDEX ix_quote_cases_tenant_id_workspace_id_ycbg_no"
    " ON sales.quote_cases (tenant_id, workspace_id, ycbg_no)",
    "CREATE INDEX ix_quote_cases_tenant_id_workspace_id_created_at_id"
    " ON sales.quote_cases (tenant_id, workspace_id, created_at DESC, id DESC)",
    "CREATE INDEX ix_quote_cases_tenant_id_workspace_id_assigned_to"
    " ON sales.quote_cases (tenant_id, workspace_id, assigned_to)",
    "CREATE INDEX ix_quote_cases_workspace_id ON sales.quote_cases (workspace_id)",
    "CREATE UNIQUE INDEX uq_order_revisions_tenant_id_workspace_id_case_id_seq"
    " ON sales.order_revisions (tenant_id, workspace_id, case_id, seq)",
    "CREATE UNIQUE INDEX uq_order_revisions_tenant_id_workspace_id_message_id"
    " ON sales.order_revisions (tenant_id, workspace_id, message_id)",
    # Exactly one current revision per case.
    "CREATE UNIQUE INDEX uq_order_revisions_tenant_id_workspace_id_case_id"
    " ON sales.order_revisions (tenant_id, workspace_id, case_id) WHERE superseded_at IS NULL",
    "CREATE INDEX ix_order_revisions_case_id ON sales.order_revisions (case_id)",
    "CREATE INDEX ix_order_revisions_workspace_id ON sales.order_revisions (workspace_id)",
    "CREATE UNIQUE INDEX uq_order_lines_tenant_id_workspace_id_revision_id_line_no"
    " ON sales.order_lines (tenant_id, workspace_id, revision_id, line_no)",
    "CREATE UNIQUE INDEX uq_order_lines_tenant_id_workspace_id_revision_id_position"
    " ON sales.order_lines (tenant_id, workspace_id, revision_id, position)",
    "CREATE INDEX ix_order_lines_revision_id ON sales.order_lines (revision_id)",
    "CREATE INDEX ix_order_lines_workspace_id ON sales.order_lines (workspace_id)",
    "CREATE UNIQUE INDEX uq_order_findings_tenant_id_workspace_id_revision_id_code"
    " ON sales.order_findings (tenant_id, workspace_id, revision_id, code, line_no)"
    " NULLS NOT DISTINCT",
    "CREATE UNIQUE INDEX uq_order_findings_tenant_id_workspace_id_revision_id_position"
    " ON sales.order_findings (tenant_id, workspace_id, revision_id, position)",
    "CREATE INDEX ix_order_findings_revision_id ON sales.order_findings (revision_id)",
    "CREATE INDEX ix_order_findings_workspace_id ON sales.order_findings (workspace_id)",
    "CREATE UNIQUE INDEX uq_messages_tenant_id_workspace_id_message_id"
    " ON sales.messages (tenant_id, workspace_id, message_id)",
    "CREATE INDEX ix_messages_tenant_id_workspace_id_processed_at_id"
    " ON sales.messages (tenant_id, workspace_id, processed_at DESC, id DESC)",
    "CREATE INDEX ix_messages_order_case_id ON sales.messages (order_case_id)",
    "CREATE INDEX ix_messages_quote_case_id ON sales.messages (quote_case_id)",
    "CREATE INDEX ix_messages_workspace_id ON sales.messages (workspace_id)",
    "CREATE INDEX ix_artifacts_tenant_id_workspace_id_created_at_id"
    " ON sales.artifacts (tenant_id, workspace_id, created_at DESC, id DESC)",
    "CREATE INDEX ix_artifacts_order_case_id ON sales.artifacts (order_case_id)",
    "CREATE INDEX ix_artifacts_quote_case_id ON sales.artifacts (quote_case_id)",
    "CREATE INDEX ix_artifacts_workspace_id ON sales.artifacts (workspace_id)",
    # The source gate asks: was this principal served this case's version?
    "CREATE INDEX ix_source_served_order_case_id_case_version_principal_id"
    " ON sales.source_served (order_case_id, case_version, principal_id)",
    "CREATE INDEX ix_source_served_quote_case_id_case_version_principal_id"
    " ON sales.source_served (quote_case_id, case_version, principal_id)",
    "CREATE INDEX ix_source_served_workspace_id ON sales.source_served (workspace_id)",
    "CREATE INDEX ix_worker_state_workspace_id ON sales.worker_state (workspace_id)",
    # One case's timeline, oldest first.
    "CREATE INDEX ix_case_events_tenant_id_case_id_occurred_at_id"
    " ON sales.case_events (tenant_id, case_id, occurred_at, id)",
)

_UPDATED_AT = ("order_cases", "quote_cases", "order_lines", "messages", "worker_state")

# Append-only: the application adds rows and never rewrites one. A changed
# artifact is a new artifact; a served record is a fact about the past.
_NO_UPDATE = ("artifacts", "source_served")
_APPEND_ONLY = ("case_events", "case_events_default")


def _for_app(statement: str) -> str:
    return f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
                {statement}
            END IF;
        END
        $$
        """


# Written out per table, not generated in a loop: `scripts/verify_invariants.py`
# reads migration text, and a statement it cannot see is a table it reports as
# unpoliced. The default partition is policed in its own right (0009).
_ROW_SECURITY: tuple[str, ...] = (
    "ALTER TABLE sales.order_cases ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.order_cases FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_order_cases ON sales.order_cases"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
    "ALTER TABLE sales.quote_cases ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.quote_cases FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_quote_cases ON sales.quote_cases"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
    "ALTER TABLE sales.order_revisions ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.order_revisions FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_order_revisions ON sales.order_revisions"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
    "ALTER TABLE sales.order_lines ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.order_lines FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_order_lines ON sales.order_lines"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
    "ALTER TABLE sales.order_findings ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.order_findings FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_order_findings ON sales.order_findings"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
    "ALTER TABLE sales.messages ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.messages FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_messages ON sales.messages"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
    "ALTER TABLE sales.artifacts ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.artifacts FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_artifacts ON sales.artifacts"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
    "ALTER TABLE sales.source_served ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.source_served FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_source_served ON sales.source_served"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
    "ALTER TABLE sales.worker_state ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.worker_state FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_worker_state ON sales.worker_state"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
    "ALTER TABLE sales.case_events ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.case_events FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_case_events ON sales.case_events"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
    "ALTER TABLE sales.case_events_default ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sales.case_events_default FORCE ROW LEVEL SECURITY",
    f"CREATE POLICY tenant_isolation_case_events_default ON sales.case_events_default"
    f" USING {_SCOPE} WITH CHECK {_SCOPE}",
)

# Every preparer and Bravo recorder the case has had, in any revision. Only
# this trigger writes `makers`: it unions what the row held with the stamps
# the row now carries, so no writer can drop a name, and the checker CHECK
# reads the whole history. `apply_change` replaces `bravo_recorded_by` on a
# revised order; without this, the previous recorder could cross-check it.
_ACCUMULATE_MAKERS = """
CREATE FUNCTION sales.accumulate_order_makers() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $fn$
BEGIN
    NEW.makers := ARRAY(
        SELECT DISTINCT maker
        FROM unnest(
            CASE WHEN TG_OP = 'UPDATE' THEN OLD.makers ELSE '{}'::text[] END
            || ARRAY[NEW.prepared_by, NEW.bravo_recorded_by]
        ) AS maker
        WHERE maker IS NOT NULL
        ORDER BY maker
    );
    RETURN NEW;
END;
$fn$
"""


# Matches any dollar-quote tag (`$fn$`), as 0012 and 0013 do. Copied rather
# than imported: an applied migration's helper is history, not a library.
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


_ENSURE_ONE_PARTITION = """
CREATE OR REPLACE FUNCTION platform._ensure_one_partition(parent text, month date)
RETURNS text
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    -- `schema.table`; a bare name is the platform table it has always meant.
    nsp text := CASE WHEN strpos(parent, '.') > 0 THEN split_part(parent, '.', 1)
                     ELSE 'platform' END;
    rel text := CASE WHEN strpos(parent, '.') > 0 THEN split_part(parent, '.', 2)
                     ELSE parent END;
    parent_oid oid;
    part text := rel || '_' || to_char(month, 'YYYY_MM');
    fallback text := rel || '_default';
    stamp text;
    next_month date := (month + interval '1 month')::date;
    using_expr text;
    check_expr text;
    stranded boolean;
BEGIN
    parent_oid := to_regclass(format('%I.%I', nsp, rel));
    IF parent_oid IS NULL THEN
        RAISE EXCEPTION '%.% does not exist', nsp, rel;
    END IF;
    IF to_regclass(format('%I.%I', nsp, part)) IS NOT NULL THEN
        RETURN NULL;
    END IF;
    SELECT a.attname INTO stamp
    FROM pg_partitioned_table p
    JOIN pg_attribute a ON a.attrelid = p.partrelid AND a.attnum = p.partattrs[0]
    WHERE p.partrelid = parent_oid;
    IF stamp IS NULL THEN
        RAISE EXCEPTION '%.% is not range-partitioned', nsp, rel;
    END IF;
    -- The partition is policed exactly as its parent is: the parent's own
    -- policy, read from the catalog. A predicate written here was a second
    -- copy, and wrong for the first parent that narrows by workspace too.
    SELECT pg_get_expr(pol.polqual, pol.polrelid), pg_get_expr(pol.polwithcheck, pol.polrelid)
    INTO using_expr, check_expr
    FROM pg_policy pol
    WHERE pol.polrelid = parent_oid AND pol.polname = 'tenant_isolation_' || rel;
    IF using_expr IS NULL THEN
        RAISE EXCEPTION '%.% has no policy tenant_isolation_% to give its partition',
            nsp, rel, rel;
    END IF;

    EXECUTE format(
        'SELECT EXISTS (SELECT 1 FROM %I.%I WHERE %I >= %L AND %I < %L)',
        nsp, fallback, stamp, month, stamp, next_month
    ) INTO stranded;
    IF stranded THEN
        EXECUTE format('ALTER TABLE %I.%I DETACH PARTITION %I.%I', nsp, rel, nsp, fallback);
    END IF;

    EXECUTE format(
        'CREATE TABLE %I.%I PARTITION OF %I.%I FOR VALUES FROM (%L) TO (%L)',
        nsp, part, nsp, rel, month, next_month
    );
    -- Postgres does not inherit row security to a partition created later, and
    -- a partition addressed by name uses its own settings. FORCE as well:
    -- without it the owner reads straight past the policy, and the owner is
    -- exactly who runs this.
    EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', nsp, part);
    EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY', nsp, part);
    EXECUTE format(
        'CREATE POLICY %I ON %I.%I USING (%s) WITH CHECK (%s)',
        'tenant_isolation_' || part, nsp, part, using_expr, coalesce(check_expr, using_expr)
    );
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dw_app') THEN
        -- `ALTER DEFAULT PRIVILEGES` has already handed this partition UPDATE
        -- and DELETE. An append-only parent (the audit log, the case event
        -- log) withholds both, and so must every month of it.
        IF NOT has_table_privilege('dw_app', parent_oid, 'UPDATE') THEN
            EXECUTE format('REVOKE UPDATE ON %I.%I FROM dw_app', nsp, part);
        END IF;
        IF NOT has_table_privilege('dw_app', parent_oid, 'DELETE') THEN
            EXECUTE format('REVOKE DELETE ON %I.%I FROM dw_app', nsp, part);
        END IF;
    END IF;

    IF stranded THEN
        EXECUTE format(
            'INSERT INTO %I.%I SELECT * FROM %I.%I WHERE %I >= %L AND %I < %L',
            nsp, rel, nsp, fallback, stamp, month, stamp, next_month
        );
        EXECUTE format(
            'DELETE FROM %I.%I WHERE %I >= %L AND %I < %L',
            nsp, fallback, stamp, month, stamp, next_month
        );
        EXECUTE format(
            'ALTER TABLE %I.%I ATTACH PARTITION %I.%I DEFAULT', nsp, rel, nsp, fallback
        );
    END IF;
    RETURN part;
END;
$fn$
"""

_ENSURE_TIME_PARTITIONS = """
CREATE OR REPLACE FUNCTION platform.ensure_time_partitions(months_ahead integer)
RETURNS SETOF text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $fn$
DECLARE
    parent text;
    step integer;
    made text;
    first_month constant date := date_trunc('month', now())::date;
BEGIN
    IF months_ahead IS NULL OR months_ahead < 1 OR months_ahead > 24 THEN
        RAISE EXCEPTION 'months_ahead must be between 1 and 24, got %', months_ahead;
    END IF;
    -- The parents are a constant: no caller-supplied string names a table.
    FOREACH parent IN ARRAY ARRAY['platform.audit_events', 'sales.case_events'] LOOP
        FOR step IN 0..months_ahead LOOP
            made := platform._ensure_one_partition(
                parent, (first_month + (step || ' month')::interval)::date
            );
            IF made IS NOT NULL THEN
                RETURN NEXT made;
            END IF;
        END LOOP;
    END LOOP;
END;
$fn$
"""


def upgrade() -> None:
    op.execute("CREATE SCHEMA sales")
    # Before any table, so every table (and every partition the maintenance
    # function makes later) is born readable by the application.
    op.execute(
        _for_app(
            "GRANT USAGE ON SCHEMA sales TO dw_app;"
            " ALTER DEFAULT PRIVILEGES IN SCHEMA sales"
            " GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO dw_app;"
        )
    )
    for ddl in _TABLES:
        op.execute(ddl)
    op.execute(_CASE_EVENTS)
    op.execute("CREATE TABLE sales.case_events_default PARTITION OF sales.case_events DEFAULT")
    for statement in _ROW_SECURITY:
        op.execute(statement)
    for statement in _INDEXES:
        op.execute(statement)
    for table in _UPDATED_AT:
        op.execute(
            f"CREATE TRIGGER touch_updated_at BEFORE UPDATE ON sales.{table}"
            " FOR EACH ROW EXECUTE FUNCTION platform.touch_updated_at()"
        )
    op.execute(_ACCUMULATE_MAKERS)
    op.execute(
        "CREATE TRIGGER accumulate_makers BEFORE INSERT OR UPDATE ON sales.order_cases"
        " FOR EACH ROW EXECUTE FUNCTION sales.accumulate_order_makers()"
    )
    # Granted explicitly as well as by default: the default applies only to
    # tables created after it, by the role that set it.
    grants = [
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA sales TO dw_app;",
        *(f"REVOKE UPDATE ON sales.{table} FROM dw_app;" for table in _NO_UPDATE),
        *(f"REVOKE UPDATE, DELETE ON sales.{table} FROM dw_app;" for table in _APPEND_ONLY),
    ]
    op.execute(_for_app(" ".join(grants)))
    op.execute(_ENSURE_ONE_PARTITION)
    op.execute(_ENSURE_TIME_PARTITIONS)


def downgrade() -> None:
    # Back to the functions 0013 installed, before the table they now name goes.
    for statement in _statements((_SQL_DIR / "0013_partition_maintenance.sql").read_text("utf-8")):
        op.execute(statement)
    op.execute(
        _for_app(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA sales"
            " REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM dw_app;"
        )
    )
    # Children first; no CASCADE, so anything else that came to depend on these
    # tables stops the downgrade instead of disappearing with them.
    for table in (
        "case_events",
        "worker_state",
        "source_served",
        "artifacts",
        "messages",
        "order_findings",
        "order_lines",
        "order_revisions",
        "quote_cases",
        "order_cases",
    ):
        op.execute(f"DROP TABLE sales.{table}")
    op.execute("DROP FUNCTION sales.accumulate_order_makers()")
    op.execute(_for_app("REVOKE USAGE ON SCHEMA sales FROM dw_app;"))
    op.execute("DROP SCHEMA sales")
