# 17 — Typed chat messages from the server: card, confirm, choice, table, file

Status: ready-for-agent
Blocked by: none
Category: chat

## What

§1: "Tin nhắn có kiểu (`card`, `decision`, `form`, `choice`, `file`, `table`)
do server gửi, thay cho một ô `action` tự do". Checked 2026-11-27: not
built. `@dw/ui`'s `ChatTurn` carries `action?: ReactNode`
(`packages/typescript/ui/src/assistant-chat.tsx:88`, drawn at :321), and
DW1 fills it with one "Xác nhận" button bound to a proposal's hash
(`apps/web/app/sales/_components/assistant-conversation.tsx:86-124`; actions
`decide_finding`, `bravo_write`, `assign`: `dw_sales/application/assistant.py:252`).
When a name matches several people, the answer lists them in words
(`assistant.py:1381`, `assign_which`) instead of offering a pick.

This ticket builds the block protocol and the four read-or-confirm blocks;
`decision` is ticket 18, `form` ticket 19, `file` ticket 23.

## Design

- **One schema, one owner:** `dw_platform.domain.chat_blocks` (Pydantic v2,
  discriminated union on `type`): `card` (title, fields as label/value text,
  link), `confirm` (statement, subject version, content hash, button label),
  `choice` (prompt, options each with a label and an opaque value code made),
  `table` (columns, rows of text). Exported to
  `contracts/jsonschema/chat_blocks.json`; the generated client types follow.
  Every value a block carries is code's, never a model's id: a model's name
  for a person becomes a `choice` of the candidates code found.
- **The frame draws them** (`AssistantChat`: `ChatTurn.blocks?: ChatBlock[]`,
  antd only: `Card`, `Descriptions`, `Radio.Group`/`Button`s, `Table`); a
  press calls the page's handler (`onConfirm`, `onChoose`) with the block,
  so the frame still starts nothing itself. `action` stays for a page's own
  control until every DW1 action is a block, then goes.
- **DW1 moves first:** a turn's `proposal` becomes a `confirm` block (same
  hash and case-version binding, same route); `assign_which` becomes a
  `choice` of the candidates, whose press asks the assign confirm for that
  person. The turn's stored shape gains `blocks` (migration on
  `sales.assistant_turns`, old rows read as before).

## Acceptance

- Schema round-trip tests; an unknown `type` refused at the API.
- Vitest (`@dw/ui`): each block renders with its words and states; a press
  calls the handler once (double-click safe).
- DW1: a confirm still refuses a stale hash or case version at the server;
  a choice's value not among the current candidates is refused (negative
  test); another tenant's turn 404.
- Mutation: the server accepting a choice value it did not offer → red.

## Owed

- none.
