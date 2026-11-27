# 25 — A person's signature on mail DW sends from their mailbox

Status: ready-for-agent
Blocked by: none
Category: mail / platform

## What

§5: "Thân thư HTML và chữ ký". Checked 2026-11-27: partly. The flow's job
already carries the body as HTML, made from text
(`dw_platform/application/outbox_folder.py:46`, `body_html`, escaped, line
breaks as `<br>`), which is what both DWs need for now; no signature is
added anywhere.

## Design

- `platform.mail_signatures` (tenant, workspace, user, text; bounded with
  `char_length`; RLS narrowed to the person like `push_subscriptions`;
  migration with grants). Set on the profile page ("Chữ ký thư"), plain text
  only, so nothing a person types becomes markup.
- `flow_job` gains `signature_text`, escaped and appended to `body_html`
  after a separator, in the one function both DWs call (one owner of the
  job's shape); each sending lane reads the sender's signature through a
  platform port and passes it.
- The preview on DW1's send panel and DW2's RFQ shows the signature as it
  will go.

## Acceptance

- Unit: `flow_job` escapes the signature (`<script>` arrives as text); no
  signature, no separator.
- PostgreSQL: a person reads and writes only their own signature; another
  tenant's unreadable.
- Vitest: the profile field and the send preview.

## Owed

- Đạt, on the first flow set up: whether Outlook adds the person's own
  signature to "Send an email (V2)" as well (measure, then keep one).
