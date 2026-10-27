# 43 — DW1 reads real mail: `.eml` files dropped in a folder, kept in PostgreSQL

Status: done (2026-10-27); the plant run owed
Blocked by: —
Category: enhancement

## Why

Proterial will not give DW1 access to Microsoft 365 (2026-10-27): their
administrators are in Japan and no app registration or shared mailbox is on
offer. Đạt measured the way around it on his own FPT account the same day: a
Sales PIC's own Power Automate flow (standard connectors only) exports each
mail that reaches the Inbox from outside the company as an `.eml` file into
their OneDrive for Business; a Windows PC in the plant syncs that folder and
shares it on the LAN. The customer guide is
`Huong-dan_Proterial_Chuyen-thu-Outlook-sang-DW1_Power-Automate.docx`
(kept outside the repository). Every mail from outside goes, unfiltered: DW1
already tells an order from an RFQ, a reply and mail that is none of them.

So DW1 needs a mailbox that is a folder of `.eml` files. Until now its only
`InboxPort` is the fictional mock.

## Shape

- **The folder is a drop box, not the mailbox.** PostgreSQL is the system of
  record: the worker's `sales_mail_drop` lane reads each new file once and
  stores the message and its attachments; the API and the worker read the
  stored mailbox (`SqlMailbox`, an `InboxPort`). The API never mounts the
  folder.
- **Parsed in the reader sandbox.** An `.eml` is the sender's bytes: MIME is
  parsed by the `mail.read` operation in `apps/reader`, like every other
  customer file. The reply is validated into `InboundMessage` on arrival.
- **The message id is the file's sha256** (`eml-<hex>`), and `received_at`
  is read from the file (the receiving server's topmost `Received:` stamp,
  else `Date:`), so the same file always lands on the same key: a second copy
  is a primary-key conflict, `ON CONFLICT DO NOTHING`. A file with neither
  date is refused.
- **Who sent it is the topmost `Authentication-Results`**, the one the
  receiving server prepends; one the sender wrote sits below it.
- **Attachments**: parts with `Content-Disposition: attachment`, or a file
  name and no `inline`; inline images (signature logos) are not attachments.
- **Append-only, range-partitioned by month on `received_at`** with a DEFAULT
  partition, both tables in `platform.ensure_time_partitions`. RLS in the
  workspace shape. `dw_app` holds SELECT and INSERT only.
- **Which mailbox** is one setting both processes read,
  `DW_SALES_MAILBOX=mock|stored` (default `mock`, the demo). `stored` with
  the lane needs `DW_SALES_MAIL_DROP_DIR` in the worker.
- **The lane audits as itself**: one `sales.mail.stored` event per message it
  stored, in the same transaction. A refused file is logged, by name and
  reason, never by content.

## Acceptance

1. `mail.read` turns an `.eml` into an `InboundMessage` and its attachment
   bytes: sender, recipients, subject (RFC 2047), bodies (HTML only gives a
   text body too), references, authentication, attachments with RFC 2231
   names; refuses a file with no sender or no date.
2. `sales.mailbox_messages` and `sales.mailbox_attachments`: RLS
   ENABLE/FORCE on parent and DEFAULT, append-only grants, partitions made by
   `ensure_time_partitions`; a cross-tenant read returns nothing.
3. The lane stores each new file once (a restart, a second worker, a copy of
   the same file); a file over 20 MB, or one the reader refuses, is skipped
   with a log line and not read again until the process restarts.
4. With `DW_SALES_MAILBOX=stored`, a stored message appears in the inbox, the
   `sales_inbox` lane queues it, and its attachment is read through
   `ScannedInbox` like a mock one.

## Owed

- **Retention of stored mail.** Nothing deletes it. A case's evidence points
  into its message's attachments, so a term must follow the cases', not a
  calendar of its own. Đạt's decision.
- `InboxPort.list_messages` returns the whole mailbox on every call, as the
  mock did. Fine for a year of one plant's mail; a window belongs to the port
  when the volume says so.
