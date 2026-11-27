# 66 — A customer's SalesOrder skill drafted by the model from the PIC's files

Status: done (2026-11-24); live on Giang's Strata, not attested; the plant measures it with real pairs (ticket 38's Remains)

## Why

Đạt, 2026-11-24: "làm phần model soạn skill riêng đi". Ticket 41 made a
customer's SalesOrder skill (`salesorder-<code>`) the way a PO becomes
Bravo's SalesOrder file, but a customer's own version had to be written by a
person on the skills page. Sales staff will not write skills. Without a
version of its own, a customer is filled with the platform's generic skill,
which is right for most customers (their differences are data: convert list,
item master, layout, notation) and wrong for the few with exceptions (a group
code in every row, a date shifted, a joined PO/line column).

## What

When a worked pair is kept for a customer (ticket 38's learning: the PO and
the file the PIC made from it), the worker drafts that customer's skill:

1. Fill the customer's newest pairs with the skill in force (the customer's
   approved version, else the generic one). Every pair reproduced: nothing to
   draft.
2. Otherwise one model call (`sales.salesorder_skill_draft@1.0.0`) is shown
   the skill in force, the layout's columns and, for up to three failing
   pairs, each differing cell: what the PIC wrote, what DW wrote and why,
   and the row's values and look-ups. It answers the whole new skill.
3. Code checks the draft: every constant it adds to `## Constants` is a text
   the PIC's files hold, and none is a value of a PO (a PO's words cannot
   become a constant written into every SalesOrder).
4. Code replays the draft on every pair. Proposed only if it reproduces more
   pairs than the skill in force and loses none that one reproduced, as a
   version of `salesorder-<code>` by the lane itself (never applied).
5. The existing replay lane replays it again on its own; the head approves
   on `/approvals` only where every pair is reproduced (ticket 41), never the
   lane.

## Acceptance

1. A customer whose pairs the skill in force reproduces gets no draft.
2. A customer the generic skill fails (KHA's two fixed codes) gets a version
   proposed by the lane, which the replay lane proves and the head approves.
3. A draft adding a constant the PIC's files do not hold, or one that is a
   PO's value, is refused and nothing is proposed (an instruction in a PO).
4. A draft that reproduces no more pairs, or breaks one the skill in force
   reproduced, is not proposed.
5. A version already waiting for the customer: nothing drafted. The lane
   never decides one.
6. No model, the model down, or the plan's quota spent: nothing proposed.
7. Another tenant's or customer's pairs are never read for a draft.

## Done

Built 2026-11-24 (dw_sales ADR 0013 addendum 2026-11-24).

- **Trigger**: `SalesOrderLearning.learn` writes `sales.salesorder_pair.added`
  with every kept pair, in the same transaction; the worker's handler
  (`consumers/sales_salesorder_skill_drafts.py`) hands the customer to
  `SalesOrderSkillDrafter.draft` (`application/salesorder_skill_drafts.py`),
  wired where the one-call door is.
- **The draft**: prompt `sales.salesorder_skill_draft@1.0.0`, up to
  `DRAFT_ROUNDS` (3) rounds, each shown the previous draft's own differing
  cells (as compared: a date by its day, a number by its value), the PIC's
  whole rows, the rows' values and look-ups. Checked (`check_draft`: a new
  constant only from the PIC's files, never a PO value, never unchanged),
  replayed on every pair (`fill_pair`, asked twice before a fill counts as
  unanswered), proposed only where it `gains`, as the lane's own version
  (`system_actor`), never applied; the replay lane proves it again and the
  head decides.
- **Eval** `sales_salesorder_skill_draft@1.0.0` (golden, prompt injection,
  cross tenant/customer, missing evidence), graders in
  `dw_sales/evals/salesorder_skill_draft.py`; smoke 4/4.
- **Measured live** (Giang's Strata, flash next Q2, not attested, 5 runs):
  KHA and KHC reproduced by the generic skill; KHB drafted and proposed in
  round 1 every run; the injection planted in KHB's PO never proposed. Two
  fixes came from the live runs: values shown as compared (a raw
  `2026-12-10T00:00:00` read as a time-of-day rule) and `unit_factor`
  spelled out (a price per km was converted backwards; the trace flagged it,
  nothing was written).
- **Security walk** (reviewing-feature-security): tenant (the event's scope,
  RLS on rule versions, pairs of that workspace and customer; eval case);
  authorization (the lane proposes with no scope and never decides; the
  head's approval needs every pair reproduced); autonomy (no effect: a
  proposal, a SalesOrder still filled only with the step on and a person's
  review); untrusted content (PO text contained by the registry; a planted
  constant refused; eval case); audit (the engine audits the proposal as the
  lane; the log carries ids and counts only); lifecycle (one draft per kept
  pair; a waiting version stops it; quota and a down model propose nothing).
  Mutation check: 8 guards removed one at a time, each turned a test red.

Left: real pairs (ticket 38's Remains) to measure on; a page line showing a
draft's rounds on /approvals (the comparison shows the words today).
