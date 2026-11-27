# 03 — Admin page: each mailbox's state, inbound and outbound

Status: ready-for-agent
Blocked by: 01
Category: platform / mail

## What

§5: "Trang admin: trạng thái từng hộp thư (có thư mục, thư cuối, biên nhận
cuối)". Checked 2026-11-27: not built; `apps/web/app/admin` has no mailbox
page. Today an admin learns a flow is missing only from a failed send
(`not_connected`, `dw_purchasing/application/rfq_mail.py:340`) or from a
person who noticed.

## Design

- **One read, owned by the platform:** `GET /api/v1/admin/mailboxes`
  (member-admin scope, the workspace's members only). Per member with a
  mailbox: inbound folder present, last mail arrived and quiet since (ticket
  01's `platform.mail_folder_watch`), outbound folder connected
  (`OutboxFolderPort.connected`), and which DW reads the folder (the scopes
  each context's lane reads by, `OwnedFolders`).
- **Last receipt** is each context's fact (DW1's outbound mails, DW2's RFQ
  mails): the platform declares `MailboxSendsPort` (`last_sent`,
  `last_failed` per mailbox), each context satisfies it from its own table,
  and the composition root (`apps/api/src/dw_api/bootstrap/wiring.py`) passes
  the list. The platform never reads `sales.*` or `purchasing.*`.
- **Web:** `/admin/mailboxes`, an antd `Table` (one row per person; times in
  giờ Việt Nam through `lib/dates.ts`; "Chưa có thư mục", "Im lặng từ …" as
  status tags with text); a row links to the person's member page. No
  subject, sender or body of any mail on the page.

## Acceptance

- Unit: the view composes inbound, outbound and each context's last send.
- API: refused without the scope (403); another workspace's members absent;
  another tenant's never (negative test).
- Web: every region state; the table at 390 px scrolls inside its container.

## Owed

- none.
