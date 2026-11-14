# 29 — The update loop: from a confirmed change to the customer's answer

Status: done (2026-11-15); `confirmed` stands for `confirmation_sent` until ticket 28
Blocked by: 27, 07
Category: enhancement

## Why

dw_sales ADR 0010 decision 3, BA step 6 (6-DW2, 6-PC, 6-DW3, 6-DW4,
"Khách quyết định?", 6.2-SP, 6.3).

## Shape

- Before Bravo: a confirmed change re-runs the checks; DW drafts the
  answer.
- In Bravo: dates/quantities draft the PC request; PC's answer drafts 6-DW4
  or 6-DW3; the customer's answer proposes keep / accept / ask PC again;
  the PIC approves the Bravo update; 6.3 drafts the PO and schedule back;
  the case returns to `confirmation_sent`.
- Each draft is sent by a person.

## Acceptance

1. A pull-in on an order in Bravo walks to `confirmation_sent` with every
   draft and approval recorded.
2. A customer keeping the original PO closes the change request and leaves
   the order as it was.

## Done

2026-11-15, decisions in dw_sales ADR 0010, "Built 2026-11-15 (ticket 29)".

- **Domain** (`domain/orders.py`): `UpdateLoop` on the order case (step
  `ask_pc` → `waiting_pc` → `answer_customer` → `waiting_customer` →
  `bravo_update`, `since`, the changed lines as `LoopLine`s holding the
  confirmed `AppliedChange`s and PC's answer, code's `verdict` `can_do` /
  `proposes`, the `BravoUpdateApproval` by artifact id and sha256); each step
  a case version. `loop_change`, `loop_ask_pc`, `loop_pc_answer`,
  `loop_answer_sent`, `loop_answered` (keep / ask PC again), `update_accepted`
  + `take_update` (accept: changes and PC's answer applied through the
  re-check path, first confirmed dates kept by `reconfirmed`, now ticket 07's
  one owner, → `change_review`), `approve_update`; `apply_change` refuses an
  unapproved update, an edit drops the approval, the approver is a maker, the
  loop ends when the order is confirmed again or moves elsewhere.
- **Service and routes** (`application/update_loop.py`,
  `presentation/routes.py`): `GET/POST /orders/{id}/update/pc-request`,
  `POST .../update/lines/{n}/pc-answer`, `.../update/answer-sent`,
  `.../update/customer-answer`, `.../update/bravo-file`; every POST names the
  case version and takes an `Idempotency-Key`; event and audit row in the
  same transaction. `change_requests.confirm` routes a line on an order in
  Bravo into the loop. The order view carries `update_loop` with the one step
  it awaits (`awaits`). The re-check no longer compares an order DW1 entered
  in Bravo with its own Bravo entry.
- **Drafts**: 6-DW2 is ticket 07's request with the values asked; 6-DW4 and
  6-DW3 are the artifacts `change_can_do_draft` / `change_options_draft`
  (`sales_emails@1.3.0`, vi/en/ja), offered by code's verdict; the Bravo
  update file is the artifact `bravo_update` (the changed lines' paste-sheet
  rows, kept by id once approved). `change_summary` is a revision's only.
- **Reminders**: `waiting_pc` and `waiting_customer` read the loop's `since`
  by its step (`followups.py`, store and in-memory world); no rule field
  changed, `sales_followups` stays 1.3.0.
- **Store**: migration `0d1d0e4eb203` (`sales.order_cases.update_loop`, a
  CHECK on its object, its step set and the statuses in Bravo; the table's
  RLS, FORCE and grants unchanged).
- **Web**: "Khách xin thay đổi đơn đã nhập Bravo" on the order page
  (`update-loop.tsx`): the step it waits on and since when, code's verdict,
  the one action (Chép bản hỏi PC / Ghi đã hỏi PC, Ghi ngày PC per line,
  Ghi đã gửi khách, Khách đồng ý / Khách giữ PO cũ / Hỏi PC lại, Duyệt tệp
  cập nhật Bravo with its version and hash), each disabled with its reason;
  the flow's explanation and the PC draft on click. The drafts and the file
  are rendered from "Tài liệu". `PcAnswerDialog` is shared with ticket 07.
- Tests: `test_update_loop.py` (acceptance 1 and 2, 6-DW3, refusals,
  reminders, cross-tenant/workspace, scope, SoD), integration
  `test_update_loop_db.py`, web `update-loop.test.tsx`.

Remains: the work list and "your turn" do not yet name a loop step on a
`confirmed` order (`next_steps.ORDER_NEXT` is keyed by status); a reply's
`accepts`/`rejects` proposing the customer's answer (with ticket 28); the
6-DW2 wording as a change ("đổi", not "đặt"), a new `sales_handoffs`
version; the Bravo write through the vendor's API (ADR 0026).
Owed by Proterial: whether a pull-in PC can do earlier than asked counts as
"can do"; who approves a Bravo update (PIC per the BA's flow, or the head).
