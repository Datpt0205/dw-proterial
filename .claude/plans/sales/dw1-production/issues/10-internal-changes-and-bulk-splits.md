# 10 — Changes Proterial makes itself: overcapacity, NG, short stock

Status: done (2026-11-16)
Blocked by: none (an example notice to the customer improves it)
Category: enhancement

## Why

Drawio 2b (6.1B): after confirmation, PC may move or split the dates of
many lines at once, or cancel lines. DW1 handles a customer's revision
(`change_review`), not a change that starts inside Proterial.

## Shape

- "Thay đổi nội bộ" on a confirmed order takes the reason (overcapacity,
  NG, short stock, other) and the lines with their new dates or quantities,
  pasted from PC's mail and read the way item 7 reads.
- It produces the change list to apply in Bravo ("Thay đổi chi tiết") and a
  drafted notice to the customer, and sends the case back to cross-check.

## Acceptance

1. A bulk split of 20 lines makes one change list and one notice.
2. Nothing on the case changes before a person applies it.

## Comments

## Done

2026-11-16:

- **One loop, one change list.** "Áp dụng" (`POST /orders/{id}/internal-change`,
  `application/internal_changes.py`) applies the reason
  (`overcapacity | ng | short_stock | other`) and the lines a person checked,
  each with PC's deliveries, through `OrderIntake.take_internal_change` →
  `OrderCase.take_internal_change`: the order enters ticket 29's update loop
  at `bravo_update` (`UpdateLoop.reason` set, no verdict, PC's answer on every
  line; a cut is an `AppliedChange` of the quantity) in `change_review`, its
  cross-check and confirmation cleared. The change list for Bravo's "Thay đổi
  chi tiết" is the loop's existing Bravo update file (`bravo_update`, a row per
  delivery of the changed lines, PC's first and current dates), approved by id
  and hash, entered, cross-checked by someone who made none of it (the
  applier is a maker), confirmed again. `update_accepted` and `take_update`
  share `_loop_applied`/`_loop_taken` with it (one owner of what a loop line
  becomes). Refused: before the confirmation left (`change_status`), another
  change in the loop (`update_busy`), a line the order does not have
  (`no_such_line`), more than ordered (`quantity_raised`), a printed
  schedule's quantities (`printed_schedules`), nothing changed (`no_change`),
  a line named twice (`line_named_twice`). Event
  `order.internal_change_applied` with the reason code; no value audited.
- **Read the way item 7 reads** (`POST /orders/{id}/internal-change/read`,
  `domain/internal_changes.py`, prompt `sales.internal_change@1.0.0`): the
  model copies line words and each delivery's quantity and date words; code
  finds each whole in the paste, resolves the line (`change_requests.named_line`,
  now also by PRV code; words naming no line are refused, never matched),
  parses through the paste's own notation; a value the paste leaves open, a
  delivery missing, another unit → `unread`, for a person. Nothing stored.
  A gated model step (`ModelStep.INTERNAL_CHANGE`, `model_assist.internal_change`,
  off where a version does not say; bar 0.85 on `all.right`, proposed),
  eval `sales_internal_change@1.0.0` with injection, cross-tenant, missing
  evidence and degrade cases.
- **Notice**: `internal_change_notice` (ORDER_GATES, while the internal loop
  runs), words in `sales_emails@1.5.0` (vi/en/ja, `reason.<code>` words): each
  line with its new deliveries and a cut's quantity; no price, every figure one
  the change list holds. A person sends it.
- **Web**: "Thay đổi nội bộ" on a confirmed order (`internal-change.tsx`,
  offered by `internal_change_open`): paste, "DW1 đọc thư PC" fills the form
  (machine-read, refused lines listed, open values tagged), "Áp dụng" with a
  confirm; the update-loop card shows "Thay đổi nội bộ: <lý do>".
- The BA's 6.1B is placed on `update.bravo_update` in the process map.

Not done: the notice is a template draft, not yet a kind of the
`reply-drafts` skill (that needs a new platform draft in `ReplyKind`, its facts
and replay examples, and a new platform skill version).

2026-11-16 (later), the leftovers:

- **A whole line cancelled** (W07 "cancel all"), with the least new surface:
  it is PC's answer of no delivery (`PcAnswer.deliveries` may be empty;
  `OrderLine.cancelled`), the cut taken to nothing. No new column, no
  migration, no new loop state: the internal loop holds it as PC's answer
  for the line like any other, `_loop_applied` applies it, the applier is a
  maker by that answer. The line keeps what the customer ordered (its
  values, its checks); it has 0 deliveries, so the confirmation takes no
  date for it (`confirm`: named with none, or not named). "Áp dụng" takes a
  line `cancelled: true` with no delivery (`InternalLine`; a line with no
  delivery that does not say so, or a cancel with deliveries, is refused by
  the schema). Refused: every line of the order cancelled
  (`every_line_cancelled`: that is the order cancelled, no change of it), a
  later change of a cancelled line, internal or the customer's
  (`line_cancelled`), and, as before, a line printing its schedules
  (`printed_schedules`).
- **Reaches the Bravo update file**: the line's rows, quantity and amount 0,
  no first or current confirmed date (`upload_rows`); also in the processed
  Excel the confirmation carries. **And the notice**: "cancelled, not
  delivered" in place of its deliveries (`sales_emails@1.6.0`, word
  `cancelled`, vi/en/ja). The confirmation sent again lists no cancelled
  line (`confirmation_draft`, `portal_checklist`). Nothing changes before a
  person applies it: the reading is unchanged (the model does not read a
  cancel; a person ticks it).
- **Web**: "PC huỷ cả dòng" per line in "Thay đổi nội bộ" (hides its
  deliveries; a cancelled line is not offered again); the order's line
  shows "PC đã huỷ cả dòng"; "Ghi đã gửi xác nhận" asks no date for it.
  `OrderLineView.cancelled`; contracts regenerated.
- **Defect fixed** (found by this ticket's first agent): a line confirmed
  without PC's answer took PC's new date as Bravo's first confirmed date
  ("Ngày XN giao hàng lần đầu") in both update loops. `reconfirmed`, the one
  owner, now takes the line and keeps the dates Sales confirmed it with
  where PC never answered. Tests: `test_update_loop.py` (the pull-in's Bravo
  row is HELD/ASKED, was ASKED/ASKED), `test_internal_changes.py`.
- Tests: `test_internal_changes.py` (the cancel walked to the confirmation,
  the refusals, cross-tenant), `test_artifacts.py` (the confirmation draft),
  web `internal-change.test.tsx`, `delivery-schedules.test.tsx`.

Owed by Proterial: how Bravo's "Thay đổi chi tiết" takes a cancelled line
(a row at quantity 0, as the file gives it now, or the row deleted), and
whether a blank date in the paste overwrites Bravo's first confirmed date.
Left: a cancelled line of a PO that prints its schedules is refused
(`printed_schedules`); the model does not read "cancelled" from PC's mail.
