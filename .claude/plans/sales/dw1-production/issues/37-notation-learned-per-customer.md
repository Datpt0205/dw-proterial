# 37 — A customer's notation learned from Sales' confirmations; evals tell wrong from deferred

Status: done (2026-11-16)
Blocked by: none
Category: enhancement

## Why

The hardcode audit's batch C (11-13) made one owner for numbers, dates and
currency (`dw_platform.domain.notation`): `1.250`, `05/12/2026` or a bare
`$` that the document itself does not settle goes to a person instead of
being read one way. Nothing is read wrong any more, but the replay goldens
fell (RFQ 0.946 → 0.828, hand-off 0.945 → 0.849), under the live bar
(0.85), so neither step can be turned on for a tenant.

A customer writes its numbers and dates one way. Who knows it is Sales, the
first time they confirm such a value.

## Shape

- When Sales confirms or corrects a value DW left as ambiguous, code records
  which notation that settles for that customer (thousands separator, date
  order, the currency a bare symbol stands for), with who and on which case:
  one record per customer and kind, shown on the customer's master data
  screen, changeable by a person. No setting to fill in by hand first.
- A later document of that customer is settled by it when the document
  itself says nothing; a document that contradicts it goes to a person.
- The goldens' graders report two numbers: **wrong** (a value read other
  than the mail states; the bar holds it near zero) and **deferred** (left
  to a person; reported, with its own floor). The live bar reads right =
  1 − wrong − deferred as today until Đạt sets the split.

## Acceptance

1. A customer whose first PO's `1.200 m` Sales confirms as 1200 m has its
   next PO's `1.500 m` read as 1500 m, flagged as settled by that record.
2. Another customer's record never settles this customer's document.
3. The goldens report wrong and deferred separately.

## Owed

- **Đạt: the bar's split.** The graders now report `wrong` and `deferred`
  separately (RFQ replay VI/EN: right 0.828, wrong 0.020, deferred 0.157;
  hand-off: right 0.849, wrong 0, deferred 0.151). The live bar still reads
  right = 1 − wrong − deferred at 0.85 (`model_readiness.BARS`) until Đạt sets
  a ceiling on wrong and a floor of its own on deferred. The replay ceilings
  are `max_wrong_vi_en` 0.02 (`evals/expected/sales_rfq_golden.json`) and
  `max_wrong` 0 (`sales_handoff_golden.json`).

- **Follow-up: change requests** (ticket 27, `domain.change_requests`
  `table_changes`/`model_changes`) still read by the mail's own notation
  only: wiring the record there is `settle` around `parse_asked` and the
  table's date column, with the order's customer (not done in this slice;
  nothing there reads wrong, its ambiguous dates go to Sales as today).

## Done

- **One owner** (`dw_platform.domain.notation`): `settle(parse, document,
  record)` reads a value by the document's own evidence and the customer's
  record, saying `by_record`, `contradicts_record` or `unsettled`; the record
  only settles what the document leaves open, and a document (even its weak
  "0.95" evidence) that reads otherwise is not read. `learned(parse,
  confirmed)` is the one kind and value under which the words read as the
  value a person kept; `record_of`, `KIND_VALUES` (decimal mark, date order,
  `$`, `¥`).
- **The record** (`sales.customer_notations`, migration `99ae8f7eb765`): one
  row per (tenant, workspace, customer, kind), its evidence (case, field,
  words, value kept, who, when) or `set` by a person; RLS tenant+workspace
  with the offboarding scope, FORCEd, every verb granted, CHECK on each fixed
  set and on the evidence's two shapes, `updated_at` trigger; written with its
  audit row in one transaction, only where the value or source changes
  (`SqlCustomerNotations`).
- **Writers**: `QuoteCommands.answer_finding` (a model-read value confirmed,
  or a quantity/date the request left open typed, `RequestedItem.unsettled`
  anchoring it at its words) and `OrderCommands.correct_value` learn after
  the decision commits (`domain.customer_notation.quote_lessons`,
  `order_lesson`). A value neither reading gives teaches nothing.
- **Readers**: RFQ (`verify_rfq`), hand-off (`quantity_at`, the line's
  date), PO in the mail body (`read_po_body`) read the sender's customer's
  record only; a value only the record read is flagged
  `notation_from_record` beside `model_read` (a hand-off line: `from_record`);
  a contradiction is counted `<field>_contradicts_record` and left to Sales.
  PC dates and Design's replies are not wired: they are internal people's
  words, not a customer's.
- **Screen**: Dữ liệu chủ → Khách hàng → "Cách viết số, ngày" → a drawer with
  each kind, where it came from on click (the words, the value, who, when, the
  case), set or forgotten by a holder of `sales.order.prepare`; the server
  checks the scope and the customer is the caller's own (404 otherwise).
  Routes `GET/PUT /sales/customers/{code}/notation`,
  `DELETE /sales/customers/{code}/notation/{kind}`.
- **Evals**: `sales.rfq_golden` and `sales.handoff_golden` report `wrong` and
  `deferred`; `sales.rfq_notation_records` and
  `sales.handoff_notation_records` read the goldens again with each customer's
  record: RFQ right 0.839 → 0.949 (deferred 0.146 → 0.035), hand-off right
  0.849 → 0.945 (deferred 0.151 → 0.055), wrong unchanged; Velatrix's
  "1.500 m" read 1500 m flagged; another customer's or another tenant's
  record changes no reading.
