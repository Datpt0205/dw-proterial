# 79 — One place for a person's work: the item opens with its chat and in-place actions

Status: ready-for-agent
Blocked by: none
Category: enhancement (UX; platform chat parts)

## Why

The case chat lives on the case page only; "Việc của tôi" lists items with
buttons but no chat, no item-code picker, no reassign. The chat frame can show
one free `action` slot and one "Xác nhận"; it cannot ask the person to pick a
person, approve, or fill a field. Asked by Đạt (11-26): can a user assign a
person straight from the chat? Not today.

## What

- `@dw/ui` chat: typed message parts sent by the server (`decision`,
  `choice`, `form`, `card`), each bound to the subject's version.
- Cards DW1 needs first: approve/return (cross-check, Manager, Bravo write);
  **assign a person** (candidates from `ScopeHoldersPort`, the list the
  reassign button uses; the head's scope decides); pick or confirm a PRV item
  code; accept PC's date (ticket 77).
- "Việc của tôi": an item expands to the case's proposal, its buttons and its
  chat; the button and the sentence in the chat call the same command.
- Lift-ready: the parts live in `@dw/ui`; DW2 reuses them.

## Acceptance

- From the chat a head assigns the case to a holder of the scope; a person
  without the assign scope is refused at the API (not only hidden).
- An approval decided in the chat equals one decided on `/approvals`
  (same version check, same audit).
