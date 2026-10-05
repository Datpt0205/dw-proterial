"""SQLAlchemy Core tables for the `sales` schema (mirrors migration 621864952a54).

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
    sa.Column("rules_version", sa.Text),
    sa.Column("catalog_as_of", _TS),
    sa.Column("cross_check_required", sa.Boolean),
    sa.Column("export_control_mode", sa.Text),
    sa.Column("changes", JSONB, nullable=False),
    sa.Column("duplicate_of_case", UUID(as_uuid=True)),
    sa.Column("duplicate_of_so", sa.Text),
    sa.Column("base_so_no", sa.Text),
    sa.Column("prepared_by", sa.Text),
    sa.Column("prepared_at", _TS),
    sa.Column("bravo_so_no", sa.Text),
    sa.Column("bravo_recorded_by", sa.Text),
    sa.Column("bravo_recorded_at", _TS),
    sa.Column("bravo_entry_compared", sa.Boolean, nullable=False),
    sa.Column("cross_checked_by", sa.Text),
    sa.Column("cross_checked_at", _TS),
    sa.Column("returned_reason", sa.Text),
    sa.Column("returned_by", sa.Text),
    sa.Column("returned_at", _TS),
    sa.Column("confirmed_by", sa.Text),
    sa.Column("confirmed_at", _TS),
    sa.Column("close_reason", sa.Text),
    sa.Column("closed_by", sa.Text),
    sa.Column("closed_at", _TS),
    sa.Column("superseded_by_case", UUID(as_uuid=True)),
    sa.Column("assigned_to", sa.Text),
    sa.Column("release_manifest_ref", sa.Text),
    # Written by the `accumulate_makers` trigger only.
    sa.Column("makers", ARRAY(sa.Text), nullable=False, server_default="{}"),
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
    sa.Column("mapping_confirmed_by", sa.Text),
    sa.Column("mapping_confirmed_at", _TS),
    sa.Column("check_basis", JSONB, nullable=False),
    sa.Column("suggested_delivery_date", sa.Date),
    sa.Column("confirmed_delivery_date", sa.Date),
    sa.Column("pc_confirmed_by", sa.Text),
    sa.Column("pc_confirmed_at", _TS),
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
    sa.Column("disposition_by", sa.Text),
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
    sa.Column("assigned_to", sa.Text),
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
    sa.Column("processed_at", _TS, nullable=False),
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
    sa.Column("created_by", sa.Text, nullable=False),
    sa.Column("created_at", _TS, nullable=False),
)

source_served = sa.Table(
    "source_served",
    metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True),
    *_scope(),
    sa.Column("principal_id", sa.Text, nullable=False),
    sa.Column("order_case_id", UUID(as_uuid=True)),
    sa.Column("quote_case_id", UUID(as_uuid=True)),
    sa.Column("case_version", sa.Integer, nullable=False),
    sa.Column("attachment_id", sa.Text, nullable=False),
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
    sa.Column("changed_by", sa.Text, nullable=False),
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
    sa.Column("initiated_by", sa.Text),
    sa.Column("finding_key", sa.Text),
    sa.Column("field", sa.Text),
    sa.Column("reason_code", sa.Text),
    sa.Column("occurred_at", _TS, primary_key=True),
)
