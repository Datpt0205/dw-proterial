# 28 — Confirmation sent, then accepted or implied

Status: ready-for-agent
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
