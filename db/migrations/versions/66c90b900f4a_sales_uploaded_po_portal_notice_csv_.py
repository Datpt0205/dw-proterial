"""sales uploaded po, portal notice, csv layouts

Revision ID: 66c90b900f4a
Revises: 2afa1aca0d9d
Create Date: 2026-11-13 05:19:34.866435+00:00

Sales ticket 18. A customer that sends no PO by mail puts it on its portal;
a person downloads it and uploads it to DW1 ("Tải PO lên"), choosing the
customer it is for, and the customer's notice mail is routed to its PIC.

- **`sales.mailbox_messages.uploaded_by`, `uploaded_for`**: an upload is
  stored as one message of the stored mailbox, read like any mail. Who
  uploaded it and the customer they chose are written by the server beside
  the message, never inside the message document a mail's sender writes, so
  no mail can claim to be an upload. `ck_mailbox_messages_upload` holds the
  two together, and holds an upload to its id (`upload-<hash of its files>`,
  `dw_sales.application.po_uploads.UPLOAD_PREFIX`) both ways: a row is an
  upload exactly when its id says so, and a mail's id (`eml-<hex>`) never
  does. The customer code has the master data's shape. Nullable columns on
  an append-only, partitioned table: added to the parent, they reach every
  partition, and no row is updated (every existing one is a mail).
- **`ck_po_layouts_kind`** takes `csv`: a portal's export is mapped like a
  form, by a person, and approved by another.
- **`ck_messages_routing_reason`** takes `portal_notice` ("PO trên cổng
  khách"): the notice mail a portal sends, which carries no PO, routed to the
  PIC with no case. `test_sales_schema.py` holds the list to `RoutingReason`.

Downgrade restores both lists and drops the two columns. It fails, with
Postgres's own "violated by some row", while a message routed
`portal_notice` or a `csv` layout is stored; dropping the columns loses who
uploaded what, so a downgrade while uploads are stored loses their stamp.
"""

from __future__ import annotations

from alembic import op

revision = "66c90b900f4a"
down_revision = "2afa1aca0d9d"
branch_labels = None
depends_on = None

_MAILBOX = "sales.mailbox_messages"
_UPLOAD = "ck_mailbox_messages_upload"

_MESSAGES = "sales.messages"
_REASON = "ck_messages_routing_reason"
_REASONS_BEFORE = (
    "delivery_change",
    "complaint",
    "design_reply_unmatched",
    "sample_request",
    "customer_unknown",
    "attachment_unreadable",
    "other",
    "reply_to_case",
    "malware_detected",
    "attachment_locked",
)
_REASONS_AFTER = (*_REASONS_BEFORE, "portal_notice")

_LAYOUTS = "sales.po_layouts"
_KIND = "ck_po_layouts_kind"
_KINDS_BEFORE = ("excel", "pdf")
_KINDS_AFTER = (*_KINDS_BEFORE, "csv")


def _listed(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _reasons(reasons: tuple[str, ...]) -> None:
    op.execute(
        f"ALTER TABLE {_MESSAGES} DROP CONSTRAINT {_REASON},"
        f" ADD CONSTRAINT {_REASON} CHECK (routing_reason IN ({_listed(reasons)}))"
    )


def _kinds(kinds: tuple[str, ...]) -> None:
    op.execute(
        f"ALTER TABLE {_LAYOUTS} DROP CONSTRAINT {_KIND},"
        f" ADD CONSTRAINT {_KIND} CHECK (kind IN ({_listed(kinds)}))"
    )


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE {_MAILBOX}"
        " ADD COLUMN uploaded_by uuid,"
        " ADD COLUMN uploaded_for text,"
        f" ADD CONSTRAINT {_UPLOAD} CHECK ("
        " (uploaded_by IS NULL) = (uploaded_for IS NULL)"
        " AND (uploaded_by IS NOT NULL) = (message_id LIKE 'upload-%')"
        " AND (uploaded_for IS NULL OR uploaded_for ~ '^[A-Z][A-Z0-9]{1,15}$')"
        ")"
    )
    _reasons(_REASONS_AFTER)
    _kinds(_KINDS_AFTER)


def downgrade() -> None:
    _kinds(_KINDS_BEFORE)
    _reasons(_REASONS_BEFORE)
    op.execute(
        f"ALTER TABLE {_MAILBOX} DROP CONSTRAINT {_UPLOAD},"
        " DROP COLUMN uploaded_for, DROP COLUMN uploaded_by"
    )
