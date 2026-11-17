# 05 — Mass or pcs, and the request to JP & HQ for a pcs price

Status: ready-for-agent: acceptances 1 and 2 met, the wait reminded; the JP & HQ mail and the model's proposal owed (see Comments)
Blocked by: none; open questions for Sales: are SGA/loyalty/profit rates fixed per pcs order, is "JP & HQ" the GM at PRV, the assembly-cable variant
Category: enhancement

## Why

Drawio 1a: JP & HQ price a pcs request, not Sales. Bravo's SO header
carries the type ("Mass production").

## Shape

- The quote case gets `production_type` (mass | pcs). Code proposes it from
  the customer's and the item's history where it can, otherwise the model
  reads it from the RFQ; Sales confirms.
- For pcs, a request to JP & HQ is drafted from one example mail (ADR
  0006): code writes every fact and Sales sends it. The case then waits on
  JP & HQ, with a follow-up.

## Acceptance

1. Sales cannot price a pcs case until JP & HQ's price is recorded.
2. The draft names no figure the facts do not hold.

## Comments

- 2026-11-16 (dw-proterial-33): done, both acceptances held where the change
  happens. `QuoteCase.production_type` (mass | pcs, set by a person before
  pricing, stamped), `pcs_price` (the GM/BC Manager's price per line, as
  Sales recorded it, every request line once; going back to mass drops it),
  and `decide_price` refuses a pcs case with none (`require_pcs_price`;
  acceptance 1, mutation-checked: removing it turns
  `test_sales_cannot_price_a_pcs_case_until_the_gm_price_is_recorded` red).
  `pcs_price_request(case)` is B49's cost sheet: the request's lines and the
  cost lines Raw material, Manufacturing, Transportation, SGA, Loyalty,
  Profit, Grand total, every amount blank (acceptance 2). Routes:
  `POST /quotes/{id}/production-type`, `POST /quotes/{id}/pcs-price`
  (quote.prepare), and `GET /quotes/{id}/pcs-price-request` (case.read: it
  carries no amount). Stored in the case body: no migration.
- Owed, safe default meanwhile: (a) `QuoteCaseView` field and the web
  controls wait for `views.py` and `labels.ts`, held by the other Sales
  session; until then the type is set through the API only, and a case
  nobody marks stays priced as today. The recorded GM price in the view
  must go behind `prices.amounts`, like every amount. (b) The JP & HQ mail
  from one example (ADR 0006) needs `configs/copy`, the other session's
  area; the cost sheet is the facts it will carry. (c) The follow-up while
  waiting lives in `followups.py` (other session). (d) Code or the model
  proposing the type from history: no signal is measured yet, so a person
  sets it. (e) `contracts/openapi` regenerates once the other session's
  uncommitted changes there are committed.
- Asked of Sales (Decisions Đạt owes): are SGA, loyalty and profit rates
  fixed per pcs order; is "JP & HQ" the GM at PRV; the assembly-cable
  variant.
- 2026-11-17 (dw-proterial-33): (a) done. `QuoteCaseView` carries
  `production_type`, who set it, `waits_on_pcs_price` and `pcs_price`, its
  amounts behind `prices.amounts` (mutation-checked). The quote page's
  "Mass hay pcs" card: a `Segmented` (disabled with its reason for a caller
  without quote.prepare or once priced), the wait in words, "Ghi giá GM"
  per line, and "Xem bảng hỏi giá GM" (the cost sheet). The price form is
  not drawn while the case waits; the server refuses it anyway. (e)
  contracts regenerated. Still owed: (b), (c), (d).
- 2026-11-17 (dw-proterial-33): (c) done. `waiting_pcs_price` reminds the
  PIC 24 h after a case was marked pcs while no GM price is recorded and
  the case is not sent (`sales_followups@1.7.0`, words
  `sales_reminders@1.1.0`, a tenant version written before reads both as
  the platform has them); the wait is read from the quote's body
  (`SqlFollowupStore`, the world the same), and migration `b01dba5d0433`
  lets the record and the feed's marks hold it. Its setting sits on step
  Q7. Mutation-checked: the rule (unit) and the SQL read (PostgreSQL).
  Still owed: (b) the mail to the GM needs one real example (ADR 0006),
  asked of Sales; (d) proposing the type from history; the process map
  draws no wait for a quote case yet (no quote subflow exists).
