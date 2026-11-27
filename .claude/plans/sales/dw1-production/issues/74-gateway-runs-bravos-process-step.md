# 74 — Gateway: run Bravo's process step after a write

Status: resolved (2026-11-26) — option A, decided by recommendation (Đạt 11-26: "làm theo khuyến nghị")
Blocked by: none
Category: enhancement (ADR 0027 amendment)

## Why

Every client save in the three traces ends with
`exec dbo.usp_B30BizDocProcess_CreateProcess @_BizDocId, @_BizProcessGroupUnique=NULL, @_BranchCode, @_DocCode`
on the same session, right after the statements. The gateway sends no such
call and its write login holds no EXECUTE, so after a DW write Bravo's
process view of the document lags what a person's save would show.

## Options

- **A (recommended):** the gateway executes that one procedure after the
  write, in the same transaction, under the PIC's context; the grant script
  (08) adds `GRANT EXECUTE ON dbo.usp_B30BizDocProcess_CreateProcess` to the
  write login only; ADR 0027 amended ("nothing created in Bravo's DB" still
  holds; one Bravo procedure is executed). Needs script 07-style proof on UAT
  that it succeeds under the write login.
- **B:** not called; the write's result page tells the person Bravo's process
  view refreshes on the next save in Bravo.

## Acceptance (A)

- Replay renders the call after the statements with the traced arguments.
- On UAT, the document's process rows equal those after a person's save.

## Comments

**2026-11-26, done (option A).** `Batch.steps` carries
`ProcedureStep(usp_B30BizDocProcess_CreateProcess, {_BizDocId, _BizProcessGroupUnique: None,
_BranchCode, _DocCode})` from the stored header and the screen's `doc_code`
("SO"); the SQL Server adapter runs it after the statements in the same
transaction (`bind_step`, which refuses any other procedure). The preview
shows it. The replay compares it with the client's traced call at the save's
second (11-20 and 11-25/26 saves); `DocCode` mutated → red. On SQL Server
2017 (throwaway container): a write ran the step as the PIC (the context
parser read 2413), and a step refused for want of EXECUTE took the write
back (outcome in doubt, the line unchanged); 20/20, and skipping the step
turned two red. Script 08 (local): EXECUTE for the write login, VIEW
DEFINITION for the read login (the watch reads it, `ROUTINES`), and the
cancel's columns (ticket 71). ADR 0027 amendment 2026-11-26.
