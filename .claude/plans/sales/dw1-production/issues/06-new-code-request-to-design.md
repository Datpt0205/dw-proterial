# 06 — No PRV code yet: the new-code request to Design, with the nearest codes

Status: done (2026-11-16)
Blocked by: none (an example of the request mail improves the wording)
Category: enhancement

## Why

Drawio 1a: when an item has no PRV code, Sales asks Design to create one.
DW1 already ranks the nearest PRV codes for a line (ticket 28).

## Shape

- On a line left unmapped, "Đề nghị Design tạo mã" drafts a mail from the
  line as read and the three nearest PRV codes with their descriptions. The
  case waits on Design. The new code in Design's reply maps the line once
  Sales confirms it, and item 3's learning keeps it.

## Acceptance

1. The draft cites only codes in the tenant's catalog.
2. The code Design names maps the line only after Sales confirms it.

## Comments

## Done

Built 2026-11-16, by the agent (migration `3d139b41fec1`, on `7c00901ada90`).

- **Nearest codes** (`domain/descriptions.py`): no ranking existed; ticket
  28's matching asks every stated attribute (`candidates`). `nearest` counts
  how many of them each item holds, by the same equality, most first then by
  PRV code, never an item holding none; three are shown (`NEAREST`). Only the
  scope's item master is ranked, so no other code can be cited. `described`
  writes an item in DW1's own vocabulary (Bravo's name where it has one),
  words `read_description` reads back to the same item.
- **Draft** (`application/design_requests.py`, `GET
  /orders/{id}/lines/{n}/design-request`): for an `unmapped` line only, the
  line as the PO prints it and the three nearest codes, in the tenant's
  hand-off copy (`sales_handoffs@1.2.0`, new `design_request` template). To:
  the tenant's `QuoteRules.design_mailboxes`, the one setting that already
  names Design (trusted for Design's replies); empty, the screen says so.
  Not the `handoffs` skill: its kinds are mail kinds of a routed message,
  copied into one of three typed shapes for PC or QA; a line's code request
  is none of those.
- **Wait** (`POST .../design-request`, "Ghi đã gửi Design"):
  `OrderCase.design_requests` (column `sales.order_cases.design_requests`,
  jsonb array, CHECK array), one per line; ends when the line's code is
  confirmed, on a new revision, or when the case leaves review.
- **Design's code**: while a line waits, verified mails from Design's
  mailboxes received since the request, naming the PO, are read by code (no
  model): each token of the newest part the item master holds is offered
  ("Design nêu trong thư", "Dùng mã …" fills the picker's box). Nothing maps
  until Sales confirms through the existing `confirm_mapping` (item master
  checked again, line rechecked, learned for the customer's code).
- **Web**: `design-request.tsx` in the picker of an unmapped line; "Chờ
  Design" tag on the line.
- Tests: `dw_sales/tests/unit/test_design_requests.py`,
  `apps/web/app/sales/_lib/__tests__/design-request.test.tsx`.

Left (closed 2026-11-16 below): no reminder while Design has not answered;
the process map did not draw the wait.

## Done: the reminder and the map (2026-11-16)

Migration `57bbf61ae6b8` (from `1f037954f3d9`).

- **`waiting_design_code`** (`domain/followups.py`): an order whose
  `design_requests` names a request reminds the PIC once per wait, from the
  oldest request still named, after the tenant's
  `sales_followups.waiting_design_code.remind.after_hours` (platform
  `sales_followups@1.6.0`: 24 h, PIC, on). The wait ends where the domain
  already ends it (the line's code confirmed, a new revision, the order out
  of review), so the reminder stops with it. Read by
  `SqlFollowupStore.cases` (`design_asked_at`, the oldest `at` of the
  column) and the eval world alike; `ck_followup_deliveries_followup` and
  `ck_reminder_marks_followup` admit it, so it reaches "Việc của tôi" and
  the phone push like every reminder. DW1 still sends Design nothing.
- **The map**: the order lane's flow `design_code` (`SubflowKey.DESIGN_CODE`,
  step `waiting_design`, in the statuses where mappings are decided,
  `orders.design_wait_statuses()`), with the BA's `2.2B` / `2.2B-DS` on it
  (`domain/process.py`); its setting is placed on O2.
- Tests: `dw_sales/tests/unit/test_followup_waits.py` (fires a day after the
  request, not before; nothing once the code is confirmed; switched off),
  `tests/integration/test_followup_waits_db.py` (the oldest request read
  back; none named, none read).
