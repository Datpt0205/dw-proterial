# 41 — A customer's SalesOrder made by a skill with tools, every cell traced by code

Status: ready-for-agent (after 40)
Blocked by: 40 (the skill store and the deep agent)
Category: enhancement

## Why

Đạt, 2026-11-16: rules learned from one worked example break on the first
PO that example did not show ("cứ chăm chăm vào ví dụ thì sau này gặp
trường hợp khác rất dễ sai"). ADR 0013 already notes the symptoms: a per-PO
value passes as a constant on a one-PO example (PCS's LME center), a PO
column the reading does not keep cannot be a source (PCS's PRS number),
the EXW date the PIC types is not expressible. Amends dw_sales ADR 0013
under ADR 0014.

## Shape

- **The skill**: per customer, "how this customer's PO becomes Bravo's
  SalesOrder" in words: which PO value goes to which column, the
  customer's exceptions (a unit in km, a date shifted from ETA, a code
  looked up), with several worked pairs as examples, not one. Written and
  edited through the skill flow of ticket 40 (a PIC proposes, the head
  approves, never the proposer).
- **The tools**, read-only, bound to the case's customer by code: the PO
  as read (lines, values, anchors), the customer's convert list, the item
  master, the calendar for a date shift, unit factors.
- **The model fills each PO's SalesOrder** with the skill and the tools, so
  a PO unlike the examples is still read, and it says where each cell came
  from: a PO value (its anchor), a tool's result, a constant the skill
  names, or a computation from the closed set ADR 0013 already has (shift
  days, unit factor, round, cut, concat, multiply).
- **Code traces every cell, on every PO** (the guard, where ADR 0013 only
  replayed one example): a PO value must be at its anchor; a looked-up
  value is looked up again; a computation is redone; a constant must be
  in the approved skill. A cell code cannot trace is not written: it is
  flagged for the PIC with the reason. Prices still come from where dw_sales
  ADR 0008 puts them, never from the model.
- **Examples grow**: a SalesOrder file the PIC corrected becomes a new
  worked pair for that customer; a skill change is replayed on all of the
  customer's pairs before the head sees it.
- The file is still approved by a person before it reaches Bravo (ADR 0026).
- ADR 0013's learned rules stay as the fallback while the skill is below
  its bar (measured on Strata first, as ADR 0014 requires).

## Acceptance

1. A PO with a line shape none of the examples showed is filled, or its
   cells flagged with reasons, never filled from a guess.
2. A cell whose value is not at its anchor, not a tool's result, not a
   redone computation and not a constant of the skill is flagged, not
   written (negative test, also with an injected instruction in the PO).
3. A skill change that breaks any of the customer's worked pairs cannot be
   sent for approval.
4. A tool never returns another customer's convert rows or items.
