---
status: Accepted
date: 2026-11-10
decided: 2026-11-17
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

## Decision 2026-11-17

**A.** Đạt left the choice to the agent's recommendation ("tự khuyến nghị
rồi làm theo"), and the recommendation was A:

- Bravo computes a quotation's price and band table; DW1 never computes
  one, and the model never does.
- The price check reads Bravo's prices once Bravo's band table can be read
  (its API, or the quotation document Bravo prints). Bravo's "Master list
  báo giá" alone does not answer it, measured on B07 (161 rows): it names no
  PRV item, only a BP code that up to 56 items share (B06), holds up to 10
  rows per customer and BP, and gives a centre price at LME 7,750 only, so
  a price for another month's band would be DW1's computation, which this
  decision rules out.
- Until then the check stays what it is: the valid-quotation list Sales
  keeps (Excel, "pass SC") plus the rows DW1 records once a quotation is
  approved, each priced per band by a person. That stand-in is replaced,
  not kept beside Bravo's, when Bravo's read arrives (ticket 12).
- Quotation history is Bravo's from the module's go-live; the Excel history
  (2,521 rows) stays read-only evidence for `suggest_price`.
- Ticket 13 (a suggested price from the LME band, margin and rate) is not
  built in DW1: what it would compute is Bravo's.
