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

## Evidence 2026-11-14 (Box B09, B18; the agent's recommendation)

- B09's rule: a band of 500 USD/t around a centre price at LME 7,750, each
  band moving the price by the copper weight / 2, rounded to 2 places; the
  band chosen by the previous month's LME average before the PO's issue
  date; the LME centre is floor(actual / 500) × 500 + 250.
- Quotations to the group's head offices ("CW Head") use no band: price =
  S/P + (LME of the PO − 7,750) × Cu / 10⁶, continuous; the same sheet
  states two contradicting rules for which LME.
- The Excel template rounds step by step and so differs from Bravo where the
  copper weight's second decimal is odd; Bravo prints the whole band table
  on its quotation already.

**Recommended: A** (Bravo computes, DW1 reads its band table and checks an
order against it), since Bravo already holds and prints it and a second
formula in DW1 would disagree with Bravo's rounding. Still Đạt's call.
