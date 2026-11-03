---
status: Accepted
date: 2026-11-02
accepted: 2026-11-02 (agent, Đạt: "làm hết đi", the master-data import "cho upload file, đừng input từng cái"; Đạt to confirm on review)
refines: docs/adr/0014-a-lift-moves-the-decisions-each-context-keeps-its-queue.md (decision 2, for DW2's master data)
---

# DW2's master data is a rule version; the workbooks wait in DW2's own queue

## Context

DW2 checked requests against fictional lists (`adapters/mock/master_data.py`),
and a deployed DW2 answered 503 until real ones could be loaded. Đạt asked for
loading by file, not row by row. Sales loads its lists through its own engine
(`dw_sales.application.catalog_imports`): a queue table, a snapshot table per
list, a run-less approval and its own decision guard and settlement.

ADR 0013 decision 3 lifts an engine to the platform once a second context
needs it; ADR 0014 refines that: the decision moves, the queue stays with the
context. The decision a master-data upload needs (one version waiting at a
time, decided by someone who did not propose it, the head's own applied at
once, a version in force superseded, every step audited) is exactly the
platform's rule-version engine's, which DW2's rules already use.

## Decision

1. **The company's lists are one document, key `purchasing_master_data`**
   (`domain.master_lists.PurchasingMasterData`: items, suppliers, quotations,
   prices paid, budgets; every code once, every quotation and price naming an
   item and supplier the lists hold). The platform ships it empty
   (`configs/policies/purchasing_master_data@1.0.0.yaml`). It is proposed,
   decided and applied through `PurchasingRulesService.propose`, under the
   `purchasing.rules` approval and its scopes: who configures DW2 loads the
   lists, who approves rule changes decides them. No second approval type,
   guard or settlement is written.
2. **The uploads are DW2's own queue** (`purchasing.master_imports`, ADR 0014
   decision 2): a workbook waits with its bytes, the worker's
   `purchasing_master_import` lane scans it and reads it in the reader sandbox
   (one sheet per list, through the composition root's adapter, ADR 0013
   decision 2's interim), and the rows it read wait to be sent. A newer upload
   forgets an open one; the lane forgets one read 90 days ago.
3. **A list left out of the workbook is kept**; a list in it replaces the one
   in force. Quotations and prices paid whose item or supplier the file
   removed are dropped with them and counted on the preview.
4. **The rule-version store is asked for what a caller reads.** A master-data
   version can hold thousands of rows, and `list_all` read every version of
   every key. It now takes `keys` and `statuses`: the engine reads only the
   key's waiting and in-force versions, and each settings page (Sales', DW2's)
   only its own keys, so no page loads a master-data document it never shows.
5. **Where deployed, every check reads the tenant's lists or the empty ones**
   (`RuleMasterData`); locally the fictional lists stand in until a tenant
   loads its own (`DemoMasterData`). The 503 that waited on this is gone.

## Consequences

- Master data has one decision path with the rules: what a version is, who
  decides it and how it applies cannot drift from them.
- Superseded master-data versions stay in `platform.rule_versions`, as every
  decided version does; their size grows with each load. A retention of
  superseded versions is a later decision, for every key at once.
- A list longer than the reader reads (5 000 rows a sheet) is refused, never
  cut short; the template's guide says to keep only the rows needed (the
  latest price paid per item and supplier).
- The approval names the key and version, never a row; the page shows the
  approver what changes, list by list.
