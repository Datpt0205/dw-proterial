"""SQLAlchemy Core tables for the `sales` schema (mirrors migrations 621864952a54
and 075dca5a6168, which made every column naming a person a uuid).

Only what the repositories read and write: constraints, policies and grants
are the migration's, and `test_sales_schema.py` holds the two together.
Generated columns are declared `Computed` so an insert never names them.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from dw_kernel.naming import NAMING_CONVENTION

metadata = sa.MetaData(schema="sales", naming_convention=NAMING_CONVENTION)

_TS = sa.TIMESTAMP(timezone=True)


def _scope() -> tuple[sa.Column[uuid.UUID], sa.Column[uuid.UUID]]:
    return (
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
    )


order_cases = sa.Table(
    "order_cases",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    *_scope(),
    sa.Column("customer_code", sa.Text, nullable=False),
    sa.Column("po_no", sa.Text, nullable=False),
    sa.Column("case_version", sa.Integer, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("received_at", _TS, nullable=False),
    # The order's due date (`OrderCase.due`), ISO text like `quote_due`, for
    # the work list's order; NULL when no line's lead time is short.
    sa.Column("due", sa.Text),
    sa.Column("rules_version", sa.Text),
    sa.Column("catalog_as_of", _TS),
    sa.Column("cross_check_required", sa.Boolean),
    sa.Column("export_control_mode", sa.Text),
    sa.Column("changes", JSONB, nullable=False),
    sa.Column("duplicate_of_case", UUID(as_uuid=True)),
    sa.Column("duplicate_of_so", sa.Text),
    sa.Column("base_so_no", sa.Text),
    sa.Column("prepared_by", UUID(as_uuid=True)),
    sa.Column("prepared_at", _TS),
    sa.Column("bravo_so_no", sa.Text),
    sa.Column("bravo_recorded_by", UUID(as_uuid=True)),
    sa.Column("bravo_recorded_at", _TS),
    sa.Column("bravo_entry_compared", sa.Boolean, nullable=False),
    sa.Column("cross_checked_by", UUID(as_uuid=True)),
    sa.Column("cross_checked_at", _TS),
    sa.Column("returned_reason", sa.Text),
    sa.Column("returned_by", UUID(as_uuid=True)),
    sa.Column("returned_at", _TS),
    sa.Column("confirmed_by", UUID(as_uuid=True)),
    sa.Column("confirmed_at", _TS),
    sa.Column("close_reason", sa.Text),
    sa.Column("closed_by", UUID(as_uuid=True)),
    sa.Column("closed_at", _TS),
    sa.Column("superseded_by_case", UUID(as_uuid=True)),
    sa.Column("assigned_to", UUID(as_uuid=True)),
    sa.Column("release_manifest_ref", sa.Text),
    # A cross-check decision recorded and not applied (ticket 14), while the
    # order awaits its cross-check: ids, an outcome and a reason code.
    sa.Column("unapplied_decision", JSONB(none_as_null=True)),
    # Written by the `accumulate_makers` trigger only.
    sa.Column("makers", ARRAY(UUID(as_uuid=True)), nullable=False, server_default="{}"),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
    sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now()),
)

order_revisions = sa.Table(
    "order_revisions",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    *_scope(),
    sa.Column("case_id", UUID(as_uuid=True), nullable=False),
    sa.Column("seq", sa.Integer, nullable=False),
    sa.Column("message_id", sa.Text, nullable=False),
    sa.Column("received_at", _TS, nullable=False),
    sa.Column("document", JSONB, nullable=False),
    sa.Column("header_corrections", JSONB, nullable=False, server_default="[]"),
    sa.Column("superseded_at", _TS),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
)

order_lines = sa.Table(
    "order_lines",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    *_scope(),
    sa.Column("revision_id", UUID(as_uuid=True), nullable=False),
    sa.Column("position", sa.Integer, nullable=False),
    sa.Column("po_line", JSONB, nullable=False),
    sa.Column("line_no", sa.Integer, sa.Computed("(po_line ->> 'line_no')::integer")),
    sa.Column("mapping_status", sa.Text, nullable=False),
    sa.Column("prv_code", sa.Text),
    sa.Column("candidates", JSONB, nullable=False),
    sa.Column("mapping_confirmed_by", UUID(as_uuid=True)),
    sa.Column("mapping_confirmed_at", _TS),
    sa.Column("check_basis", JSONB, nullable=False),
    sa.Column("suggested_delivery_date", sa.Date),
    # One per delivery, NULL until confirmed (ticket 35, migration owning it).
    sa.Column("confirmed_delivery_dates", ARRAY(sa.Date)),
    sa.Column("pc_confirmed_by", UUID(as_uuid=True)),
    sa.Column("pc_confirmed_at", _TS),
    sa.Column("corrections", JSONB, nullable=False, server_default="[]"),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
    sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now()),
)

order_findings = sa.Table(
    "order_findings",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    *_scope(),
    sa.Column("revision_id", UUID(as_uuid=True), nullable=False),
    sa.Column("position", sa.Integer, nullable=False),
    sa.Column("code", sa.Text, nullable=False),
    sa.Column("severity", sa.Text, nullable=False),
    sa.Column("line_no", sa.Integer),
    sa.Column("expected", sa.Text),
    sa.Column("actual", sa.Text),
    sa.Column("rule_version", sa.Text, nullable=False),
    sa.Column("disposition", sa.Text, nullable=False),
    sa.Column("disposition_reason", sa.Text),
    sa.Column("disposition_value", sa.Text),
    sa.Column("disposition_source", sa.Text),
    sa.Column("disposition_by", UUID(as_uuid=True)),
    sa.Column("disposition_at", _TS),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
)

quote_cases = sa.Table(
    "quote_cases",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    *_scope(),
    sa.Column("case_version", sa.Integer, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("body", JSONB, nullable=False),
    sa.Column("ycbg_no", sa.Text, sa.Computed("body #>> '{ycbg,ycbg_no}'")),
    sa.Column("received_at", _TS, nullable=False),
    # The quotation's due date, ISO text (sorts as the dates do), for the work
    # list's order (ticket 24).
    sa.Column("quote_due", sa.Text, sa.Computed("body #>> '{request,document,quote_due,value}'")),
    sa.Column(
        "priced_by", UUID(as_uuid=True), sa.Computed("(body #>> '{pricing,decided_by}')::uuid")
    ),
    sa.Column("assigned_to", UUID(as_uuid=True)),
    sa.Column("release_manifest_ref", sa.Text),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
    sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now()),
)

messages = sa.Table(
    "messages",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    *_scope(),
    sa.Column("message_id", sa.Text, nullable=False),
    sa.Column("disposition", sa.Text, nullable=False),
    sa.Column("order_case_id", UUID(as_uuid=True)),
    sa.Column("quote_case_id", UUID(as_uuid=True)),
    sa.Column("routing_reason", sa.Text),
    sa.Column("detail", sa.Text),
    sa.Column("owner", sa.Text),
    sa.Column("customer_code", sa.Text),
    sa.Column("compliance", JSONB(none_as_null=True)),
    sa.Column("model_reading", JSONB(none_as_null=True)),
    sa.Column("case_reply", JSONB(none_as_null=True)),
    sa.Column("handoff", JSONB(none_as_null=True)),
    sa.Column("layout_prefill", JSONB(none_as_null=True)),
    sa.Column("processed_at", _TS, nullable=False),
    # A routed message a person marked handled (migration `handled`): all
    # three null while it is open.
    sa.Column("handled_at", _TS),
    sa.Column("handled_by", UUID(as_uuid=True)),
    sa.Column("handled_note", sa.Text),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
    sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now()),
)

artifacts = sa.Table(
    "artifacts",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    *_scope(),
    sa.Column("order_case_id", UUID(as_uuid=True)),
    sa.Column("quote_case_id", UUID(as_uuid=True)),
    sa.Column("case_version", sa.Integer, nullable=False),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("template_ref", sa.Text, nullable=False),
    sa.Column("object_key", sa.Text, nullable=False),
    sa.Column("sha256", sa.Text, nullable=False),
    sa.Column("content_type", sa.Text, nullable=False),
    sa.Column("size_bytes", sa.BigInteger, nullable=False),
    sa.Column("created_by", UUID(as_uuid=True), nullable=False),
    sa.Column("created_at", _TS, nullable=False),
)

source_served = sa.Table(
    "source_served",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    *_scope(),
    sa.Column("principal_id", UUID(as_uuid=True), nullable=False),
    sa.Column("order_case_id", UUID(as_uuid=True)),
    sa.Column("quote_case_id", UUID(as_uuid=True)),
    sa.Column("case_version", sa.Integer, nullable=False),
    # NULL is the message's own text, served to a quote (ticket 29).
    sa.Column("attachment_id", sa.Text),
    sa.Column("attachment_sha256", sa.Text, nullable=False),
    sa.Column("page", sa.Integer),
    sa.Column("sheet", sa.Text),
    sa.Column("served_at", _TS, nullable=False),
)

worker_state = sa.Table(
    "worker_state",
    metadata,
    sa.Column("tenant_id", UUID(as_uuid=True), primary_key=True),
    sa.Column("workspace_id", UUID(as_uuid=True), primary_key=True),
    sa.Column("paused", sa.Boolean, nullable=False),
    sa.Column("changed_by", UUID(as_uuid=True), nullable=False),
    sa.Column("changed_at", _TS, nullable=False),
    sa.Column("reason", sa.Text),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
    sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now()),
)

case_events = sa.Table(
    "case_events",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    *_scope(),
    sa.Column("case_kind", sa.Text, nullable=False),
    sa.Column("case_id", UUID(as_uuid=True), nullable=False),
    sa.Column("case_version", sa.Integer, nullable=False),
    sa.Column("action", sa.Text, nullable=False),
    sa.Column("from_status", sa.Text),
    sa.Column("to_status", sa.Text, nullable=False),
    sa.Column("actor_kind", sa.Text, nullable=False),
    sa.Column("actor_id", sa.Text, nullable=False),
    sa.Column("worker_id", sa.Text),
    sa.Column("worker_version", sa.Text),
    sa.Column("initiated_by", UUID(as_uuid=True)),
    sa.Column("finding_key", sa.Text),
    sa.Column("field", sa.Text),
    sa.Column("reason_code", sa.Text),
    sa.Column("occurred_at", _TS, primary_key=True),
)

# A customer's PO form as people mapped and decided it (ticket 30, migration
# of `PoLayout`): the record in `body`, the columns constraints and lookups need.
po_layouts = sa.Table(
    "po_layouts",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    *_scope(),
    sa.Column("customer_code", sa.Text, nullable=False),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("proposed_by", UUID(as_uuid=True), nullable=False),
    sa.Column("decided_by", UUID(as_uuid=True)),
    # The platform approval (`sales.layout`) a person's proposal waits on, of
    # the same tenant and workspace (`fk_po_layouts_approval_requests`); NULL
    # for a layout DW1 learned (`e91d0c239874`, ADR 0006).
    sa.Column("approval_id", UUID(as_uuid=True)),
    sa.Column("origin", sa.Text, nullable=False, server_default="person"),
    sa.Column("body", JSONB, nullable=False),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
    sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now()),
)

# A tenant's own versions of a Sales rule, proposed and decided (ticket 19).
rule_versions = sa.Table(
    "rule_versions",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    *_scope(),
    sa.Column("key", sa.Text, nullable=False),
    sa.Column("version", sa.Text, nullable=False),
    sa.Column("document", JSONB, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("proposed_by", UUID(as_uuid=True), nullable=False),
    sa.Column("proposed_at", _TS, nullable=False),
    sa.Column("decided_by", UUID(as_uuid=True)),
    sa.Column("decided_at", _TS),
    sa.Column("comment", sa.Text),
    # The platform approval (`sales.rules`) the proposal waits on, of the same
    # tenant and workspace (`fk_rule_versions_approval_requests`, ticket 38);
    # null on a version decided before it.
    sa.Column("approval_id", UUID(as_uuid=True)),
    # Applied by the head who wrote it, with no approval (40266fbc98bf).
    sa.Column("applied_directly", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
    sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now()),
)

# Each message's processing job (ticket 25, migration 0a78ca5e96d3).
processing_jobs = sa.Table(
    "processing_jobs",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    *_scope(),
    sa.Column("message_id", sa.Text, nullable=False),
    # The order jobs queued at one instant run in (an identity: never written).
    sa.Column("seq", sa.BigInteger, sa.Identity(always=True), nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("requested_by", UUID(as_uuid=True), nullable=False),
    sa.Column("requested_at", _TS, nullable=False),
    sa.Column("attempts", sa.Integer, nullable=False),
    sa.Column("failures", sa.Integer, nullable=False),
    sa.Column("available_at", _TS, nullable=False),
    sa.Column("claimed_at", _TS),
    sa.Column("error", sa.Text),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
    sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now()),
)

# What DW1's follow-ups and morning brief delivered (ticket 42, migration
# d2b1394c67b1): one row per (follow-up, stage, case or day, wait).
followup_deliveries = sa.Table(
    "followup_deliveries",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    *_scope(),
    sa.Column("followup", sa.Text, nullable=False),
    sa.Column("stage", sa.Text, nullable=False),
    sa.Column("subject", sa.Text, nullable=False),
    sa.Column("since", _TS, nullable=False),
    sa.Column("recipients", sa.Integer, nullable=False),
    sa.Column("sent_at", _TS, nullable=False),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
)

# Master-data imports (ticket 41, migration 511ef1b71dee): one snapshot per
# import of one list, the file until it is read, and the parsed records.
catalog_snapshots = sa.Table(
    "catalog_snapshots",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    *_scope(),
    sa.Column("list", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("source", sa.Text, nullable=False),
    sa.Column("file_name", sa.Text),
    sa.Column("file_sha256", sa.Text),
    sa.Column("file_size", sa.Integer),
    sa.Column("imported_by", UUID(as_uuid=True), nullable=False),
    sa.Column("imported_at", _TS, nullable=False),
    sa.Column("as_of", _TS, nullable=False),
    sa.Column("error", sa.Text),
    sa.Column("row_count", sa.Integer, nullable=False),
    sa.Column("rejected_count", sa.Integer, nullable=False),
    sa.Column("rejected", JSONB, nullable=False),
    sa.Column("unknown_headers", JSONB, nullable=False),
    sa.Column("submitted_by", UUID(as_uuid=True)),
    sa.Column("submitted_at", _TS),
    sa.Column("approval_id", UUID(as_uuid=True)),
    sa.Column("base_snapshot_id", UUID(as_uuid=True)),
    sa.Column("decided_by", UUID(as_uuid=True)),
    sa.Column("decided_at", _TS),
    sa.Column("comment", sa.Text),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
    sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now()),
)

catalog_import_files = sa.Table(
    "catalog_import_files",
    metadata,
    *_scope(),
    sa.Column("snapshot_id", UUID(as_uuid=True), nullable=False),
    sa.Column("content", sa.LargeBinary, nullable=False),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
)

catalog_rows = sa.Table(
    "catalog_rows",
    metadata,
    *_scope(),
    sa.Column("snapshot_id", UUID(as_uuid=True), nullable=False),
    sa.Column("position", sa.Integer, nullable=False),
    sa.Column("key", sa.Text, nullable=False),
    sa.Column("record", JSONB, nullable=False),
)

# Rule drafts from a company's template ("Tạo từ tệp mẫu", migration
# 42868d8c21c5): one row per uploaded template, and its bytes until read.
rule_drafts = sa.Table(
    "rule_drafts",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    *_scope(),
    sa.Column("rule_key", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("requested_by", UUID(as_uuid=True), nullable=False),
    sa.Column("requested_at", _TS, nullable=False),
    sa.Column("file_name", sa.Text, nullable=False),
    sa.Column("file_sha256", sa.Text, nullable=False),
    sa.Column("file_size", sa.Integer, nullable=False),
    # SQL NULL for None, not JSON `null`, which `ck_rule_drafts_document` refuses.
    sa.Column("template", JSONB(none_as_null=True)),
    sa.Column("document", JSONB(none_as_null=True)),
    sa.Column("machine_read", JSONB, nullable=False),
    sa.Column("evidence", JSONB, nullable=False),
    sa.Column("problems", JSONB, nullable=False),
    sa.Column("error", sa.Text),
    sa.Column("prompt_ref", sa.Text),
    sa.Column("model_profile", sa.Text),
    # A draft from a person's words (`71305f72d962`, ADR 0006).
    sa.Column("request", sa.Text),
    sa.Column("focus", sa.Text),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
    sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now()),
)

rule_draft_files = sa.Table(
    "rule_draft_files",
    metadata,
    *_scope(),
    sa.Column("draft_id", UUID(as_uuid=True), nullable=False),
    sa.Column("content", sa.LargeBinary, nullable=False),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
)

# Each live measurement of a model step (dw_sales ADR 0005, addendum of
# 2026-10-23, migration 2d97d03c937a): append-only, narrowed by tenant only.
model_step_measurements = sa.Table(
    "model_step_measurements",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    *_scope(),
    sa.Column("step", sa.Text, nullable=False),
    sa.Column("model", sa.Text, nullable=False),
    sa.Column("prompt", sa.Text, nullable=False),
    sa.Column("metric", sa.Text, nullable=False),
    sa.Column("value", sa.Numeric(5, 4), nullable=False),
    sa.Column("bar", sa.Numeric(5, 4), nullable=False),
    sa.Column("passed", sa.Boolean, nullable=False),
    sa.Column("dataset", sa.Text, nullable=False),
    sa.Column("measured_at", _TS, nullable=False),
    sa.Column("recorded_by", sa.Text, nullable=False),
    sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
)

# The stored mailbox (ticket 43, migration e544ff20fad6): each message whole in
# `message`, the keys the queries need beside it, and each attachment's bytes.
# Both append-only and partitioned by month on `received_at`.
mailbox_messages = sa.Table(
    "mailbox_messages",
    metadata,
    sa.Column("tenant_id", UUID(as_uuid=True), primary_key=True),
    sa.Column("workspace_id", UUID(as_uuid=True), primary_key=True),
    sa.Column("message_id", sa.Text, primary_key=True),
    sa.Column("received_at", _TS, primary_key=True),
    sa.Column("sender_address", sa.Text, nullable=False),
    sa.Column("internet_message_id", sa.Text),
    sa.Column("source_name", sa.Text, nullable=False),
    sa.Column("message", JSONB, nullable=False),
    sa.Column("stored_at", _TS, nullable=False, server_default=sa.func.now()),
)

mailbox_attachments = sa.Table(
    "mailbox_attachments",
    metadata,
    sa.Column("tenant_id", UUID(as_uuid=True), primary_key=True),
    sa.Column("workspace_id", UUID(as_uuid=True), primary_key=True),
    sa.Column("message_id", sa.Text, primary_key=True),
    sa.Column("received_at", _TS, primary_key=True),
    sa.Column("attachment_id", sa.Text, primary_key=True),
    sa.Column("content", sa.LargeBinary, nullable=False),
    sa.Column("stored_at", _TS, nullable=False, server_default=sa.func.now()),
)

# Every file the drop lane handled and what became of it, so a restart does
# not parse the folders' history again (ticket 43).
mailbox_files = sa.Table(
    "mailbox_files",
    metadata,
    sa.Column("tenant_id", UUID(as_uuid=True), primary_key=True),
    sa.Column("workspace_id", UUID(as_uuid=True), primary_key=True),
    sa.Column("source_name", sa.Text, primary_key=True),
    sa.Column("handled_at", _TS, primary_key=True, server_default=sa.func.now()),
    sa.Column("outcome", sa.Text, nullable=False),
    sa.Column("message_id", sa.Text),
    # A refused file's reason (`2b666371099a`).
    sa.Column("reason", sa.Text),
)

# Export control, WIV-03-032: the latest result per customer and step
# (`1a21c3a78c93`).
export_control_screenings = sa.Table(
    "export_control_screenings",
    metadata,
    *_scope(),
    sa.Column("customer_code", sa.Text, primary_key=True),
    sa.Column("step", sa.Text, primary_key=True),
    sa.Column("outcome", sa.Text, nullable=False),
    sa.Column("checked_on", sa.Date, nullable=False),
    sa.Column("fiscal_year", sa.Integer),
    sa.Column("answers", JSONB, nullable=False),
    sa.Column("note", sa.Text),
    sa.Column("evidence_file_id", UUID(as_uuid=True)),
    sa.Column("evidence_sha256", sa.Text),
    sa.Column("evidence_content_type", sa.Text),
    sa.Column("evidence_size", sa.Integer),
    sa.Column("recorded_by", UUID(as_uuid=True), nullable=False),
    sa.Column("recorded_at", _TS, nullable=False),
)

# WIV-03-023 step 11: the quotations Sales sent and confirmed, which a later PO
# line is checked against (`c1c192e011e1`). Appended, never changed.
recorded_quotations = sa.Table(
    "recorded_quotations",
    metadata,
    *_scope(),
    sa.Column("quote_no", sa.Text, primary_key=True),
    sa.Column("prv_code", sa.Text, primary_key=True),
    sa.Column("customer_code", sa.Text, nullable=False),
    sa.Column("quotation", JSONB, nullable=False),
    sa.Column("recorded_at", _TS, nullable=False, server_default=sa.func.now()),
)
