# 72 — Gateway: create an SO, a new line filled as the screen fills it

Status: in-progress — the window's bindings, a new document and a create's statements built offline 2026-11-27; the create's pipeline path not built; `so.create@1` stays `pending`; ready-for-human (ticket 50's live procedures and lookups, the UAT create, script 08 rerun)
Blocked by: 70
Category: enhancement (tickets 51, 59, 63)

## Why

A typed SO create is traced twice (11-20, and `02-trace-3.csv` 11-25
16:53:33). What blocked it was how a new line's `QuantityBox` is set. It is in
the layouts: the grid layout 8213 binds the item lookup (`vB20Item_Lookup`)
into the line when `ItemCode` is chosen (`bindingMembers`: `QuantityBox`,
`Length`, `CoilBox`, `BasePriceCode`, `Specification`, `DesignNumber`,
`CartonSize`…), and the data layout 8212 sets `QuantityBox = 1` when
`CartonSize='-'` (`Eval_Detail_QuantityBox_SetValue`). The runner reads 8212
only.

## What

- `dw_bravo` reads the grid layout's `bindingMembers` for the line's lookup
  columns and applies them to a new line from the item read through the
  gateway; then 8212's rules run as today.
- `so.create`: header INSERT and line INSERTs with the traced column sets,
  `SCOPE_IDENTITY` read-back, then the process step (ticket 74).
- Kind leaves `pending`; switch off until UAT proof.

## Acceptance

- Replay of 16:53:33 renders the client's INSERTs.
- A unit test: an item whose `CartonSize` is `-` gets `QuantityBox` 1; another
  gets the item's own value; removing the binding read turns it red.

## Comments

**2026-11-27, built offline (unattended, decided by recommendation).**
Plan and its adversarial critique from workflow `wf_c5489c26-ef9`; each of
the critique's points checked against the code, the layouts, the survey
outputs and `02-trace-3.csv`, and taken where it held.

