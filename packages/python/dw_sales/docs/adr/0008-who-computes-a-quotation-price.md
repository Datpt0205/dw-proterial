---
status: Proposed
date: 2026-11-10
source:
    - ../../../../../.claude/plans/sales/dw1-production/spec.md
    - ../../../../../.claude/plans/sales/dw1-production/issues/13-suggested-price.md
---

# Who computes a quotation price: Bravo's quotation module or DW1

## Context

The BA's flow (11-09, page 1b) prices a request from three inputs: the LME
band, the customer's margin, and the exchange rate. A strategy decides
among the results. Today Sales does this in Excel.

DW1 already does part of the job:
- `suggest_price` proposes a price from evidence (past quotations and
  orders);
- Sales decides the price and the head approves it.

Bravo is gaining a quotation module, live from 11/2026, and it already has
a "Master list báo giá". If DW1 computes a price and Bravo computes one
too, the same question has two answers, and they will drift
(`failure-modes.md` #2).

## Options

- **A. Bravo computes, DW1 reads.** DW1 reads Bravo's price through the
  API (`docs/adr/0026`), explains it, and checks the order against it. It
  works only once the module and its API exist.
- **B. DW1 computes, Bravo records.** The formula becomes a tenant rule in
  DW1, computed by code. Sales keys the approved price into Bravo. This
  works now, but if Bravo's module computes as well, the formula is kept
  twice.

## Proposed decision

**A**, if Bravo's module computes prices from the same inputs. **B** only
for what the module does not cover, written as a list. Until the module is
live, `suggest_price` stays as it is. Neither option ever lets the model
compute a price.

## Owed

- Đạt's choice.
- From Proterial: what the module computes, and when its API is ready.
