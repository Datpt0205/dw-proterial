# 79 — One place for a person's work: the item opens with its chat and in-place actions

Status: in-progress — assigning from the chat done 2026-11-26; the item's chat and the PRV code card in "Việc của tôi" done 2026-11-27; approve/return said in the chat and the PC-date card left
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

**2026-11-27, slice 2: the item in "Việc cần làm" opens its case's chat and
picks a line's PRV code.** Web only: no route, prompt, copy or migration.
Three commits on `feat/dw1-uat-gateway`:
- `1996c8dd` fix: the item of an order seen only through its NOC/ESF hold
  (ticket 78 lists it as the export PIC's work) drew the case page's buttons
  with the full viewer; it narrows with `onHeldOrder` as the case page does.
- `eafff25d` the chat: an order or quotation item has "Hỏi DW1 về hồ sơ
  này", which opens the case's own conversation in a drawer (right from
  `lg`, bottom sheet below), mounted on first open (nothing is marked seen
  before it is read), with the controls the case page offers it and the work
  list read again after a decision in it (a flag, giving the case to a
  person). The general widget hides while it is open. The offer conditions
  moved out of both case pages into `orders|quotes/[caseId]/chat-offers.tsx`,
  one owner for page and item.
- `7b270868` the code card: "N dòng chưa có mã PRV", the first five lines with
  the lines table's own "Chọn mã" (`PickCodeButton`, the condition and the
  refusal in one place) and the candidate picker behind it, the rest linked to
  the case; one line at a time, focus moves to the next line's button after a
  confirm (ui-quality §7). The source drawers moved out of the order page
  (`order-source.tsx`, `useOrderSource`), so the picker's "Xem nguồn" works in
  the item; the item reads `useServedRevision`, so a source served from it
  reaches the buttons' source gate at once. The server still checks
  `sales.order.prepare` and the case version (`confirm_mapping`).

Decisions taken against the plan's critique (each checked in the code):
- **A drawer, not the chat inline in the row.** `AssistantChat` follows its
  newest turn by scrolling the nearest scrolling ancestor; inside a row that
  is `.ant-table-body` (the list has `scroll.y`), so the list would jump. A
  drawer is a portal and is the phone layout §9 asks for anyway. Inline at
  `lg` would need a scroll boundary in `@dw/ui` first.
- **No accordion.** rc-table keeps an expanded row mounted after it was
  opened once, so one-open-at-a-time would not bound what is mounted; the
  chat is mounted only once its drawer is opened, and the widget's hide hook
  lives only while the drawer is open, so a hidden row never holds it.
- **Typed chat parts stay out of `@dw/ui`** (the ticket's "What" said parts
  in `@dw/ui`): `ChatTurn.action` and `ProposalConfirm` already carry the
  decision bound by hash and version; lifting them waits for a second user
  (DW2), per code-quality.md "Where this stops".

Tests: web `today-page` +10 (held order, chat read only when opened, the
page's own control offered, a decision reloads the work, widget hidden and
back, mail item has no chat; one "Chọn mã" per line that needs it with the
confirm call and focus moving on, five shown and the rest linked, refused on
a held order, a source served from the item updates the gate),
`chat-offers` 6 (the offer conditions themselves; `case-chat.test` passes
its own offers and could not catch a drift). Mutations, each red then
restored: no `onHeldOrder`; `offers={}`; `onDecided` dropped; no widget hide;
the reminder status; the agent-kind check; `needsCode` accepting `exact`;
five raised to 50; no focus move; no `useServedRevision`; the refusal
ignoring the scope. Whole web suite: 920/921, the one red
`quote-preview.test.tsx` timing out at 22 s under the full run and green
alone (twice), untouched by this change.

Not measured: the rendered page. No local stack was up, so the drawer at
320/390 px and on both sides of `lg`, and the list keeping its scroll when the
item's chat answers, are owed to a Playwright look (ui-quality, closing
section). The unread dot of a case read from the item's chat stays on the row
until the list is read again (any decision, or a reload): `useUnreadCases`
has no reload, and a stale hint was preferred to a second read per open.
Pre-existing, noted: the quotation page never calls `useCaseChatDecided`, so
a case given from a quote's own page conversation does not reload that page
(the item does).

Left: an approval or a return said as a sentence in the chat (a new
`question_intent` kind, a migration to the turns' kind CHECK, and a live
measurement in ticket 83's attestation run); the buttons for the same
decisions are already in the item. Accepting PC's date waits on ticket 77's
PC-reply lane (DW reading `pc_dates` on its own).