Built, each in its own commit:
- `c7644b2c` Layout selection. Bravo holds a screen's DataSource at
  `IsTemplate` 3 and its window at 0 (03a lines 4522-4523, 06 lines
  123-124; every `EDIT_*` screen). The adapter filtered `IsTemplate = 0`,
  so on the real Bravo it read 8213, which has no `<Tables>`: every live
  `EDIT_BizDocSO` write (70, 71, 73 too) was refused, and the fingerprint
  watched the form only. Now the DataSource is the 3 row and the screen's
  one layout component digests both. The integration fixture held the
  DataSource at 0, a shape Bravo does not have (failure-modes #0).
- `36d14ac3` Binding direction. `bindingMembers` read
  `<source>target</source>` (the lookup's column, then the row's: the
  client's item lookup SELECTs `Name`, its INSERT writes `Description`).
  The runner read them backwards, untested because every 8212 binding but
  DmCt's is same-name. `Condition_N` members (8212's `Ma_Gd_Ct` into
  `TransCode` while empty; both traced creates write `TransCode`) were
  flattened to an empty target; they are conditional members now, and any
  other shape refuses when its rule runs, not when the layout is read.
- `1c40d8c6` The window (`read_window`, `Layout.window`): every binding
  lookup box, header or grid, with `FilterKey`, `SelectKey` and the
  editor's `Expr`. The runner runs one after its column's `ColumnChanged`
  rules, on any change, a rule's included: at 16:50:01 the client ran
  `usp_SalesSpecialNote_GetVale` (an ItemCode rule), then the item lookup's
  SELECT, then the unit lookup's, right after 8212 set `Unit` from
  `Unit_Item`. The read carries FilterKey and SelectKey, as the client's
  does (16:50:38, the customer's `IsGroup=0 AND ISNULL(Property,'')=1 AND
  ISNULL(Status,0)=0`). A '-' carton gives `QuantityBox` 1 through 8212's
  own rule; another carton keeps the item's. 8212 hangs that rule on both
  columns, so member order does not change it. Refused: a column set while
  its editor is closed, an emptied lookup, a lookup a user's own window
  binds otherwise (`merge_windows`). At load nothing binds, and what would
  stays UNKNOWN.
- `6e2cf07c` The live adapter reads the window and every
  `B00LayoutDataEdit` copy of it. Proterial's 8213 copy binds the item,
  customer, indirect customer and customer description lookups otherwise,
  so those refuse when they bind (which copy a user opens, by
  `UserId`/`RoleId`, is not measured) and the rest bind. A window not
  readable, or not exactly one, leaves every plan provisional. The copies
  are fingerprinted.
- `5815266a` `RuleRunner.new_document`: the header the `New` window starts
  with, the layout's `DefaultValues`, an `Id` below zero never written,
  then `RowAdded`.
- `208c6622` A create's statements: the header INSERT first, its lines and
  the process step carrying `ReadBack(B30BizDoc, BizDocId)` (16:53:33:
  `N''` on the header, the filled key on the line and the step). The writer
  keeps that INSERT's `SCOPE_IDENTITY()` SELECT in the same batch, steps
  past trigger counts (`nextset`) and resolves each ReadBack; no row or an
  empty key is `WriteRejectedError`, settled as refused, not in doubt. The
  SO screen carries the line table's relation column. The two creates'
  header seeds (`ParentId` -1, `IsActive` 1; no rule of 8212 sets them, and
  PR's create has `IsActive` NULL, so they are per screen) were declared
  here too, read by nothing; dropped in review (below), they go in with the
  create's pipeline path.
  `so.create@1`'s pending reason is rewritten; the schema is unchanged
  (regenerated: line endings only).

Measured: the dw_bravo and gateway unit suites are green with the local
trace and layouts, but for the two known 11-20-count failures
(`test_bravo_so_layout`, `test_bravo_rq_layout`); 22 new unit cases (3
binding, 13 window and new document, 6 create). On a throwaway SQL Server
2017, `test_gateway_sqlserver.py` passes 25 of 26 (the failing one is the
known `IsCancel` fixture gap), 4 of them new: the DataSource by
`IsTemplate`, the window and a user's copy, both fingerprinted, a copy the
read login cannot read, and a create read back under a trigger that fills
the key and logs an identity row without `SET NOCOUNT ON`. 25 mutations,
each red and restored: the `IsTemplate` filter, the form in the digest,
the copies merged, fingerprinted, the window attached; the binding
direction, the condition, the unread refusal; the window lookup call,
SelectKey, the closed editor, the merge, binding at load, the unread
lookup, the several-columns rule path; RowAdded and DefaultValues of a new
document; the relation key, the step's ReadBack, the empty read-back,
WriteRejectedError's mapping, the kept SELECT; and on SQL Server: no
`nextset` (the first result is the trigger's count), the SELECT stripped,
`@@IDENTITY` for `SCOPE_IDENTITY()` (it names the change log's row).

Not taken from the plan, after checking: keying the context's event by new
or stored document (a split is `update` since ticket 73, so `Edit`, and a
create `New`); a second "pending refuses" test (`test_gateway_checks` has
it).

Left, and why:
- The create's pipeline path, and the header seeds with it (`ParentId` -1,
  `IsActive` 1 on the SO screen's new header, measured above): typed edits in a fixed header order
  (`CustomerCode` first, so its binding does not overwrite the approved
  currency or delivery terms), lines `ItemCode` before quantity; a check
  that each typed value survives to the INSERT; the duplicate guard by
  `customer_po` under a pace key on customer and PO; the planned `DocNo` in
  the ledger's claim; reconcile by the read-back `Id`; `_batch`'s year from
  the contract's `doc_date`. Not started: every live create refuses before
  it anyway (ticket 50), and it is the next slice.
- Contract fields no traced create typed, to be refused as unmeasured in
  that path: `indirect_customer_code`, `end_user` (NULL or absent in both
  header INSERTs), a line with `customer_description` but no `item_code`
  (that editor is a `zLookupSource` box, open only while `ItemCode` is
  empty). A line with both: the screen closes `CustomerDescription` once
  `ItemCode` is set; refuse it, or make the contract either/or
  (`so.create@2`).
- A replay of 16:53:33 and 11-20 10:26:40 that is not circular: the
  members the runner reads per lookup against the client's own lookup
  SELECTs. It would fail today on the customer: the UAT client reads no
  `DeliveryTerm/Mode/Place`, the local 8213 binds all three. The local
  layouts are production's (03b `USE B8_Hitachi_Cable`), the trace is UAT's;
  the live gateway reads the layout of the Bravo it writes, so this is a
  replay gap, not a runner one.
- Live lookups: `references.find` receives finished SQL text (`substitute`
  runs before the call). Ticket 50's live port must bind the substituted
  values as parameters, or refuse a filter it cannot parse; decide it there
  before the port is built.
- Row permission (`ufn_sys_GetTablePermissionExprAll` on the SO view,
  which the client calls) is not checked: ticket 75.

Owed by Đạt / Proterial:
- Script 08 rerun (outside git) with `SELECT` on `B00LayoutDataEdit` for the
  read login (added locally). For a create, later: `INSERT` on `B30BizDoc`
  and `SELECT (Id, BizDocId, CreatedAt, ModifiedAt, timestamp)` on it for
  the write login (not added while the create is pending).
- UAT (ticket 52): DW's create for a DWTEST PO beside a PIC's own create of
  the same PO, traced; one item whose `CartonSize` is '-' (no traced create
  has one, so the unit test is the rule's only proof); a PIC with a
  `B00LayoutDataEdit` copy opening the SO screen.
- Is `B30BizDoc.LeadTime` nullable on UAT (`sys.columns`)? The one header
  column the listing rule does not explain in the traced creates.
- Proterial IT: `DocNo` has no unique index. Does Bravo guard two creates
  numbered in the same instant (a person and DW)?

**2026-11-27, review findings checked and fixed (unattended).** Eight
findings from the ticket's code review; each verified against the code
before it was taken.

Fixed, each with a test that goes red without the fix (mutated, red,
restored):
- The fingerprint lost whole when the read login cannot SELECT
  `B00LayoutDataEdit` (Proterial's cannot, until script 08 is rerun):
  `_layout_components` re-read the copies outside any handler, so the raw
  driver error left `fingerprint()` and `/v1/fingerprint` answered 500.
  Now the copies not read are a marker in the layout's digest and the
  window is named in `unknown` (`_window` already reads it as not
  readable), so the watch keeps every other component and pauses the
  screen's writes on the change. `test_a_window_the_read_login_cannot_read_
  leaves_every_plan_provisional` now takes the fingerprint under the DENY
  too (SQL Server 2017: the driver raises `ProgrammingError`). Mutations:
  the handler removed (red: `ProgrammingError`), the marker removed (red:
  the digest did not change, so the watch would never have seen it).
- Declared and read by nothing (failure-modes #1): `ScreenTables.new_header`
  dropped (the seeds are recorded above, for the create's path), and
  `Window.grid_columns` dropped (`merge_windows` also kept only the base's,
  ignoring a user's copy); the test that read it now checks the lookups only.
- The gateway's trace replay ran without the window the live adapter
  always attaches: `_so_layout()` now hands every replay 8212 with 8213
  merged with Proterial's `B00LayoutDataEdit` copy, as
  `SqlServerBravo.layout` does. Date, quantity and cancel still replay to
  the client's statements. Both traced splits are still held back, now for
  the reason live gives first: the item lookup that `Eval_Detail_Divi_
  GetData`'s `ItemCode` copy binds is bound otherwise by the user's copy;
  the item row not in the trace and the `GroupDivi` comparison wait behind
  it. Mutation: the window not attached (red: the reason is `GroupDivi`'s).
- Untested refusals, each now tested: the writer's read-back with no SELECT,
  no row or two rows (a fake cursor: rejected, rolled back, the line never
  sent; and the one-row path after a trigger's count keys the line); a
  stored row's UPDATE in a new document's save; an emptied window lookup; a
  lookup row not found; a conditional member whose condition the members
  before it change; two lookups binding each other round and round (the
  window lookup's depth guard; without it, Python's `RecursionError`); a
  binding box that is not a `BravoLookupBox` with a `LookupKey` and a member
  binding to no column (both refuse when they bind, never reading a lookup
  with no key); the short form `<bindingMembers>A,B</bindingMembers>` (no
  local layout uses it; it is the `Parameters` short form's shape); two
  lookups on one column and a grid item naming no table or columns (the
  window refused whole). 13 mutations, each red.

Rejected: none. Finding 4 repeats finding 2 (`new_header`); taken once.

Measured: dw_bravo and gateway unit suites with the local trace and layouts,
349 passed, 2 failed (the two known 11-20-count failures,
`test_bravo_so_layout`, `test_bravo_rq_layout`). On a throwaway SQL Server
2017, `test_gateway_sqlserver.py` 25 of 26 (the known `IsCancel` fixture
gap). ruff and mypy clean on the changed files.
