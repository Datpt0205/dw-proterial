# 79 — One place for a person's work: the item opens with its chat and in-place actions

Status: in-progress — assigning a person from the case's chat done 2026-11-26; the item's chat in "Việc của tôi" and the other cards left
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

## Comments

**2026-11-26, slice 1: give the case to a person from its conversation.**
The head writes "giao cho Diệu"; `sales.question_intent@1.5.0` reads it as
`assign_case` with the name as written (never an id); code looks for exactly
one of `AssignmentService.candidates` by the whole name or the given name
(diacritics folded), says it back ("Giao hồ sơ … cho Hoàng Thị Diệu?"), and
the turn carries a `ProposedAssignment` bound by hash and case version. The
button reads "Giao cho Hoàng Thị Diệu"; pressing it runs "Giao lại" itself
(`AssignmentService.reassign`), which checks `sales.case.assign` and the
version again and notifies the person. Someone without the right is told
it is not theirs to give; a name matching nobody or several asks who, with
the list. A quotation's conversation binds its version now too.
- Migration `1bf300e276b7`: the turns' kind and proposal CHECKs admit
  `assign_case` (the kinds test caught the missing admission first).
- Copy `sales_assistant@1.4.0` (`assign_*`), prompt bundle 1.8.0.
- `INTENT_TOKENS` 1500 → 1600: 1.4.0 rendered at 1486, a kind more did not
  fit; the step's input room is 6000.
- Tests: unit 5 (+80 chat), web 6, Postgres schema, migration down/up.
  Mutations red: the right check in the chat, the name matching.
- Not measured on a live model: the prompt's new kind joins the plant's
  attestation run (ticket 83); until then the chat step is the tenant's
  `model_assist.case_chat` switch as before.

Left: the item in "Việc của tôi" opening with its case's chat; cards for an
item code, PC's date, approve/return (typed chat parts in `@dw/ui`).
