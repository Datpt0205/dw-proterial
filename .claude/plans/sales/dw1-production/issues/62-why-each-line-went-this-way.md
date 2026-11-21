# 62 — "Why this line went this way": a per-line decision trail with rule codes

Status: in-progress — the order page is done (2026-11-21); left: the quote page, BR-* codes (pending: the BA's BR-* list mapped to DW1's check and finding codes), Bravo validator steps (pending: ticket 49, the runner reading live Bravo)
Blocked by: none (rule codes come from the BA's spec, BR-*; Bravo's validators by name)
Category: enhancement

## Why

ATLAS shows each ticket line's path as steps, each with a rule code and a reason
("L1-09f vượt định mức…"). PICs and auditors trust a system they can follow.
DW1 already traces every cell it fills (ticket 41) but shows it per finding, not
as a line's path.

## Shape

- On the order and quote case pages, each PO line shows, round by round, the
  steps it took. A step reads, for example:
  - code converted (by Bravo's converting list);
  - price checked (quotation X, valid on the SO date);
  - Bravo warning "Short leadtime";
  - asked PC;
  - PIC chose …
- Each step shows the rule's code (BR-* or the Bravo validator's name), its
  evidence and who decided: rule, model or person.
- Short by default; the detail opens on click (Đạt's UI rule).

## Acceptance

- A line's trail is complete: every state change has its step.
- The page shows it at phone width.

## Done (2026-11-21, the order page)

- **Read, never kept twice:** `dw_sales.application.line_trail` builds a
  line's steps from what the case already stamps on the line: the read and
  its anchor (or the model's reading of a PO in the mail), the convert
  list's code, the model's description reading (prompt, outcome, confidence,
  gate), the mapping and who confirmed it (a person, or DW itself through the
  ADR 0015 lane), the quotation and checks it was held to, each finding with
  its rule version and the decision on it, corrections, the customer's
  changes, Design's and PC's requests, PC's answer and short lead time,
  Bravo's entry, the cross-check and the confirmation, and the model steps
  `sales.step_outcomes` names for the line. Each step says who decided:
  rule, model, DW or person (with the user id), and carries its code.
- **No amount on a step:** a finding's compared values and a quotation's
  price stay on the case page under `sales.price.read`.
- **API:** `GET /api/v1/sales/orders/{case_id}/lines/{line_no}/trail`, through
  the case's own gate and record visibility (another tenant, a person who
  may not see the case, and a line the case lacks are all not found).
- **Web:** "Vì sao dòng N đi như vậy" in the line's expanded detail opens a
  drawer: a count by who decided, then a timeline, each step with its actor
  tag (words and icon), title, code and evidence. Labels are the glossary's
  (`CONTEXT.md` "Line trail steps", "Who decided a step"), held by the labels
  test.
- **Tests:** `test_line_trail.py` (a line with every decision set has every
  step kind; `OrderLine`'s fields are each covered, so a field added
  without a step turns it red; DW's own apply reads as DW; no amount for a
  price reader; the gate), `line-trail.test.tsx` (vitest), and
  `e2e/line-trail.spec.ts` (Playwright on the dev stack, M03 processed by the
  worker): the drawer at desktop and at 320 px with no sideways scroll, both
  passing on 2026-11-21. A desktop run once failed with "Page crashed" while
  the machine had 1.8 GB free; rerun alone it passed.
- **Mutation check:** visibility on the read, the missing-line refusal, an
  amount on a finding step, the PC answer's step and DW's actor: each broken,
  each turned a test red.
- **Fixed on the way:** the `reader` image no longer built since its
  compile step met `olefile2.py` (Python 2, never imported); it is excluded.

## Comments
