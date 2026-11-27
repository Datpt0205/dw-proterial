# 36 — Reply in the customer's own thread

Status: needs-info (Đạt: measure the flow's reply first)
Blocked by: a measurement on a Power Automate flow
Category: mail

## What

§5: "Trả lời **trong cùng luồng thư** của khách (In-Reply-To): hiện mỗi lần
gửi là một thư mới". Checked 2026-11-27: not built. The job has no reply
field (`dw_platform/application/outbox_folder.py:27-49`: job, from, to, cc,
subject, body_html, attachments) and the documented flow sends with "Send an
email (V2)" (`infra/onprem/README.md:182`), which starts a new message.

## Why it waits

Which Outlook action replies inside an existing thread, and which id it
needs (the message's id in the mailbox, or its Internet message id), is a
fact about Power Automate's connector, not something to assume
(`failure-modes.md` #4). Until a flow is measured, code cannot know what to
put in the job.

## Design (after the measurement)

- DW already keeps each received mail's message id (the context's
  `message_id` columns). The job gains an optional reply reference (the id
  the measured action takes), `flow_job` writes it, and the flow branches:
  reply when present, send otherwise. The subject keeps the thread's.
- The reply reference is code's, from the case's own received mail, never
  typed or model-read; a reply to a mail of another case is refused.

## Acceptance (after the measurement)

- Unit: the job carries the reference only for a mail of the same case.
- On the measured flow: a reply lands in the customer's thread (Đạt).

## Owed

- Đạt: one test flow with a reply action, sent to an outside address, and
  what id it took; then this ticket becomes ready-for-agent (S). Sales
  ticket 23 (does a sent mail's export keep its thread headers) needs the
  same test mailbox: measure both in one session.
