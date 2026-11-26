# 52 — Measure on UAT what the writes depend on

Status: ready-for-human (Đạt at Proterial: the 02a/02b trace, then scripts 05, 03c, 06 and 07, and the IT questions in item 8)
Blocked by: none
Category: research

## Why

Tickets 51 and 53 rest on three assumptions. They are cheap to measure now
and expensive to discover after the code is written (failure-modes #4:
measure, do not trust).

## Shape

With `docs/proterial/sql/02a`/`02b` recording, on Bravo UAT:

1. Import a DWTEST SO file built from template 72, with a PO price that
   differs from the quotation's.
   - Does the SO keep DW's price, or does Bravo's quotation lookup overwrite it?
   - Does Import show the same blocks and warnings as typing?
2. Cancel one line for real (tick, save), and once more through "Cancelled
   order information".
3. Approve ("Duyệt") an SO, and note which columns change.
4. Save a quotation ("Báo giá, chào hàng").
5. Later, for DW2: save a PR, save a PO from it, change the PO's date.

**Added 2026-11-21 (ADR 0027 rests on these; `docs/proterial/sql/06` and `07`).**

6. **Script 06: users and rights, as counts only.**
   - Are employee codes filled, and unique, for active Bravo users?
   - Are employee e-mails filled?
   - How many users are mapped to Windows accounts?
   - Which permission rows exist for the SO, YCBG, quotation, PR and PO
     commands?
7. **Script 07, on UAT, inside a rolled-back transaction.** Does an SO line
   UPDATE, with its triggers, succeed under a login holding only column
   grants? Does `SET CONTEXT_INFO` work under it? Does a SNAPSHOT read work
   under the read login?
8. **Questions for IT, not scripts.**
   - Can the DW host reach the AD over LDAPS, or through their federation
     service (AD FS or Entra ID)?
   - Can DW have a read-only AD account?
   - Is the AD's `employeeID` filled?

**Added 2026-11-25 (runbook handed to Đạt for his remote session).**

9. Script 03b again on the production database: the Import templates
   (`B00ImportSetting`) were read on UAT only (11-20).
10. A person's fact, not a script: which Import template Sales picks in
    Bravo's Import dialog for an SO (template 72 by the 11-20 survey).
11. Then: DW on the AI server's Ubuntu VM with its database, and the live
    evals run with `--attest` there (ticket 01; nothing is attested yet).
    Owed by Đạt: whether the VM has Docker and the repository, and the
    address it reaches Strata at.

**2026-11-25, Đạt:** the full UAT trace (items 1-5) is declined as too
costly. Writes it would prove stay refused by the gateway (an existing SO's
save, a cancel, the command right, Import's price). Offered instead: one
5-minute trace of an existing SO's date change (unlocks ticket 53's date and
quantity). The 11-25 production runs of 05, 03c, 06 and 03b came back as
empty files (0 bytes in `Downloads/DB-Bravo`): to be saved again from the
remote machine.

**2026-11-25, the production runs read** (`Downloads/DB-Bravo-2.rar`, local
only): 05, 06, 03b and 03c all complete.
- 05: Bravo has **no approval workflow for SO or quotations** (only PR's
  statuses are configured), so "Duyệt an SO" (item 3) is moot. Quotation
  kinds QN 62, QM 9, QS 2, none 29; 1,099 POs sit under 2 SOs, a few under
  up to 93 (2.3% of POs: the read-back's "PO under several SOs" refusal
  matters).
- 06: 197 active users, 173 with an employee code (24 without), 6 codes
  shared by up to 3 active users, valid e-mail on 18 only, Windows mapping
  last touched 2019 and pointing at one active user: the employee code is
  the only workable anchor (ADR 0027 holds); IT to fill 24 codes. SO
  permission rows exist for Edit, New, NewAsCopy, Save. Section 6 failed on
  a bug in the script (an aggregate of an aggregate), not needed now.
