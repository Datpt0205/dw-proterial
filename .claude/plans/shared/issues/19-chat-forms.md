# 19 — Small forms in the chat: a date, a quantity

Status: ready-for-agent
Blocked by: 17
Category: chat

## What

§1: "Form nhỏ trong chat (sửa ngày, số lượng) thay cho gõ tự do". Checked
2026-11-27: not built. DW1's chat proposes an SO line's confirmed date or
quantity from words (Sales ticket 56 slice 2) and the PC date card is left in
Sales ticket 79.

## Design

- **A `form` block** (in `dw_platform.domain.chat_blocks`): fields typed
  `date` (calendar day), `quantity` (decimal with the line's unit and
  bounds), `text` (with a max length); each field's current value and the
  subject's version. The frame draws an antd `Form` inside the bubble
  (`validateTrigger="onBlur"`, labels visible, the Vietnamese decimal comma,
  dates through `lib/dates.ts`).
- **The server validates again** with the same domain rule the order page
  uses (one owner), and turns the submitted values into the existing
  proposal (`bravo_write` for an SO line; PC's date for ticket 79's card),
  which still goes through its approval.
- DW1 offers it when the intent is "change the date/quantity" with no value
  read, or when the value read is ambiguous.

## Acceptance

- Unit: a date before the order date or a quantity out of bounds refused by
  the server with the field named; a submitted form on a stale version 409.
- Vitest: the form's states (blur check, the summary alert, loading).
- Negative: a form submitted for a line of another case or tenant is 404.

## Owed

- none.
