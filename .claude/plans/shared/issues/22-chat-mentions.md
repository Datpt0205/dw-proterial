# 22 — @mention a colleague in a case's chat

Status: ready-for-agent
Blocked by: none
Category: chat / notifications

## What

§1: "@nhắc tên một người trong ô gõ, người đó nhận thông báo kèm link tới câu
chat". Checked 2026-11-27: not built (no mention handling in `apps/web` or
`@dw/ui`).

## Design

- **Who can be mentioned is the server's answer:** members who may read this
  case (the case's visibility rule, `sees_case`), from
  `GET /api/v1/sales/{kind}/{id}/mentionable`. The Sender (antd X) opens that
  list on `@`; the turn stores the mentioned user ids.
- **Checked where it is written:** a mention of someone who may not read the
  case is refused without saying whether they exist; the text still goes to
  the model as untrusted input (the mention changes nothing it may do).
- **Told:** a notice through `deliver` ("<người> nhắc bạn trong <hồ sơ>"),
  source key with the turn, link `/sales/{orders|quotes}/{id}?turn=<seq>`;
  the case page opens its chat at that turn.
- Conversations are each person's own today (RLS by user, migration
  `bfe2d1aeadcd`): the mentioned person sees the mentioning turn as a quote
  in their notice and the case's record, not the other person's whole
  conversation. Whether a case chat becomes shared is ticket 35's decision.

## Acceptance

- API: the mentionable list excludes a member who cannot read the case;
  mentioning them is refused; another tenant's member never listed
  (PostgreSQL).
- Unit: one notice per mention per turn; the link opens the turn.
- Mutation: the visibility filter on the list removed → red.

## Owed

- none (what a mentioned person sees of the conversation follows ticket 35).
