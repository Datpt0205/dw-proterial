# 28 — Confirmation sent, then accepted or implied

Status: done (2026-11-15)
Blocked by: 25 for the sent-copy path (the button path does not wait)
Category: enhancement

## Why

dw_sales ADR 0011. Also takes the earlier item "the confirmation as the
customer's own PO plus the processed Excel" (spec 11-13).

## Shape

- Order states `confirmation_sent` (Đã gửi xác nhận, chờ khách) and
  `confirmed` (Khách đã đồng ý) with how: `accepted` / `implied`.
- Entering `confirmation_sent`: the PIC records it (the send button's
  receipt does it for them), or a sent copy in the thread carrying the case
  version's Excel (sha256) proposes it.
- Per-customer days of implied acceptance in the order rules, empty by
  default; the follow-up lane tells the PIC when they pass; the PIC
  records it.
- Customer 1's PO terms read "5 business days after the P/O date" (Box B01,
  inventory item 9): the days count from the PO date there, in business
  days, while Đạt's rule (11-13, via the 24/7 change) is calendar days by
  default. Each customer's value says which day count and from which date
  (PO date or confirmation sent); calendar from the confirmation by
  default; Proterial confirms customer 1's.

## Acceptance

1. No customer days: never proposed as implied, whatever the wait.
2. A reply read `accepts` proposes `accepted` with its quote; the PIC
   records it.
3. `rejects` after `confirmation_sent` moves to `change_review`.

## Done

2026-11-15, decisions in dw_sales ADR 0011, "Built 2026-11-15 (ticket 28)".

- **Domain** (`domain/orders.py`): `OrderStatus.CONFIRMATION_SENT`
  (Đã gửi xác nhận, chờ khách) before `CONFIRMED` (Khách đã đồng ý);
  `ConfirmationSent` (sent at, the sent copy, the customer's `ImpliedTerm`
  and the instant silence counts) on `confirm`; `CustomerAgreement`
  (`accepted` / `implied`, who, when, the reply and its quotes) on `agreed`;
  `declined` -> `change_review`. Implied refused with no term
  (`no_implied_term`) or before its instant (`implied_too_early`); both
  answers refused while the update loop runs (`update_running`). The loop
  starts from `confirmation_sent` and `confirmed` (`CONFIRMATION_LEFT`).
- **Rules**: `sales_order_rules@1.14.0` `implied_acceptance` per customer
  (days, `calendar`/`business`, from `confirmation_sent`/`po_date`), empty;
  `sales_followups@1.4.0` `implied_acceptance.enabled`, read by the lane
  (`owed`), which tells the PIC once and writes nothing on the case.
- **Service and routes** (`application/confirmations.py`):
  `POST /orders/{id}/confirm` (now with an optional `sent_message_id`, the
  server finding the copy itself), `POST .../agreement`, `POST .../decline`,
  each at a case version, `Idempotency-Key`, event and audit in the
  transaction; `confirmation_copy` (the sha256 match) shared by the view and
  the service. `INTENT_STEPS` rows: a customer's `accepts` / `rejects` on
  `confirmation_sent` propose "record_accepted" / "record_declined"; nothing
  while the loop runs.
- **Readers**: settled orders, the open-work index, process edges and O10,
  assistant labels, artifact gates, follow-ups store and eval world, web
  labels, tags, filters, lines, export-control hold.
- **Store**: migration `64d50dbc1d00` (statuses, `confirmation`,
  `agreement` with their CHECKs, the loop's statuses, the follow-up name,
  the open-work index; existing `confirmed` rows and events to
  `confirmation_sent`).
- **The draft** (`confirmation_draft`): the customer's own PO files byte for
  byte plus the paste sheet as the processed Excel.
- **Web**: "Khách xác nhận đơn" on the order page (`agreement.tsx`): state,
  how, the term on click, "Khách đã đồng ý" / "Khách im lặng quá hạn → ghi
  đồng ý ngầm" / "Khách từ chối" each disabled with its reason, the reply's
  proposal with its quote and "Xem trong thư"; the sent copy marks "Đã gửi
  xác nhận" with "Xem trong thư".
- Tests: `test_confirmation_agreement.py` (acceptance 1-3, the term,
  sent copy match and mismatch, another mail, a reply before the
  confirmation, the loop, stale version, cross-tenant/workspace, scope, the
  lane never writes), `test_artifacts.py` (the draft's files), integration
  `test_confirmation_agreement_db.py`, `test_confirmation_migration.py`,
  web `agreement.test.tsx`.

Remains: Proterial to confirm customer 1's term (5 business days from the
PO date) and every other customer's; a holiday calendar for business days;
which Excel is "processed" (B11); a `requests_change` after the confirmation
proposing "Ghi yêu cầu thay đổi" (ticket 27's remains); a reply's answer in
the update loop proposing the loop's buttons (ticket 29's remains); sent
copies reach a case only with thread headers (ticket 23).
