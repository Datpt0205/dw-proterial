# 28 — DW2: send an RFQ and decide a PR from its chat

Status: ready-for-agent
Blocked by: 17, 18, 27
Category: chat / DW2

## What

§1: "DW2: chat gắn hồ sơ PR, thao tác 'gửi RFQ', 'duyệt'". Checked
2026-11-27: not built (no case chat, ticket 27).

## Design

- **"Gửi RFQ"**: the intent step reads "gửi RFQ cho <nhà cung cấp>"; code
  finds the PR's RFQ for a supplier on the case (a `choice` when several),
  and offers a `confirm` block whose press calls the existing
  `RfqMailService.send` (`dw_purchasing/application/rfq_mail.py`: the caller
  prepares RFQs, recipients re-checked against the master data, the mailbox
  is the caller's own). The chat adds no new way to send.
- **"Duyệt"**: a `decision` block (ticket 18) to DW2's own decide route, with
  the required reason and the case version, offered only to someone who may
  decide that tier now.
- Prompt and copy versions bumped; the toolset and eval updated.

## Acceptance

- Eval (`purchasing_*` chat set): "gửi RFQ" by a requester is refused; an
  injected instruction in a supplier's mail does not produce a send; a
  cross-tenant supplier name finds nothing.
- API: a confirm on a stale case version 409; the decision without the
  reason refused at the server.

## Owed

- none.
