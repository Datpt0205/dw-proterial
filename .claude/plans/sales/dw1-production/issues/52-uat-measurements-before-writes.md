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
