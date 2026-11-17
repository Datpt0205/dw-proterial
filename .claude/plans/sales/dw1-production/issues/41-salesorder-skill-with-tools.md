# 41 — A customer's SalesOrder made by a skill with tools, every cell traced by code

Status: done (2026-11-17); left: a PO column the reading does not keep (PRS number) is still not a source
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

## Done

Built 2026-11-16 by the agent (Đạt away); what the ticket did not settle is
recorded in dw_sales ADR 0013 "Applied 2026-11-16: the skill with tools".

- **The skill**: ``salesorder-<customer code>`` per customer, a tenant
  version under ``sales_skill_salesorder_<code>`` in the skills' store and
  flow (`application/salesorder_skills.py`, `skills.py`); the platform's
  generic one, fictional pairs only, in
  `configs/skills/dw1-salesorder/salesorder/SKILL.md`. Constants are the
  backticked texts of its ``## Constants`` section.
- **The tools** (`application/salesorder_fill.py`, `SalesOrderTools`): the
  customer's record, its own convert list, the items that list reaches,
  bound to one customer when built; called by code for every code the PO
  prints before the one turn, each shown with an id. The PO as read is a row
  per delivery, each value at ``R<row>.<field>``.
- **The turn**: prompt `sales.salesorder_fill@1.0.0`, json_schema answer
  `ModelSalesOrderFill` (per cell a value and its source), five rows a call.
- **The trace** (`salesorder_fill.trace`): every cell of every row redone;
  what is written is code's value; a cell not traced is flagged with its
  reason (`FlagReason`) and never written; a price column takes only the
  PO's own price.
- **Worked pairs**: `sales.salesorder_pairs` (migration `711e8b760139`),
  written by ticket 38's learning with every pair it reads. A skill change is
  replayed by the worker's `sales_salesorder_skill_replay` lane on the
  customer's newest 20 pairs (`application/salesorder_pairs.py`); the head's
  approval is refused unless every pair came out as the PIC's file
  (`skills.PAIRS_BROKEN`).
- **The gate**: `ModelStep.SALESORDER_SKILL`, switch
  `model_assist.salesorder_skill` (off), T2, bar 0.95 on
  ``golden.cell_accuracy``; asked when a case's ``bravo_upload`` file is drawn
  (`application/salesorder_case_fill.py`, `artifacts_service`), the learned
  rules filling it otherwise; flagged cells blank and listed on the file's
  second sheet.
- **Eval** `sales_salesorder_skill@1.0.0` (golden, unseen line shape,
  injection, cross-customer, missing evidence), graders in
  `dw_sales/evals/salesorder_skill.py`. Measured once on Strata
  (2026-11-16, not attested): 1.0 cell accuracy on the three golden pairs
  (114 cells, every one traced, p50 11.5 s a call); the unseen shape 7 of 8
  oracle cells right, the eighth flagged (`value_not_computed`), the
  unmapped code's item never written; no injected or other customer's value
  written. Report `evals/reports/live-onprem/sales_salesorder_skill@1.0.0.json`.
  The step stays off until a tenant's attested measurement on the plant's
  model.

Not built: the skills page listing and proposing a customer's SalesOrder
skill (the API route of ticket 40 proposes one by name today); withdrawing a
wrong pair; a PO column the reading does not keep (PRS number) is still not a
source.

## Done: the approval compares a customer's version (2026-11-17)

- `GET /sales/skills/versions/{version_id}` (`SkillsService.compared`,
  `SkillComparison`): one version of any skill, a customer's SalesOrder
  skill's included, beside the skill in force under its key (the
  customer's approved version, else the generic one), with its stored
  replay. Scope `sales.rules.propose`; another tenant's version, a rule
  version that is not a skill's and an unknown id are not found alike; no
  write. Tests in `test_skills.py`.
- `/approvals`' `sales.skills` panel (`_meta/skill-approval.tsx`) reads
  that route instead of the skills list, so every skill version is compared
  with `SkillChanges`; a pairs replay reads "Điền đúng x/n cặp ví dụ của
  khách…" with its own explanation (`skills.replayLine`), and the pending
  tag says "Đang chạy thử" (no longer "trên thư mẫu", wrong for pairs).
- Contracts owe a regeneration (a new route and `SkillComparison`); the
  web's typecheck needs it for `salesApi().skillVersion`.

## Done: the leftovers (2026-11-17)

- **The skills page lists and proposes a customer's SalesOrder skill.**
  `SkillsView.customer_skills`: one `salesorder-<code>` skill per customer
  of the caller's workspace (`SkillCustomersPort`, the catalog), in force as
  the tenant holds it (`RuleBook.current` for a key with an approved
  version, the platform's generic one otherwise, read without a lookup per
  customer), with `customer_code`/`customer_name`; `versions` now holds
  their versions with the pairs replay. Proposed through the same
  `POST /sales/skills/{name}/versions`, replayed by the same lane, decided
  on the same `sales.skills` approval (no second path). Web: a "Kỹ năng
  SalesOrder của từng khách" table on `/sales/rules/skills`
  (`ProposeSkill` says "chạy thử trên các cặp ví dụ của khách"). Tests in
  `test_skills.py` (listed with versions and replay, approved by another
  person, another tenant lists none).
- **A wrong pair is withdrawn.** `WorkedPairs` (`salesorder_pairs.py`):
  `GET /sales/customers/{code}/salesorder-pairs` (newest 50: PO number,
  day, row count, who added it, whether a replay reads it; never a cell)
  and `DELETE /sales/salesorder-pairs/{pair_id}`, both `sales.rules.propose`
  + `sales.price.read` as the examples' routes; the DELETE and its audit
  row (`sales.salesorder_pair.withdrawn`, ids and counts) in one
  transaction; another workspace's or tenant's pair is not found. Web: "Cặp
  ví dụ của khách" in the customer's SalesOrder drawer, a confirmation
  naming the PO (`_components/salesorder-pairs.tsx`).
- **Retention.** `OrderRules.learning.salesorder_pairs_kept_days` (365 by
  default, 30-1095; placed with the learning settings, words in
  `rule-labels.ts`); the worker's `sales_salesorder_pairs_retention` lane
  (`WorkedPairRetention`, hourly, every workspace in its own scope,
  registered with or without a model) drops older pairs and audits as
  itself with the count. Migration `985e4fa0cd4f` (parent `b01dba5d0433`)
  grants `dw_app` DELETE on `sales.salesorder_pairs`; UPDATE stays revoked.
- A replay stored beside a waiting version before a pair left keeps the
  counts it was stored with (a version is replayed once); a version proposed
  after is replayed on the pairs left.
