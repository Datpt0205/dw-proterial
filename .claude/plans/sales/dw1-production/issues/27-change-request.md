# 27 — A change request on an order, confirmed line by line

Status: done (2026-11-15); the model step stays off until attested for a tenant
Blocked by: 26
Category: enhancement

## Why

dw_sales ADR 0010 decision 2, BA step 6.1A/6-DW1; Box B03 asks for a
pull-in as a table in the mail's HTML body.

## Shape

- `ChangeRequest` on the order case: lines of (line no, field, held value,
  asked value, anchor into the mail), each open / confirmed / rejected; one
  open per case, a later one queued.
- A table in the HTML body is split by code into rows; free text is read
  by the model as spans that code locates and parses (dates, quantities
  with units).
- Confirming a line applies it and bumps the case version (ADR 0005's body
  rule as amended).

## Acceptance

1. A B03-shaped fixture (no customer data) yields one change line per row,
   none applied until confirmed.
2. A second change request while one is open is queued, not merged.
3. A quantity whose unit differs from the line's (km vs m) is flagged, not
   converted silently.

## Done

- **Domain** (`domain/change_requests.py`): `ChangeRequest` (numbered per
  order, `open` / `queued` / `closed`, versioned) of `ChangeLine`s (line,
  field `requested_date` | `quantity`, held, asked, the words, the unit,
  an anchor into the mail's newest part, `table` | `model` | `person`,
  `blocked`, open / confirmed / rejected with who, when, why). Reading:
  `table_changes` (a table split by its markup, `mail_parts.newest_tables`,
  columns told by their values), `model_changes` (spans found and parsed by
  code), `person_line`; `merged`, `first_state`, `next_to_open`.
- **The order** (`domain/orders.py`): `AppliedChange` on `OrderLine.changes`
  (the effective line takes it), `OrderCase.changed` / `take_change` (in
  `in_review` or `prepared` only; the checks run again through the same path
  as a typed value, `OrderCase._rechecked` / `OrderIntake._recheck`, shared
  with `correct_value`); the confirmer is a maker.
- **Service and routes** (`application/change_requests.py`,
  `application/change_reading.py`, `presentation/routes.py`):
  `POST /orders/{id}/change-requests` (from a reply on the order),
  `.../{request_id}/lines`, `.../lines/{seq}/confirm`,
  `.../lines/{seq}/reject`; the order view carries `change_requests`, the
  mail text only for a price reader. Every one names the case version it
  was decided on (`stale_case_version`). Audit rows in the same transaction.
- **Store**: migration `c7d0730fcccd` (`sales.change_requests`, RLS
  ENABLE+FORCE with the workspace shape, one open per order by a partial
  unique index, one per mail, SELECT/INSERT/UPDATE with DELETE revoked;
  `sales.order_lines.changes`; the step checks admit `change_request`).
- **Model step** `model_assist.change_request` (default off), prompt
  `sales.change_request@1.0.0`, bar 0.85 on `all.right_change`, eval
  `sales_change_request@1.0.0` (golden 8 mails VI/EN/JA, injection,
  missing evidence, cross-customer, cross-tenant, degrade); smoke 6/6
  scripted. **Measured live** (2026-11-15, onprem `qwen3.5-9b-dw` on a
  local Ollama, thinking off): 6/6, `all.right_change` 1.0 (12 of 12
  changes in 8 mails, the km quantity kept in km), bar 0.85 met; the
  injected 99999 m not given; p50 3.1 s, p95 61.9 s (the first call loads
  the model). Not attested for any tenant (`--attest` not run), so the gate
  keeps it off; the golden set is small and synthetic, and a plant
  measurement on real replies is owed before anyone turns it on.
- **Web**: "Khách xin thay đổi" on the order page (`change-requests.tsx`):
  each request line by line, held beside asked, its source, "Xem trong thư",
  Xác nhận / Từ chối per line, each disabled button with its reason; "Ghi
  yêu cầu thay đổi" and "Thêm dòng" for lines a person types.
- Decisions the ADR did not settle: dw_sales ADR 0010, "Built 2026-11-15".
- Tests: `test_change_requests.py`, `test_change_request_flow.py`,
  integration `test_change_requests_db.py`, `test_privileges.py`, web
  `change-requests.test.tsx`.

Remains: an attested measurement on the plant's model and real replies; a reply's
`requests_change` intent proposing "Ghi yêu cầu thay đổi"; in-Bravo changes
(ticket 29).
Open (Đạt): `prepare` is not refused while a change request is open, so an
order can be prepared with a customer change pending.