- 03b on production: the 5 active SO Import templates (3, 16, 17, 18, 72)
  and every SO/YCBG layout are identical to the 11-20 run; one layout
  changed (the item catalogue's).
- Still unmeasured, so the gateway keeps refusing writes: the event word of
  an existing SO's save, which permission rows a save applies, whether the
  change-log triggers write to `<db>_Log` (script 07, IT), and the kind of
  the 6 validators with no `ClassName` (ticket 59).

## Acceptance

- The trace CSV and the document numbers are in `Downloads/DB-Bravo`.
- Each question above has its answer recorded in this ticket.

## Comments

**2026-11-21, from building the gateway (ticket 63).** Added to what UAT must answer:
- Script 07: do Bravo's `DML_*_ChangeLog` triggers write to `<db>_Log`? Measured on a
  throwaway SQL Server: a trigger writing another database fails (error 916) under a
  login with column grants only, so the write login would need a user there.
- A save of an **existing** SO in the trace (open it, change a date, save): the trace
  holds only saves after `EDIT_BizDocSO|New`, so the context's event word for an
  existing document is unknown and the gateway refuses it.
- Which `ufn_B00Permission_Getdata` rows the client applies when a user opens and saves
  the SO screen (its `@_PermissionType`): until known the gateway's command right
  answers "unknown" and refuses.
- A real cancel (item 2 above): the trace's one cancel save clears `IsCancel`; nothing
  shows what a cancel writes.
- `B00UserList.Expire` (tinyint): the gateway reads a set value as an inactive user.

**2026-11-26, `02-trace-3.csv` read** (local only, `Downloads/DB-Bravo-5-extract/DB-Bravo`;
the file holds every `dw_trace_uat*.xel` on the host, so it repeats 11-20 and
11-25; new rows: 11-25 16:38–17:32 and 11-26 08:00–15:41).
- **F, a cancel: traced** (test SO `SO2611-000002`, 17:31:50, both lines in
  one save). The client sends the whole cancel in one UPDATE per line:
  `IsCancel='Cancel'`, `CancelDate` (today), `CancelQuantity` (the old
  quantity), `CancelPrice` (the old unit price), `CancelAmount`,
  `CancelRemark` (typed), `CancelPRS=DEFAULT`, and `Quantity`, `Quantity9`,
  `UnitCost`, the four amounts to 0, `OriginalUnitCost=DEFAULT`; the first line
  also `Remark`, `BoxQuantity`, `QuantityGroup`, `Divide` to 0. The 0s are
  sent by the client (the screen's own rules), not by a trigger. Header:
  totals and `TotalQuantity` to 0.
- **E, a split: traced once, not cleanly** (17:28:58). One save did three
  things: deleted an empty line added at 16:56, set a quantity on a line that
  had 0 saved, and split it 135 + 115. Original line UPDATE: `Quantity`,
  `Quantity9`, amounts, `BoxQuantity` (= Quantity9 / (QuantityBox × Length),
  the layout's `Eval_BoxQuantity_SetValue`), `QuantityBox` 0→1,
  `QuantityGroup` = the total (250), `GroupDivi`, `Divide` = 1. New line
  INSERT: the copied columns plus `OriginalQuantity`, `GroupDivi`, `POLine` 0,
  `QuantityBox` 0, no `QuantityGroup`/`Divide`/`BoxQuantity`. Header: totals,
  `TotalQuantity`, `LMEFixed`. Item `01-01-0001` (a roller, unit Pc), not
  the bobbin/drum item asked for, so the shape is known and a clean split of a
  saved quantity on a cable item is still the `uat_proof` the switch needs.
- **A new SO by typing: traced again** (16:53:33, header and one line), and
  **a new line's `QuantityBox` is in the layouts after all**: the grid layout
  8213 binds the item lookup (`vB20Item_Lookup`) into the line on `ItemCode`
  (`QuantityBox`, `Length`, `CoilBox`, `BasePriceCode`, `Specification`,
  `DesignNumber`, `CartonSize`…), and the data layout 8212 sets
  `QuantityBox = 1` when `CartonSize='-'` (`Eval_Detail_QuantityBox_SetValue`).
  The runner reads neither the grid's `bindingMembers` nor applies it to a new
  line yet.
- **G, a unit price change: not traced.** `so.line.set_price` stays pending.
- **Every save ends in `exec usp_B30BizDocProcess_CreateProcess @_BizDocId,
  @_BizProcessGroupUnique=NULL, @_BranchCode, @_DocCode`** on the same
  session right after the statements; the gateway does not call it (and its
  write login holds no EXECUTE). Before it, `usp_B20BizProcessGroup` runs on
  another session (a read for the process group); after, the list refreshes
  through `usp_B30BizDocDetail_Transferred`.
- **The command right is not in any save.** The client calls
  `usp_sys_GetControlPermission(@UserId, '<screen>')` when a screen opens and
  `ufn_sys_GetTablePermissionExprAll` per table (row filters), and receives
  the rest at login (`usp_sys_Login`, a compressed output); no
  `ufn_B00Permission_Getdata` call appears. Bravo's permission editor shows
  the storage: `B00Permission` (`UserId` or `RoleId`, `NoOpen`, `NoDisplay`,
  `NoInherit`, `IsActive`) joined to `B00PermissionData`
  (`ParentCommandKey`, `SubCommandKey` New/Edit/Print/Export/Delete…). How
  the client combines a user's row, its roles' rows and `NoInherit` is not
  visible in SQL.
- **The change log is in `<db>_Log`**: Bravo's History screen reads
  `B8_Hitachi_Cable_UAT_Log.dbo.B30BizDoc$0` by `__$LastWriteAt`; whether a
  trigger writes it (so the write login needs a user there) is still script 07.
  The client itself writes `<db>_Log.dbo.B00CommandLog` only at login/logout.
- **DW2 material, 11-26** (many Purchasing users on UAT): PRs created by New
  (header + 1–3 `B30BizDocDetail` lines), a PR edited, a PO created from a PR
  (`B30BizDocDetailPO`), PRs approved through `ApprovalVouchersPR`
  (`usp_B30AccDoc_ApprovalVouchers` with the documents as XML; `DocStatus`
  10→13; refusals "Người dùng không có quyền duyệt chứng từ số …"). Not
  traced: a PO's date change.
