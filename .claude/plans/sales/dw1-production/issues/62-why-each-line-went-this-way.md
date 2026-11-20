# 62 — "Why this line went this way": a per-line decision trail with rule codes

Status: needs-triage
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

## Comments
