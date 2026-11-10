---
status: Accepted
date: 2026-11-10
accepted: 2026-11-10 (Proterial IT, 11-09: no database login, an API over Bravo's stored procedures; Đạt: DW only reads)
source:
    - ../../.claude/plans/ops-hardening.md
    - ../../.claude/plans/sales/dw1-production/spec.md
---

# Bravo is read through its vendor's API and written by a person

## Context

Bravo 8 is two-tier. Each PC runs a client that talks straight to SQL Server
on Proterial's Windows Server, and roles live inside Bravo. On 11-09
Proterial IT declined to give a database login. Instead, the Bravo vendor
will build an API over its own stored procedures, so the business logic
stays theirs.

Today Sales enters an order by pasting rows from an Excel sheet into
Bravo's sales-order grid, and checks the entry against the customer's PO
with a second workbook.

Both DW1 and DW2 need Bravo's data:
- DW1: customers, items, conversions, prices, sales orders;
- DW2: items, suppliers, prices paid, budgets, purchase orders, goods
  receipts.

## Decision

1. **No database access, ever.** DW never connects to Bravo's SQL Server,
   not even read-only. Every read goes through a port each context declares
   (for example `BravoSalesOrders`), satisfied by an adapter over the
   vendor's API.
2. **DW does not write to Bravo.** A person enters the data:
   - DW1 prepares the paste sheet in Bravo's own layout;
   - a person pastes it and presses Bravo's buttons;
   - DW reads the result back and compares it.

   A write through the API comes later, only if Proterial asks for it. It
   is called when a person presses, carries an idempotency key, and goes
   through approval like any other side effect.
3. **Until the API exists**, the same ports take an Excel export of the
   Bravo screen, uploaded by a person. The flow does not change when the
   adapter does.
4. **The API key is DW's own.** It has the least rights the reads need, is
   called over HTTPS on the LAN, and is tried against Bravo's test company
   first. A client login (such as the `SALEAI` user seen on 11-10) is
   never used by DW.
5. **No answer from Bravo means no answer.** When Bravo is unreachable, a
   check says it could not run. It never passes.

## Consequences

- The vendor's endpoints are the contract; the list FPT asked for is in
  `docs/proterial/` (outside git).
- The paste sheet is a versioned tenant policy (`sales_bravo_upload`).
  Proterial's real layout is a new version of it, not a code change.
- Anything Bravo already owns (the quotation master list, the module live
  from 11/2026) is read, not kept a second time in DW.
